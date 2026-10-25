import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest

ROOT = Path(__file__).resolve().parent
ENGINE = ROOT.parent.parent / 'Qwen_cpt_version/region_preprocessing_v5_official'
sys.path.insert(0, str(ENGINE)); sys.path.insert(0, str(ROOT))
from jsonl_adapter import JSONLDecodeError, install, loads_jsonl, read_jsonl
from common import atomic_json, digest, rows, write_compact_archive


class JSONLTests(unittest.TestCase):
    def test_unicode_separators_are_content_not_record_boundaries(self):
        expected = [{'text': 'Tiếng Việt \u0085 A\u2028B\u2029C; x ≤ 2; ∑, ×, →; (a|b)'}, {'id': 2}]
        data = ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in expected)
        with self.assertRaises(json.JSONDecodeError):
            [json.loads(line) for line in data.splitlines() if line.strip()]
        self.assertEqual(loads_jsonl(data), expected)
        self.assertEqual(loads_jsonl(b'\xef\xbb\xbf' + data.encode()), expected)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'records.jsonl'; path.write_bytes(data.encode())
            before = digest(path)
            self.assertEqual(read_jsonl(path), expected)
            self.assertEqual(rows(path), expected)
            self.assertEqual(digest(path), before)

    def test_crlf_blank_lines_bom_and_final_line_without_newline(self):
        data = '\ufeff{"x":"A\\nB"}\r\n\r\n{"y":"C\u2028D"}'
        self.assertEqual(loads_jsonl(data), [{'x': 'A\nB'}, {'y': 'C\u2028D'}])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'rows.jsonl'; path.write_bytes(data.encode())
            self.assertEqual(read_jsonl(path), loads_jsonl(data))

    def test_truncation_is_rejected_with_path_and_physical_line(self):
        data = '{"text":"A\u2028B"}\n\n{"text":"truncated'
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'records.jsonl'; path.write_bytes(data.encode())
            before = path.read_bytes()
            for reader in [read_jsonl, rows]:
                with self.assertRaises(JSONLDecodeError) as caught:
                    reader(path)
                self.assertEqual(caught.exception.physical_line, 3)
                self.assertIn(str(path), str(caught.exception))
                self.assertIn('Unterminated string', str(caught.exception))
            self.assertEqual(path.read_bytes(), before)
        with self.assertRaises(JSONLDecodeError): loads_jsonl(data, 'archive.zip!records.jsonl')

    def test_adjacent_json_without_physical_newline_is_rejected(self):
        with self.assertRaises(JSONLDecodeError): loads_jsonl('{"id":1}{"id":2}')

    def test_install_updates_preimported_core_aliases_and_is_idempotent(self):
        import io_utils, corpus, package_cloud, workflow
        install(); install()
        for module in [io_utils, corpus, package_cloud, workflow]:
            self.assertIs(module.jsonl, read_jsonl)
        self.assertEqual(json.loads('{"text":"x\u2028y"}'), {'text': 'x\u2028y'})

    def test_complete_result_with_unicode_passes_hash_and_page_validation(self):
        from test_units import fixture, minimal_result
        from unit_store import inspect_result
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); index, _ = fixture(root, (1,))
            entry = index['bundles'][0]
            original = minimal_result(root, entry, index['plan_sha256'])
            import zipfile
            files = {}; folder = root/'expanded'; folder.mkdir()
            with zipfile.ZipFile(original) as z:
                metadata = json.loads(z.read('return.json'))
                for number, (name, sha) in enumerate(metadata['logical_files'].items()):
                    data = z.read('objects/' + sha)
                    if name.endswith('records.jsonl'):
                        records = loads_jsonl(data)
                        records[0]['native_text'] = 'Nguồn \u2028 x ≤ 3\u0085 và \u2029 y → z'
                        data = ''.join(json.dumps(r, ensure_ascii=False)+'\n' for r in records).encode()
                    path = folder/str(number); path.write_bytes(data); files[name] = path
            metadata.pop('files'); metadata.pop('logical_files')
            patched = root/'unicode_result.zip'
            write_compact_archive(patched, files, metadata)
            before = digest(patched)
            self.assertTrue(inspect_result(patched, entry, index['plan_sha256'])['processing_complete'])
            self.assertEqual(digest(patched), before)

    def test_actual_it4025_unit61_native_and_frozen_packaging(self):
        import pymupdf
        from native_batches import prepare_native
        from corpus import package_job
        source = Path('D:/bk_quizz_data/slide_processed/pdf/IT4025-Mật mã ứng dụng.pdf')
        if not source.exists(): self.skipTest('Original IT4025 PDF is unavailable')
        sha = digest(source)
        self.assertEqual(sha, 'ff432ad5e84a1ed80617cd3219fccbfdef056b3f4c59651f72f1b0c9d9d234b9')
        install()
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            root = Path(tmp); run = root/'run'
            job = {'job_id':'it4025_ff432ad5e84a_p00264-00363', 'document_id':'it4025_ff432ad5e84a',
                   'source_path':str(source), 'source_sha256':sha, 'first_page':264, 'last_page':363,
                   'source_pages':834, 'run':str(run), 'vlm_page_budget':5,
                   'course':'IT4025', 'split_policy':'train', 'layout_required':True}
            prepare_native(job, None, 20)
            data = (run/'records.jsonl').read_bytes(); before = digest(run/'records.jsonl')
            with self.assertRaises(json.JSONDecodeError) as old:
                [json.loads(line) for line in data.decode().splitlines() if line.strip()]
            records = read_jsonl(run/'records.jsonl')
            pages = read_jsonl(run/'document_pages.jsonl')
            self.assertEqual([p['page'] for p in pages], list(range(264,364)))
            actual = {p['page']:p['native_text'] for p in pages}
            with pymupdf.open(source) as doc:
                import io_utils
                for number in range(264,364):
                    self.assertEqual(actual[number], io_utils.normalize(doc[number-1].get_text('text',sort=True)))
            self.assertEqual(sum('\u2028' in t for t in actual.values()), 6)
            packet = package_job({'work_root':str(root), 'maximum_packet_bytes':536870912}, job, 'discovery')
            self.assertTrue(packet.is_file())
            self.assertEqual(digest(run/'records.jsonl'), before)
            self.assertFalse(any(r.get('semantic_verified') or r.get('human_verified') for r in records))
            atomic_json(ROOT/'JSONL_IT4025_REGRESSION_20261023.json', {
                'source_sha256':sha, 'unit':'unit_0061', 'first_page':264, 'last_page':363,
                'pages':len(pages), 'records':len(records), 'sorted_native_pages_with_U2028':6,
                'old_reader_error':str(old.exception), 'native_characters_preserved':True,
                'frozen_package_job_succeeded':True, 'record_file_unchanged_by_packaging':True,
                'GPU_inference_executed':False, 'Colab_executed':False})


if __name__ == '__main__': unittest.main(verbosity=2)
