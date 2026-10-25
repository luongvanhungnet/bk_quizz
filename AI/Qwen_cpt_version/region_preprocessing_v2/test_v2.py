import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from validation import validate_prediction,parse_json_output,cache_is_valid,semantic_warnings
from revalidate import migrate_vlm
from formula_routing import classify_formula,table_geometry
from semantic_eval import score


def graph():return {'image_type':'graph','nodes':[],'edges':[],'observed_facts':[],'uncertain':[]}


class SchemaTests(unittest.TestCase):
    def test_all_prompt_enums_match_validator(self):
        for kind in ['graph','diagram','chart','illustration','unknown']:
            self.assertEqual(validate_prediction('vlm',{**graph(),'image_type':kind}),[])

    def test_prompt_example_is_valid_and_has_no_pipe_enum(self):
        prompt=Path(__file__).with_name('prompt.txt').read_text()
        example=next(l for l in prompt.splitlines() if l.startswith('{'))
        self.assertEqual(validate_prediction('vlm',json.loads(example)),[])
        self.assertNotIn('|',example)

    def test_migration_is_explicit_unknown_and_never_verified(self):
        pred={**graph(),'image_type':'diagram|graph'}
        r={'id':'x','status':'invalid_structure','cache_key':'old','raw_content':json.dumps(pred)}
        before=copy.deepcopy(r);new=migrate_vlm(r)
        self.assertEqual(r,before);self.assertEqual(new['prediction']['image_type'],'unknown')
        self.assertFalse(new['semantic_verified']);self.assertEqual(new['destination'],'review_queue')
        self.assertEqual(new['schema_status'],'ok')

    def test_migration_does_not_fix_dangling_edges(self):
        pred={**graph(),'image_type':'diagram|graph','edges':[{'source':'A','target':'B','directed':True,'weight':None,'highlighted':None}]}
        r=migrate_vlm({'id':'x','status':'invalid_structure','cache_key':'old','raw_content':json.dumps(pred)})
        self.assertIn('dangling_edge_reference',r['errors'])

    def test_bad_json_never_repaired_by_inventing_content(self):
        self.assertEqual(migrate_vlm({'id':'x','status':'invalid_json','cache_key':'old','raw_content':'{"nodes":['})['schema_status'],'invalid_json')

    def test_weight_bool_rejected(self):
        pred=graph();pred['nodes']=[{'id':'a','label':'A'}]
        pred['edges']=[{'source':'a','target':'a','weight':True,'directed':False,'highlighted':False}]
        self.assertIn('invalid_weight',validate_prediction('vlm',pred))

    def test_empty_graph_is_schema_valid_but_incomplete(self):
        self.assertEqual(validate_prediction('vlm',graph()),[])
        self.assertIn('diagram_nodes_missing',semantic_warnings(graph()))

    def test_formula_repetition_and_corruption_rejected(self):
        for text,flag in [('\\, '*150,'repetitive_latex_tokens'),('a\ufffd=b','corrupt_latex_characters'),('\\begin{array}a=b','unbalanced_latex_environments')]:
            self.assertIn(flag,validate_prediction('formula',{'latex':text}))

    def test_formula_symbols_and_valid_environments_preserved(self):
        for text in [r'2\times10^{18}',r'\begin{array}x\end{array}\begin{aligned}a=b\end{aligned}',r'\sum_{i=1}^{n}i=\frac{n(n+1)}{2}']:
            self.assertEqual(validate_prediction('formula',{'latex':text}),[])


class RoutingTests(unittest.TestCase):
    def page(self,text,spans=None):
        return {'render_width':1000,'page_size_pt':[1000,800],'blocks':[{'type':'text','lines':[{'text':text,'bbox':[10,10,600,60],'spans':spans or []}]}]}

    def test_paragraph_not_sent_as_formula(self):
        p=self.page('Sử dụng phương pháp phân tích thuật toán để xác định lời giải')
        result=classify_formula({'bbox_pixels':[0,0,650,80]},p,[])
        self.assertEqual(result['decision'],'native_review');self.assertFalse(result['formula_boxes'])

    def test_table_overlap_prevents_formula_route(self):
        result=classify_formula({'bbox_pixels':[10,10,200,100]},self.page('x=2'),[{'id':'t','bbox_pixels':[0,0,300,200]}])
        self.assertEqual(result['decision'],'table_existing')

    def test_mixed_text_keeps_native_and_crops_math_only(self):
        spans=[{'text':'Khi sử dụng các giá trị ','bbox':[10,10,250,40]},
               {'text':'10','bbox':[260,10,280,40],'math_font':True},
               {'text':'18','bbox':[280,5,300,20],'superscript':True}]
        p=self.page('Khi sử dụng các giá trị 10^{18}',spans)
        result=classify_formula({'bbox_pixels':[0,0,650,80]},p,[])
        self.assertEqual(result['decision'],'formula_crops');self.assertTrue(result['native_text_preserved'])
        self.assertGreaterEqual(result['formula_boxes'][0][0],260)
        self.assertEqual(result['formula_boxes'][0][1],5)

    def test_table_geometry(self):
        lines=[{'bbox':[x,y,x+30,y+10]} for x in [10,100,200] for y in [10,40,70]]
        self.assertTrue(table_geometry(lines))

    def test_weight_and_direction_errors_are_measured(self):
        pred={'nodes':[{'id':'x','label':'a'},{'id':'y','label':'b'}],
              'edges':[{'source':'x','target':'y','directed':None,'weight':9,'highlighted':None}]}
        result=score(pred,{'nodes':['a','b'],'edges':[{'source':'a','target':'b','directed':True,'weight':15,'highlighted':False}]})
        self.assertEqual(result['topology']['correct'],1)
        self.assertEqual(result['weights']['correct'],0);self.assertEqual(result['directions']['correct'],0)


class WorkerTests(unittest.TestCase):
    def test_small_bbox_overhang_is_clipped_without_mutation(self):
        from table_adapter import clip_native_boxes
        original=[[-1,10,99,30]]
        self.assertEqual(clip_native_boxes(original,100,100).tolist(),[[0,10,99,30]])
        self.assertEqual(original,[[-1,10,99,30]])

    def test_large_bbox_overhang_requires_review(self):
        from table_adapter import clip_native_boxes
        with self.assertRaisesRegex(ValueError,'review required'):clip_native_boxes([[-50,10,50,30]],100,100)

    def test_nonfinite_bbox_rejected(self):
        from table_adapter import clip_native_boxes
        with self.assertRaises(ValueError):clip_native_boxes([[0,0,float('nan'),30]],100,100)

    def test_batch_table_gate_runs_before_paddle_import(self):
        import worker
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as d,patch.object(worker,'pending',return_value=({'requests':[{'id':'t','engine':'table'}]},[{'engine':'table'}])):
            with self.assertRaisesRegex(RuntimeError,'table-canary'):worker.paddle_stage(Path(d),Path(d))

    def test_finish_schema_success_does_not_verify(self):
        import worker
        with tempfile.TemporaryDirectory() as d:
            q={'id':'q','engine':'vlm','cache_key':'k','raw_pixel_sha256':'p'}
            worker.finish(Path(d),q,{'status':'ok','prediction':graph(),'semantic_verified':True})
            r=json.loads((Path(d)/'records/q.json').read_text())
            self.assertFalse(r['semantic_verified'])

    def test_cache_rejects_model_change(self):
        r={'engine':'vlm','cache_key':'old-model','status':'ok','prediction':graph()}
        self.assertFalse(cache_is_valid(r,{'engine':'vlm','cache_key':'new-model'}))


class SourceRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import zipfile
        cls.root=Path(__file__).resolve().parent
        with zipfile.ZipFile(cls.root.parent/'region_preprocessing/model/region_results_33f6b7b75d29.zip') as z:
            cls.records=json.loads(z.read('results.json'))['records']
        cls.gold=json.loads((cls.root/'gold_cases.json').read_text(encoding='utf-8'))

    def test_revalidate_all_55_parsed_outputs_without_inference(self):
        rows=[migrate_vlm(r) for r in self.records if r['engine']=='vlm']
        self.assertEqual(sum(r['schema_status']=='ok' for r in rows),46)
        self.assertEqual(sum(r['schema_status']=='invalid_structure' for r in rows),9)
        self.assertFalse(any(r['semantic_verified'] for r in rows))

    def metric(self,page):
        old=next(r for r in self.records if r['engine']=='vlm' and int(r['id'][1:5])==page)
        return score(old['prediction'],next(g for g in self.gold if g['page']==page))

    def test_page_494_missing_edges_and_wrong_weight_remain_visible(self):
        r=self.metric(494)
        self.assertEqual(r['topology']['correct'],9);self.assertEqual(r['topology']['gold'],11)
        self.assertEqual(r['weights']['correct'],8)

    def test_page_812_annotation_is_not_an_extra_vertex(self):
        r=self.metric(812)
        self.assertEqual(r['node_labels']['predicted'],3);self.assertEqual(r['node_labels']['gold'],2)
        self.assertEqual(r['topology']['correct'],0)

    def test_page_930_null_direction_is_not_correct_arrow(self):
        r=self.metric(930)
        self.assertEqual(r['directions'],{'correct':0,'gold':11})

    def test_page_1042_duplicates_do_not_count_as_complete_labels(self):
        r=self.metric(1042)
        self.assertEqual(r['duplicate_visible_labels'],2);self.assertEqual(r['node_labels']['correct'],7)

    def test_page_129_is_not_scored_by_an_invented_state_tree(self):
        g=next(g for g in self.gold if g['page']==129)
        self.assertTrue(g['manual_only']);self.assertTrue(g['rubric'])


if __name__=='__main__':unittest.main()
