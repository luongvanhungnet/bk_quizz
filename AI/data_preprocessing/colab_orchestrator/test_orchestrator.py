import contextlib
import copy
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parent
ENGINE = ROOT.parent.parent / 'Qwen_cpt_version/region_preprocessing_v5_official'
sys.path.insert(0, str(ENGINE))
sys.path.insert(0, str(ROOT))
from common import atomic_json, checked_extract, checkpoint, digest, load, restore_checkpoint, write_archive
from build_bundles import partition
from warm_worker import Engines, LazyObserver, select_tasks
from orchestrator import Coordinator, Worker


class ArchiveTests(unittest.TestCase):
    def test_partition_covers_148_jobs_in_exactly_14_uploads(self):
        jobs = [{'id': i} for i in range(148)]
        groups = partition(jobs)
        self.assertEqual(len(groups), 14)
        self.assertEqual([j for g in groups for j in g], jobs)
        self.assertTrue(all(len(g) in {10, 11} for g in groups))

    def test_hash_tampering_fails_before_extracting_payload(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); (root / 'a').write_text('good')
            write_archive(root / 'good.zip', {'a': root / 'a'}, {}, 'bundle.json')
            with zipfile.ZipFile(root / 'good.zip') as z, zipfile.ZipFile(root / 'bad.zip', 'w') as bad:
                bad.writestr('bundle.json', z.read('bundle.json')); bad.writestr('a', 'bad')
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                checked_extract(root / 'bad.zip', root / 'dest', 'bundle.json')
            self.assertFalse((root / 'dest/a').exists())

    def test_zip_path_escape_and_duplicate_names_rejected(self):
        for name in ['../x', '/tmp/x', 'C:/Windows/x', 'folder\\x']:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                with zipfile.ZipFile(root / 'bad.zip', 'w') as z:
                    z.writestr('bundle.json', json.dumps({'files': {name: 'x'}})); z.writestr(name, 'x')
                with self.assertRaises(ValueError):
                    checked_extract(root / 'bad.zip', root / 'dest', 'bundle.json')

    def test_checkpoint_is_delta_and_resumes_exactly(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); run = root / 'run'; (run / 'assets').mkdir(parents=True)
            (run / 'assets/image.png').write_bytes(b'image'); atomic_json(run / 'manifest.json', {'revision': 1})
            first = checkpoint(run, root / 'cp')
            atomic_json(run / 'manifest.json', {'revision': 2})
            second = checkpoint(run, root / 'cp')
            self.assertEqual(len(first['archives']), 1); self.assertEqual(len(second['archives']), 2)
            with zipfile.ZipFile(root / 'cp' / second['archives'][-1]['name']) as z:
                self.assertNotIn('assets/image.png', z.namelist())
            restore_checkpoint(root / 'cp', root / 'restored')
            self.assertEqual(load(root / 'restored/manifest.json'), {'revision': 2})
            self.assertEqual(digest(root / 'restored/assets/image.png'), digest(run / 'assets/image.png'))


class WarmTests(unittest.TestCase):
    def test_real_vlm_queue_reuses_model_and_cache_across_packets(self):
        import vlm_worker
        from PIL import Image
        from io_utils import sha
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); created = []; inference = []
            class Toy:
                telemetry = {'possibly_truncated': False}
                def __init__(self, config): created.append(config)
                def infer(self, image, text): inference.append(str(image)); return 'Observed academic content'
            packets = []
            for i in range(2):
                p = root / str(i); p.mkdir(); Image.new('RGB', (64,64), 'white').save(p / 'image.png')
                h = digest(p / 'image.png')
                m = {'code_sha256': {}, 'vlm_config': {'model': 'toy', 'prompt_sha256': sha(vlm_worker.PROMPT)},
                     'requests': [{'id': str(i), 'page': i+1, 'use_vlm': True, 'vlm_image': 'image.png',
                                   'vlm_image_sha256': h, 'crop_sha256': h, 'bbox': [0,0,1000,1000],
                                   'kind': 'diagram', 'source_sha256': 'f'*64, 'context_text': 'page ' + str(i)}]}
                atomic_json(p / 'manifest.json', m); packets.append(p)
            engine = Engines('vlm')
            with patch.object(vlm_worker, 'Observer', Toy), patch.dict('os.environ', {'V5_VLM_CACHE': str(root / 'cache')}), contextlib.redirect_stdout(io.StringIO()):
                for p in packets: engine.vlm(p, root / ('out'+p.name))
                engine.vlm(packets[0], root / 'cached_replay')
            self.assertEqual(len(created), 1); self.assertEqual(len(inference), 2)
            self.assertEqual(engine.initializations, 1)
            replay = load(next((root / 'cached_replay').glob('vlm_results_*.json')))
            self.assertTrue(replay['observations'][0]['cache_hit'])
            self.assertFalse(replay['semantic_verified'])

    def test_paddle_pipeline_stays_resident_across_packets(self):
        import paddle_worker
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); created = []; seen = []
            pipeline = object()
            def create(*args): created.append(args); return pipeline
            def infer(task, *args, **kwargs):
                seen.append(kwargs['pipeline'])
                return {'id': task['id'], 'status': 'ok', 'candidates': []}
            versions = {'paddleocr': '3.7.0', 'paddlex': '3.7.2', 'paddlepaddle': None, 'paddlepaddle-gpu': '3.2.2'}
            e = Engines('ocr')
            with patch.object(paddle_worker, 'package_version', versions.get), patch.object(paddle_worker, 'create_pipeline', create), patch.object(paddle_worker, 'infer_task', infer):
                for i in range(2):
                    p = root / str(i); p.mkdir(); atomic_json(p / 'manifest.json', {'requests': [{'id': str(i), 'kind': 'text'}]})
                    e.paddle(p, root / ('out'+str(i)), 'ocr')
            self.assertEqual(len(created), 1); self.assertEqual(seen, [pipeline, pipeline])

    def test_one_observer_for_multiple_images(self):
        calls = []
        class Toy:
            telemetry = {'ok': True}
            def __init__(self, config): calls.append(config)
            def infer(self, image, text): return 'observed ' + text
        observer = LazyObserver({'model': 'test'}, Toy)
        self.assertEqual(observer.infer('a', 'first'), 'observed first')
        self.assertEqual(observer.infer('b', 'second'), 'observed second')
        self.assertEqual(observer.initializations, 1); self.assertEqual(len(calls), 1)

    def test_initialization_failure_not_retried_for_every_image(self):
        calls = []
        def fail(config): calls.append(config); raise RuntimeError('load failure')
        observer = LazyObserver({}, fail)
        for _ in range(3):
            with self.assertRaises(RuntimeError): observer.infer('a', 'b')
        self.assertEqual(len(calls), 1)

    def test_specialist_seeds_and_misrouted_paragraphs_skipped(self):
        m = {'requests': [{'kind': 'formula', 'id': 'a', 'specialist_seed_valid': True},
                          {'kind': 'formula', 'id': 'b', 'skip_specialist': True},
                          {'kind': 'text', 'id': 'c'}, {'kind': 'formula', 'id': 'd'}]}
        self.assertEqual([q['id'] for q in select_tasks(m, 'formula')], ['d'])

    def test_vlm_config_change_rejected_without_loading_another_model(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); atomic_json(root / 'manifest.json', {'vlm_config': {'model': 'different'}})
            engine = Engines('vlm'); engine.config = {'model': 'first'}
            with self.assertRaisesRegex(ValueError, 'config changed'): engine.vlm(root, root / 'out')
            self.assertEqual(engine.initializations, 0)

    def test_ipc_preserves_full_traceback_and_owned_worker_closes(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            worker = Worker(sys.executable, 'vlm', ENGINE, root / 'logs')
            try:
                response = worker.call(root / 'missing_packet', root / 'out', root / 'ipc')
                self.assertFalse(response['completed'])
                self.assertIn('Traceback', response['traceback'])
                self.assertIn('FileNotFoundError', response['traceback'])
            finally:
                worker.close()
            self.assertIsNotNone(worker.process.poll())

    def test_completed_stage_is_not_executed_again(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); c = Coordinator(root / 'base', root / 'work', {})
            c.state['stages']['job:inference:vlm'] = {'completed': True, 'result': {'status': 'ok'}}
            class NeverCall:
                role = 'vlm'
                def call(self, *args): raise AssertionError('replayed completed stage')
            result = c.execute_stage(NeverCall(), {'job_id': 'job'}, 'inference')
            self.assertTrue(result['completed'])


class EndToEndTests(unittest.TestCase):
    def test_synthetic_pdf_discovery_inference_checkpoint_export(self):
        """Exercise real v5 mapping/validation/packaging; only model inference is fake."""
        import pymupdf
        import corpus
        import vlm_worker
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); (root / 'docs').mkdir()
            pdf = pymupdf.open()
            for _ in range(2):
                page = pdf.new_page(width=600, height=400); page.insert_text((50, 50), 'graph sample academic text')
            pdf.save(root / 'docs/A-graph.pdf'); pdf.close()
            cfg = {'source_root': str(root / 'docs'), 'work_root': str(root / 'original'), 'pages_per_packet': 1,
                   'maximum_packet_bytes': 536870912, 'vlm_target_fraction': .05, 'vlm_maximum_fraction': .08,
                   'upstream_manifest': str(root / 'none'), 'upstream_page_map': str(root / 'none'), 'reuse_runs': []}
            with contextlib.redirect_stdout(io.StringIO()):
                corpus.inventory(cfg, root / 'catalog'); jobs = corpus.plan(cfg, root / 'catalog', root / 'plan')
            c = Coordinator(root / 'base', root / 'work', {'paddle': sys.executable, 'vlm': sys.executable, 'docling': sys.executable})
            c.engine = ENGINE; c.config = {**cfg, 'work_root': str(c.work)}
            c.jobs = [{**j, 'run': str(c.work / 'runs' / j['document_id'])} for j in jobs]
            c.plan = {'jobs_sha256': digest(root / 'plan/jobs.jsonl')}; c.state['plan_sha256'] = 'test'
            c.bundle_manifests = [{'bundle_id': 'upload_01', 'jobs': [j['job_id'] for j in jobs]}]
            class Toy:
                telemetry = {'possibly_truncated': False}
                def infer(self, image, text): return 'Sơ đồ có các thành phần nhìn thấy trong ảnh.'
            class FakeWorker:
                events = []
                def __init__(self, python, role, engine, logs, env=None): self.role = role; self.events.append(('open', role))
                def close(self): self.events.append(('close', self.role))
                def call(self, packet, out, control, visual_only=False):
                    out.mkdir(parents=True, exist_ok=True); m = load(packet / 'manifest.json')
                    if self.role == 'vlm':
                        vlm_worker.run(packet, out, scope='all', model=Toy())
                    elif self.role != 'docling':
                        tasks = select_tasks(m, self.role, visual_only)
                        records = []
                        for q in tasks:
                            kind = 'diagram' if self.role == 'structure' else 'text'
                            record = {'id': q['id'], 'page': q['page'], 'mode': self.role, 'status': 'ok',
                                      'input_file_sha256': q['crop_sha256'], 'candidates': [{'page': q['page'],
                                      'bbox': [100, 100, 800, 800] if kind == 'diagram' else q['bbox'], 'kind': kind,
                                      'text': 'graph sample academic text', 'engine': 'paddle_structure' if self.role == 'structure' else 'paddle_ocr',
                                      'status': 'ok', 'evidence': {'source_sha256': q['source_sha256'], 'region_id': q['id']}}]}
                            records.append(record)
                            atomic_json(out / 'records' / (q['id'].replace(':', '_') + '.json'), record)
                        atomic_json(out / 'results_fake.json', {'mode': self.role, 'records': records})
                    return {'completed': True, 'result': {'status': 'ok'}, 'role': self.role}
            with patch('orchestrator.Worker', FakeWorker), patch.dict('os.environ', {'V5_VLM_CACHE': str(root / 'cache')}), contextlib.redirect_stdout(io.StringIO()):
                summary = c.run(); exports = c.export()
                before = len(FakeWorker.events); c.run()
            self.assertTrue(summary['all_jobs_executed']); self.assertEqual(summary['completed_jobs'], 2)
            self.assertEqual(before, len(FakeWorker.events))
            self.assertLess(FakeWorker.events.index(('close', 'structure')), FakeWorker.events.index(('open', 'vlm')))
            returned = checked_extract(exports[0]['path'], root / 'return', 'return.json')
            self.assertEqual(len(returned['phase_results']), 4)
            final = root / 'return/runs' / jobs[0]['document_id']
            self.assertTrue((final / 'records.jsonl').exists())
            self.assertFalse((final / 'human_reviews.sqlite3').exists())
            self.assertFalse(any(r.get('semantic_verified') for r in __import__('common').rows(final / 'records.jsonl')))
            # Import to the original local plan and verify a second import cannot overwrite reviews.
            import import_returns
            atomic_json(root / 'bundle_index.json', {'plan_sha256': 'test'})
            with contextlib.redirect_stdout(io.StringIO()):
                checked = import_returns.import_returns(root / 'plan', root / 'bundle_index.json', [exports[0]['path']], check_only=True)
                imported = import_returns.import_returns(root / 'plan', root / 'bundle_index.json', [exports[0]['path']])
            self.assertEqual(checked['mutated_runs'], 0); self.assertEqual(imported['new_local_runs'], 1)
            local_run = Path(jobs[0]['run'])
            human = local_run / 'human_reviews.sqlite3'; human.write_bytes(b'existing-human-audit-must-not-change')
            original = human.read_bytes()
            with contextlib.redirect_stdout(io.StringIO()):
                again = import_returns.import_returns(root / 'plan', root / 'bundle_index.json', [exports[0]['path']])
            self.assertEqual(again['job_phases_merged'], 0)
            self.assertEqual(human.read_bytes(), original)


class NotebookTests(unittest.TestCase):
    def test_drive_upload_and_install_are_separate_cells(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('orchestrator_notebook_builder', ROOT / 'build_notebook.py')
        builder = importlib.util.module_from_spec(spec); spec.loader.exec_module(builder)
        nb = load(builder.build())
        code = [''.join(c['source']) for c in nb['cells'] if c['cell_type'] == 'code']
        for source in code: compile(source, 'test_notebook', 'exec')
        drive = next(c for c in code if 'drive.mount(' in c)
        upload = next(c for c in code if 'files.upload(' in c)
        setup = next(c for c in code if 'ENVS=setup(BASE)' in c)
        self.assertNotIn('files.upload(', drive); self.assertNotIn('drive.mount(', upload)
        self.assertNotIn('files.upload(', setup); self.assertIn('len(INPUTS)==14', upload)
        self.assertEqual(sum('ENVS=setup(BASE)' in c for c in code), 1)


if __name__ == '__main__':
    unittest.main()
