"""Generic PDF native preparation, checkpointed in bounded page groups.

The frozen v5 record validators, normalization, rendering scale, contextual crop
and image diagnostics are reused. Existing seed runs are never regenerated.
"""
from collections import Counter, defaultdict
import gc
import json
from pathlib import Path
import re
import shutil

from common import atomic_json, checkpoint, digest, load, rows
from telemetry import event, span


def prepare_native(job, remote, batch_pages=20):
    import pymupdf
    from PIL import Image
    from prepare import context_crop, image_diagnostics, text_in_box
    from io_utils import normalize
    from cross_validation import cross_validate
    from models import validate_record
    run, pdf = Path(job['run']), Path(job['source_path'])
    if digest(pdf) != job['source_sha256']: raise ValueError('Native source changed')
    for directory in ['assets/slides','assets/crops','assets/context','sources','machine_snapshots','external_raw','native_batches']:
        (run/directory).mkdir(parents=True, exist_ok=True)
    if (run/'manifest.json').exists():
        if load(run/'manifest.json')['document']['sha256'] != job['source_sha256']:
            raise ValueError('Existing native source mismatch')
        if not (run/'records.jsonl').exists(): raise ValueError('Existing native records missing')
        return
    if batch_pages < 1: raise ValueError('batch_pages must be positive')
    progress_path = run/'native_progress.json'
    progress = load(progress_path) if progress_path.exists() else {'source_sha256': job['source_sha256'], 'batches': []}
    if progress['source_sha256'] != job['source_sha256']: raise ValueError('Partial native source mismatch')
    committed = {b['first']: b for b in progress['batches']}
    hashes = defaultdict(list)
    classes = Counter(); buckets=Counter(); kinds=Counter(); count=0
    with pymupdf.open(pdf) as doc:
        total = len(doc)
        for first in range(1,total+1,batch_pages):
            last = min(total, first+batch_pages-1)
            stem = f'{first:05d}-{last:05d}'
            rp=run/'native_batches'/f'{stem}_records.jsonl'; pp=run/'native_batches'/f'{stem}_pages.jsonl'
            if first in committed:
                old=committed[first]
                if old['last']!=last or digest(rp)!=old['records_sha256'] or digest(pp)!=old['pages_sha256']:
                    raise ValueError('Native checkpoint batch changed or batch size changed')
            else:
                with span('native_batch', document=job['document_id'], first=first, last=last):
                    batch_records=[]; batch_metadata=[]
                    for number in range(first,last+1):
                        page=doc[number-1]; target=run/f'assets/slides/page_{number:04d}.png'
                        scale=1400/page.rect.width
                        pix=page.get_pixmap(matrix=pymupdf.Matrix(scale,scale),alpha=False); pix.save(target)
                        raw=page.get_text('text'); text=normalize(page.get_text('text',sort=True))
                        classification='scanned_or_visual_only' if len(raw.strip())<10 else 'mixed' if page.get_images(full=True) and len(raw.strip())<80 else 'native_text'
                        meta={'page':number,'native_text':text,'blocks':[b for b in page.get_text('dict',sort=True)['blocks'] if b.get('type')==0],
                              'page_size_pt':list(page.rect)[2:],'render_path':target.relative_to(run).as_posix(),'render_sha256':digest(target),
                              'width':pix.width,'height':pix.height,'text_layer_characters':len(raw.strip()),
                              'document_class':classification,'native_cache_reused':False}
                        del pix

                        def base(rid,kind,bbox,crop=None,native=''):
                            crop=crop or meta['render_path']; context='assets/context/'+rid.replace(':','_')+'.png'
                            cb=context_crop(target,run/context,bbox)
                            return {'id':rid,'page':number,'kind':kind,'bbox':bbox,'render_path':meta['render_path'],
                                'crop_path':crop,'context_path':context,'context_bbox':cb,'source_sha256':job['source_sha256'],
                                'render_sha256':meta['render_sha256'],'crop_sha256':digest(run/crop),'context_sha256':digest(run/context),
                                'group_id':'course:'+job['course'],'split':job['split_policy'],'native_text':native,'candidates':[],
                                'document_class':classification,'image_quality':image_diagnostics(run/crop),'pending_engines':[],
                                'human_review_required':True,'semantic_verified':False,'optional_engines':['docling','mineru']}

                        kind='code' if len(re.findall(r'\b(?:for|while|return|int|void|include)\b',text))>7 else 'text'
                        r=base(f'{job["source_sha256"][:12]}:p{number:04d}:text',kind,[0,0,1000,1000],native=text)
                        r['candidates']=[{'engine':'native','text':text,'status':'ok' if text.strip() else 'empty',
                            'evidence':{'backend_family':'pymupdf','lineage':'pymupdf','source_sha256':job['source_sha256'],
                                        'render_sha256':r['render_sha256'],'region_id':r['id'],'crop_sha256':r['crop_sha256']}}]
                        r['pending_engines']=['paddle_ocr'];batch_records.append(validate_record(cross_validate(r)))
                        for n,img in enumerate(page.get_images(full=True)):
                            for occurrence,box in enumerate(page.get_image_rects(img[0])):
                                bbox=[max(0,min(1000,v)) for v in [box.x0*1000/page.rect.width,box.y0*1000/page.rect.height,
                                                                                box.x1*1000/page.rect.width,box.y1*1000/page.rect.height]]
                                if bbox[2]<=bbox[0] or bbox[3]<=bbox[1]: continue
                                rid=f'p{number:04d}_image{n}_instance{occurrence}';crop='assets/crops/'+rid+'.png'
                                with Image.open(target) as im:
                                    im.crop(tuple(int(v*im.size[i%2]/1000) for i,v in enumerate(bbox))).save(run/crop)
                                r=base(rid,'diagram',bbox,crop,text_in_box(meta,bbox))
                                r.update(legacy_routing_state=None,legacy_priority=None,layout_score=None)
                                if r['native_text']:
                                    r['candidates']=[{'engine':'native','text':r['native_text'],'status':'ok','evidence':{
                                        'lineage':'pymupdf','source_sha256':job['source_sha256'],'region_id':rid,
                                        'crop_sha256':r['crop_sha256'],'same_region':True}}]
                                r['pending_engines']=['vlm'];batch_records.append(validate_record(cross_validate(r)))
                        batch_metadata.append({k:v for k,v in meta.items() if k!='blocks'})
                        del meta, page
                    for path, values in [(rp,batch_records),(pp,batch_metadata)]:
                        temp=path.with_suffix('.next')
                        with temp.open('w',encoding='utf-8') as f:
                            for value in values:f.write(json.dumps(value,ensure_ascii=False,allow_nan=False)+'\n')
                        temp.replace(path)
                    progress['batches'].append({'first':first,'last':last,'records_sha256':digest(rp),'pages_sha256':digest(pp)})
                    atomic_json(progress_path,progress)
                    del batch_records,batch_metadata
                    gc.collect()
                    with span('native_checkpoint',document=job['document_id'],last=last):checkpoint(run,remote)
                    print(f'NATIVE {job["document_id"]} {last}/{total}',flush=True)
            for p in rows(pp): classes[p['document_class']]+=1
            for r in rows(rp):
                count+=1;kinds[r['kind']]+=1;buckets[r['machine_bucket']]+=1
                if r['kind']!='text' and r['image_quality'].get('phash'): hashes[r['image_quality']['phash']].append(r['id'])
        for suffix,target in [('records','records.jsonl'),('pages','document_pages.jsonl')]:
            with (run/target).open('wb') as out:
                for b in progress['batches']:
                    p=run/'native_batches'/f'{b["first"]:05d}-{b["last"]:05d}_{suffix}.jsonl'
                    with p.open('rb') as src:shutil.copyfileobj(src,out,1024*1024)
        shutil.copyfile(run/'records.jsonl',run/'machine_snapshots/initial.jsonl')
        duplicates=[{'method':'perceptual_hash_candidate_only','records':ids,'automatically_removed':False} for ids in hashes.values() if len(ids)>1]
        atomic_json(run/'duplicate_candidates.json',duplicates)
        atomic_json(run/'classification.json',{'pages':total,'page_classes':dict(classes),'classification_scope':'native_text_presence_is_not_proof_of_text_accuracy','pptx_supplied':False,'pptx_priority':False})
        atomic_json(run/'prepare_summary.json',{'records':count,'by_kind':dict(kinds),'buckets':dict(buckets),
            'unverified_predictions_exported':0,'full_source_renders':total,'reused_layout_and_specialist_cache':False,
            'perceptual_duplicate_groups':len(duplicates),'training_ready':False,'native_batch_pages':batch_pages})
        atomic_json(run/'manifest.json',{'schema_version':'it3170-preprocessing-v5','document':{'sha256':job['source_sha256'],'path':str(pdf),'pages':total},
            'asset_root':str(run),'records':'records.jsonl','pilot_pages':sorted({1,max(1,total//4),max(1,total//2),max(1,3*total//4),total}),
            'source_pptx':None,'human_review_policy':'explicit_human_approve_or_correct_only','layout_inventory_status':'requires_layout_enrichment',
            'vlm_policy':'one_image_one_plain_text_observation_no_required_graph_inventory','initial_records_sha256':digest(run/'records.jsonl'),
            'native_adapter':'v3-page-batches','created_date':'2026-10-21'})
        event('native_complete',document=job['document_id'],pages=total,records=count)
