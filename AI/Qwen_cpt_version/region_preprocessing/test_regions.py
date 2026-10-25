import copy
import tempfile
import json
import zipfile
import unittest
from pathlib import Path
from argparse import Namespace
from unittest.mock import patch
from route import strict_page_budget,schedule,pixel_hash,resize_crop,regions_for_page,merge,digest
from validation import parse_json_output,validate_prediction,cache_is_valid


class RegionChecks(unittest.TestCase):
    def test_budget_is_strictly_less_than_five_percent(self):
        self.assertEqual(strict_page_budget(1060),52)
        self.assertEqual(strict_page_budget(1000),49)
        for n in [1,20,100,1000,1060]:self.assertLess(strict_page_budget(n)/n,.05)

    def test_budget_overflow_is_explicit_review_work(self):
        regions=[{'page':i+1,'engine':'vlm','state':'candidate','priority':.5} for i in range(100)]
        result=schedule(regions,100,strict_page_budget(100))
        self.assertEqual(len(result['scheduled_vlm_pages']),4)
        self.assertEqual(sum(r['state']=='deferred_budget' for r in regions),96)
        self.assertFalse(any(r.get('verified') for r in regions))

    def test_specialized_routes_never_consume_vlm_page_budget(self):
        regions=[{'page':i,'engine':engine,'state':'candidate','priority':0}
                 for i in range(1,101) for engine in ['formula','table']]
        result=schedule(regions,100,4)
        self.assertFalse(result['scheduled_vlm_pages'])
        self.assertTrue(all(r['state']=='scheduled' for r in regions))

    def test_pixel_hash_keeps_changed_small_labels_and_resize_bounds(self):
        from PIL import Image
        a=Image.new('RGB',(2000,1200),'white');b=a.copy();b.putpixel((100,100),(0,0,0))
        self.assertNotEqual(pixel_hash(a),pixel_hash(b))
        small=resize_crop(a,'vlm')
        self.assertLessEqual(max(small.size),1024)
        self.assertLessEqual(small.width*small.height,768*28*28)

    def test_recover_markdown_without_claiming_semantic_verification(self):
        obj,recovered=parse_json_output('```json\n{"nodes": []}\n```')
        self.assertTrue(recovered)
        self.assertIn('root_fields',validate_prediction('vlm',obj))

    def test_dangling_edge_is_rejected(self):
        obj={'image_type':'graph','nodes':[{'id':'1','label':'A'}],
             'edges':[{'source':'1','target':'2','directed':True,'weight':5,'highlighted':False}],
             'observed_facts':[],'uncertain':[]}
        self.assertIn('dangling_edge_reference',validate_prediction('vlm',obj))

    def test_cache_identity_and_schema_both_required(self):
        request={'cache_key':'one','engine':'formula'}
        record={'cache_key':'one','engine':'formula','status':'ok','prediction':{'latex':'a=b'}}
        self.assertTrue(cache_is_valid(record,request))
        self.assertFalse(cache_is_valid(record,{**request,'cache_key':'different-model-or-resolution'}))
        record['prediction']['latex']=''
        self.assertFalse(cache_is_valid(record,request))

    def test_formula_missed_by_layout_is_still_routed(self):
        page={'render_width':1000,'page_size_pt':[1000,800], 'vector_regions':[],
              'blocks':[{'type':'text','math_candidate':True,'bbox':[100,100,500,150]}]}
        regions,_=regions_for_page(page,[])
        self.assertEqual(regions[0]['engine'],'formula')

    def test_body_graph_is_not_discarded_as_mislabelled_footer(self):
        page={'render_width':1000,'page_size_pt':[1000,800], 'vector_regions':[],'blocks':[]}
        regions,ignored=regions_for_page(page,[{'label':'footer_image','coordinate':[100,200,500,600],'score':.8}])
        self.assertEqual(regions[0]['engine'],'vlm')
        self.assertFalse(ignored)

    def test_structural_success_never_auto_promotes_a_graph_to_train(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);request={'id':'r1','cache_key':'key','engine':'vlm'}
            (root/'manifest.json').write_text(json.dumps({'requests':[request]}))
            (root/'carried_train.metadata.jsonl').write_text('')
            prediction={'image_type':'graph','nodes':[{'id':'A','label':'A'}],
                        'edges':[],'observed_facts':[],'uncertain':[]}
            result={'manifest_sha256':digest((root/'manifest.json').read_bytes()),
                    'records':[{'id':'r1','cache_key':'key','status':'ok','prediction':prediction}]}
            zipped=root/'result.zip'
            with zipfile.ZipFile(zipped,'w') as z:z.writestr('results.json',json.dumps(result))
            with patch('route.pack') as packing:
                merge(Namespace(out=root,results=zipped,reviews=None,tokenizer=root))
                self.assertEqual(packing.call_args.args[0],[])
            queued=json.loads((root/'prediction_review.jsonl').read_text())
            self.assertFalse(queued['semantic_verified'])

    def test_worker_rejects_changed_config_with_stale_cache_keys(self):
        import worker
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for name in ['worker.py','prompt.txt','validation.py','crop.png']:(root/name).write_bytes(name.encode())
            config={key:worker.sha(root/name) for name,key in [('worker.py','worker_sha256'),
                      ('prompt.txt','prompt_sha256'),('validation.py','validation_sha256')]}
            config['max_new_tokens']=1024
            request={'engine':'vlm','raw_pixel_sha256':'raw','input_pixel_sha256':'small',
                     'image':'crop.png','input_file_sha256':worker.sha(root/'crop.png')}
            identity={k:request.get(k) for k in ['engine','raw_pixel_sha256','input_pixel_sha256','native_ocr']}
            identity['config']=config
            request['cache_key']=digest(json.dumps(identity,sort_keys=True,ensure_ascii=False,separators=(',',':')))
            data={'config':config,'requests':[request]}
            (root/'manifest.json').write_text(json.dumps(data))
            worker.manifest(root)
            config['max_new_tokens']=2048
            (root/'manifest.json').write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,'cache identities'):worker.manifest(root)

    def test_footer_logo_crossing_margin_boundary_is_not_a_diagram(self):
        page={'render_width':1400,'page_size_pt':[1400,1050],'blocks':[],'vector_regions':[]}
        regions,ignored=regions_for_page(page,[{'label':'footer_image','coordinate':[48,907,224,1008],'score':.6}])
        self.assertFalse(regions)
        self.assertEqual(ignored[0]['reason'],'layout_margin_decoration')

    def test_code_line_background_vectors_do_not_trigger_vlm(self):
        page={'render_width':1000,'page_size_pt':[1000,800],
              'blocks':[{'type':'code','math_candidate':False,'bbox':[100,100,300,180]},
                        {'type':'code','math_candidate':False,'bbox':[100,200,300,280]}],
              'vector_regions':[{'bbox':[90,y,700,y+20]} for y in [100,140,200,240]]}
        regions,_=regions_for_page(page,[{'label':'algorithm','coordinate':[80,80,750,300],'score':.7}])
        self.assertFalse(any(r['engine']=='vlm' for r in regions))


if __name__=='__main__':unittest.main()
