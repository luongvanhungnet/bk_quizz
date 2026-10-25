"""Long-lived isolated model processes. Responses use files so model logs cannot corrupt IPC."""
import argparse
import gc
import json
import os
from pathlib import Path
import sys
import time
import traceback
from common import atomic_json, digest, load


class LazyObserver:
    def __init__(self, config, factory):
        self.config, self.factory = config, factory
        self.observer = None
        self.failure = None
        self.initializations = 0
        self.telemetry = {}

    def infer(self, image, text):
        if self.failure:
            raise RuntimeError('VLM initialization already failed; retained diagnostic: ' + self.failure)
        if self.observer is None:
            self.initializations += 1
            try:
                self.observer = self.factory(self.config)
            except Exception as exc:
                self.failure = repr(exc)
                raise
        try:
            return self.observer.infer(image, text)
        finally:
            self.telemetry = getattr(self.observer, 'telemetry', {})


def select_tasks(manifest, mode, visual_only=False):
    tasks = manifest['requests']
    if mode == 'structure':
        return [q for q in tasks if q.get('is_full_page') is True]
    if mode in {'formula', 'table'}:
        return [q for q in tasks if q['kind'] == mode and not q.get('specialist_seed_valid') and not q.get('skip_specialist')]
    return [q for q in tasks if (q['kind'] in {'text', 'code'} and not visual_only) or q.get('ocr_requested') is True]


class Engines:
    def __init__(self, role):
        self.role = role
        self.model = None
        self.config = None
        self.initializations = 0
        self.initialization_error = None

    def vlm(self, packet, out):
        import vlm_worker
        m = load(packet / 'manifest.json')
        if self.config is not None and self.config != m['vlm_config']:
            raise ValueError('VLM config changed inside warm queue; refusing model/cache mismatch')
        self.config = m['vlm_config']
        if self.model is None:
            self.model = LazyObserver(self.config, vlm_worker.Observer)
        result = vlm_worker.run(packet, out, scope='all', model=self.model)
        self.initializations = self.model.initializations
        return {'status': 'ok' if not result['not_run_ids'] and all(o['status'] == 'ok' for o in result['observations']) else 'error',
                'observations': len(result['observations']), 'errors': sum(o['status'] != 'ok' for o in result['observations']),
                'not_run': result['not_run_ids'], 'model_initializations': self.initializations}

    def paddle(self, packet, out, mode, visual_only=False):
        import paddle_worker as p
        start = time.perf_counter()
        manifest = load(packet / 'manifest.json')
        tasks = select_tasks(manifest, mode, visual_only)
        versions = {name: p.package_version(name) for name in ['paddleocr', 'paddlex', 'paddlepaddle', 'paddlepaddle-gpu']}
        if any(versions[n] != v for n, v in {'paddleocr': '3.7.0', 'paddlex': '3.7.2', 'paddlepaddle-gpu': '3.2.2'}.items()):
            raise RuntimeError('Paddle pinned versions mismatch: ' + repr(versions))
        records = []
        initialized = 0.0
        for task in tasks:
            cached = out / 'records' / f'{p.safe_id(task["id"])}_{mode}.json'
            if self.model is None and not cached.exists():
                if self.initialization_error:
                    raise RuntimeError(self.initialization_error)
                t = time.perf_counter()
                self.initializations += 1
                try:
                    self.model = p.create_pipeline(mode, 'gpu:0', 'vi', 'PP-FormulaNet-S', 'PP-OCRv3')
                except Exception:
                    self.initialization_error = traceback.format_exc()
                    raise
                initialized += time.perf_counter() - t
            records.append(p.infer_task(task, packet, out, mode=mode, device='gpu:0', lang='vi',
                                        pipeline=self.model, versions=versions))
        result = {'status': 'ok' if all(r['status'] == 'ok' for r in records) else 'error', 'mode': mode,
                  'request_count': len(tasks), 'record_count': len(records), 'records': records, 'versions': versions,
                  'actual_model_names': {k: v for k, v in getattr(self.model, '_params', {}).items()
                                         if k.endswith('_model_name') and isinstance(v, str)},
                  'initialization_seconds': initialized, 'total_elapsed_seconds': time.perf_counter() - start,
                  'device': 'gpu:0', 'lang': 'vi', 'ocr_version': 'PP-OCRv3', 'formula_model': 'PP-FormulaNet-S',
                  'model_initializations': self.initializations, 'semantic_verified': False}
        p.write_new(out / f'results_{time.time_ns()}.json', result)
        return {k: v for k, v in result.items() if k != 'records'}

    def docling(self, packet, out):
        import adapters
        import parser_worker
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        if self.model is None:
            options = PdfPipelineOptions(do_ocr=False, do_table_structure=True, do_formula_enrichment=False, do_code_enrichment=False)
            self.model = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)})
            self.initializations += 1

        def convert(input_path, out_json, **kwargs):
            if Path(out_json).exists():
                return load(out_json)
            started = time.perf_counter()
            result = self.model.convert(str(input_path))
            payload = {'status': 'ok', 'metadata': {'source_file': str(Path(input_path).resolve()),
                       'source_sha256': digest(input_path), 'version': adapters.package_version('docling'),
                       'do_ocr': False, 'backend_family': 'docling_native_layout'},
                       'document': result.document.export_to_dict(), 'elapsed_seconds': time.perf_counter() - started}
            adapters._write_new(out_json, payload)
            return payload

        # Keep the frozen import/mapping path; only the converter lifecycle changes.
        parser_worker.run_docling = convert
        result = parser_worker.run(packet, out, 'docling')
        return {'status': result['status'], 'candidates': len(result['parser_candidates']), 'model_initializations': self.initializations}

    def handle(self, command):
        packet, out = Path(command['packet']), Path(command['out'])
        out.mkdir(parents=True, exist_ok=True)
        manifest = load(packet / 'manifest.json')
        for name, wanted in manifest['code_sha256'].items():
            from common import safe
            if digest(safe(packet, name)) != wanted:
                raise ValueError('Changed packet engine: ' + name)
        if self.role == 'vlm':
            return self.vlm(packet, out)
        if self.role == 'docling':
            return self.docling(packet, out)
        return self.paddle(packet, out, self.role, command.get('visual_only', False))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--engine', type=Path, required=True)
    p.add_argument('--role', choices=['ocr', 'structure', 'formula', 'table', 'docling', 'vlm'], required=True)
    args = p.parse_args()
    sys.path.insert(0, str(args.engine.resolve()))
    engine = Engines(args.role)
    for line in sys.stdin:
        command = json.loads(line)
        if command.get('action') == 'close':
            break
        started = time.perf_counter()
        try:
            result = engine.handle(command)
            response = {'completed': True, 'result': result}
        except Exception as exc:
            response = {'completed': False, 'error': repr(exc), 'traceback': traceback.format_exc()}
        response.update(seconds=time.perf_counter() - started, role=args.role, pid=os.getpid())
        atomic_json(command['response'], response)
    engine.model = None
    gc.collect()


if __name__ == '__main__':
    main()
