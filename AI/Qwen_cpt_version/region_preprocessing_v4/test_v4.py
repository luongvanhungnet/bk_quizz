import copy
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from PIL import Image
from schema import SCHEMAS,EXAMPLES,ATTR_EXAMPLE,parse,validate,validate_task
from prompts import prompt
from contracts import canonical,load,write_once,task_identity
from geometry import fit_image,local_box,parent_box,endpoint_consistent
from worker import run_task,assemble,valid_cached,collect,run

ROOT=Path(__file__).resolve().parent
V3=ROOT.parent/'region_preprocessing_v3'

class SchemaTests(unittest.TestCase):
    def test_all_examples_match_same_schema(self):
        for stage,p in EXAMPLES.items():self.assertEqual(validate(p,SCHEMAS[stage]),[],stage)
    def test_generated_prompt_contains_exact_contract(self):
        for stage in SCHEMAS:
            text=prompt(stage,{})
            self.assertIn(json.dumps(SCHEMAS[stage],ensure_ascii=False,separators=(',',':')),text)
            self.assertIn(json.dumps(EXAMPLES[stage],ensure_ascii=False,separators=(',',':')),text)
    def test_tree_example_is_nonempty_and_correct(self):
        self.assertEqual(set(EXAMPLES['tree_links']['relations'][0]),{'parent','child','bbox'})
    def test_historical_tree_relation_shape_is_rejected(self):
        p={'relations':[{'parent_bbox':[1,1,2,2],'child_bbox':[3,3,4,4]}],'complete':True,'uncertain':[]}
        self.assertTrue(validate(p,SCHEMAS['tree_links']))
    def test_tree_references_are_checked(self):
        self.assertIn('relation_identity',validate_task('tree_links',EXAMPLES['tree_links'],{'boards':[{'id':'b1'}]}))
    def test_duplicate_keys_rejected(self):
        with self.assertRaises(ValueError):parse('{"node_ids":[],"node_ids":[]}', 'inventory')
    def test_nan_rejected(self):
        with self.assertRaises(ValueError):parse('{"x":NaN}', 'nodes')
    def test_incomplete_markdown_rejected(self):
        with self.assertRaises(ValueError):parse('```json\n{}','nodes')
    def test_only_single_object_array_is_repaired(self):
        p,repairs,errors=parse(json.dumps([EXAMPLES['inventory']]),'inventory')
        self.assertEqual(errors,[]);self.assertIn('unwrap_singleton_object_array',repairs)
        self.assertTrue(parse('[{},{}]','inventory')[2])
    def test_null_quote_repair_does_not_create_facts(self):
        p=copy.deepcopy(EXAMPLES['edge_attributes']);p['attributes'][0]['native_quote']=None
        q,repairs,errors=parse(json.dumps(p),'edge_attributes')
        self.assertFalse(errors);self.assertEqual(q['attributes'][0]['native_quote'],'')
        self.assertIsNone(q['attributes'][0]['weight']);self.assertTrue(repairs)
    def test_no_relation_or_vertex_invention_during_parse(self):
        q,_,errors=parse('{"relations":[],"complete":false,"uncertain":[]}', 'tree_links')
        self.assertFalse(errors);self.assertEqual(q['relations'],[])
    def test_unknown_inventory_id_rejected(self):
        errors=validate_task('inventory',EXAMPLES['inventory'],{'nodes':[],'edges':[]})
        self.assertTrue(errors)
    def test_dangling_fallback_edge_rejected(self):
        self.assertIn('dangling_edge',validate_task('edges',EXAMPLES['edges'],{'nodes':[{'id':'n1'}]}))
    def test_missing_attribute_rejected(self):
        self.assertIn('attribute_inventory',validate_task('edge_attributes',{'attributes':[],'uncertain':[]},{'edges':[{'id':'e1'}]}))
    def test_arrow_endpoint_rejected(self):
        p=copy.deepcopy(EXAMPLES['edge_attributes']);a=p['attributes'][0];a.update(directed=True,arrow_target='wrong')
        self.assertIn('arrow_not_endpoint',validate_task('edge_attributes',p,{'edges':[{'id':'e1','source':'n1','target':'n2'}]}))
    def test_board_queen_removed_overlap(self):
        p=copy.deepcopy(EXAMPLES['board']);p['removed_cells']=p['queens']
        self.assertIn('queen_removed_overlap',validate_task('board',p,{'id':'b1','board_size':4}))
    def test_board_out_of_range(self):
        p=copy.deepcopy(EXAMPLES['board']);p['queens']=[[4,0]]
        self.assertTrue(validate_task('board',p,{'id':'b1','board_size':4}))
    def test_bool_not_number_in_bbox(self):
        p=copy.deepcopy(EXAMPLES['nodes']);p['nodes'][0]['bbox']=[False,0,1,1]
        self.assertTrue(validate(p,SCHEMAS['nodes']))
    def test_bad_box_not_accepted(self):
        p=copy.deepcopy(EXAMPLES['nodes']);p['nodes'][0]['bbox']=[100,0,10,20]
        self.assertTrue(validate(p,SCHEMAS['nodes']))

class GeometryTests(unittest.TestCase):
    def test_resize_budget_and_grid(self):
        for size in [(4000,3000),(50,50),(5000,40)]:
            for cap in [256,384]:
                im=fit_image(Image.new('RGB',size),cap)
                self.assertLessEqual(im.width*im.height,cap*28*28)
                self.assertEqual(im.width%28,0);self.assertEqual(im.height%28,0)
    def test_coordinate_roundtrip(self):
        b=[200,300,400,500];clip=[100,200,800,900]
        for a,c in zip(parent_box(local_box(b,clip),clip),b):self.assertAlmostEqual(a,c,2)
    def test_tiny_board_has_enough_visual_patches(self):
        im=fit_image(Image.new('RGB',(50,50)),384)
        self.assertGreaterEqual(im.width,224);self.assertGreaterEqual(im.height,224)
    def test_endpoint_mismatch(self):
        nodes={'a':{'bbox':[0,0,20,20]},'b':{'bbox':[900,900,950,950]}}
        self.assertFalse(endpoint_consistent({'source':'a','target':'b','bbox':[0,0,100,100]},nodes))

class RuntimeTests(unittest.TestCase):
    def setup_task(self,root):
        write_once(root/'payload.json',{'nodes':[{'id':'n1'},{'id':'n2'}],'edges':[{'id':'e1','source':'n1','target':'n2'}]})
        return {'id':'task','parent_id':'parent','stage':'inventory','image':'source.png','context':'payload.json','input_file_sha256':'pixel','context_sha256':'context','cache_key':'key','max_new_tokens':100}
    def test_oom_retry_uses_lower_visual_cap(self):
        class Fake:
            telemetry={}
            def __init__(self):self.caps=[]
            def infer(self,image,text,profile,limit):
                self.caps.append(profile['visual_tokens'])
                if len(self.caps)==1:raise RuntimeError('CUDA out of memory')
                return json.dumps(EXAMPLES['inventory']),False
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);t=self.setup_task(root);model=Fake()
            r=run_task(root,root/'out',t,{'max_attempts_per_task':2,'visual_tokens':384,'retry_visual_tokens':256},model,'attempt')
            self.assertEqual(model.caps,[384,256]);self.assertEqual(r['status'],'ok');self.assertFalse(r['semantic_verified'])
            self.assertTrue(r['reduced_resolution_retry']);self.assertEqual(len(r['attempts']),2)
    def test_invalid_output_is_not_success_cache(self):
        class Fake:
            telemetry={}
            def infer(self,*args):return '{}',False
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);t=self.setup_task(root)
            r=run_task(root,root/'out',t,{'max_attempts_per_task':2,'visual_tokens':384,'retry_visual_tokens':256},Fake(),'a')
            self.assertEqual(r['status'],'error');self.assertFalse(list((root/'out/cache').glob('*.json')))
    def test_valid_cache_skips_model(self):
        class Fake:
            telemetry={}
            def infer(self,*args):return json.dumps(EXAMPLES['inventory']),False
        class Never:
            def infer(self,*args):raise AssertionError('Model must not run')
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);t=self.setup_task(root);cfg={'max_attempts_per_task':2,'visual_tokens':384,'retry_visual_tokens':256}
            run_task(root,root/'out',t,cfg,Fake(),'a');r=run_task(root,root/'out',t,cfg,Never(),'b')
            self.assertTrue(r['cache_hit']);self.assertFalse(r['semantic_verified'])
    def test_truncated_response_is_not_cached(self):
        class Fake:
            telemetry={}
            def infer(self,*args):return json.dumps(EXAMPLES['inventory']),True
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);t=self.setup_task(root)
            r=run_task(root,root/'out',t,{'max_attempts_per_task':1,'visual_tokens':384,'retry_visual_tokens':256},Fake(),'a')
            self.assertEqual(r['status'],'error')
    def test_changed_upstream_changes_cache_eligibility(self):
        t={'cache_key':'key','stage':'inventory'}
        r={'cache_key':'key','status':'ok','upstream_key':'old','semantic_verified':False,'prediction':EXAMPLES['inventory']}
        self.assertFalse(valid_cached(r,t,{},'new'))
    def test_transform_part_of_task_identity(self):
        t={'parent_id':'a','stage':'board','input_file_sha256':'x','context_sha256':'y','max_new_tokens':200,'source_bbox':[0,0,10,10]}
        self.assertNotEqual(task_identity(t,{}),task_identity({**t,'source_bbox':[0,0,20,20]},{}))
    def test_audit_overwrite_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'record.json';write_once(p,{'raw':'old'})
            with self.assertRaises(ValueError):write_once(p,{'raw':'new'})
    def test_pending_annotation_is_not_gold(self):
        from annotations import validate_benchmark
        q={'page':1,'document_sha256':'x','render_sha256':'y','group_id':'g','split':'development','annotation_status':'pending','gold':None}
        with self.assertRaises(ValueError):validate_benchmark([q],[q])
    def test_empty_gold_is_not_scored(self):
        from annotations import validate_benchmark
        with self.assertRaises(ValueError):validate_benchmark([],[])
    def test_cpt_export_rejects_holdout(self):
        from annotations import export_reviews
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);write_once(root/'manifest.json',{'document':{'sha256':'x'}})
            write_once(root/'benchmark_groups.json',{'protected_holdout_pages':[1]})
            (root/'carried_cpt_archive').mkdir();(root/'carried_cpt_archive/train.metadata.jsonl').write_text('',encoding='utf-8')
            with self.assertRaises(ValueError):export_reviews(root,[{'page':1}],root/'dataset')
    def test_full_run_requires_pilot(self):
        from unittest.mock import patch
        with patch('worker.collect',return_value={'records':[{'engine':'vlm','source':{'page':930},'status':'error'}]}):
            with self.assertRaises(RuntimeError):run(Path('.'),Path('.'),{'pilot_pages':[930]},'all')

class RealSourceRegression(unittest.TestCase):
    def test_v3_raw_failures_are_preserved_as_regressions(self):
        archive=V3/'result/region_v3_results_aa4973c0f29f_1792386371941271361.zip'
        with zipfile.ZipFile(archive) as z:
            for tree in ['tree1','tree2']:
                r=json.loads(z.read('stages/p0129_r00070_'+tree+'_state_tree.json'))
                self.assertIn('relation_fields',r['structural_errors'])
                self.assertIn('parent_bbox',r['prediction']['relations'][0])
            for page,rid in [(930,'p0930_r01239'),(1042,'p1042_r01351')]:
                r=json.loads(z.read('stages/'+rid+'_nodes.json'));self.assertEqual(r['error_type'],'OutOfMemoryError')
    def test_native_shapes_exclude_page812_captions(self):
        root=V3/'runs/it3170_v3_20261019';m=load(root/'manifest.json');q=next(r for r in m['requests'] if r['engine']=='vlm' and r['page']==812)
        nodes=load(root/q['context'])['native_graph_candidates']['nodes']
        self.assertEqual({n['label'] for n in nodes},{'0','1'})
    def test_native_candidates_preserve_missing_v3_edge(self):
        root=V3/'runs/it3170_v3_20261019';m=load(root/'manifest.json');q=next(r for r in m['requests'] if r['engine']=='vlm' and r['page']==494)
        graph=load(root/q['context'])['native_graph_candidates'];labels={n['id']:n['label'] for n in graph['nodes']}
        pairs={tuple(sorted([labels[e['source']],labels[e['target']]])) for e in graph['edges']}
        self.assertIn(('b','e'),pairs);self.assertEqual(len(pairs),11)

if __name__=='__main__':unittest.main()
