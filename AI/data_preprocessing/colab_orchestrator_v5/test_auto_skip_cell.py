"""Exercise the notebook skip policy without loading models or editing receipts."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parent


class AutoSkipCellTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.base=self.root/'drive';self.base.mkdir()
        self.complete=set();self.calls=[];self.errors={};self.die=False
        self.source=(ROOT/'COLAB_AUTO_SKIP_CELL.txt').read_text(encoding='utf-8')
        entries=[]
        for n in [25,26,27]:
            path=self.root/f'input_{n}.zip';path.write_bytes(b'placeholder')
            entries.append({'unit_id':f'unit_{n:04d}','path':str(path),'filename':path.name,'pages':100})
        self.ns={'BASE':self.base,'WORK':self.root/'work','ENVS':{'controller':'fake-python'},
                 'PROFILE':'test-profile','DOC_HF_HOME':self.root/'models','KEEP_MODEL_RESIDENT':True,
                 'MAX_UNITS':None,'INDEX':{'plan_sha256':'original-plan','bundles':entries}}
        owner=self

        class FakeSession:
            def __init__(self,*args,**kwargs):
                self.base=owner.base;self.work=owner.ns['WORK'];self.keep_model=True
                self.runtime_revision='v6-bounded-regions-l4-20261022'
                self.runtime_profile='test-profile';self.docling_hf_home=str(owner.ns['DOC_HF_HOME'])
                self.alive=True;self.process=SimpleNamespace(poll=lambda:None if self.alive else 1)
            def scan(self):return self.status()
            def status(self):
                pending=[e['unit_id'] for e in entries if e['unit_id'] not in owner.complete]
                return {'completed_units':len(owner.complete),'total_units':3,'completed_pages':100*len(owner.complete),
                        'pending_units':pending,'next_unit':pending[0] if pending else None}
            def process_unit(self,uid):
                owner.calls.append(uid)
                if uid in owner.errors:
                    if owner.die:self.alive=False
                    raise owner.errors[uid]
                owner.complete.add(uid)
                return {'archive':str(owner.base/(uid+'.zip')),'archive_sha256':'f'*64}
            def close(self):self.alive=False

        self.Session=FakeSession

    def execute(self,*,retry=False,include25=False):
        source=self.source
        if retry:source=source.replace('RETRY_FAILED = False','RETRY_FAILED = True')
        if include25:source=source.replace("EXCLUDED_UNITS = {'unit_0025'}",'EXCLUDED_UNITS = set()')
        with patch('client.Session',self.Session),contextlib.redirect_stdout(io.StringIO()) as output:
            exec(compile(source,'auto_skip_cell','exec'),self.ns)
        return output.getvalue()

    def test_empty_crop_skips_once_and_runs_next_pending_unit(self):
        self.errors['unit_0026']=RuntimeError('ValueError: cannot write empty image')
        output=self.execute()
        self.assertEqual(self.calls,['unit_0026','unit_0027'])
        self.assertEqual(self.complete,{'unit_0027'})
        self.assertEqual(self.ns['STATE']['pending_units'],['unit_0025','unit_0026'])
        self.assertNotIn('Hoàn tất toàn bộ gói.',output)
        saved=json.loads((self.base/'auto_skipped_units.json').read_text(encoding='utf-8'))
        self.assertIn('cannot write empty image',saved['failed']['unit_0026']['traceback'])
        self.assertFalse((self.base/'queue_state.json').exists())
        self.assertFalse((self.base/'receipts').exists())

    def test_skip_survives_status_reload_and_reexecution(self):
        self.errors['unit_0026']=RuntimeError('cannot write empty image');self.execute();self.calls.clear()
        self.execute();self.assertEqual(self.calls,[])

    def test_explicit_retry_resolves_error_and_preserves_history(self):
        self.errors['unit_0026']=RuntimeError('cannot write empty image');self.execute();self.errors.clear();self.calls.clear()
        output=self.execute(retry=True,include25=True)
        self.assertEqual(self.calls,['unit_0025','unit_0026'])
        self.assertEqual(len(self.complete),3);self.assertIn('Hoàn tất toàn bộ gói.',output)
        data=json.loads((self.base/'auto_skipped_units.json').read_text(encoding='utf-8'))
        self.assertNotIn('unit_0026',data['failed'])
        self.assertEqual([e['event'] for e in data['history']],['failed','resolved'])

    def test_runtime_syntax_error_stops_without_mass_skipping(self):
        self.errors['unit_0026']=RuntimeError('IndentationError: expected an indented block')
        with self.assertRaisesRegex(RuntimeError,'IndentationError'):self.execute()
        self.assertEqual(self.calls,['unit_0026']);self.assertEqual(self.complete,set())

    def test_dead_controller_stops_without_attempting_remaining_inputs(self):
        self.errors['unit_0026']=RuntimeError('Coordinator exited');self.die=True
        with self.assertRaisesRegex(RuntimeError,'Coordinator exited'):self.execute()
        self.assertEqual(self.calls,['unit_0026'])

    def test_max_units_counts_failures_as_attempts(self):
        self.ns['MAX_UNITS']=1;self.errors['unit_0026']=RuntimeError('cannot write empty image');self.execute()
        self.assertEqual(self.calls,['unit_0026']);self.assertFalse(self.complete)

    def test_manual_interrupt_is_not_swallowed(self):
        self.errors['unit_0026']=KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):self.execute()
        self.assertFalse((self.base/'auto_skipped_units.json').exists())

    def test_none_session_variable_is_safe(self):
        self.ns['SESSION']=None;self.execute();self.assertEqual(self.complete,{'unit_0026','unit_0027'})

    def test_cross_plan_failure_registry_does_not_overwrite_state(self):
        data={'plan_sha256':'other-plan','failed':{},'history':[]}
        path=self.base/'auto_skipped_units.json';path.write_text(json.dumps(data),encoding='utf-8')
        before=path.read_bytes()
        with self.assertRaisesRegex(RuntimeError,'kế hoạch khác'):self.execute()
        self.assertEqual(before,path.read_bytes());self.assertEqual(self.calls,[])

    def test_blank_error_message_is_still_recorded_and_skipped(self):
        self.errors['unit_0026']=ValueError();self.execute()
        self.assertEqual(self.complete,{'unit_0027'})


if __name__=='__main__':unittest.main()
