import contextlib
import copy
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parent
ENGINE=ROOT.parent.parent/'Qwen_cpt_version/region_preprocessing_v5_official'
sys.path.insert(0,str(ENGINE));sys.path.insert(0,str(ROOT))
from common import atomic_json,digest,load,rows
from region_policy import proposals,MAX_REGIONS_PER_PAGE,limit_candidates
from fast_routing import route
from stage_guard import run_guarded,StageTimeout


def record(i):
    return {'id':str(i),'page':i%20+1,'kind':'diagram','bbox':[100,200,800,800],
            'image_quality':{'pixel_sha256':str(i%5)},'pending_engines':['vlm'],'native_text':'graph'}


class V6Tests(unittest.TestCase):
    def test_docling_fatal_stops_first_batch_and_never_publishes_unit(self):
        from test_units import fixture,ENVS,FakeWorker
        from unit_queue import UnitRunner
        calls=[]
        class BrokenDocling(FakeWorker):
            def call(self,*args,**kwargs):
                if self.role=='docling':
                    calls.append('failure')
                    return {'completed':False,'error':'header too large','traceback':'full model loading traceback'}
                return super().call(*args,**kwargs)
        with tempfile.TemporaryDirectory() as tmp,contextlib.redirect_stdout(io.StringIO()):
            root=Path(tmp);index,_=fixture(root,(21,))
            with patch('orchestrator.Worker',BrokenDocling),patch('unit_queue.Worker',BrokenDocling):
                runner=UnitRunner(root/'base',root/'work',index,ENVS);runner.scan()
                with self.assertRaisesRegex(RuntimeError,'Docling failed'):runner.process('unit_0001')
                runner.close()
            self.assertEqual(len(calls),1)
            self.assertEqual(list((root/'base/receipts').glob('*.json')),[])
            errors=list((root/'base/failures/unit_0001').glob('*.json'))
            self.assertTrue(errors);self.assertIn('full model loading traceback',errors[0].read_text(encoding='utf-8'))

    def test_model_deadline_terminates_worker_instead_of_heartbeat_forever(self):
        import subprocess
        from orchestrator import Worker
        with tempfile.TemporaryDirectory() as tmp,contextlib.redirect_stdout(io.StringIO()):
            root=Path(tmp);worker=Worker.__new__(Worker);worker.role='ocr';worker.log_path=root/'model.log'
            worker.log=worker.log_path.open('w',encoding='utf-8')
            worker.process=subprocess.Popen([sys.executable,'-c','import sys,time;sys.stdin.readline();time.sleep(30)'],
                stdin=subprocess.PIPE,stdout=worker.log,stderr=subprocess.STDOUT,text=True)
            with patch.dict('os.environ',{'BKQUIZ_MODEL_TIMEOUT_SECONDS':'.3'}):
                with self.assertRaises(StageTimeout):worker.call(root,root,root/'ipc')
            self.assertIsNotNone(worker.process.poll());worker.close()

    def test_batch_splits_on_request_budget_even_below_twenty_pages(self):
        import pymupdf
        from page_batches import split_packet
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);packet=root/'packet';packet.mkdir();(packet/'image.png').write_bytes(b'image')
            with pymupdf.open() as doc:
                for _ in range(4):doc.new_page()
                doc.save(packet/'parser.pdf')
            requests=[{'id':f'{page}:{i}','page':page,'image':'image.png','vlm_image':'image.png'} for page in range(1,5) for i in range(100)]
            atomic_json(packet/'manifest.json',{'requests':requests,'page_map':{str(i):i for i in range(1,5)},
                'parser_input':'parser.pdf','parser_input_sha256':digest(packet/'parser.pdf'),'code_sha256':{}})
            batches=list(split_packet(packet,root/'batches',20))
            self.assertEqual([len(load(p/'manifest.json')['requests']) for p in batches],[200,200])

    def test_one_page_over_budget_does_not_launch_unbounded_batch(self):
        import pymupdf
        from page_batches import split_packet
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);packet=root/'packet';packet.mkdir();(packet/'image.png').write_bytes(b'image')
            with pymupdf.open() as doc:doc.new_page();doc.save(packet/'parser.pdf')
            atomic_json(packet/'manifest.json',{'requests':[{'id':str(i),'page':1,'image':'image.png','vlm_image':'image.png'} for i in range(257)],
                'page_map':{'1':1},'parser_input':'parser.pdf','parser_input_sha256':digest(packet/'parser.pdf'),'code_sha256':{}})
            with self.assertRaisesRegex(ValueError,'exceeds region/asset budget'):list(split_packet(packet,root/'batches',20))

    def test_routing_matches_frozen_rules_and_budget(self):
        import batch_layout
        # The frozen route is unchanged on disk; compare before the coverage adapter.
        data=[record(i) for i in range(180)]
        old=copy.deepcopy(data);new=copy.deepcopy(data)
        self.assertEqual(batch_layout.route(old,20),route(new,20))
        self.assertEqual(old,new)

    def test_large_exact_duplicate_group_routes_without_quadratic_rescans(self):
        data=[record(i) for i in range(50000)];start=time.perf_counter()
        result=route(data,20)
        self.assertLess(time.perf_counter()-start,15)
        self.assertEqual(result['candidate_pages'],5)
        self.assertEqual(sum(r['legacy_routing_state']=='exact_duplicate' for r in data),49995)

    def test_actual_it4906_background_is_audited_before_crop_and_ocr(self):
        import pymupdf
        from native_batches import prepare_native
        source=Path('D:/bk_quizz_data/slide_processed/pdf/IT4906-Tính toán tiến hóa.pdf')
        self.assertTrue(source.exists(),'IT4906 regression source is required for this local release')
        sha=digest(source)
        with tempfile.TemporaryDirectory() as tmp,contextlib.redirect_stdout(io.StringIO()):
            root=Path(tmp);job={'run':str(root/'run'),'source_path':str(source),'source_sha256':sha,
                'first_page':217,'last_page':217,'vlm_page_budget':1,'course':'IT4906','split_policy':'train','document_id':'it4906'}
            prepare_native(job,None,20)
            audit=load(root/'run/region_audit/page_0217.json');records=rows(root/'run/records.jsonl')
            self.assertEqual(audit['displayed_occurrences'],24378)
            self.assertEqual(audit['suppressed_background_occurrences'],24378)
            self.assertEqual(len(audit['groups'][0]['bboxes']),24378)
            self.assertEqual(len(records),1);self.assertEqual(records[0]['native_text'],'TỐI ƯU ĐA MỤC TIÊU')
            self.assertTrue((root/'run/assets/slides/page_0217.png').is_file())
            self.assertFalse(records[0]['semantic_verified']);self.assertEqual(digest(source),sha)

    def test_unknown_tiny_images_are_held_for_review_instead_of_deleted(self):
        import pymupdf
        from PIL import Image
        from io import BytesIO
        stream=BytesIO();Image.new('RGB',(2,8),'white').save(stream,format='PNG')
        with tempfile.TemporaryDirectory() as tmp,pymupdf.open() as doc:
            page=doc.new_page(width=100,height=100);xref=0
            for i in range(600):
                x=i%25*4;y=i//25*4
                xref=page.insert_image(pymupdf.Rect(x,y,x+2,y+4),stream=stream.getvalue() if not xref else None,xref=xref)
            kept,audit=proposals(page,'unknown-source',tmp,1)
            self.assertEqual(kept,[]);self.assertTrue(audit['review_required'])
            self.assertEqual(audit['suppressed_background_occurrences'],0)
            self.assertEqual(len(audit['deferred_proposals']),600)

    def test_small_unknown_formula_image_is_preserved(self):
        import pymupdf
        from PIL import Image
        from io import BytesIO
        stream=BytesIO();Image.new('RGB',(2,8),'black').save(stream,format='PNG')
        with tempfile.TemporaryDirectory() as tmp,pymupdf.open() as doc:
            page=doc.new_page();page.insert_image(pymupdf.Rect(10,10,20,50),stream=stream.getvalue())
            kept,audit=proposals(page,'unknown-source',tmp,1)
            self.assertEqual(len(kept),1);self.assertFalse(audit['review_required'])

    def test_cpu_stage_timeout_terminates_owned_process(self):
        with tempfile.TemporaryDirectory() as tmp,contextlib.redirect_stdout(io.StringIO()):
            start=time.monotonic()
            with self.assertRaises(StageTimeout):
                run_guarded([sys.executable,'-c','import time;time.sleep(30)'],tmp,'hang',timeout=.3,interval=.1)
            self.assertLess(time.monotonic()-start,10)

    def test_cpu_stage_failure_retains_full_trace_in_log(self):
        with tempfile.TemporaryDirectory() as tmp,contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError,'deliberate error'):
                run_guarded([sys.executable,'-c',"raise ValueError('deliberate error')"],tmp,'failure')
            self.assertIn('Traceback',(Path(tmp)/'failure.log').read_text(encoding='utf-8'))

    def test_layout_overflow_preserves_candidates_in_review_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            data=[{'page':1,'id':i} for i in range(201)]
            self.assertEqual(limit_candidates(data,tmp),[])
            audit=load(Path(tmp)/'region_audit/layout_overflow_0001.json')
            self.assertTrue(audit['review_required']);self.assertEqual(audit['candidates'],data)

    def test_docling_cache_bad_header_is_never_persisted(self):
        from model_cache import seal
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);weights=root/'models/docling_hf/hub/models--docling-project--docling-layout-heron/snapshots/test/model.safetensors'
            weights.parent.mkdir(parents=True);weights.write_bytes(b'version https://git-lfs.github.com/spec/v1')
            with self.assertRaisesRegex(ValueError,'invalid'):seal(root/'base',root/'models')
            self.assertFalse((root/'base/model_cache/docling_hf/latest.json').exists())

    def test_model_cache_roundtrip_verifies_full_archive_and_preserves_original(self):
        from model_cache import seal,restore
        with tempfile.TemporaryDirectory() as tmp,contextlib.redirect_stdout(io.StringIO()):
            root=Path(tmp);weights=root/'models/docling_hf/hub/models--docling-project--docling-layout-heron/snapshots/test/model.safetensors'
            weights.parent.mkdir(parents=True)
            header=json.dumps({'x':{'dtype':'F32','shape':[1],'data_offsets':[0,4]}}).encode()
            weights.write_bytes(struct.pack('<Q',len(header))+header+b'\0'*4);before=digest(weights)
            result=seal(root/'base',root/'models');self.assertTrue(result['saved'])
            result=restore(root/'base',root/'restored');self.assertTrue(result['restored'])
            other=root/'restored/docling_hf'/weights.relative_to(root/'models/docling_hf')
            self.assertEqual(digest(other),before);self.assertEqual(digest(weights),before)

    def test_adoption_preserves_old_result_bytes_and_never_calls_model(self):
        from test_units import fixture,minimal_result,UnitStore
        from reuse_previous import adopt
        with tempfile.TemporaryDirectory() as tmp,contextlib.redirect_stdout(io.StringIO()):
            root=Path(tmp);index,_=fixture(root,(1,));entry=index['bundles'][0]
            old=UnitStore(root/'old',index);archive=minimal_result(root,entry,index['plan_sha256'])
            receipt=old.publish(archive,entry)
            before={str(p.relative_to(root/'old')):digest(p) for p in (root/'old').rglob('*') if p.is_file()}
            new=UnitStore(root/'new',index);adopt(new,root/'old',root/'work')
            self.assertEqual(new.summary()['completed_units'],1)
            after={str(p.relative_to(root/'old')):digest(p) for p in (root/'old').rglob('*') if p.is_file()}
            self.assertEqual(before,after)
            provenance=load(root/'new/previous_provenance'/f'{entry["unit_id"]}.json')
            self.assertFalse(provenance['new_policy_rerun']);self.assertFalse(provenance['semantic_verified'])


if __name__=='__main__':unittest.main()
