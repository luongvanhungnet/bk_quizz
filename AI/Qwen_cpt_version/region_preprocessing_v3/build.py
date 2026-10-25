"""Build v3 from immutable v2 outputs, with source geometry, contexts and split groups."""
import argparse
from collections import Counter
import copy
import json
from pathlib import Path
import shutil
import zipfile
from PIL import Image,ImageDraw
from contracts import canonical,digest,file_hash,load,write_once,identity
from evidence import native_context,vector_candidates,native_graph_candidates,board_candidates,overlap
from benchmark import make_benchmark
from validation import validate_prediction
from quality import assess
from dataset import pack_dataset

ROOT=Path(__file__).resolve().parent;V2=ROOT.parent/'region_preprocessing_v2'
SOURCE=V2/'runs/it3170_v2_release/7B';OLD=ROOT.parent/'region_preprocessing'
PILOT=[129,494,812,930,1042]
def jsonl(path,rows):path.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows),encoding='utf-8')
def pixel(im):
    im=im.convert('RGB');return digest(f'RGB:{im.width}:{im.height}:'.encode()+im.tobytes())


def new_crop(r,im,page_box,out,suffix):
    r=copy.deepcopy(r);r.update(parent_id=r['id'],id=r['id']+suffix,bbox_pixels=page_box,
        original_size=list(im.size),input_size=list(im.size),raw_pixel_sha256=pixel(im),input_pixel_sha256=pixel(im))
    r['image']='crops/'+r['id']+'.png';im.save(out/r['image']);r['input_file_sha256']=file_hash(out/r['image']);return r


def build(out):
    if out.exists():raise ValueError('Existing run preserved; choose a new --out')
    out.mkdir(parents=True);(out/'crops').mkdir();(out/'contexts').mkdir();(out/'seeds').mkdir()
    source=load(SOURCE/'manifest.json')
    if file_hash(Path(source['document']['path']))!=source['document']['sha256']:raise ValueError('Source PDF changed')
    archive=V2/'result/region_v2_results_d682e3b25b0d.zip'
    with zipfile.ZipFile(archive) as z:
        if z.testzip():raise ValueError('Corrupt v2 ZIP')
        previous=json.loads(z.read('7B/results.json'))
    if previous['manifest_sha256']!=file_hash(SOURCE/'manifest.json'):raise ValueError('Wrong v2 source')
    old={r['id']:r for r in previous['records']}
    pages={p['page']:p for p in map(json.loads,(Path(source['source_native_root'])/'native_pages.jsonl').read_text(encoding='utf-8').splitlines())}
    import pymupdf
    requests=[];seeds={};audit=[];split_notes=[]
    with pymupdf.open(source['document']['path']) as pdf:
        for original in source['requests']:
            r=copy.deepcopy(original);p=pages[r['page']]
            if old[r['id']]['cache_key']!=r['cache_key']:raise ValueError('Changed source result identity')
            if file_hash(SOURCE/r['image'])!=r['input_file_sha256']:raise ValueError('Changed v2 crop')
            if p['document_sha256']!=r['document_sha256'] or p['render_sha256']!=r['render_sha256']:raise ValueError('Changed native source')
            r['source_request_id']=r['id'];r['execution']='inference';r['kind']='graph' if r['engine']=='vlm' else r['engine']
            children=[r]
            # This is a source-bound routing annotation for an inspected image,
            # not expected board states or an answer supplied to the VLM.
            if r['engine']=='vlm' and r['page']==129:
                expected=next(g for g in load(V2/'gold_cases.json') if g['page']==129)
                if expected['input_file_sha256']!=r['input_file_sha256']:raise ValueError('State-tree routing source changed')
                image=Image.open(SOURCE/r['image']).convert('RGB');children=[]
                for i,(x1,x2) in enumerate([(0,.475),(.480,1)]):
                    left=int(image.width*x1);right=int(image.width*x2)
                    im=image.crop((left,0,right,image.height));box=r['bbox_pixels'];span=box[2]-box[0]
                    page_box=[box[0]+span*left/image.width,box[1],box[0]+span*right/image.width,box[3]]
                    child=new_crop(r,im,page_box,out,f'_tree{i+1}');child['kind']='state_tree';children.append(child)
                split_notes.append({'page':129,'source_input_file_sha256':r['input_file_sha256'],'routing_only':True,
                    'reviewer':'Codex_source_visual_inspection','evidence':'Two side-by-side 4-Queens state trees in the inspected crop',
                    'children':[c['id'] for c in children]})
            elif r['engine']=='formula' and r['id']=='p0033_r00013_f01':
                # Re-crop a known punctuation-contaminated boundary using native
                # geometry, not by editing the recognized mathematical content.
                scale=p['render_width']/p['page_size_pt'][0];clip=r['bbox_pixels'];boxes=[]
                for block in p['blocks']:
                    for line in block.get('lines',[]):
                        for span in line.get('spans',[]):
                            b=[v*scale for v in span['bbox']];text=span['text'].strip()
                            if text and text not in ['?',':',';'] and overlap(b,clip)/max(1,(b[2]-b[0])*(b[3]-b[1]))>.9:boxes.append(b)
                if boxes:
                    render=Path(p['render_path']);render=render if render.is_absolute() else Path(source['source_native_root'])/render
                    if file_hash(render)!=p['render_sha256']:raise ValueError('Changed native render')
                    image=Image.open(render).convert('RGB')
                    box=[max(0,int(min(b[0] for b in boxes))-2),max(0,int(min(b[1] for b in boxes))-2),
                         min(image.width,int(max(b[2] for b in boxes))+3),min(image.height,int(max(b[3] for b in boxes))+3)]
                    children=[new_crop(r,image.crop(box),box,out,'_v3_boundary')]
            for child in children:
                target=out/child['image']
                if not target.exists():shutil.copy2(SOURCE/child['image'],target)
                context=native_context(p,child)
                if child['engine']=='vlm':
                    if child['kind']=='state_tree':
                        context.update(board_candidates=board_candidates(target),expected_tree_roots=1,board_size=4)
                    else:
                        text=context['native_text'].casefold()
                        if any(w in text for w in ['flowchart','lưu đồ']):child['kind']='flowchart'
                        elif original.get('label')=='chart' and any(w in text for w in ['accuracy','epoch','trục','biểu đồ thống kê']):child['kind']='chart'
                        context['vector_paths']=vector_candidates(pdf[child['page']-1],p,child)
                        context['native_graph_candidates']=native_graph_candidates(pdf[child['page']-1],p,child,context)
                context['native_ocr']=child.get('native_ocr',[])
                child['context']='contexts/'+child['id']+'.json';write_once(out/child['context'],context);child['context_sha256']=file_hash(out/child['context'])
                previous_record=old[original['id']]
                # No blind rerun of 41 deterministic failures on identical crops.
                if child['engine']!='vlm' and child['input_file_sha256']==original['input_file_sha256']:
                    previous_copy=copy.deepcopy(previous_record);previous_copy.update(reused_inference=True,
                        source_cache_key=previous_record['cache_key'],source_manifest_sha256=previous['manifest_sha256'],
                        source_archive_sha256=file_hash(archive),semantic_verified=False)
                    seeds[child['id']]=previous_copy
                    child['execution']='review_only' if previous_record['status']!='ok' else 'reuse'
                canary=ROOT/'evidence/formula_canary_cpu/records'/(child['id']+'.json')
                if child['engine']=='formula' and child['execution']=='inference' and canary.exists():
                    canary_identity=load(ROOT/'evidence/formula_canary_identity.json')
                    if file_hash(canary)!=canary_identity['record_sha256'] or canary_identity['formula_model']!='PP-FormulaNet-S':raise ValueError('Changed canary evidence')
                    checked=load(canary)
                    if checked.get('input_file_sha256')==child['input_file_sha256'] and checked.get('status')=='ok' and not validate_prediction('formula',checked.get('prediction')):
                        checked.update(reused_inference=True,source_cache_key=checked['cache_key'],
                            source_manifest_sha256=load(ROOT/'evidence/formula_canary_identity.json')['source_manifest_sha256'],
                            source_evidence_sha256=file_hash(canary),source_device='cpu',semantic_verified=False)
                        seeds[child['id']]=checked;child['execution']='reuse'
                requests.append(child)
    features={r['page']:r for r in map(json.loads,(OLD/'runs/it3170_scored_v3/page_features.jsonl').read_text(encoding='utf-8').splitlines())}
    near=load(ROOT.parent/'hybrid_preprocessing/runs/it3170_test/deduplication.json')['near_pairs']
    known_dev={11,20,33,34,60,73,85,100}|{r['page'] for r in map(json.loads,(ROOT.parent/'data_preprocessing/outputs/it3170/reviewed_annotations.jsonl').read_text(encoding='utf-8').splitlines())}
    visual_groups={}
    for r in map(json.loads,(OLD/'runs/it3170_scored_v3/regions.jsonl').read_text(encoding='utf-8').splitlines()):
        if r['engine']=='vlm':visual_groups.setdefault(r['raw_pixel_sha256'],set()).add(r['page'])
    visual_groups=[sorted(v) for v in visual_groups.values() if len(v)>1]
    benchmark,groups,protected=make_benchmark(pages,features,source['requests'],near,set(PILOT),known_dev,visual_groups)
    jsonl(out/'benchmark_queue.jsonl',benchmark);write_once(out/'benchmark_groups.json',{'page_to_group':groups,'protected_holdout_pages':sorted(protected),
        'exact_visual_groups':visual_groups,'group_policy':'source_50page_segments_plus_near_pairs_plus_exact_VLM_pixels'})
    write_once(out/'routing_annotations.json',split_notes)
    # Local review kit: source images, not model-created gold. Not included in GPU ZIP.
    (out/'benchmark_images').mkdir();cards=[]
    for row in benchmark:
        p=pages[row['page']];render=Path(p['render_path']);render=render if render.is_absolute() else Path(source['source_native_root'])/render
        if file_hash(render)!=row['render_sha256']:raise ValueError('Changed benchmark source image')
        name=f"page_{row['page']:04d}.png";shutil.copy2(render,out/'benchmark_images'/name)
        cards.append(f'<article><h3>Page {row["page"]}: {row["category"]} / {row["split"]}</h3><a href="benchmark_images/{name}"><img width="640" src="benchmark_images/{name}"></a><p>Gold pending. Group {row["group_id"]}. Do not use holdout for prompt tuning.</p></article>')
    (out/'benchmark_review.html').write_text('<!doctype html><meta charset="utf-8"><title>IT3170 v3 annotation queue</title><style>body{font:16px sans-serif;margin:32px}article{border-bottom:1px solid #aaa;padding:20px}img{max-width:100%;height:auto}</style><h1>Source-bound annotation queue, not completed gold</h1>'+''.join(cards),encoding='utf-8')
    code_names=['worker.py','validation.py','legacy_validation.py','quality.py','prompts.py','contracts.py','table_adapter.py']
    code_hashes={name:file_hash(ROOT/name) for name in code_names}
    config={'schema':'it3170-region-v3','vlm_model':'Qwen/Qwen2.5-VL-7B-Instruct',
        'vlm_revision':source['config']['vlm_revision'],'quantization':'nf4','vlm_batch_size':1,
        'max_visual_tokens':768,'max_new_tokens':3072,'formula_model':'PP-FormulaNet-S',
        'runtime_code_sha256':digest(canonical(code_hashes)),'evidence_code_sha256':file_hash(ROOT/'evidence.py'),
        'semantic_acceptance':False,'graph_stages':['nodes','edges','attributes']}
    for r in requests:
        r['cache_key']=identity(r,config)
        if r['id'] in seeds:
            record=seeds[r['id']];record.update(id=r['id'],cache_key=r['cache_key'],input_file_sha256=r['input_file_sha256'])
            write_once(out/'seeds'/(r['id']+'.json'),record)
    for name in code_names:shutil.copy2(ROOT/name,out/name)
    manifest={'schema_version':'it3170-region-v3','document':source['document'],'source_manifest_sha256':file_hash(SOURCE/'manifest.json'),
        'source_archive_sha256':file_hash(archive),'source_render_hashes':source['source_render_hashes'],
        'config':config,'code_sha256':code_hashes,'requests':requests,'pilot_pages':PILOT,
        'seed_sha256':{p.name:file_hash(p) for p in (out/'seeds').glob('*.json')},
        'budget':{'scheduled_vlm_pages':sorted({r['page'] for r in requests if r['engine']=='vlm'}),
                  'page_ratio':len({r['page'] for r in requests if r['engine']=='vlm'})/len(pages),
                  'target':[.04,.08],'not_a_coverage_claim':True},'semantic_acceptance':False}
    (out/'build_sources').mkdir()
    local_sources=['build.py','evidence.py','dataset.py','benchmark.py']
    for name in local_sources:shutil.copy2(ROOT/name,out/'build_sources'/name)
    manifest['local_build_sha256']={name:file_hash(out/'build_sources'/name) for name in local_sources}
    write_once(out/'manifest.json',manifest)
    carried=[json.loads(l) for l in (SOURCE.parent/'cpt/train.metadata.jsonl').read_text(encoding='utf-8').splitlines()]
    shutil.copytree(SOURCE.parent/'cpt',out/'carried_cpt_archive')
    dataset=pack_dataset(carried,out/'cpt',ROOT.parent/'local_qwen3/models/merged_hf_fp16',protected)
    preserved=[SOURCE/'manifest.json',archive,V2/'worker.py',V2/'validation.py',V2/'evaluation_d682e3b25b0d/metrics.json']+list((SOURCE.parent/'cpt').glob('*'))
    write_once(out/'preserved_source_hashes.json',{str(p.resolve()):file_hash(p) for p in preserved if p.is_file()})
    with zipfile.ZipFile(out/'region_v3_input.zip','w',zipfile.ZIP_DEFLATED) as z:
        for directory in ['crops','contexts','seeds']:
            for p in sorted((out/directory).glob('*')):z.write(p,p.relative_to(out).as_posix())
        for name in code_names+['manifest.json']:z.write(out/name,name)
    report={'requests_by_engine':dict(Counter(r['engine'] for r in requests)),
        'request_kinds':dict(Counter(r['kind'] for r in requests)),
        'execution':dict(Counter(r['execution'] for r in requests)),
        'pilot_requests':sum(r['engine']=='vlm' and r['page'] in PILOT for r in requests),
        'benchmark_pages':len(benchmark),'benchmark_categories':dict(Counter(r['category'] for r in benchmark)),
        'benchmark_splits':dict(Counter(r['split'] for r in benchmark)),'benchmark_gold_completed':0,
        'below_threshold_graph_audits':sum(r['category']=='graph' and not r['scheduled_vlm'] for r in benchmark),
        'protected_holdout_group_pages':len(protected),'cpt':dataset,
        'new_verified_predictions':0,'gpu_inference_executed':False,'full_knowledge_coverage_met':False}
    write_once(out/'build_metrics.json',report);print(json.dumps(report,ensure_ascii=True,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,default=ROOT/'runs/it3170_v3_20261019');build(p.parse_args().out)
