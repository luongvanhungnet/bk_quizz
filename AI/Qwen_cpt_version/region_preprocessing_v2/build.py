"""Build immutable v2 packages from the existing scored plan; no GPU inference."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import zipfile
from PIL import Image
from formula_routing import classify_formula,intersection,area
from validation import validate_prediction

ROOT=Path(__file__).resolve().parent
OLD=ROOT.parent/'region_preprocessing'
SOURCE=OLD/'runs/it3170_scored_v3'
DIFFICULT=[129,494,812,930,1042]


def sha(data):return hashlib.sha256(data).hexdigest()
def load(p):return json.loads(p.read_text(encoding='utf-8'))
def write(p,d):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')
def jsonl(p,rows):p.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows),encoding='utf-8')
def pixel(im):
    im=im.convert('RGB');return sha(f'RGB:{im.width}:{im.height}:'.encode()+im.tobytes())


def native_cells(page,clip,size):
    scale=page['render_width']/page['page_size_pt'][0]
    sx=size[0]/(clip[2]-clip[0]);sy=size[1]/(clip[3]-clip[1]);out=[]
    for block in page['blocks']:
        for line in block.get('lines',[]):
            b=[v*scale for v in line['bbox']]
            if intersection(clip,b)/max(1,area(b))>.95 and line['text'].strip():
                out.append({'text':line['text'],'bbox':[(b[0]-clip[0])*sx,(b[1]-clip[1])*sy,(b[2]-clip[0])*sx,(b[3]-clip[1])*sy]})
    return out


def crop_child(parent,box,page,out,index):
    image=Image.open(page['render_path']).convert('RGB')
    assert sha(Path(page['render_path']).read_bytes())==page['render_sha256']
    b=[max(0,int(box[0])-4),max(0,int(box[1])-4),min(image.width,int(box[2])+5),min(image.height,int(box[3])+5)]
    im=image.crop(b);raw_hash=pixel(im);original=list(im.size)
    if max(im.size)>1800:
        im.thumbnail((1800,1800),Image.Resampling.LANCZOS)
    r=copy.deepcopy(parent);r.update(id=parent['id']+f'_f{index:02d}',parent_id=parent['id'],
        bbox_pixels=b,original_size=original,input_size=list(im.size),raw_pixel_sha256=raw_hash,
        input_pixel_sha256=pixel(im),method='v2_isolated_native_math',semantic_verified=False)
    r['image']='crops/'+r['id']+'.png';im.save(out/r['image']);r['input_file_sha256']=sha((out/r['image']).read_bytes())
    return r


def build(out):
    if out.exists():raise ValueError('Choose a new output directory; existing artifacts are immutable')
    out.mkdir(parents=True);(out/'crops').mkdir()
    source=load(SOURCE/'manifest.json');assert sha(Path(source['document']['path']).read_bytes())==source['document']['sha256']
    pages={p['page']:p for p in map(json.loads,(Path(source['source_native_root'])/'native_pages.jsonl').read_text(encoding='utf-8').splitlines())}
    with zipfile.ZipFile(OLD/'model/region_results_33f6b7b75d29.zip') as z:previous=json.loads(z.read('results.json'))
    assert previous['manifest_sha256']==sha((SOURCE/'manifest.json').read_bytes())
    old_records={r['id']:r for r in previous['records']}
    tables=[r for r in source['requests'] if r['engine']=='table']
    requests=[];decisions=[]
    for parent in source['requests']:
        assert sha((SOURCE/parent['image']).read_bytes())==parent['input_file_sha256']
        assert parent['render_sha256']==pages[parent['page']]['render_sha256']
        if parent['engine']!='formula':
            requests.append(copy.deepcopy(parent));continue
        p=copy.deepcopy(pages[parent['page']])
        render=Path(p['render_path'])
        if not render.is_absolute():render=Path(source['source_native_root'])/render
        p['render_path']=str(render)
        result=classify_formula(parent,p,[t for t in tables if t['page']==parent['page']])
        decision={'id':parent['id'],'page':parent['page'],'source_crop_sha256':parent['input_file_sha256'],**result}
        children=[]
        if result['decision']=='formula_crops':
            for i,box in enumerate(result['formula_boxes']):
                # Keep identical old pixels when the already-tight math crop
                # covers the same formula. This permits safe inference reuse.
                clip=parent['bbox_pixels']
                if len(result['formula_boxes'])==1 and intersection(clip,box)/max(1,area(clip))>=.75:
                    child=copy.deepcopy(parent);child['parent_id']=parent['id']
                else:child=crop_child(parent,box,p,out,i)
                children.append(child)
        elif result['decision']=='table_candidate':
            child=copy.deepcopy(parent);child.update(id=parent['id']+'_table',parent_id=parent['id'],engine='table',method='v2_native_tabular_geometry')
            child['native_ocr']=native_cells(p,child['bbox_pixels'],child['input_size'])
            if child['native_ocr']:children.append(child)
            else:decision.update(decision='native_review',reason='table_without_native_cell_geometry')
        decision['child_ids']=[r['id'] for r in children];decisions.append(decision);requests.extend(children)
    # Crop files and native text are never reconstructed by a language model.
    for r in requests:
        target=out/r['image']
        if not target.exists():shutil.copy2(SOURCE/r['image'],target)
    # Exact pixel grouping after recropping. Aliases remain auditable and unresolved
    # until the canonical output is reviewed; never dedup changed states by text.
    unique=[];seen={};aliases=[]
    for r in requests:
        key=(r['engine'],r['input_pixel_sha256'],json.dumps(r.get('native_ocr'),sort_keys=True,ensure_ascii=False))
        if key in seen:aliases.append({'id':r['id'],'page':r['page'],'duplicate_of':seen[key],'semantic_verified':False})
        else:seen[key]=r['id'];unique.append(r)
    revisions={size:load(ROOT/'evidence'/f'Qwen2.5-VL-{size}-Instruct_revision.json')['revision'] for size in ['3B','7B']}
    preserved=[SOURCE/'manifest.json',SOURCE/'regions.jsonl',OLD/'worker.py',OLD/'validation.py',OLD/'prompt.txt',OLD/'model/region_results_33f6b7b75d29.zip']+list((SOURCE/'cpt').glob('*'))
    write(out/'preserved_source_hashes.json',{str(p.resolve()):sha(p.read_bytes()) for p in preserved if p.is_file()})
    jsonl(out/'formula_routing_review.jsonl',decisions);jsonl(out/'exact_aliases.jsonl',aliases)
    shutil.copytree(SOURCE/'cpt',out/'cpt')
    shutil.copy2(SOURCE/'review_queue.jsonl',out/'review_queue.jsonl')
    for size in ['3B','7B']:
        package=out/size;package.mkdir();(package/'crops').mkdir()
        selected=[copy.deepcopy(r) for r in unique if size=='7B' or (r['engine']=='vlm' and r['page'] in DIFFICULT)]
        config=copy.deepcopy(source['config']);config.update(schema='region-v2',vlm_model=f'Qwen/Qwen2.5-VL-{size}-Instruct',
            vlm_revision=revisions[size],vlm_batch_size=1,max_new_tokens=2048,quantization='nf4',
            bitsandbytes_version='0.48.1',formula_routing_version='native-math-runs-v2',
            builder_sha256=sha(Path(__file__).read_bytes()),formula_routing_sha256=sha((ROOT/'formula_routing.py').read_bytes()))
        for name,key in [('worker.py','worker_sha256'),('prompt.txt','prompt_sha256'),('validation.py','validation_sha256'),('table_adapter.py','table_adapter_sha256')]:
            shutil.copy2(ROOT/name,package/name);config[key]=sha((ROOT/name).read_bytes())
        auxiliary=['semantic_eval.py','gold_cases.json']
        for name in auxiliary:shutil.copy2(ROOT/name,package/name)
        reused=[]
        for r in selected:
            identity={'engine':r['engine'],'raw_pixel_sha256':r['raw_pixel_sha256'],
                'input_pixel_sha256':r['input_pixel_sha256'],'native_ocr':r.get('native_ocr'),'config':config}
            r['cache_key']=sha(json.dumps(identity,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode())
            shutil.copy2(out/r['image'],package/r['image'])
            old=old_records.get(r.get('parent_id',r['id']))
            old_request=next((q for q in source['requests'] if old and q['id']==old['id']),None)
            if r['engine']=='formula' and old and old.get('status')=='ok' and not validate_prediction('formula',old.get('prediction')) and old_request['input_pixel_sha256']==r['input_pixel_sha256']:
                seeded=copy.deepcopy(old);seeded.update(id=r['id'],cache_key=r['cache_key'],semantic_verified=False,
                    reused_inference=True,source_cache_key=old['cache_key'],source_manifest_sha256=previous['manifest_sha256'])
                write(package/'seed_records'/f"{r['id']}.json",seeded);reused.append(r['id'])
            if r['engine']=='table' and old_request and old_request['input_pixel_sha256']==r['input_pixel_sha256'] and old_request.get('native_ocr')==r.get('native_ocr'):
                evidence=ROOT/'evidence/table_bbox_retry'/f"{r['id']}.json"
                if not evidence.exists():evidence=ROOT/'evidence/table_cpu_regression'/f"{r['id']}.json"
                if evidence.exists():
                    cpu=load(evidence)['fixed']
                    if not validate_prediction('table',cpu.get('prediction')):
                        seeded={'id':r['id'],'engine':'table','status':'ok','cache_key':r['cache_key'],
                            'raw_pixel_sha256':r['raw_pixel_sha256'],'prediction':cpu['prediction'],'device':'cpu',
                            'semantic_verified':False,'reused_inference':True,'source_cache_key':old['cache_key'],
                            'source_manifest_sha256':previous['manifest_sha256'],'evidence_sha256':sha(evidence.read_bytes())}
                        write(package/'seed_records'/f"{r['id']}.json",seeded);reused.append(r['id'])
        manifest={**source,'schema_version':'region-v2','config':config,'requests':selected,
                  'source_manifest_sha256':previous['manifest_sha256'],'stage':'baseline_canary' if size=='3B' else 'production',
                  'difficult_pages':DIFFICULT,'semantic_acceptance':False,'seeded_inference_ids':reused,
                  'seeded_inference_files':{p.name:sha(p.read_bytes()) for p in (package/'seed_records').glob('*.json')},
                  'auxiliary_files':{name:sha((ROOT/name).read_bytes()) for name in auxiliary}}
        manifest['source_regions_sha256']=manifest.pop('regions_sha256')
        write(package/'manifest.json',manifest)
        with zipfile.ZipFile(out/f'region_v2_{size}_input.zip','w',zipfile.ZIP_DEFLATED) as z:
            for p in sorted(package.rglob('*')):
                if p.is_file():z.write(p,p.relative_to(package).as_posix())
    from collections import Counter
    stats={'source_formula_requests':644,'formula_decisions':dict(Counter(r['decision'] for r in decisions)),
           'new_requests':dict(Counter(r['engine'] for r in unique)), 'exact_aliases':len(aliases),
           'baseline_difficult_pages':DIFFICULT,'reused_inference_ids':load(out/'7B/manifest.json')['seeded_inference_ids'],
           'preserved_cpt_samples':264,'new_verified_samples':0,'gpu_executed':False}
    write(out/'build_metrics.json',stats);print(json.dumps(stats,ensure_ascii=True,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,default=ROOT/'runs/it3170_v2');build(p.parse_args().out)
