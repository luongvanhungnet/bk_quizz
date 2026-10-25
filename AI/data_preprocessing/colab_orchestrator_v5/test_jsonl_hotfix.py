import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from build_jsonl_hotfix import apply_hotfix, build
from common import digest


class HotfixTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.runtime = self.root/'runtime'; self.runtime.mkdir()
        self.base = self.root/'drive'; self.base.mkdir()
        with zipfile.ZipFile(ROOT/'colab_orchestrator_v5_v6_runtime.zip') as z:
            for name in z.namelist():
                if name.endswith('.py'): (self.runtime/name).write_bytes(z.read(name))
        self.adapter = (ROOT/'jsonl_adapter.py').read_text(encoding='utf-8')

    def test_updates_old_runtime_and_keeps_manual_crop_fix_and_results(self):
        native = self.runtime/'native_batches.py'
        native.write_bytes(native.read_bytes()+b'\n# Existing cloud crop fix must survive.\n')
        result = self.base/'results/unit_0060.zip'; result.parent.mkdir(); result.write_bytes(b'existing result')
        original = {p.name:p.read_bytes() for p in self.runtime.glob('*.py')}
        receipt = self.base/'queue_state.json'; receipt.write_text('{"completed_units":60}')
        report = apply_hotfix(self.runtime, self.base, self.adapter)
        backup = Path(report['backup'])
        for name, data in original.items(): self.assertEqual((backup/name).read_bytes(), data)
        self.assertEqual(native.read_bytes(), original['native_batches.py'])
        self.assertEqual(result.read_bytes(), b'existing result')
        self.assertEqual(receipt.read_text(), '{"completed_units":60}')
        self.assertFalse(report['source_core_modified'])
        self.assertFalse(report['records_modified'])
        self.assertIn('install_jsonl()', (self.runtime/'unit_queue.py').read_text())
        self.assertIn('loads_jsonl(read_logical(name)', (self.runtime/'unit_store.py').read_text())
        # Independent child interpreter confirms packaging aliases pick up the fix.
        import subprocess
        engine = ROOT.parent.parent/'Qwen_cpt_version/region_preprocessing_v5_official'
        command = [sys.executable, '-X', 'utf8', '-c',
                   'import sys;sys.path.insert(0,sys.argv[1]);sys.path.insert(0,sys.argv[2]);'
                   'import corpus;from jsonl_adapter import install,loads_jsonl,read_jsonl;install();'
                   'assert corpus.jsonl is read_jsonl;'
                   'assert loads_jsonl(\'{"text":"A\\u2028B"}\\n\')==[{"text":"A\\u2028B"}]',
                   str(engine), str(self.runtime)]
        subprocess.run(command,check=True,capture_output=True,text=True,encoding='utf-8')

    def test_reapplying_is_idempotent(self):
        apply_hotfix(self.runtime, self.base, self.adapter)
        before = {p.name:digest(p) for p in self.runtime.glob('*.py')}
        apply_hotfix(self.runtime, self.base, self.adapter)
        self.assertEqual(before,{p.name:digest(p) for p in self.runtime.glob('*.py')})

    def test_unknown_edit_refuses_before_changing_any_runtime_file(self):
        path = self.runtime/'unit_store.py'
        path.write_text(path.read_text().replace('def json_rows(name):','def unexpected_json_rows(name):'))
        before = {p.name:p.read_bytes() for p in self.runtime.glob('*.py')}
        with self.assertRaisesRegex(RuntimeError,'unit_store.py'):
            apply_hotfix(self.runtime, self.base, self.adapter)
        self.assertEqual(before,{p.name:p.read_bytes() for p in self.runtime.glob('*.py')})

    def test_write_failure_rolls_back_changes(self):
        before = {p.name:p.read_bytes() for p in self.runtime.glob('*.py')}
        import os
        replace = os.replace
        calls = []
        def fail_second(source,target):
            calls.append(str(target))
            if len(calls) == 2: raise OSError('simulated local write failure')
            return replace(source,target)
        with patch('os.replace',side_effect=fail_second):
            with self.assertRaisesRegex(OSError,'simulated'):
                apply_hotfix(self.runtime, self.base, self.adapter)
        self.assertEqual(before,{p.name:p.read_bytes() for p in self.runtime.glob('*.py')})

    def test_generated_cell_uses_existing_runtime_not_a_venv_reinstall(self):
        source = build().read_text(encoding='utf-8')
        compile(source,'repair_cell','exec')
        self.assertIn('SESSION.close()',source)
        self.assertIn("globals().pop('SESSION', None)",source)
        self.assertNotIn('pip install',source)
        self.assertNotIn('rmtree',source)
        self.assertNotIn('files.upload',source)
        self.assertNotIn('files.download',source)


if __name__ == '__main__': unittest.main(verbosity=2)
