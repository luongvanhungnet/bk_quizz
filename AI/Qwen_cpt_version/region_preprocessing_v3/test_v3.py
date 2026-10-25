import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from validation import validate_stage,validate_prediction,bbox
from quality import assess,delimiter_warnings
from worker import compose_graph,finish,stage
from benchmark import make_benchmark
from contracts import write_once,identity


def attrs():return {'edge_id':'e','directed':None,'weight':None,'highlighted':None,'arrow_target':None,
    'arrow_bbox':None,'weight_bbox':None,'highlight_bbox':None,'reference_bbox':None,'direction_basis':'unknown','native_quote':''}
def graph():
    return {'image_type':'graph','nodes':[{'id':'a','label':'a','bbox':[50,50,100,100]},
        {'id':'b','label':'b','bbox':[800,800,850,850]}],
        'edges':[{'id':'e','source':'a','target':'b','bbox':[50,50,850,850],'attributes':attrs()}],'uncertain':[]}


class SchemaTests(unittest.TestCase):
    def test_duplicate_json_keys_rejected(self):
        from validation import parse_json_output
        with self.assertRaisesRegex(ValueError,'Duplicate JSON key'):parse_json_output('{"directed":true,"directed":false}')
    def test_prompt_examples_match_stage_schema(self):
        from prompts import PROMPTS
        for name,text in PROMPTS.items():
            example=next(l.split('Example: ',1)[1] for l in text.splitlines() if l.startswith('Example: '))
            self.assertEqual(validate_stage(name,json.loads(example)),[],name)
            self.assertNotIn('|',example)

    def test_bbox_rejects_bool_nan_and_wrong_frame(self):
        for value in [[False,0,100,100],[0,0,float('nan'),100],[0,0,1001,100],[20,20,10,10],None]:self.assertFalse(bbox(value))

    def test_graph_references_and_attribute_inventory(self):
        p=graph();self.assertEqual(validate_prediction('vlm',p),[])
        p['edges'][0]['target']='missing';self.assertIn('dangling_edge_reference',validate_prediction('vlm',p))

    def test_malformed_nodes_does_not_crash(self):
        p=graph();p['nodes']=42;self.assertTrue(validate_prediction('vlm',p))

    def test_state_tree_cannot_use_caption_labels(self):
        p={'states':[{'id':'s','label':'State 1','bbox':[1,1,30,30]}],'relations':[],'uncertain':[]}
        self.assertIn('state_fields',validate_stage('state_tree',p))

    def test_state_cell_coordinates_and_overlap(self):
        p={'states':[{'id':'s','bbox':[1,1,30,30],'board_size':4,'queens':[[0,0]],'removed_cells':[[0,0]]}],'relations':[],'uncertain':[]}
        self.assertIn('queen_removed_overlap',validate_stage('state_tree',p))

    def test_chart_numeric_values_require_local_bbox(self):
        p={'axes':[],'series':[{'name':'a','points':[{'x':1,'y':2,'bbox':None}]}],'uncertain':[]}
        self.assertIn('point_bbox',validate_stage('chart',p))


class EvidenceQualityTests(unittest.TestCase):
    def test_native_label_and_weight_disagreement(self):
        p=graph();p['edges'][0]['attributes']['weight']=9
        native={'nodes':[{'id':'v1','label':'wrong','bbox':p['nodes'][0]['bbox']},
                         {'id':'v2','label':'b','bbox':p['nodes'][1]['bbox']}],
                'edges':[{'source':'v1','target':'v2','weight_candidates':[{'text':'15'}]}]}
        q=assess('vlm',p,{'native_graph_candidates':native})
        self.assertIn('native_node_label_disagreement',q['flags']);self.assertIn('native_connection_missing_from_prediction',q['flags'])

    def test_legitimate_all_directed_with_evidence_not_flagged_by_pattern(self):
        p=graph();p['edges'][0]['attributes'].update(directed=True,arrow_target='b',direction_basis='arrowhead',arrow_bbox=[805,805,815,815])
        flags=assess('vlm',p,{})['flags']
        self.assertNotIn('all_edges_directed_without_complete_arrow_evidence',flags)

    def test_cache_only_lazy_model_does_not_load_qwen(self):
        from worker import LazyQwen
        with patch('worker.Qwen') as model:
            lazy=LazyQwen({});self.assertIsNone(lazy.loaded);model.assert_not_called()
    def test_true_without_arrow_is_flagged(self):
        p=graph();p['edges'][0]['attributes']['directed']=True
        self.assertIn('directed_without_arrow_evidence',assess('vlm',p,{})['flags'])

    def test_unknown_is_not_silently_false(self):
        p=graph();before=copy.deepcopy(p);q=assess('vlm',p,{})
        self.assertEqual(p,before);self.assertIn('direction_unresolved',q['flags']);self.assertFalse(q['semantic_verified'])

    def test_false_needs_actual_native_caption(self):
        p=graph();p['edges'][0]['attributes'].update(directed=False,direction_basis='explicit_undirected_caption',native_quote='đồ thị vô hướng')
        self.assertIn('undirected_without_native_caption_evidence',assess('vlm',p,{'native_text':'đồ thị có hướng'})['flags'])
        self.assertNotIn('undirected_without_native_caption_evidence',assess('vlm',p,{'native_text':'Đây là đồ thị vô hướng.'})['flags'])

    def test_arrow_evidence_must_be_near_target(self):
        p=graph();p['edges'][0]['attributes'].update(directed=True,direction_basis='arrowhead',arrow_target='b',arrow_bbox=[55,55,65,65])
        self.assertIn('arrow_not_near_target',assess('vlm',p,{})['flags'])

    def test_highlight_needs_different_reference(self):
        p=graph();p['edges'][0]['attributes'].update(highlighted=True,highlight_bbox=[100,100,200,200],reference_bbox=[100,100,200,200])
        self.assertIn('highlight_reference_equals_subject',assess('vlm',p,{})['flags'])

    def test_reciprocal_duplicate_and_inconsistent_weight(self):
        p=graph();other=copy.deepcopy(p['edges'][0]);other.update(id='e2',source='b',target='a');other['attributes'].update(edge_id='e2',weight=9)
        p['edges'].append(other);flags=assess('vlm',p,{})['flags']
        self.assertIn('reciprocal_edges_require_source_check',flags);self.assertIn('contradictory_weights_same_pair',flags)

    def test_orientation_changes_are_explicit_and_audited(self):
        p=graph();a=attrs();a.update(directed=True,arrow_target='a',direction_basis='arrowhead',arrow_bbox=[55,55,65,65])
        result,changes=compose_graph({'nodes':p['nodes'],'uncertain':[]},{'edges':[{k:v for k,v in p['edges'][0].items() if k!='attributes'}],'uncertain':[]},
            {'attributes':[a],'uncertain':[]},'graph')
        self.assertEqual(result['edges'][0]['target'],'a');self.assertEqual(changes[0]['before'],['a','b'])
        self.assertEqual(p['edges'][0]['target'],'b')

    def test_formula_fragment_and_superscript_punctuation(self):
        self.assertIn('relation_fragment_requires_native_context',assess('formula',{'latex':'<x'},{'native_text':'x'})['flags'])
        self.assertIn('possible_punctuation_as_superscript',assess('formula',{'latex':r'O(n)^{\cdot}'},{'native_text':'x'})['flags'])

    def test_intervals_and_exponents_not_deleted(self):
        for value in [r'[0,1)',r'(a,b]',r'2\times10^{18}']:
            self.assertEqual(delimiter_warnings(value),[])
        self.assertTrue(delimiter_warnings('n<=30)'))

    def test_table_missing_negative_number_is_detected(self):
        p={'html':'<table><tr><td>128</td></tr></table>'}
        q=assess('table',p,{'native_ocr':[{'text':'-128'}]})
        self.assertIn('table_numeric_inventory_mismatch',q['flags'])

    def test_table_rowspan_and_cell_text(self):
        p={'html':'<table><tr><td rowspan="2">a</td><td>1</td></tr><tr><td>2</td></tr></table>'}
        q=assess('table',p,{'native_ocr':[{'text':'a'},{'text':'1'},{'text':'2'}]})
        self.assertEqual(q['metrics']['column_counts'],[2,2]);self.assertEqual(q['metrics']['native_token_coverage'],1)

    def test_state_tree_cycle_flag(self):
        p={'image_type':'state_tree','states':[{'id':str(i),'bbox':[1,1,30,30],'board_size':4,'queens':[],'removed_cells':[]} for i in [1,2]],
           'relations':[{'parent':'1','child':'2','bbox':[1,1,30,30]},{'parent':'2','child':'1','bbox':[1,1,30,30]}],'uncertain':[]}
        self.assertIn('cycle_in_state_tree',assess('vlm',p,{'expected_tree_roots':1})['flags'])


class PreservationTests(unittest.TestCase):
    def test_reference_metrics_keep_pending_gold_out_and_measure_text(self):
        from evaluate import reference_metrics
        queue=[{'page':1,'document_sha256':'d','render_sha256':'r','group_id':1,'split':'development','scheduled_vlm':False}]
        annotation={**queue[0],'annotation_status':'verified','reviewer':'source_reviewer','evidence':'visually transcribed',
            'gold':{'contains_knowledge_visual':False,'requires_vlm':False,'reference':{'text':'abc','regions':[
                {'request_id':'f','input_file_sha256':'x','latex':'a=b'}]}}}
        requests={'f':{'id':'f','page':1,'engine':'formula','kind':'formula','input_file_sha256':'x'}}
        result=reference_metrics([annotation],queue,requests,{'f':{'prediction':{'latex':'a=b'}}},{1:{'blocks':[{'text':'adc'}]}})
        self.assertAlmostEqual(result['components'][0]['native_text']['CER'],1/3)
        self.assertTrue(result['components'][0]['regions'][0]['latex_exact'])
        self.assertIsNone(result['routing']['splits']['holdout']['precision'])
    def test_dangling_stage_is_not_saved_as_success_cache(self):
        import os
        class Model:
            def infer(self,*args):return '{"edges":[{"id":"e","source":"a","target":"missing","bbox":[1,1,20,20]}],"uncertain":[]}',False,0
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);write_once(root/'context.json',{})
            r={'id':'r','cache_key':'k','context':'context.json','image':'x.png'}
            with patch.dict(os.environ,{'REGION_V3_CACHE':str(root/'shared')}):
                result=stage(root,root/'out',r,'edges',{'nodes':[{'id':'a','label':'a','bbox':[1,1,10,10]}]},Model())
            self.assertEqual(result['status'],'invalid_structure')
            self.assertFalse((root/'shared').exists())
    def test_full_run_requires_pilot_before_loading_model(self):
        from worker import vlm
        with tempfile.TemporaryDirectory() as d,patch('worker.seed'),patch('worker.Qwen') as model:
            with self.assertRaisesRegex(RuntimeError,'pilot'):vlm(Path(d),Path(d),{'requests':[{'id':'x','engine':'vlm','page':1}],'pilot_pages':[1]},'all')
            model.assert_not_called()

    def test_known_calibration_pages_cannot_be_holdout(self):
        pages={i:{'original_source':{'source_sha256':str(i),'source_page':1},'document_sha256':'d','render_sha256':str(i)} for i in range(1,101)}
        rows,groups,protected=make_benchmark(pages,{i:{} for i in pages},[{'page':i,'engine':'formula'} for i in pages],[],{1},{33})
        self.assertNotIn(33,protected)

    def test_exact_visual_duplicates_join_same_split(self):
        pages={i:{'original_source':{'source_sha256':str(i),'source_page':1},'document_sha256':'d','render_sha256':str(i)} for i in range(1,101)}
        rows,groups,protected=make_benchmark(pages,{i:{} for i in pages},[],[],{1},set(),[[1,99]])
        self.assertEqual(groups[1],groups[99]);self.assertNotIn(99,protected)

    def test_no_gold_is_not_valid_annotation(self):
        from annotations import validate_benchmark
        with self.assertRaises(ValueError):validate_benchmark([],[])

    def test_transcript_cannot_enter_protected_holdout(self):
        from annotations import export_reviews
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);write_once(root/'manifest.json',{'document':{'sha256':'d'},'source_render_hashes':{'1':'r'}})
            write_once(root/'benchmark_groups.json',{'protected_holdout_pages':[1]})
            (root/'carried_cpt_archive').mkdir();(root/'carried_cpt_archive/train.metadata.jsonl').write_text('')
            with self.assertRaisesRegex(ValueError,'holdout'):export_reviews(root,[{'page':1}],root/'export')
    def test_append_only_write(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'x.json';write_once(p,{'x':1});write_once(p,{'x':1})
            with self.assertRaises(ValueError):write_once(p,{'x':2})

    def test_context_or_model_changes_cache_identity(self):
        r={'engine':'vlm','kind':'graph','context_sha256':'x'}
        self.assertNotEqual(identity(r,{'model':'3B'}),identity(r,{'model':'7B'}))
        self.assertNotEqual(identity(r,{}),identity({**r,'context_sha256':'y'},{}))

    def test_model_cannot_promote_itself(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);write_once(root/'c.json',{'native_text':'a'})
            r={'id':'r','engine':'vlm','cache_key':'k','input_file_sha256':'i','raw_pixel_sha256':'p','page':1,'document_sha256':'d','render_sha256':'r','context':'c.json','image':'x.png'}
            result=finish(root,root/'out',r,{'status':'ok','prediction':graph(),'semantic_verified':True})
            self.assertFalse(result['semantic_verified']);self.assertEqual(result['destination'],'review_queue')

    def test_near_duplicate_and_chapter_split_groups(self):
        pages={i:{'original_source':{'source_sha256':str(i),'source_page':1},'document_sha256':'d','render_sha256':str(i)} for i in range(1,101)}
        features={i:{} for i in pages};requests=[{'page':i,'engine':'formula'} for i in pages]
        rows,groups,protected=make_benchmark(pages,features,requests,[{'page_a':1,'page_b':99}],{1})
        self.assertEqual(groups[1],groups[99]);self.assertNotIn(99,protected)
        self.assertTrue(all(r['gold'] is None and r['annotation_status']=='pending' for r in rows))

    def test_cached_stage_does_not_call_model(self):
        from contracts import canonical,digest
        r={'id':'x','cache_key':'k'};key=digest(canonical({'request_cache_key':'k','stage':'nodes','upstream':{}}))
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);write_once(out/'stages/x_nodes.json',{'stage_key':key,'status':'ok','prediction':{'nodes':[],'uncertain':[]}})
            class Model:
                def infer(self,*args):raise AssertionError('Inference must not run')
            self.assertEqual(stage(out,out,r,'nodes',{},Model())['status'],'ok')


class SourceGeometryRegression(unittest.TestCase):
    def test_native_topology_matches_four_development_references(self):
        from contracts import load
        from evidence import native_context,vector_candidates,native_graph_candidates
        import pymupdf
        root=Path(__file__).resolve().parents[1]/'region_preprocessing_v2'
        m=load(root/'runs/it3170_v2_release/7B/manifest.json');golds=load(root/'gold_cases.json')
        pages={p['page']:p for p in map(json.loads,(Path(m['source_native_root'])/'native_pages.jsonl').read_text(encoding='utf-8').splitlines())}
        with pymupdf.open(m['document']['path']) as pdf:
            for n in [494,812,930,1042]:
                q=next(q for q in m['requests'] if q['engine']=='vlm' and q['page']==n)
                context=native_context(pages[n],q);context['vector_paths']=vector_candidates(pdf[n-1],pages[n],q)
                graph=native_graph_candidates(pdf[n-1],pages[n],q,context);labels={v['id']:v['label'] for v in graph['nodes']}
                gold=next(g for g in golds if g['page']==n)
                self.assertEqual(set(labels.values()),set(gold['nodes']),n)
                got={tuple(sorted([labels[e['source']],labels[e['target']]])) for e in graph['edges']}
                expected={tuple(sorted([e['source'],e['target']])) for e in gold['edges']}
                self.assertEqual(got,expected,n)
                self.assertTrue(all(e['semantic_verified'] is False for e in graph['edges']))

    def test_twenty_board_proposals_still_unverified(self):
        from contracts import load
        from evidence import board_candidates
        root=Path(__file__).resolve().parents[1]/'region_preprocessing_v2/runs/it3170_v2_release/7B'
        q=next(q for q in load(root/'manifest.json')['requests'] if q['engine']=='vlm' and q['page']==129)
        boards=board_candidates(root/q['image']);self.assertEqual(len(boards),20)
        self.assertTrue(all(b['semantic_verified'] is False for b in boards))


if __name__=='__main__':unittest.main()
