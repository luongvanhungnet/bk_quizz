"""Native document classification, full-slide renders, contextual regions and provenance."""
import copy
import html
import json
from pathlib import Path
import shutil
from collections import Counter,defaultdict
import re
from PIL import Image,ImageStat
import pymupdf
from io_utils import canonical,sha,file_sha,load,jsonl,write_json,write_jsonl,normalize
from cross_validation import cross_validate
from models import validate_record

ROOT=Path(__file__).resolve().parent
V3=ROOT.parent/'region_preprocessing_v3/runs/it3170_v3_20261019'
REGIONS=ROOT.parent/'region_preprocessing/runs/it3170_scored_v3'
NATIVE=ROOT.parent/'hybrid_preprocessing/runs/it3170_test/native'
PILOT=[20,33,35,49,129,300,494,812,869,930,1042]

def image_diagnostics(path):
    im=Image.open(path).convert('RGB');gray=im.convert('L');stat=ImageStat.Stat(gray)
    out={'width':im.width,'height':im.height,'tiny_crop':min(im.size)<48,'near_blank':stat.stddev[0]<2,'issue_flags':[]}
    if out['tiny_crop']:out['issue_flags'].append('small_source_crop')
    if out['near_blank']:out['issue_flags'].append('near_blank_image')
    try:
        import cv2
        import numpy as np
        out['blur_score']=float(cv2.Laplacian(np.asarray(gray),cv2.CV_64F).var())
        # Low contrast/sharpness is a review hint, never proof of unreadability.
        if out['blur_score']<20:out['issue_flags'].append('low_sharpness_hint')
    except ImportError:out['blur_score']=None
    try:
        import imagehash
        out['phash']=str(imagehash.phash(im));out['perceptual_hash_method']='imagehash.phash'
    except ImportError:out['phash']=None;out['perceptual_hash_method']='unavailable'
    out['pixel_sha256']=sha(f'RGB:{im.width}:{im.height}:'.encode()+im.tobytes())
    return out

def native_pages(pdf,out):
    document=load(NATIVE/'document.json') if (NATIVE/'document.json').exists() else {}
    use_cache=document.get('sha256')==file_sha(pdf)
    cached={r['page']:r for r in jsonl(NATIVE/'native_pages.jsonl')} if use_cache else {}
    pages=[];classes=Counter()
    with pymupdf.open(pdf) as doc:
        for index,page in enumerate(doc):
            p=cached.get(index+1);target=out/f'assets/slides/page_{index+1:04d}.png'
            if p:
                source=Path(p['render_path']);source=source if source.is_absolute() else NATIVE/source
                if file_sha(source)!=p['render_sha256']:raise ValueError('Changed cached render')
                shutil.copy2(source,target);native=normalize('\n'.join(b['text'] for b in p['blocks']))
                w,h=Image.open(target).size;blocks=p['blocks']
            else:
                pix=page.get_pixmap(matrix=pymupdf.Matrix(1400/page.rect.width,1400/page.rect.width),alpha=False);pix.save(target)
                w,h=pix.width,pix.height;native=normalize(page.get_text('text',sort=True))
                blocks=[b for b in page.get_text('dict',sort=True)['blocks'] if b.get('type')==0]
            raw=page.get_text('text');images=page.get_images(full=True)
            if len(raw.strip())<10:kind='scanned_or_visual_only'
            elif images and len(raw.strip())<80:kind='mixed'
            else:kind='native_text'
            classes[kind]+=1
            pages.append({'page':index+1,'native_text':native,'blocks':blocks,'page_size_pt':list(page.rect)[2:],
                'render_path':target.relative_to(out).as_posix(),'render_sha256':file_sha(target),'width':w,'height':h,
                'text_layer_characters':len(raw.strip()),'document_class':kind,'native_cache_reused':bool(p)})
    return pages,dict(classes)

def context_crop(render,out_path,bbox):
    im=Image.open(render).convert('RGB');w,h=im.size
    x1,y1,x2,y2=bbox
    # Preserve nearby caption/title context rather than clipping just a shape.
    box=[max(0,int(x1*w/1000)-35),max(0,int(y1*h/1000)-65),min(w,int(x2*w/1000)+35),min(h,int(y2*h/1000)+65)]
    im.crop(box).save(out_path)
    return [box[0]*1000/w,box[1]*1000/h,box[2]*1000/w,box[3]*1000/h]

def text_in_box(page,bbox):
    x1,y1,x2,y2=bbox;w,h=page['page_size_pt'];spans=[]
    for block in page['blocks']:
        for line in block.get('lines',[]):
            for span in line.get('spans',[]):
                b=span['bbox'];cx=(b[0]+b[2])*500/w;cy=(b[1]+b[3])*500/h
                if x1<=cx<=x2 and y1<=cy<=y2:spans.append(span.get('text',''))
    return normalize(' '.join(spans))

def prepare(pdf,out,pptx=None):
    pdf=Path(pdf).resolve();out=Path(out).resolve()
    if out.exists():raise ValueError('Choose a fresh v5 run')
    for directory in ['assets/slides','assets/crops','assets/context','sources','machine_snapshots','external_raw']:(out/directory).mkdir(parents=True,exist_ok=True)
    digest=file_sha(pdf);pages,classes=native_pages(pdf,out);page_by_id={p['page']:p for p in pages}
    groups=load(V3/'benchmark_groups.json') if (V3/'manifest.json').exists() and load(V3/'manifest.json')['document']['sha256']==digest else {}
    protected=set(groups.get('protected_holdout_pages',[]));benchmark={r['page']:r for r in jsonl(V3/'benchmark_queue.jsonl')} if groups else {}
    pptx_candidates=[]
    if pptx:
        from adapters import extract_pptx
        pptx_candidates=extract_pptx(Path(pptx))
        pptx_pages={c['page'] for c in pptx_candidates if c.get('page')}
        if max(pptx_pages,default=0)!=len(pages):raise ValueError('PPTX/PDF slide count differs; explicit page mapping is required')
    records=[]
    def base(rid,page,kind,bbox,crop_path=None,native_text=''):
        p=page_by_id[page];crop_path=crop_path or p['render_path'];context='assets/context/'+rid.replace(':','_')+'.png'
        cb=context_crop(out/p['render_path'],out/context,bbox)
        b=benchmark.get(page,{});split='holdout' if page in protected else 'development' if b.get('split')=='development' else 'train'
        return {'id':rid,'page':page,'kind':kind,'bbox':bbox,'render_path':p['render_path'],'crop_path':crop_path,'context_path':context,
            'source_sha256':digest,'render_sha256':p['render_sha256'],'crop_sha256':file_sha(out/crop_path),
            'context_sha256':file_sha(out/context),'context_bbox':cb,'group_id':str(groups.get('page_to_group',{}).get(str(page),f'{digest[:12]}:p{page:04d}')),
            'split':split,'native_text':native_text,'candidates':[],'document_class':p['document_class'],
            'image_quality':image_diagnostics(out/crop_path),'pending_engines':[],'human_review_required':True,'semantic_verified':False}
    for p in pages:
        text=p['native_text'];kind='code' if len(re.findall(r'\b(?:for|while|return|int|void|include)\b',text))>7 else 'text'
        r=base(f'{digest[:12]}:p{p["page"]:04d}:text',p['page'],kind,[0,0,1000,1000],native_text=text)
        r['candidates']=[{'engine':'native','text':text,'status':'ok' if text.strip() else 'empty','evidence':{'backend_family':'pymupdf','lineage':'pymupdf','source_sha256':digest,'render_sha256':p['render_sha256'],'region_id':r['id'],'crop_sha256':r['crop_sha256']}}]
        if pptx_candidates:
            parts=[c for c in pptx_candidates if c.get('page')==p['page']]
            r['candidates'].append({'engine':'native_pptx','text':'\n'.join(c['text'] for c in parts),'status':'ok','evidence':{'backend_family':'native_office','lineage':'native_office','source_sha256':digest,'pptx_source_sha256':file_sha(pptx),'paired_pdf_sha256':digest,'association':'explicit_user_paired_same_slide_count'}})
            r['preferred_native_source']='native_pptx'
        r['pending_engines']=['paddle_ocr'];r['optional_engines']=['docling','mineru'];records.append(r)
    source=load(V3/'manifest.json') if (V3/'manifest.json').exists() and load(V3/'manifest.json')['document']['sha256']==digest else None
    region_sources=[]
    if source:
        # Preserve the corrected formula crops and successful specialist seeds.
        region_sources=[(r,V3) for r in source['requests'] if r['engine']!='vlm']
        # Bring all known visual candidates into review, not only the old score quota.
        region_sources += [(r,REGIONS) for r in jsonl(REGIONS/'regions.jsonl') if r['engine']=='vlm']
    else:
        # Generic documents: keep image rectangles and native text; external
        # layout parsers can corroborate existing regions; unmatched components
        # remain in import receipts for explicit routing instead of vanishing.
        with pymupdf.open(pdf) as doc:
            for i,page in enumerate(doc):
                for n,img in enumerate(page.get_images(full=True)):
                    for occurrence,box in enumerate(page.get_image_rects(img[0])):
                        region_sources.append(({'id':f'p{i+1:04d}_image{n}_instance{occurrence}','page':i+1,'engine':'vlm','bbox_pixels':[box.x0*page_by_id[i+1]['width']/page.rect.width,box.y0*page_by_id[i+1]['height']/page.rect.height,box.x1*page_by_id[i+1]['width']/page.rect.width,box.y1*page_by_id[i+1]['height']/page.rect.height]},None))
    for q,root in region_sources:
        p=page_by_id[q['page']];b=q['bbox_pixels'];bbox=[max(0,min(1000,v*1000/(p['width'] if i%2==0 else p['height']))) for i,v in enumerate(b)]
        if bbox[2]<=bbox[0] or bbox[3]<=bbox[1]:continue
        kind='formula' if q['engine']=='formula' else 'table' if q['engine']=='table' else 'diagram'
        rid=q['id'];target='assets/crops/'+rid+'.png'
        if root and (root/q.get('image','')).is_file():
            source_crop=root/q['image']
            if file_sha(source_crop)!=q['input_file_sha256']:raise ValueError('Changed region crop')
            shutil.copy2(source_crop,out/target)
        else:
            im=Image.open(out/p['render_path']);im.crop(tuple(int(v*im.size[i%2]/1000) for i,v in enumerate(bbox))).save(out/target)
        native=text_in_box(p,bbox);r=base(rid,q['page'],kind,bbox,target,native)
        r.update(legacy_routing_state=q.get('state'),legacy_priority=q.get('priority'),layout_score=q.get('layout_score'))
        if native:r['candidates'].append({'engine':'native','text':native,'status':'ok','evidence':{'lineage':'pymupdf','source_sha256':digest,'region_id':r['id'],'crop_sha256':r['crop_sha256'],'same_region':True}})
        seed=V3/'seeds'/(q['id']+'.json')
        if kind in ['formula','table'] and seed.exists():
            s=load(seed);pred=s.get('prediction') or {};text=pred.get('latex','') if kind=='formula' else pred.get('html','')
            r['candidates'].append({'engine':'paddle_formula' if kind=='formula' else 'paddle_table','text':text,'status':'ok' if s['status']=='ok' else 'error',
                'evidence':{'backend_family':'paddle','lineage':'paddle','seed_sha256':file_sha(seed),'source_sha256':digest,'input_file_sha256':r['crop_sha256'],
                            'structural_errors':s.get('structural_errors',[]),'reuse_only':True}})
            r['native_ocr']=q.get('native_ocr',[])
        r['pending_engines']=['vlm'] if kind=='diagram' else [];r['optional_engines']=['docling','mineru']
        records.append(r)
    # Similar image hash only proposes review groups: never delete changed weights,
    # directions, colors, symbols or distinct board states.
    hashes=defaultdict(list)
    for r in records:
        if r['kind']!='text' and r['image_quality'].get('phash'):hashes[r['image_quality']['phash']].append(r['id'])
    duplicates=[{'method':'perceptual_hash_candidate_only','records':ids,'automatically_removed':False} for ids in hashes.values() if len(ids)>1]
    processed=[validate_record(cross_validate(r)) for r in records]
    write_jsonl(out/'records.jsonl',processed);write_jsonl(out/'machine_snapshots/initial.jsonl',processed)
    write_jsonl(out/'document_pages.jsonl',[{k:v for k,v in p.items() if k!='blocks'} for p in pages])
    write_json(out/'duplicate_candidates.json',duplicates)
    write_json(out/'classification.json',{'pages':len(pages),'page_classes':classes,'classification_scope':'native_text_presence_is_not_proof_of_text_accuracy','pptx_supplied':bool(pptx),'pptx_priority':bool(pptx_candidates)})
    if groups:write_json(out/'benchmark_groups.json',groups);write_jsonl(out/'benchmark_queue.jsonl',list(benchmark.values()))
    pilot=PILOT if source else sorted({1,max(1,len(pages)//4),max(1,len(pages)//2),max(1,3*len(pages)//4),len(pages)})
    manifest={'schema_version':'it3170-preprocessing-v5','document':{'sha256':digest,'path':str(pdf),'pages':len(pages)},'asset_root':str(out),
        'records':'records.jsonl','pilot_pages':pilot,'source_pptx':str(pptx) if pptx else None,'human_review_policy':'explicit_human_approve_or_correct_only',
        'layout_inventory_status':'cached_inventory' if source else 'requires_layout_enrichment',
        'vlm_policy':'one_image_one_plain_text_observation_no_required_graph_inventory','created_date':'2026-10-20','initial_records_sha256':file_sha(out/'records.jsonl')}
    write_json(out/'manifest.json',manifest)
    write_json(out/'prepare_summary.json',{'records':len(processed),'by_kind':dict(Counter(r['kind'] for r in processed)),
        'buckets':dict(Counter(r['machine_bucket'] for r in processed)),'unverified_predictions_exported':0,'full_source_renders':len(pages),
        'reused_layout_and_specialist_cache':bool(source),'perceptual_duplicate_groups':len(duplicates),'training_ready':False})
    print(out);return out

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--pdf',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--pptx',type=Path)
    a=p.parse_args();prepare(a.pdf,a.out,a.pptx)
