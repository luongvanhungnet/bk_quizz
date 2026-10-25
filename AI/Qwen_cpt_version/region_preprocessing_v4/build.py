"""Build v4 from immutable v3 source crops/seeds, never overwrite an earlier run."""
import argparse
import copy
import json
import html
from collections import Counter
from pathlib import Path
import shutil
import zipfile
from contracts import canonical,digest,file_hash,identity,task_identity,load,write_once
from geometry import crop,union,local_box
from prompts import prompt
from validation import validate_prediction
from quality import assess

ROOT=Path(__file__).resolve().parent
SOURCE=ROOT.parent/'region_preprocessing_v3/runs/it3170_v3_20261019'
ARCHIVE=ROOT.parent/'region_preprocessing_v3/result/region_v3_results_aa4973c0f29f_1792386371941271361.zip'
CODE=['worker.py','contracts.py','schema.py','prompts.py','geometry.py','validation.py','v3_validation.py','legacy_validation.py','quality.py','quality_base.py']

def jsonl(path,rows):path.write_text(''.join(canonical(r)+'\n' for r in rows),encoding='utf-8')

def build(out):
    if out.exists():raise ValueError('Existing run preserved; choose a new --out')
    source=load(SOURCE/'manifest.json')
    if file_hash(SOURCE/'manifest.json')!='aa4973c0f29fe834579fd5f92625e10538cad733218e88c692552a4a0e3d1c73':raise ValueError('Wrong v3 source')
    for name,sha in source['code_sha256'].items():
        if file_hash(SOURCE/name)!=sha:raise ValueError('V3 source runtime changed')
    if file_hash(Path(source['document']['path']))!=source['document']['sha256']:raise ValueError('Source PDF changed')
    out.mkdir(parents=True)
    for name in ['crops','contexts','seeds','task_crops','task_contexts','build_sources']:(out/name).mkdir()
    for name in CODE:shutil.copy2(ROOT/name,out/name)
    code_hashes={n:file_hash(ROOT/n) for n in CODE}
    config={'schema':'it3170-region-v4','vlm_model':'Qwen/Qwen2.5-VL-7B-Instruct','vlm_revision':source['config']['vlm_revision'],
        'quantization':'nf4','batch_size':1,'visual_tokens':384,'retry_visual_tokens':256,'min_visual_tokens':64,'max_text_tokens':2048,'max_total_tokens':4096,
        'max_attempts_per_task':2,'formula_model':'PP-FormulaNet-S','runtime_sha256':digest(canonical(code_hashes)),
        'resize_policy':'direct_PIL_then_processor_same_cap','semantic_acceptance':False}
    requests=[];tasks=[];triage=[];order=0
    def task(r,stage,payload,clip,suffix,limit,depends_on=None,chunk_index=None):
        nonlocal order
        tid=r['id']+'__'+suffix;image='task_crops/'+tid+'.png';effective=crop(out/r['image'],out/image,clip)
        # Candidate boxes supplied in parent space are transformed into this exact crop.
        def transform(v):
            if isinstance(v,dict):return {k:local_box(value,effective) if k=='bbox' else transform(value) for k,value in v.items()}
            if isinstance(v,list):return [transform(i) for i in v]
            return v
        payload=transform(payload)
        context='task_contexts/'+tid+'.json';write_once(out/context,payload)
        t={'id':tid,'parent_id':r['id'],'page':r['page'],'stage':stage,'image':image,'input_file_sha256':file_hash(out/image),
           'context':context,'context_sha256':file_hash(out/context),'source_bbox':effective,'max_new_tokens':limit,'order':order}
        if depends_on:t['depends_on']=depends_on
        if chunk_index is not None:t['chunk_index']=chunk_index
        t['cache_key']=task_identity(t,config);tasks.append(t);order+=1
        return tid
    for original in source['requests']:
        r=copy.deepcopy(original)
        for field,key in [('image','input_file_sha256'),('context','context_sha256')]:
            if file_hash(SOURCE/r[field])!=r[key]:raise ValueError('Changed v3 evidence')
        shutil.copy2(SOURCE/r['image'],out/r['image']);context=load(SOURCE/r['context'])
        if r['engine']!='vlm':
            # Seeds include original invalid predictions, retained for review only.
            seed=load(SOURCE/'seeds'/(r['id']+'.json'))
            if file_hash(SOURCE/'seeds'/(r['id']+'.json'))!=source['seed_sha256'][r['id']+'.json']:raise ValueError('Changed specialist seed')
            seed.update(source_v3_cache_key=seed['cache_key'],semantic_verified=False,reused_inference=True)
            errors=validate_prediction(r['engine'],seed.get('prediction'))
            context['native_ocr']=r.get('native_ocr',[])
            seed['structural_errors']=errors
            seed['quality']=assess(r['engine'],seed['prediction'],context) if not errors else {'flags':['structural_validation_failed'],'evidence_gate_pass':False,'semantic_verified':False}
            flags=seed['quality']['flags']
            if flags or seed['status']!='ok':
                text=canonical(errors+flags)
                category='latex_repetition' if 'repeat' in text or 'repet' in text else 'latex_delimiters' if any(s in text for s in ['brace','environment','delimiter']) else 'native_content_mismatch'
                triage.append({'id':r['id'],'engine':r['engine'],'page':r['page'],'category':category,'structural_errors':errors,'quality_flags':flags,
                    'image':r['image'],'context':r['context'],'input_file_sha256':r['input_file_sha256'],
                    'action':'inspect_crop_and_native_context; rerun only after changed input/config or source-reviewed transcript',
                    'automatic_rerun':False,'semantic_verified':False})
        else:
            native=context.get('native_graph_candidates',{})
            if r['kind']=='state_tree':
                boards=context.get('board_candidates',[])
                context['board_candidates']=[{**b,'id':f'b{i+1}'} for i,b in enumerate(boards)]
                r['route']='individual_boards_and_tree_links'
                for board in context['board_candidates']:
                    task(r,'board',{'id':board['id'],'board_size':board['board_size']},union([board['bbox']],5),'board_'+board['id'],512)
                task(r,'tree_links',{'boards':[{k:b[k] for k in ['id','bbox']} for b in context['board_candidates']]},[0,0,1000,1000],'tree_links',1024)
            elif len(native.get('nodes',[]))>=2 and native.get('edges') and len(native['nodes'])<=24:
                r['route']='native_geometry_with_vlm_checks'
                nodes=[{k:n[k] for k in ['id','label','bbox']} for n in native['nodes']]
                edges=[{**e,'id':f'e{i+1}'} for i,e in enumerate(native['edges'])]
                context['v4_edges']=edges;clip=union([n['bbox'] for n in nodes]+[e['bbox'] for e in edges],20)
                for i in range(0,len(edges),8):
                    group=edges[i:i+8];endpoint_ids={e[k] for e in group for k in ['source','target']}
                    payload={'nodes':[n for n in nodes if n['id'] in endpoint_ids],
                             'edges':[{k:e[k] for k in ['id','source','target','bbox']} for e in group],
                             'candidate_subset':len(edges)>8,'native_caption':context.get('native_local_context','')[:220]}
                    task(r,'inventory',payload,clip,f'inventory_{i//8:02d}',768)
                for i in range(0,len(edges),4):
                    group=edges[i:i+4];endpoint_ids={e[k] for e in group for k in ['source','target']}
                    payload={'nodes':[n for n in nodes if n['id'] in endpoint_ids],
                             'edges':[{k:e[k] for k in ['id','source','target','bbox']}|{'weight_candidates':e.get('weight_candidates',[])[:2]} for e in group],
                             'native_caption':context.get('native_local_context','')[:220]}
                    task(r,'edge_attributes',payload,clip,f'attributes_{i//4:02d}',1024)
            else:
                r['route']='fallback_small_graph_stages'
                nodes_task=task(r,'nodes',{'native_caption':context.get('native_local_context','')[:200]},[0,0,1000,1000],'nodes',768)
                edges_task=task(r,'edges',{'nodes':[]},[0,0,1000,1000],'edges',1024,depends_on=nodes_task)
                # Dynamic chunks are predeclared for at most 32 fallback edges.
                # Empty chunks are marked skipped-success without invoking a model.
                for i in range(8):task(r,'edge_attributes',{'nodes':[],'edges':[],'native_caption':context.get('native_local_context','')[:200]},[0,0,1000,1000],f'attributes_{i:02d}',1024,depends_on=edges_task,chunk_index=i)
        write_once(out/r['context'],context);r['context_sha256']=file_hash(out/r['context']);r['cache_key']=identity(r,config);requests.append(r)
        if r['engine']!='vlm':seed['cache_key']=r['cache_key'];write_once(out/'seeds'/(r['id']+'.json'),seed)
    for name in ['benchmark_queue.jsonl','benchmark_groups.json','routing_annotations.json','benchmark_review.html']:
        shutil.copy2(SOURCE/name,out/name)
    for name in ['benchmark_images','cpt','carried_cpt_archive']:shutil.copytree(SOURCE/name,out/name)
    jsonl(out/'specialist_review_plan.jsonl',triage)
    cards=[]
    for item in triage:
        native=load(out/item['context']).get('native_crop_text','')
        cards.append('<article><h2>'+html.escape(item['id'])+' — '+html.escape(item['category'])+'</h2><img src="'+item['image']+'"><p>'+html.escape(', '.join(item['structural_errors']+item['quality_flags']))+'</p><pre>'+html.escape(native)+'</pre></article>')
    (out/'specialist_review.html').write_text('<!doctype html><meta charset="utf-8"><title>V4 specialist review</title><style>body{font:16px sans-serif;margin:32px}article{padding:20px;border-bottom:1px solid #aaa}img{max-width:900px;max-height:400px}pre{white-space:pre-wrap}</style><h1>Source review queue — not verified training data</h1>'+''.join(cards),encoding='utf-8')
    fixtures=ROOT/'fixtures';fixtures.mkdir(exist_ok=True)
    with zipfile.ZipFile(ARCHIVE) as z:
        if z.testzip():raise ValueError('Corrupt v3 results')
        for name in z.namelist():
            if name.startswith('stages/') and name.endswith('.json'):
                data=z.read(name);target=fixtures/Path(name).name
                if target.exists() and target.read_bytes()!=data:raise ValueError('Fixture changed')
                if not target.exists():target.write_bytes(data)
    preserved={str(SOURCE/'manifest.json'):file_hash(SOURCE/'manifest.json'),str(ARCHIVE):file_hash(ARCHIVE)}
    for name in ['cpt','carried_cpt_archive']:
        for p in (SOURCE/name).glob('*'):
            if p.is_file():preserved[str(p)]=file_hash(p)
    write_once(out/'preserved_source_hashes.json',preserved)
    for name in ['build.py']:shutil.copy2(ROOT/name,out/'build_sources'/name)
    manifest={'schema_version':'it3170-region-v4','document':source['document'],'source_manifest_sha256':file_hash(SOURCE/'manifest.json'),
        'source_archive_sha256':file_hash(ARCHIVE),'source_render_hashes':source['source_render_hashes'],'config':config,'code_sha256':code_hashes,
        'requests':requests,'tasks':tasks,'pilot_pages':source['pilot_pages'],'canary_pages':[930,1042],
        'seed_sha256':{p.name:file_hash(p) for p in (out/'seeds').glob('*.json')},'budget':source['budget'],'semantic_acceptance':False,
        'local_build_sha256':{'build.py':file_hash(ROOT/'build.py')}}
    write_once(out/'manifest.json',manifest)
    with zipfile.ZipFile(out/'region_v4_input.zip','w',zipfile.ZIP_DEFLATED) as z:
        for directory in ['crops','contexts','seeds','task_crops','task_contexts']:
            for p in sorted((out/directory).glob('*')):z.write(p,p.relative_to(out).as_posix())
        for name in CODE+['manifest.json']:z.write(out/name,name)
    report={'requests_by_engine':dict(Counter(r['engine'] for r in requests)),'parent_routes':dict(Counter(r.get('route','specialist_seed') for r in requests)),
        'tasks_by_stage':dict(Counter(t['stage'] for t in tasks)),'pilot_tasks':sum(t['page'] in manifest['pilot_pages'] for t in tasks),
        'canary_tasks':sum(t['page'] in manifest['canary_pages'] for t in tasks),'specialist_review_count':len(triage),
        'CPT':load(out/'cpt/manifest.json'),'manifest_sha256':file_hash(out/'manifest.json'),'input_zip_sha256':file_hash(out/'region_v4_input.zip'),
        'GPU_inference_executed':False,'new_semantically_verified':0}
    write_once(out/'build_metrics.json',report);print(json.dumps({k:v for k,v in report.items() if k!='CPT'},indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,default=ROOT/'runs/it3170_v4_20261019_final');build(p.parse_args().out)
