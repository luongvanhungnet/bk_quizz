"""Exercise the generated notebook cell with fake IPC; never run model inference."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

from build_resume_10_14 import ROOT, build


class ResumeRangeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cell = build().read_text(encoding='utf-8')
        cls.release = json.loads((ROOT/'BATCHFIX_RELEASE.json').read_text(encoding='utf-8'))

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.base = self.root/'drive/base'; self.base.mkdir(parents=True)
        self.work = self.root/'work'
        self.inputs = self.root/'inputs'; self.inputs.mkdir()
        self.events = []
        self.fail_index = None; self.wrong_result = False; self.blocked = False
        self.save_state(9)
        (self.base/'environments.json').write_text(json.dumps({'controller':sys.executable}),encoding='utf-8')
        shutil.copyfile(ROOT/self.release['runtime_zip'],self.inputs/self.release['runtime_zip'])
        for index in range(10,15): self.write_input(index)
        self.namespace = {'BASE':self.base,'WORK':self.work,'INPUT_DIR':self.inputs,
                          'BATCH_PAGES':999,'MAX_INPUTS':1,'INPUTS':[]}
        owner = self

        class FakeSession:
            def __init__(self,python,base,keep_model=True,batch_pages=20,work=None):
                self.base,self.work = Path(base),Path(work)
                self.keep_model,self.batch_pages = keep_model,batch_pages
                self.runtime_revision = os.environ.get('BKQUIZ_RUNTIME_REVISION')
                self.runtime_profile = os.environ.get('BKQUIZ_RUNTIME_PROFILE')
                self.docling_hf_home = os.environ.get('BKQUIZ_DOCLING_HF_HOME')
                self.alive = True
                self.process = SimpleNamespace(poll=lambda:None if self.alive else 0)
                owner.events.append(('start',batch_pages))

            def process_input(self,path):
                with zipfile.ZipFile(path) as z: index = json.loads(z.read('bundle.json'))['bundle_index']
                owner.events.append(('process',index))
                if owner.fail_index == index: raise RuntimeError('simulated worker error')
                return {'bundle_index':index+1 if owner.wrong_result else index,
                        'archive':str(owner.base/f'result_{index}.zip'),'archive_sha256':'a'*64,
                        'summary':{'all_jobs_executed':not owner.blocked,'all_stages_successful':False,
                                   'semantic_verified':False}}

            def commit(self,result):
                index = result['bundle_index']; state = owner.state()
                if index != state['last_acknowledged_index']+1: raise AssertionError('out of order commit')
                owner.events.append(('commit',index));state['last_acknowledged_index']=index
                (owner.base/'queue_state.json').write_text(json.dumps(state),encoding='utf-8')

            def close(self): self.alive=False;owner.events.append(('close',))

        self.Session = FakeSession

    def save_state(self,index):
        (self.base/'queue_state.json').write_text(json.dumps({'schema':'v5-orchestrator-3-drive',
            'last_acknowledged_index':index,'plan_sha256':'test-plan','batch_pages':20,
            'finished_inputs':{'9':{'semantic_verified':False,'archive_sha256':'original'}}}),encoding='utf-8')

    def state(self): return json.loads((self.base/'queue_state.json').read_text(encoding='utf-8'))

    def write_input(self,index,**overrides):
        manifest={'schema':'v5-orchestrator-2-sequential','sequence_required':True,
                  'bundle_count':14,'bundle_index':index,'plan_sha256':'test-plan',**overrides}
        with zipfile.ZipFile(self.inputs/f'v5_sequential_{index:02d}_of_14.zip','w') as z:
            z.writestr('bundle.json',json.dumps(manifest))

    def run_cell(self):
        loader=SimpleNamespace(exec_module=lambda module:None)
        spec=SimpleNamespace(loader=loader)
        with contextlib.redirect_stdout(io.StringIO()), patch.dict(os.environ), \
             patch.object(importlib.util,'spec_from_file_location',return_value=spec), \
             patch.object(importlib.util,'module_from_spec',return_value=SimpleNamespace(Session=self.Session)):
            exec(compile(self.cell,'resume_10_14','exec'),self.namespace)

    def test_runs_10_through_14_ignoring_old_max_inputs_and_keeps_failed_quality(self):
        self.run_cell()
        self.assertEqual([e[1] for e in self.events if e[0]=='process'],list(range(10,15)))
        self.assertEqual([e[1] for e in self.events if e[0]=='commit'],list(range(10,15)))
        self.assertEqual(self.state()['last_acknowledged_index'],14)
        self.assertEqual(self.state()['finished_inputs']['9']['archive_sha256'],'original')
        self.assertFalse(self.namespace['RESULT']['summary']['semantic_verified'])
        self.assertFalse(self.namespace['RESULT']['summary']['all_stages_successful'])
        self.assertIn(('start',20),self.events)

    def test_skips_already_committed_10_and_11(self):
        self.save_state(11);self.run_cell()
        self.assertEqual([e[1] for e in self.events if e[0]=='process'],[12,13,14])

    def test_failure_stops_without_advancing_and_rerun_starts_at_failed_input(self):
        self.fail_index=12
        with self.assertRaisesRegex(RuntimeError,'simulated worker'):self.run_cell()
        self.assertEqual(self.state()['last_acknowledged_index'],11)
        self.assertNotIn(('process',13),self.events)
        self.events.clear();self.fail_index=None;self.run_cell()
        self.assertEqual([e[1] for e in self.events if e[0]=='process'],[12,13,14])
        self.assertNotIn(('start',20),self.events)  # Reuse the same live, patched session.

    def test_never_fakes_the_missing_first_nine_commits(self):
        self.save_state(8);before=(self.base/'queue_state.json').read_bytes()
        with self.assertRaisesRegex(RuntimeError,'commit đủ input 1–9'):self.run_cell()
        self.assertEqual((self.base/'queue_state.json').read_bytes(),before);self.assertFalse(self.events)

    def test_completed_queue_needs_no_runtime_upload_or_venv(self):
        self.save_state(14);(self.inputs/self.release['runtime_zip']).unlink()
        (self.base/'environments.json').unlink();self.run_cell();self.assertFalse(self.events)

    def test_wrong_plan_fails_before_closing_existing_session(self):
        old=SimpleNamespace(process=SimpleNamespace(poll=lambda:None),close=lambda:self.fail('closed before validation'))
        self.namespace['SESSION']=old;self.write_input(13,plan_sha256='other-plan')
        with self.assertRaisesRegex(RuntimeError,'khác kế hoạch'):self.run_cell()
        self.assertEqual(self.state()['last_acknowledged_index'],9)

    def test_wrong_runtime_fails_before_launch(self):
        (self.inputs/self.release['runtime_zip']).write_bytes(b'wrong runtime')
        with self.assertRaisesRegex(RuntimeError,'Sai runtime ZIP'):self.run_cell()
        self.assertFalse(self.events)

    def test_old_runtime_session_is_closed_then_replaced_by_patched_controller(self):
        old=self.Session(sys.executable,self.base,batch_pages=20,work=self.work)
        old.runtime_revision='old';self.namespace['SESSION']=old;self.events.clear()
        self.run_cell();self.assertEqual(self.events[0],('close',));self.assertFalse(old.alive)
        self.assertEqual(self.namespace['SESSION'].runtime_revision,self.release['runtime_revision'])

    def test_wrong_result_index_is_not_committed(self):
        self.wrong_result=True
        with self.assertRaisesRegex(RuntimeError,'chưa hoàn chỉnh'):self.run_cell()
        self.assertEqual(self.state()['last_acknowledged_index'],9)
        self.assertFalse([e for e in self.events if e[0]=='commit'])

    def test_blocked_job_is_not_committed(self):
        self.blocked=True
        with self.assertRaisesRegex(RuntimeError,'chưa hoàn chỉnh'):self.run_cell()
        self.assertEqual(self.state()['last_acknowledged_index'],9)

    def test_existing_runtime_archive_hash_is_unchanged(self):
        self.run_cell()
        self.assertEqual(hashlib.sha256((ROOT/self.release['runtime_zip']).read_bytes()).hexdigest(),
                         self.release['runtime_zip_sha256'])


if __name__=='__main__':unittest.main()
