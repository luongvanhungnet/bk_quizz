import copy
from pathlib import Path
import tempfile
import unittest
import zipfile
import json
from test_production import make_pdf
from io_utils import load,jsonl,file_sha
from corpus import inventory,plan,prepare_documents,package_job,merge_job,check_source
from batch_layout import route

def settings(root):
    (root/'docs').mkdir()
    return {'source_root':str(root/'docs'),'work_root':str(root/'work'),'upstream_manifest':str(root/'missing.json'),
        'upstream_page_map':str(root/'missing_map.json'),'reuse_runs':[],'pages_per_packet':2,'maximum_packet_bytes':50_000_000,
        'vlm_target_fraction':.05,'vlm_maximum_fraction':.08,'sample_pdf_pages':True,'course_splits':{}}

class CorpusTests(unittest.TestCase):
    def test_inventory_deduplicates_sources_and_plan_covers_pages_once(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);cfg=settings(root);make_pdf(root/'docs/A-one.pdf',pages=3)
            (root/'docs/B-copy.pdf').write_bytes((root/'docs/A-one.pdf').read_bytes())
            rows=inventory(cfg,root/'catalog');self.assertEqual([r['status'] for r in rows],['ready','exact_duplicate_source'])
            jobs=plan(cfg,root/'catalog',root/'plan')
            self.assertEqual([(j['first_page'],j['last_page']) for j in jobs],[(1,2),(3,3)])
    def test_new_document_requires_layout_before_inference(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);cfg=settings(root);make_pdf(root/'docs/A-one.pdf')
            inventory(cfg,root/'catalog');jobs=plan(cfg,root/'catalog',root/'plan');prepare_documents(cfg,jobs)
            with self.assertRaisesRegex(ValueError,'discovery'):package_job(cfg,jobs[0],'inference')
            path=package_job(cfg,jobs[0],'discovery');m=load(path.parent/'manifest.json')
            self.assertFalse(any(q['use_vlm'] for q in m['requests']));self.assertEqual(m['page_map'],{'1':1,'2':2})
    def test_layout_materialization_creates_table_without_verification(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);cfg=settings(root);make_pdf(root/'docs/A-one.pdf')
            inventory(cfg,root/'catalog');jobs=plan(cfg,root/'catalog',root/'plan');prepare_documents(cfg,jobs)
            packet=package_job(cfg,jobs[0],'discovery').parent;pm=load(packet/'manifest.json')
            raw={'status':'ok','engine':'docling','original_source_sha256':pm['document']['sha256'],
                'packet_manifest_sha256':file_sha(packet/'manifest.json'),'parser_input_sha256':pm['parser_input_sha256'],
                'parser_candidates':[{'page':1,'kind':'table','bbox':[100,100,500,600],'text':'<table><tr><td>x</td></tr></table>',
                    'status':'ok','engine':'docling','evidence':{'backend_family':'docling_native_layout'}}]}
            results=root/'results.zip'
            with zipfile.ZipFile(results,'w') as z:z.writestr('parser_candidates_docling.json',json.dumps(raw))
            summary=merge_job(cfg,jobs[0],packet,results)
            rows=jsonl(Path(jobs[0]['run'])/'records.jsonl');tables=[r for r in rows if r['kind']=='table']
            self.assertEqual(len(tables),1);self.assertFalse(tables[0]['semantic_verified'])
            self.assertIn('paddle_table',tables[0]['pending_engines']);self.assertEqual(summary['layout']['layout_inventory_status'],'ready')
            production=package_job(cfg,jobs[0],'inference')
            m=load(production.parent/'manifest.json');self.assertTrue(any(q['kind']=='table' for q in m['requests']))
    def test_changed_source_requires_new_plan(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);cfg=settings(root);make_pdf(root/'docs/A-one.pdf');inventory(cfg,root/'catalog')
            job=plan(cfg,root/'catalog',root/'plan')[0];Path(job['source_path']).write_bytes(b'changed')
            with self.assertRaises(ValueError):check_source(job)
    def test_paddle_structure_uses_original_page_not_subset_index(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);cfg=settings(root);cfg['pages_per_packet']=1;make_pdf(root/'docs/A-one.pdf')
            inventory(cfg,root/'catalog');jobs=plan(cfg,root/'catalog',root/'plan');prepare_documents(cfg,jobs)
            job=jobs[1];packet=package_job(cfg,job,'discovery').parent;pm=load(packet/'manifest.json')
            q=next(q for q in pm['requests'] if q['is_full_page'])
            record={'id':q['id'],'mode':'structure','status':'ok','input_file_sha256':q['crop_sha256'],'candidates':[
                {'page':2,'kind':'formula','bbox':[100,100,500,600],'text':'x=2','engine':'paddle_structure','status':'ok',
                    'evidence':{'region_id':q['id'],'source_sha256':pm['document']['sha256']}}]}
            returned=root/'structure.zip'
            with zipfile.ZipFile(returned,'w') as z:z.writestr('paddle_structure/records/page2_structure.json',json.dumps(record))
            result=merge_job(cfg,job,packet,returned)
            formulas=[r for r in jsonl(Path(job['run'])/'records.jsonl') if r['kind']=='formula']
            self.assertEqual(len(formulas),1);self.assertEqual(formulas[0]['page'],2)
            self.assertEqual(result['layout']['layout_inventory_status'],'partial_layout')
    def test_routing_budget_defers_without_deleting_knowledge(self):
        rows=[]
        for i in range(20):
            rows.append({'id':str(i),'page':i+1,'kind':'diagram','bbox':[100,100,800,800],'native_text':'graph',
                'pending_engines':[],'image_quality':{'pixel_sha256':str(i)}})
        summary=route(rows,100)
        self.assertEqual(len(summary['scheduled_pages']),5);self.assertEqual(len(summary['deferred_pages']),15)
        self.assertEqual(len(rows),20);self.assertTrue(all('routing' in r for r in rows))
    def test_identical_margin_logo_is_filtered_but_retained(self):
        rows=[{'id':str(i),'page':i+1,'kind':'image','bbox':[10,10,100,100],'native_text':'',
            'pending_engines':[],'image_quality':{'pixel_sha256':'same'}} for i in range(3)]
        summary=route(rows,100)
        self.assertEqual(summary['scheduled_pages'],[]);self.assertEqual(len(rows),3)
        self.assertTrue(all(r['routing']['features']['B'] for r in rows))

if __name__=='__main__':unittest.main()
