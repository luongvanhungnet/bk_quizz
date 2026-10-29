import copy
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from PIL import Image
from io_utils import sha,canonical,file_sha,write_json,write_jsonl,load,jsonl
from cross_validation import cross_validate
from models import validate_record
from review_store import ReviewStore
from workflow import export_cpt,associate,ingest_cloud
from vlm_worker import run,PROMPT,fit_image
from package_cloud import wants_vlm

def fixture(run,split='train',kind='text',text='Thuật toán chia để trị.'):
    run.mkdir(parents=True,exist_ok=True);Image.new('RGB',(100,100),'white').save(run/'slide.png');digest=file_sha(run/'slide.png')
    r={'id':'r1','page':1,'kind':kind,'bbox':[0,0,1000,1000],'render_path':'slide.png','crop_path':'slide.png','context_path':'slide.png',
        'source_sha256':'a'*64,'render_sha256':digest,'crop_sha256':digest,'context_sha256':digest,'context_bbox':[0,0,1000,1000],
        'group_id':'g','split':split,'native_text':text,'candidates':[{'engine':'native','text':text,'status':'ok','evidence':{'lineage':'pymupdf','source_sha256':'a'*64,'region_id':'r1','crop_sha256':digest}}],
        'image_quality':{'pixel_sha256':digest},'pending_engines':['paddle_ocr'],'semantic_verified':False}
    r=validate_record(cross_validate(r));write_jsonl(run/'records.jsonl',[r]);write_json(run/'manifest.json',{'document':{'sha256':'a'*64,'pages':1},'asset_root':str(run)})
    return r

def packet(root,ids=('r1',)):
    root.mkdir(parents=True,exist_ok=True);Image.new('RGB',(100,100),'white').save(root/'image.png');digest=file_sha(root/'image.png')
    cfg={'model':'fake_only','prompt_sha256':sha(PROMPT),'max_new_tokens':512,'visual_tokens':512}
    requests=[{'id':i,'page':1,'kind':'diagram','bbox':[0,0,1000,1000],'source_sha256':'a'*64,'crop_sha256':digest,'vlm_image':'image.png','vlm_image_sha256':digest,'use_vlm':True} for i in ids]
    write_json(root/'manifest.json',{'document':{'sha256':'a'*64},'pilot_pages':[1],'requests':requests,'vlm_config':cfg,'parser_input_sha256':'b'*64,'page_map':{'1':1}})
    return cfg

class PlainVLMTests(unittest.TestCase):
    def test_one_call_accepts_partial_plain_text(self):
        class Fake:
            telemetry={}
            calls=0
            def infer(self,*args):self.calls+=1;return 'Hình có một cây; một số nhãn mờ, không đọc rõ.'
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);packet(root/'packet');model=Fake();result=run(root/'packet',root/'out',model=model)
            self.assertEqual(model.calls,1);self.assertEqual(result['observations'][0]['status'],'ok')
            self.assertTrue(result['observations'][0]['partial_observation']);self.assertFalse(result['observations'][0]['semantic_verified'])
    def test_success_cache_prevents_second_call(self):
        class Fake:
            telemetry={}
            calls=0
            def infer(self,*args):self.calls+=1;return 'Đồ thị nối hai đỉnh nhìn rõ.'
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);packet(root/'packet');model=Fake();run(root/'packet',root/'out',model=model);r=run(root/'packet',root/'out',model=model)
            self.assertEqual(model.calls,1);self.assertTrue(r['observations'][0]['cache_hit'])
    def test_failure_does_not_create_schema_retry_chain(self):
        class Fake:
            telemetry={}
            calls=0
            def infer(self,*args):self.calls+=1;raise RuntimeError('CUDA out of memory')
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);packet(root/'packet');model=Fake();result=run(root/'packet',root/'out',model=model)
            self.assertEqual(model.calls,1);self.assertEqual(result['observations'][0]['status'],'error');self.assertFalse(list((root/'out/vlm_cache').glob('*.json')))
    def test_failed_image_does_not_block_other_images(self):
        class Fake:
            telemetry={}
            calls=0
            def infer(self,*args):
                self.calls+=1
                if self.calls==1:raise RuntimeError('Image unreadable')
                return 'Ảnh thứ hai có sơ đồ.'
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);packet(root/'packet',('r1','r2'));model=Fake();r=run(root/'packet',root/'out',model=model)
            self.assertEqual([x['status'] for x in r['observations']],['error','ok']);self.assertEqual(model.calls,2)
    def test_bad_image_hash_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);packet(root/'packet');(root/'packet/image.png').write_bytes(b'changed')
            with self.assertRaises(ValueError):run(root/'packet',root/'out',model=object())
    def test_resize_limits_patch_count(self):
        for size in [(4000,3000),(40,40)]:
            im=fit_image(Image.new('RGB',size),512)
            self.assertLessEqual(im.width*im.height,512*28*28);self.assertEqual(im.width%28,0)

class ExportTests(unittest.TestCase):
    def test_machine_trusted_is_not_human_approval(self):
        with tempfile.TemporaryDirectory() as d:
            run=Path(d)/'run';r=fixture(run);r['pending_engines']=[]
            r['candidates'][0]['evidence'].update(region_id=r['id'],crop_sha256=r['crop_sha256'])
            r['candidates'].append({'engine':'paddle_ocr','text':r['native_text'],'status':'ok','evidence':{'lineage':'paddle','region_id':r['id'],'source_sha256':r['source_sha256'],'crop_sha256':r['crop_sha256']}})
            r=cross_validate(r);self.assertEqual(r['machine_bucket'],'trusted');write_jsonl(run/'records.jsonl',[r])
            report=export_cpt(run,Path(d)/'cpt');self.assertEqual(report['samples'],0);self.assertFalse(report['training_ready'])
    def test_human_approved_text_preserves_math_signs(self):
        with tempfile.TemporaryDirectory() as d:
            run=Path(d)/'run';r=fixture(run,kind='formula',text='x ≤ 2; O(n log n)')
            ReviewStore(run).submit('r1','Test human fixture','approve',r['proposed_text'],'Source checked in test',r['machine_revision'],True)
            report=export_cpt(run,Path(d)/'cpt');self.assertEqual(report['samples'],1)
            self.assertEqual(jsonl(Path(d)/'cpt/train.jsonl')[0]['text'],'x ≤ 2; O(n log n)')
    def test_approved_holdout_not_exported(self):
        with tempfile.TemporaryDirectory() as d:
            run=Path(d)/'run';r=fixture(run,split='holdout')
            ReviewStore(run).submit('r1','Test fixture','approve',r['proposed_text'],'Source checked',r['machine_revision'])
            self.assertEqual(export_cpt(run,Path(d)/'cpt')['samples'],0)
    def test_changed_approved_asset_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            run=Path(d)/'run';r=fixture(run);ReviewStore(run).submit('r1','Test fixture','approve',r['proposed_text'],'Checked',r['machine_revision'])
            (run/'slide.png').write_bytes(b'changed')
            with self.assertRaises(ValueError):export_cpt(run,Path(d)/'cpt')
    def test_stale_machine_revision_requires_new_human_review(self):
        with tempfile.TemporaryDirectory() as d:
            run=Path(d)/'run';r=fixture(run);ReviewStore(run).submit('r1','Test fixture','approve',r['proposed_text'],'Checked',r['machine_revision'])
            r['candidates'][0]['text']='Nội dung đã thay đổi';r=cross_validate(r);write_jsonl(run/'records.jsonl',[r])
            self.assertEqual(export_cpt(run,Path(d)/'cpt')['samples'],0)
    def test_changed_manifest_cannot_export_approved_source(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);r=fixture(root/'run');ReviewStore(root/'run').submit('r1','Test human','approve',r['proposed_text'],'Checked',r['machine_revision'])
            m=load(root/'run/manifest.json');m['document']['sha256']='c'*64;write_json(root/'run/manifest.json',m)
            with self.assertRaises(ValueError):export_cpt(root/'run',root/'cpt')

class AssociationTests(unittest.TestCase):
    def test_full_inventory_does_not_expand_vlm_budget_silently(self):
        r={'kind':'diagram','machine_bucket':'uncertain','legacy_routing_state':'score_review'}
        self.assertFalse(wants_vlm(r,'all'));self.assertTrue(wants_vlm(r,'pilot'));self.assertTrue(wants_vlm(r,'all',all_visuals=True))
        r['legacy_routing_state']='scheduled';self.assertTrue(wants_vlm(r,'all'))
        r['legacy_routing_state']='exact_duplicate';self.assertFalse(wants_vlm(r,'all'))
    def test_parser_formula_needs_same_region(self):
        r={'id':'a','page':1,'kind':'formula','bbox':[0,0,100,100],'source_sha256':'a'*64,'candidates':[]}
        c={'page':1,'kind':'formula','bbox':[800,800,900,900],'text':'x+y','engine':'mineru','status':'ok'}
        self.assertEqual(associate([r],[c])[0],0)
    def test_unknown_geometry_cannot_create_agreement(self):
        r={'id':'a','page':1,'kind':'formula','bbox':[0,0,100,100],'source_sha256':'a'*64,'candidates':[]}
        c={'page':1,'kind':'formula','bbox':None,'text':'x+y','engine':'mineru','status':'ok'}
        n,missing=associate([r],[c]);self.assertEqual(n,0);self.assertTrue(missing)
    def test_cloud_merge_preserves_observation_without_verifying_it(self):
        class Fake:
            telemetry={}
            def infer(self,*args):return 'Một cây minh họa; không cần liệt kê mọi trạng thái.'
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);r=fixture(root/'run',kind='diagram',text='');packet(root/'packet')
            # Use the same original crop in the synthetic packet.
            result=run(root/'packet',root/'cloud',model=Fake());archive=root/'returned.zip'
            with zipfile.ZipFile(archive,'w') as z:
                for p in (root/'cloud').glob('vlm_results_*.json'):z.write(p,p.name)
            ingest_cloud(root/'run',archive,root/'packet')
            updated=jsonl(root/'run/records.jsonl')[0]
            self.assertIn('Một cây',updated['proposed_text']);self.assertFalse(updated['semantic_verified'])
            self.assertEqual(updated['machine_bucket'],'uncertain');self.assertEqual(ReviewStore(root/'run').stats()['human_verified'],0)
    def test_stale_context_rejects_old_vlm_output(self):
        class Fake:
            telemetry={}
            def infer(self,*args):return 'Mô tả ảnh cũ.'
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);r=fixture(root/'run',kind='diagram',text='');packet(root/'packet');run(root/'packet',root/'cloud',model=Fake())
            Image.new('RGB',(100,100),'blue').save(root/'run/new_context.png')
            r.update(context_path='new_context.png',context_sha256=file_sha(root/'run/new_context.png'))
            write_jsonl(root/'run/records.jsonl',[cross_validate(r)])
            archive=root/'result.zip'
            with zipfile.ZipFile(archive,'w') as z:
                for p in (root/'cloud').glob('vlm_results_*.json'):z.write(p,p.name)
            with self.assertRaisesRegex(ValueError,'context'):ingest_cloud(root/'run',archive,root/'packet')
    def test_paddle_same_request_lines_aggregated_and_bound(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);r=fixture(root/'run',text='Dòng một.\nDòng hai.');packet(root/'packet')
            payload={'id':'r1','mode':'ocr','status':'ok','input_file_sha256':r['crop_sha256'],'candidates':[
                {'engine':'paddle_ocr','text':text,'status':'ok','evidence':{'source_sha256':r['source_sha256'],'region_id':'r1','reading_order':i}}
                for i,text in enumerate(['Dòng một.','Dòng hai.'])]}
            archive=root/'ocr.zip'
            with zipfile.ZipFile(archive,'w') as z:z.writestr('paddle/records/r1_ocr.json',json.dumps(payload))
            ingest_cloud(root/'run',archive,root/'packet');updated=jsonl(root/'run/records.jsonl')[0]
            ocr=[c for c in updated['candidates'] if c['engine']=='paddle_ocr']
            self.assertEqual(len(ocr),1);self.assertEqual(ocr[0]['text'],r['native_text']);self.assertEqual(updated['machine_bucket'],'trusted')
            self.assertEqual(ReviewStore(root/'run').stats()['human_verified'],0)
    def test_paddle_wrong_crop_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);fixture(root/'run');packet(root/'packet');archive=root/'ocr.zip'
            with zipfile.ZipFile(archive,'w') as z:z.writestr('paddle/records/r1_ocr.json',json.dumps({'id':'r1','mode':'ocr','status':'ok','input_file_sha256':'f'*64,'candidates':[]}))
            with self.assertRaisesRegex(ValueError,'crop'):ingest_cloud(root/'run',archive,root/'packet')

if __name__=='__main__':unittest.main()
