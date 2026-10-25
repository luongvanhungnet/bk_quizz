import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from batch_restore import restore_output
from common import digest,load
from test_drive_queue import FakeWorker,SequentialCoordinator,ENVS,fixture


class BatchRestoreTests(unittest.TestCase):
    def test_empty_failed_checkpoint_creates_audit_container_and_preserves_failure(self):
        with tempfile.TemporaryDirectory() as d,contextlib.redirect_stdout(io.StringIO()):
            root=Path(d);response={'completed':False,'error':'Docling init failed','traceback':'original full traceback'}
            m={'files':{'child_manifest.json':'unused'},'response':response,'stage_key':'job:discovery:docling'}
            self.assertEqual(restore_output(root/'unpacked',root/'out',m),0)
            audit=load(root/'out/_restored_failure.json')
            self.assertEqual(audit['original_response'],response);self.assertFalse(audit['semantic_verified'])
            self.assertFalse(response['completed']);self.assertFalse((root/'out/parser_candidates_docling.json').exists())

    def test_empty_error_result_with_completed_process_is_still_failure(self):
        with tempfile.TemporaryDirectory() as d,contextlib.redirect_stdout(io.StringIO()):
            root=Path(d);response={'completed':True,'result':{'status':'error'}}
            self.assertEqual(restore_output(root/'in',root/'out',{'files':{},'response':response}),0)
            self.assertEqual(load(root/'out/_restored_failure.json')['original_response']['result']['status'],'error')

    def test_empty_success_checkpoint_is_not_fabricated_into_success(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with self.assertRaisesRegex(ValueError,'reports success but contains no output'):
                restore_output(root/'in',root/'out',{'files':{},'response':{'completed':True,'result':{'status':'ok'}}})
            self.assertFalse((root/'out').exists())

    def test_stale_output_directory_not_listed_in_manifest_is_ignored(self):
        with tempfile.TemporaryDirectory() as d,contextlib.redirect_stdout(io.StringIO()):
            root=Path(d);stale=root/'in/output';stale.mkdir(parents=True);(stale/'parser_candidates_docling.json').write_text('stale success')
            restore_output(root/'in',root/'out',{'files':{},'response':{'completed':False}})
            self.assertFalse((root/'out/parser_candidates_docling.json').exists())

    def test_normal_output_copy_is_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'in/output/records/x.json';source.parent.mkdir(parents=True);source.write_text('original')
            self.assertEqual(restore_output(root/'in',root/'out',{'files':{'output/records/x.json':'unused'},
                'response':{'completed':True,'result':{'status':'ok'}}}),1)
            self.assertEqual(digest(source),digest(root/'out/records/x.json'))

    def test_recovery_artifacts_preserve_14_input_base_and_do_not_reinstall(self):
        from build_batchfix import publish,ROOT,REVISION
        release=publish();nb=load(ROOT/release['notebook'])
        cell=(ROOT/'COLAB_RESUME_INPUT7_CELL.txt').read_text(encoding='utf-8')
        compile(cell,'recovery','exec')
        self.assertIn('BKQuiz_v5_drive_v3',cell);self.assertIn('len(FIX_INPUTS)==14',cell)
        self.assertNotIn('setup(',cell);self.assertNotIn('rmtree(',cell)
        self.assertIn('SESSION.commit(RESULT)',cell);self.assertIn(REVISION,cell)
        self.assertEqual(nb['metadata']['bkquiz_runtime']['revision'],REVISION)
        self.assertIn('batch_restore.py',release['files'])
        self.assertEqual(digest(ROOT/release['runtime_zip']),release['runtime_zip_sha256'])

    def test_failed_docling_no_output_resumes_without_inference_or_marking_success(self):
        class EmptyDocling(FakeWorker):
            def call(self,packet,out,*args,**kwargs):
                if self.role=='docling':
                    out.mkdir(parents=True,exist_ok=True);self.calls.append(('docling_failed',tuple(load(packet/'manifest.json')['page_map'].values())))
                    return {'completed':False,'role':'docling','error':'simulated Docling startup failure',
                            'traceback':'original Docling traceback retained','seconds':.1}
                return super().call(packet,out,*args,**kwargs)
        with tempfile.TemporaryDirectory() as d,contextlib.redirect_stdout(io.StringIO()):
            root=Path(d);_,inputs=fixture(root,(3,));FakeWorker.calls=[]
            with patch.dict('os.environ',{'BKQUIZ_SHARED_CACHE':str(root/'cache')}),patch('orchestrator.Worker',EmptyDocling),patch('sequential.Worker',EmptyDocling):
                old=SequentialCoordinator(root/'base',root/'old_work',ENVS,batch_pages=2)
                old.register_one(inputs[0]);old.prepare();pairs=[(old.jobs[0],'discovery')]
                for role in ['ocr','structure','docling']:old.group_stage(role,pairs)
                originals={k:v for k,v in old.state['page_batches'].items() if ':docling:' in k};old.close()
                previous_failed_calls=len([c for c in FakeWorker.calls if c[0]=='docling_failed'])
                new=SequentialCoordinator(root/'base',root/'new_work',ENVS,batch_pages=2)
                result=new.process(inputs[0]);new.acknowledge(1,result['archive_sha256']);new.close()
            self.assertEqual(len([c for c in FakeWorker.calls if c[0]=='docling_failed']),previous_failed_calls)
            self.assertTrue(result['summary']['all_jobs_executed']);self.assertFalse(result['summary']['all_stages_successful'])
            key=next(k for k in new.state['stages'] if k.endswith(':discovery:docling'))
            self.assertFalse(new.state['stages'][key]['completed']);self.assertEqual(new.state['stages'][key]['result']['status'],'error')
            self.assertIn('original Docling traceback retained',str(new.state['stages'][key]))
            for v in originals.values():self.assertEqual(digest(v['archive']),v['archive_sha256'])


if __name__=='__main__':unittest.main()
