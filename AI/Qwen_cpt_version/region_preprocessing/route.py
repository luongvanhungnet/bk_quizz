"""Region routing with an honest VLM page budget and source-bound review gates."""
import argparse
import collections
import hashlib
import json
import math
import sys
import time
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parent
BASE=ROOT.parent/'data_preprocessing'
sys.path.insert(0,str(BASE/'src'))
from common import digest,dump_json,read_jsonl,write_jsonl,area,overlap,box_union,normalize,redact
from pack_qwen import pack_records

DEFAULT_NATIVE=ROOT.parent/'hybrid_preprocessing/runs/it3170_test/native'
DEFAULT_OLD=BASE/'outputs/it3170'
DEFAULT_TOKENIZER=ROOT.parent/'local_qwen3/models/merged_hf_fp16'
MODEL_REVISION='66285546d2b821cf421d4f5eb2576359d3770cd3'
SCHEMA='region-routing-v1'


def load(path):return json.loads(Path(path).read_text(encoding='utf-8'))


def strict_page_budget(n,ratio=.05):
    if n<1 or not 0<ratio<=1:raise ValueError('Invalid page count/ratio')
    return max(0,math.ceil(n*ratio)-1)


def pixel_hash(im):
    rgb=im.convert('RGB')
    return hashlib.sha256(f'RGB:{rgb.width}:{rgb.height}:'.encode()+rgb.tobytes()).hexdigest()


def resize_crop(im,engine):
    from PIL import Image
    longest=1024 if engine=='vlm' else 1800
    limit=768*28*28 if engine=='vlm' else 1800*1800
    scale=min(1,longest/max(im.size),math.sqrt(limit/(im.width*im.height)))
    if scale<1:im=im.resize((max(1,int(im.width*scale)),max(1,int(im.height*scale))),Image.Resampling.LANCZOS)
    return im


def contains(a,b,ratio=.85):return overlap(a,b)/max(1,area(b))>=ratio


def collapse_regions(items):
    """Only remove nested same-engine detections; keep graphs with changed content."""
    result=[]
    for item in sorted(items,key=lambda x:area(x['bbox_pixels']),reverse=True):
        if any(r['engine']==item['engine'] and contains(r['bbox_pixels'],item['bbox_pixels']) for r in result):continue
        result.append(item)
    return result


def schedule(regions,n,budget):
    candidates=[r for r in regions if r['engine']=='vlm' and r['state']=='candidate']
    pages=collections.defaultdict(list)
    for r in candidates:pages[r['page']].append(r)
    # Round robin slide sections avoids spending every slot on adjacent states.
    sections=collections.defaultdict(list)
    for page,items in pages.items():sections[(page-1)//50].append((max(r['priority'] for r in items),page))
    for values in sections.values():values.sort(reverse=True)
    selected=[]
    while len(selected)<budget and any(sections.values()):
        for section in sorted(sections):
            if sections[section] and len(selected)<budget:selected.append(sections[section].pop(0)[1])
    selected=set(selected)
    for r in candidates:r['state']='scheduled' if r['page'] in selected else 'deferred_budget'
    for r in regions:
        if r['engine'] in ['formula','table'] and r['state']=='candidate':r['state']='scheduled'
    return {'natural_unique_vlm_pages':len(pages),'natural_unique_vlm_page_ratio':len(pages)/n,
            'scheduled_vlm_pages':sorted(selected),'scheduled_vlm_page_ratio':len(selected)/n,
            'budget_pages':budget,'strict_under_five_percent':len(selected)/n<.05,
            'deferred_unique_vlm_pages':sorted(set(pages)-selected)}


def regions_for_page(page,boxes):
    scale=page['render_width']/page['page_size_pt'][0]
    result=[];ignored=[]
    code=[[v*scale for v in b['bbox']] for b in page['blocks'] if b['type']=='code']
    W=page['render_width'];H=page['page_size_pt'][1]*scale
    # Syntax-highlighted code has one vector rectangle per line. Protect the
    # full detector algorithm region, not just each fragment of native text.
    if code:code += [b['coordinate'] for b in boxes if b['label']=='algorithm']
    for b in boxes:
        label=b['label'];coords=b['coordinate']
        if label in ['footer','footer_image','header','number','seal']:
            # Require geometric margin too; a misclassified body figure is retained.
            center=(coords[1]+coords[3])/2
            if coords[1]>H*.87 or coords[3]<H*.15 or (area(coords)<W*H*.08 and (center>H*.9 or center<H*.1)):
                ignored.append({'label':label,'bbox_pixels':coords,'reason':'layout_margin_decoration'});continue
            if label not in ['number']:label='image'
        engine={'formula':'formula','table':'table','image':'vlm','figure':'vlm','chart':'vlm'}.get(label)
        if not engine:continue
        if any(contains(c,coords,.65) for c in code):
            ignored.append({'label':label,'bbox_pixels':coords,'reason':'native_code_preserved'});continue
        if area(coords)<160:
            ignored.append({'label':label,'bbox_pixels':coords,'reason':'tiny_region_review','review_required':True});continue
        result.append({'engine':engine,'bbox_pixels':coords,'label':label,'layout_score':b.get('score'),
                       'method':'layout_model','priority':float(b.get('score',0))})
    # Include native formula candidates missed by the detector, including superscripts.
    for b in page['blocks']:
        if b['math_candidate'] and b['type']!='code':
            coords=[v*scale for v in b['bbox']]
            if not any(r['engine']=='formula' and contains(r['bbox_pixels'],coords,.5) for r in result):
                result.append({'engine':'formula','bbox_pixels':coords,'label':'native_math_candidate',
                               'layout_score':None,'method':'native_math_baseline','priority':0})
    # Vector fallback is deliberately uncertain; no uncovered body vectors disappear.
    vectors=page.get('vector_regions',[])
    if len(vectors)>=3:
        stripes=sum((v['bbox'][2]-v['bbox'][0])*scale>W*.4 and
                    (v['bbox'][3]-v['bbox'][1])*scale<H*.06 and v.get('primitive_count',99)<=2 for v in vectors)
        if code and stripes/len(vectors)>=.8:
            ignored.append({'label':'code_background','reason':'native_code_line_backgrounds','bbox_pixels':None})
            return collapse_regions(result),ignored
        vector=[v*scale for v in box_union(x['bbox'] for x in vectors)]
        if area(vector)>W*H*.025 and not any(contains(c,vector,.65) for c in code) and not any(
                r['engine'] in ['vlm','table'] and contains(r['bbox_pixels'],vector,.7) for r in result):
            result.append({'engine':'vlm','bbox_pixels':vector,'label':'unclassified_body_vectors',
                           'layout_score':None,'method':'vector_fallback_requires_review','priority':.1})
    return collapse_regions(result),ignored


def native_table_ocr(page,clip,size):
    scale=page['render_width']/page['page_size_pt'][0]
    sx=size[0]/(clip[2]-clip[0]);sy=size[1]/(clip[3]-clip[1]);lines=[]
    for b in page['blocks']:
        for line in b.get('lines',[]):
            box=[v*scale for v in line['bbox']]
            if contains(clip,box,.95) and line['text'].strip():
                lines.append({'text':line['text'],'bbox':[(box[0]-clip[0])*sx,(box[1]-clip[1])*sy,
                                                         (box[2]-clip[0])*sx,(box[3]-clip[1])*sy]})
    return lines


def plan(a):
    from PIL import Image
    import pymupdf
    start=time.perf_counter();out=a.out.resolve()
    if (out/'manifest.json').exists():raise ValueError('Completed plan exists; use a new --out')
    document=load(a.native/'document.json');pdf=Path(document['path'])
    if digest(pdf.read_bytes())!=document['sha256']:raise ValueError('Source PDF changed')
    with pymupdf.open(pdf) as source:
        if len(source)!=document['pages']:raise ValueError('PDF page count changed')
    pages=read_jsonl(a.native/'native_pages.jsonl');notes={r['page']:r for r in read_jsonl(a.previous/'reviewed_annotations.jsonl')}
    routing_notes={r['page']:r for r in read_jsonl(ROOT/'routing_annotations.jsonl')}
    for p in pages:
        note=routing_notes.get(p['page'])
        if note and note.get('verified') and note.get('reviewer') and note.get('evidence') and all(
                note.get(k)==p[k] for k in ['document_sha256','render_sha256']):
            if note.get('disposition')=='non_content':notes[p['page']]=note
    verified={};non_content=set()
    for p in pages:
        note=notes.get(p['page'])
        if note and note.get('verified') is True and note.get('reviewer') and note.get('evidence') and all(
                note.get(k)==p[k] for k in ['document_sha256','render_sha256']):
            verified[p['page']]=note
            if note.get('disposition')=='non_content':non_content.add(p['page'])
    regions=[];ignored=[];missing_layout=[];layout_sources={};detector=None;source_hashes={}
    for p in pages:
        image=a.native/p['render_path']
        if digest(image.read_bytes())!=p['render_sha256']:raise ValueError('Damaged source render')
        source_hashes[p['page']]=p['render_sha256']
        cache=a.previous/'components'/f"page_{p['page']:04d}.json"
        record=load(cache) if cache.exists() else {}
        valid=record.get('status')=='ok' and record.get('layout_model')=='PP-DocLayout-M' and all(
            record.get(k)==p[k] for k in ['document_sha256','render_sha256'])
        if valid:
            boxes=record['result']['layout_det_res'].get('boxes',[])
            layout_sources[p['page']]={'kind':'verified_existing_layout_cache','sha256':digest(cache.read_bytes())}
        elif a.detect_missing:
            if detector is None:
                from paddleocr import LayoutDetection
                detector=LayoutDetection(model_name='PP-DocLayout-M',device='cpu',cpu_threads=4,enable_mkldnn=False)
            raw=next(iter(detector.predict(str(image),batch_size=1))).json
            if isinstance(raw,str):raw=json.loads(raw)
            boxes=raw.get('res',raw).get('boxes',[])
            dump_json(out/'layout'/f"page_{p['page']:04d}.json",{'document_sha256':p['document_sha256'],
                       'render_sha256':p['render_sha256'],'result':raw})
            layout_sources[p['page']]={'kind':'fresh_cpu_layout'}
        else:
            missing_layout.append(p['page']);boxes=[]
        items,removed=regions_for_page(p,boxes)
        ignored += [{'page':p['page'],**x} for x in removed]
        if p['page'] in non_content:
            ignored.append({'page':p['page'],'reason':'source_bound_reviewed_non_content'});continue
        with Image.open(image) as im:
            for item in items:
                box=item['bbox_pixels'];clip=[max(0,math.floor(box[0])-8),max(0,math.floor(box[1])-8),
                                             min(im.width,math.ceil(box[2])+8),min(im.height,math.ceil(box[3])+8)]
                if clip[2]<=clip[0] or clip[3]<=clip[1]:continue
                raw=im.crop(clip).convert('RGB');optimized=resize_crop(raw,item['engine'])
                region_id=f"p{p['page']:04d}_r{len(regions):05d}"
                target=out/'crops'/f'{region_id}.png';target.parent.mkdir(parents=True,exist_ok=True);optimized.save(target)
                item.update(id=region_id,page=p['page'],document_sha256=p['document_sha256'],
                    render_sha256=p['render_sha256'],bbox_pixels=clip,raw_pixel_sha256=pixel_hash(raw),
                    input_pixel_sha256=pixel_hash(optimized),input_file_sha256=digest(target.read_bytes()),
                    image=target.relative_to(out).as_posix(),original_size=list(raw.size),input_size=list(optimized.size),
                    state='reviewed_source' if p['page'] in verified else 'candidate',verified=p['page'] in verified)
                routing_note=routing_notes.get(p['page'])
                if routing_note and routing_note.get('reviewer') and routing_note.get('evidence') and routing_note.get('routing')=='illustration_review' and all(
                        routing_note.get(k)==p[k] for k in ['document_sha256','render_sha256']) and routing_note.get('verified') and item['engine']=='vlm':
                    item.update(engine='review',state='illustration_requires_review',verified=False,
                                routing_evidence=routing_note['evidence'])
                if item['engine']=='table':item['native_ocr']=native_table_ocr(p,clip,optimized.size)
                regions.append(item)
        if p['page']%100==0:print('routed',p['page'],'regions',len(regions),flush=True)
    # Equality uses pre-resize pixels. Downsampling cannot merge changed small labels.
    canonical={};aliases=collections.defaultdict(list)
    for r in regions:
        key=(r['engine'],r['raw_pixel_sha256'])
        if r['state']=='reviewed_source':continue
        if key in canonical:
            r['state']='exact_duplicate';r['duplicate_of']=canonical[key]['id'];aliases[canonical[key]['id']].append(r['id'])
        else:canonical[key]=r
    budget=strict_page_budget(len(pages),a.max_page_ratio)
    stats=schedule(regions,len(pages),budget)
    if stats['scheduled_vlm_page_ratio']>=a.max_page_ratio:raise AssertionError('VLM page budget exceeded')
    config={'schema':SCHEMA,'vlm_model':'Qwen/Qwen2.5-VL-3B-Instruct','vlm_revision':MODEL_REVISION,
            'vlm_batch_size':a.batch_size,'max_visual_tokens':768,'max_new_tokens':1024,'dtype':'float16',
            'do_sample':False,'formula_model':'PP-FormulaNet-S','table_model':'TableRecognitionPipelineV2',
            'table_text_source':'native_pdf_no_automatic_Vietnamese_OCR','crop_padding_pixels':8,
            'paddle_versions_expected':{'paddleocr':'3.7.0','paddlex':'3.7.2','paddlepaddle-gpu':'3.2.2'},
            'validation_sha256':digest((ROOT/'validation.py').read_bytes()),
            'routing_annotations_sha256':digest((ROOT/'routing_annotations.jsonl').read_bytes()) if (ROOT/'routing_annotations.jsonl').exists() else None,
            'prompt_sha256':digest((ROOT/'prompt.txt').read_bytes()),'worker_sha256':digest((ROOT/'worker.py').read_bytes())}
    for r in regions:
        # Table native text can change the output even if the crop stays the same.
        payload={'engine':r['engine'],'raw_pixel_sha256':r['raw_pixel_sha256'],
                 'input_pixel_sha256':r['input_pixel_sha256'],'native_ocr':r.get('native_ocr'), 'config':config}
        r['cache_key']=digest(json.dumps(payload,sort_keys=True,ensure_ascii=False,separators=(',',':')))
    scheduled=[r for r in regions if r['state']=='scheduled']
    pending={r['page'] for r in regions if r['state']!='reviewed_source'}|set(missing_layout)
    pending|={r['page'] for r in ignored if r.get('review_required')}
    previous=read_jsonl(a.previous/'cpt/train.metadata.jsonl')
    previous_normalized={r['page']:r for r in read_jsonl(a.previous/'normalized.jsonl')}
    carried=[r for r in previous if r.get('quality',{}).get('status')=='accepted' and r['page'] not in pending
             and r['text']==previous_normalized[r['page']]['text'] and r['source']['document_sha256']==document['sha256']
             and r['source']['render_sha256']==source_hashes[r['page']]]
    write_jsonl(out/'regions.jsonl',regions);write_jsonl(out/'ignored_regions.jsonl',ignored)
    write_jsonl(out/'carried_train.metadata.jsonl',carried)
    review=[{'page':p['page'],'document_sha256':p['document_sha256'],'render_sha256':p['render_sha256'],
             'reasons':sorted(set(['layout_missing'] if p['page'] in missing_layout else [])|
                       set(previous_normalized.get(p['page'],{}).get('quality',{}).get('flags',[]))|
                       {r['state'] for r in regions if r['page']==p['page'] and r['state']!='reviewed_source'}),
             'region_ids':[r['id'] for r in regions if r['page']==p['page']],
             'source_image':str((a.native/p['render_path']).resolve()),'verified':False}
            for p in pages if p['page'] not in {r['page'] for r in carried} and p['page'] not in non_content]
    write_jsonl(out/'review_queue.jsonl',review)
    manifest={'schema_version':SCHEMA,'document':document,'config':config,'requests':scheduled,
              'layout_sources':layout_sources,'source_render_hashes':source_hashes,
              'regions_sha256':digest((out/'regions.jsonl').read_bytes()),
              'source_native_root':str(a.native.resolve()),'budget':stats}
    dump_json(out/'manifest.json',manifest)
    with zipfile.ZipFile(out/'region_input.zip','w',zipfile.ZIP_DEFLATED) as z:
        z.write(out/'manifest.json','manifest.json')
        for r in scheduled:z.write(out/r['image'],r['image'])
        for name in ['worker.py','prompt.txt','validation.py']:z.write(ROOT/name,name)
    report={**stats,'pages_total':len(pages),'reviewed_source_pages_reused':len(verified),
            'excluded_reviewed_non_content_pages':len(non_content),'regions':len(regions),
            'region_engine_counts':dict(collections.Counter(r['engine'] for r in regions)),
            'ignored_region_reasons':dict(collections.Counter(r['reason'] for r in ignored)),
            'region_state_counts':dict(collections.Counter(r['state'] for r in regions)),
            'scheduled_requests_by_engine':dict(collections.Counter(r['engine'] for r in scheduled)),
            'deduplicated_exact_regions':sum(r['state']=='exact_duplicate' for r in regions),
            'vlm_alias_coverage_pages':len({r['page'] for r in regions if r['engine']=='vlm' and
                   (r['state']=='scheduled' or r.get('duplicate_of') in {v['id'] for v in scheduled})}),
            'layout_cache_pages':sum(v['kind']=='verified_existing_layout_cache' for v in layout_sources.values()),
            'layout_missing_pages':missing_layout,'carried_train_samples':len(carried),'review_queue_pages':len(review),
            'elapsed_local_seconds':time.perf_counter()-start,'gpu_inference_executed':False,
            'full_knowledge_coverage_met':False,'note':'Budget compliance is not content coverage. Deferred/uncertain regions remain in review.'}
    dump_json(out/'routing_report.json',report)
    print(json.dumps(report,ensure_ascii=False,indent=2))
    pack(carried,out/'cpt',a.tokenizer)


def pack(rows,out,tokenizer):
    sys.path.insert(0,str(ROOT.parent))
    from hybrid_preprocessing.local_pipeline import dedup
    dump_json(out/'text_deduplication.json',dedup(rows))
    from transformers import AutoTokenizer
    tok=AutoTokenizer.from_pretrained(str(tokenizer),local_files_only=True,trust_remote_code=False)
    if tok.eos_token_id is None:raise ValueError('Missing EOS')
    unique=[];seen=set()
    for row in rows:
        key=digest(row['text'])
        if key not in seen:unique.append(row);seen.add(key)
    packs=list(pack_records(unique,lambda s:tok.encode(s,add_special_tokens=False),tok.eos_token_id,1024))
    actual=[t for p in packs for t in p['input_ids']]
    expected=[t for r in unique for t in tok.encode(r['text'],add_special_tokens=False)+[tok.eos_token_id]]
    assert actual==expected
    write_jsonl(out/'train.jsonl',({'text':r['text']} for r in unique));write_jsonl(out/'train.metadata.jsonl',unique)
    write_jsonl(out/'train.packed.jsonl',({k:v for k,v in p.items() if k!='source_spans'} for p in packs))
    write_jsonl(out/'train.packed.sources.jsonl',({'index':i,'source_spans':p['source_spans']} for i,p in enumerate(packs)))
    dump_json(out/'manifest.json',{'samples':len(unique),'tokens':len(actual),'sequence_length':1024,
              'sequences':len(packs),'tokenizer_source':str(tokenizer),'eos_token_id':tok.eos_token_id,
              'tokenizer_files_sha256':{p.name:digest(p.read_bytes()) for p in tokenizer.glob('*token*') if p.is_file()},
              'chat_template_applied':False,'cross_sample_attention':True,'labels_shift':'causal_model_shifts_once',
              'all_tokens_preserved':True,'all_pdf_content_complete':False,'split_policy':'one_document_train_only',
              'training_layer':'prior_accepted_native_or_hash_bound_reviewed_transcripts_only'})


def merge(a):
    from validation import validate_prediction
    manifest=load(a.out/'manifest.json');identity=digest((a.out/'manifest.json').read_bytes())
    with zipfile.ZipFile(a.results) as z:results=json.loads(z.read('results.json'))
    if results['manifest_sha256']!=identity:raise ValueError('Wrong routing manifest')
    requests={r['id']:r for r in manifest['requests']};checked=[]
    if len({r['id'] for r in results['records']})!=len(results['records']):raise ValueError('Duplicate result')
    for r in results['records']:
        request=requests[r['id']]
        if r['cache_key']!=request['cache_key']:raise ValueError('Stale prediction cache identity')
        errors=validate_prediction(request['engine'],r.get('prediction')) if r.get('status')=='ok' else ['inference_failed_or_invalid_json']
        checked.append({'request':request,'result':r,'structural_errors':errors,
                        'semantic_verified':False,'destination':'review_queue'})
    if {r['id'] for r in results['records']}!=set(requests):raise ValueError('Missing region results')
    write_jsonl(a.out/'prediction_review.jsonl',checked)
    rows=read_jsonl(a.out/'carried_train.metadata.jsonl')
    if a.reviews:
        approved=read_jsonl(a.reviews);seen=set()
        original={r['page']:r for r in read_jsonl(a.out/'review_queue.jsonl')}
        for review in approved:
            p=review['page']
            if p in seen:raise ValueError('Duplicate review page')
            seen.add(p);source=original[p]
            if not (review.get('verified') is True and review.get('reviewer') and review.get('evidence') and
                    isinstance(review.get('text'),str) and review['text'].strip()):raise ValueError('Incomplete semantic review')
            if any(review.get(k)!=source[k] for k in ['document_sha256','render_sha256']):raise ValueError('Stale source review')
            rows=[r for r in rows if r['page']!=p]
            rows.append({'id':f"{manifest['document']['id']}:p{p:04d}",'page':p,
                         'text':redact(normalize(review['text'],code=True))[0],
                         'source':{'document_sha256':review['document_sha256'],'render_sha256':review['render_sha256'],
                                   'page':p,'pdf_path':manifest['document']['path']},'review':review})
    pack(rows,a.out/'cpt',a.tokenizer)
    print('Validated structural predictions stay in review; CPT contains only previously accepted/source-reviewed text.')


if __name__=='__main__':
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='action',required=True)
    a=sub.add_parser('plan');a.add_argument('--native',type=Path,default=DEFAULT_NATIVE)
    a.add_argument('--previous',type=Path,default=DEFAULT_OLD)
    a.add_argument('--max-page-ratio',type=float,default=.05);a.add_argument('--detect-missing',action='store_true')
    a.add_argument('--batch-size',type=int,choices=[1,2,4],default=2)
    b=sub.add_parser('merge');b.add_argument('--results',type=Path,required=True);b.add_argument('--reviews',type=Path)
    for x in [a,b]:
        x.add_argument('--out',type=Path,default=ROOT/'runs/it3170_regions_v4')
        x.add_argument('--tokenizer',type=Path,default=DEFAULT_TOKENIZER)
    args=p.parse_args();plan(args) if args.action=='plan' else merge(args)
