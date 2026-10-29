"""Offline ingestion, same-region association and explicit human-only CPT export."""
import copy
import json
from pathlib import Path
from collections import Counter
import re
import shutil
import zipfile
from io_utils import canonical,sha,file_sha,load,jsonl,write_json,write_jsonl,write_once,safe_path,normalize
from cross_validation import cross_validate
from models import validate_record

def iou(a,b):
    overlap=max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
    area=lambda x:(x[2]-x[0])*(x[3]-x[1])
    return overlap/max(1e-9,area(a)+area(b)-overlap)

def publish(run,records,receipt):
    run=Path(run);processed=[validate_record(cross_validate(r)) for r in records]
    key=sha(canonical(receipt))[:16];snapshot=run/'machine_snapshots'/('revision_'+key+'.jsonl')
    if snapshot.exists():
        if jsonl(snapshot)!=processed:raise ValueError('Import snapshot conflict')
    else:write_jsonl(snapshot,processed)
    temporary=run/('records_'+key+'.next');write_jsonl(temporary,processed);temporary.replace(run/'records.jsonl')
    write_once(run/'import_receipts'/(key+'.json'),receipt)
    summary={'records':len(processed),'buckets':dict(Counter(r['machine_bucket'] for r in processed)),
        'snapshot':snapshot.relative_to(run).as_posix(),'human_decisions_auto_created':0}
    write_json(run/'machine_summary.json',summary);return summary

def ingest_cloud(run,archive,packet):
    run=Path(run);packet=Path(packet);archive=Path(archive);m=load(run/'manifest.json');pm=load(packet/'manifest.json')
    if pm['document']['sha256']!=m['document']['sha256']:raise ValueError('Wrong packet source PDF')
    requests={q['id']:q for q in pm['requests']};records=jsonl(run/'records.jsonl');by_id={r['id']:r for r in records}
    observations={};paddle_records={};parser_envelopes=[]
    with zipfile.ZipFile(archive) as z:
        if z.testzip():raise ValueError('Corrupt ZIP')
        for name in z.namelist():
            if name.startswith(('/', '\\')) or '..' in Path(name).parts:raise ValueError('Unsafe archive path')
            if name.endswith('.json') and ('vlm_results_' in name or '/records/' in name or name.startswith('records/') or 'parser_candidates_' in name or Path(name).name.startswith('results_')):
                item=json.loads(z.read(name))
                if 'observations' in item:
                    if item['packet_manifest_sha256']!=file_sha(packet/'manifest.json'):raise ValueError('VLM packet identity mismatch')
                    for r in item['observations']:
                        # Prefer successful observation over a failure; do not repair facts.
                        old=observations.get(r['id'])
                        if old is None or old.get('status')!='ok':observations[r['id']]=r
                elif 'parser_candidates' in item:parser_envelopes.append(item)
                elif 'candidates' in item and 'id' in item:paddle_records.setdefault(item['id'],[]).append(item)
                elif item.get('mode') in ['ocr','formula','table','structure'] and isinstance(item.get('records'),list):
                    for p in item['records']:
                        if 'id' in p:paddle_records.setdefault(p['id'],[]).append(p)
    added=0
    def add(record,c):
        nonlocal added
        key=sha(canonical(c))
        if not any(sha(canonical(old))==key for old in record['candidates']):record['candidates'].append(c);added+=1
    for rid,p in observations.items():
        if rid not in requests or rid not in by_id:raise ValueError('Unknown VLM request')
        q=requests[rid];r=by_id[rid]
        if p['source_sha256']!=r['source_sha256'] or p['crop_sha256']!=r['crop_sha256'] or p['input_image_sha256']!=q['vlm_image_sha256']:raise ValueError('VLM source/crop mismatch')
        expected_context=r.get('context_sha256') or r.get('crop_sha256') or r['render_sha256']
        if q['vlm_image_sha256']!=expected_context or q['bbox']!=r['bbox']:raise ValueError('VLM current context/target changed')
        if q.get('context_bbox') is not None and q['context_bbox']!=r['context_bbox']:raise ValueError('VLM context geometry changed')
        for field,digest in [('render_path','render_sha256'),('crop_path','crop_sha256'),('context_path','context_sha256')]:
            if r.get(field) and file_sha(safe_path(run,r[field]))!=r[digest]:raise ValueError('VLM current asset changed')
        if p.get('model_config')!=pm['vlm_config']:raise ValueError('VLM model/config mismatch')
        add(r,{'engine':'vlm','text':p.get('text',''),'status':p['status'],'evidence':{'backend_family':'vlm','region_id':rid,
            'source_sha256':r['source_sha256'],'crop_sha256':r['crop_sha256'],'input_image_sha256':p['input_image_sha256'],
            'context_bbox':r['context_bbox'],'partial_observation':p.get('partial_observation',False),'telemetry':p.get('telemetry'),
            'error_message':p.get('error_message'),'cache_key':p['cache_key'],'one_generation_call':True}})
        r['pending_engines']=[e for e in r.get('pending_engines',[]) if e!='vlm']
    for rid,items in paddle_records.items():
        if rid not in requests or rid not in by_id:raise ValueError('Unknown Paddle request')
        r=by_id[rid]
        for p in items:
            if p.get('input_file_sha256') is not None and p['input_file_sha256']!=r['crop_sha256']:raise ValueError('Paddle input crop mismatch')
            if p['status']=='ok' and p.get('input_file_sha256')!=r['crop_sha256']:raise ValueError('Successful Paddle output lacks crop identity')
            parts=copy.deepcopy(p['candidates'])
            for c in parts:
                ev=c.get('evidence') or {}
                if ev.get('source_sha256') and ev['source_sha256']!=r['source_sha256']:raise ValueError('Paddle PDF mismatch')
                if ev.get('region_id') and ev['region_id']!=rid:raise ValueError('Paddle region mismatch')
                if ev.get('crop_sha256') and ev['crop_sha256']!=r['crop_sha256']:raise ValueError('Paddle candidate crop mismatch')
            # OCR line boxes belong to one request image. Compare one ordered
            # transcript with native extraction, not each short line against a page.
            if p.get('mode')=='ocr' and parts:
                lines=sorted(parts,key=lambda c:(c.get('evidence') or {}).get('reading_order',0))
                parts=[{'engine':'paddle_ocr','text':'\n'.join(c['text'] for c in lines),'status':'ok',
                    'evidence':{'backend_family':'paddle','source_sha256':r['source_sha256'],'region_id':rid,
                        'crop_sha256':r['crop_sha256'],'same_region':True,'component_count':len(lines),
                        'components':lines,'input_file_sha256':p['input_file_sha256']}}]
            for c in parts:
                c=copy.deepcopy(c);ev=c.get('evidence') or {}
                if ev.get('source_sha256') and ev['source_sha256']!=r['source_sha256']:raise ValueError('Paddle PDF mismatch')
                if ev.get('region_id') and ev['region_id']!=rid:raise ValueError('Paddle region mismatch')
                ev.update(source_sha256=r['source_sha256'],crop_sha256=r['crop_sha256'],region_id=rid);c['evidence']=ev;add(r,c)
            if not p['candidates'] and p['status'] not in ['ok','skipped_seed']:
                engine='paddle_formula' if p.get('mode')=='formula' else 'paddle_table' if p.get('mode')=='table' else 'paddle_ocr'
                add(r,{'engine':engine,'text':'','status':'error','evidence':{'source_sha256':r['source_sha256'],'region_id':rid,'error':p.get('error')}})
        completed={'ocr':'paddle_ocr','formula':'paddle_formula','table':'paddle_table','structure':'paddle_structure'}
        done={completed.get(p.get('mode')) for p in items}
        r['pending_engines']=[e for e in r.get('pending_engines',[]) if e not in done]
    unmatched=[]
    for envelope in parser_envelopes:
        if envelope.get('original_source_sha256')!=m['document']['sha256'] or envelope.get('parser_input_sha256')!=pm['parser_input_sha256']:raise ValueError('Independent parser source mismatch')
        if envelope.get('packet_manifest_sha256')!=file_sha(packet/'manifest.json'):raise ValueError('Parser packet identity mismatch')
        mapped=[]
        for c in envelope['parser_candidates']:
            c=copy.deepcopy(c);page=c.get('page');original=pm['page_map'].get(str(page))
            if original is None:unmatched.append({'candidate':c,'reason':'unmapped_page'});continue
            c['page']=original;c.setdefault('evidence',{})['source_sha256']=m['document']['sha256'];mapped.append(c)
        n,miss=associate(records,mapped);added+=n;unmatched+=miss
    archive_target=run/'external_raw'/archive.name
    archive_target.parent.mkdir(parents=True,exist_ok=True)
    if archive_target.exists() and file_sha(archive_target)!=file_sha(archive):raise ValueError('Archive filename conflict')
    if not archive_target.exists():shutil.copy2(archive,archive_target)
    receipt={'type':'cloud_ingest','archive_sha256':file_sha(archive),'packet_manifest_sha256':file_sha(packet/'manifest.json'),
        'added_candidates':added,'observations':len(observations),'paddle_records':len(paddle_records),'unmatched_parser_candidates':unmatched}
    return publish(run,records,receipt)

def associate(records,candidates):
    """Only compare mapped regions; unknown geometry never creates agreement."""
    added=0;unmatched=[];by_page={p:[r for r in records if r['page']==p] for p in {r['page'] for r in records}}
    for page,rows in by_page.items():
        local=[c for c in candidates if c.get('page')==page]
        for r in rows:
            if r['kind'] in ['text','code'] and r['bbox']==[0,0,1000,1000]:
                grouped={}
                for c in local:
                    if c.get('kind') in ['text','code'] and c.get('status')=='ok' and c.get('bbox'):
                        grouped.setdefault(c['engine'],[]).append(c)
                for engine,parts in grouped.items():
                    parts.sort(key=lambda c:c.get('order',c.get('evidence',{}).get('reading_order',0)))
                    c={'engine':engine,'text':'\n'.join(p['text'] for p in parts),'status':'ok','evidence':{
                        **parts[0].get('evidence',{}),'source_sha256':r['source_sha256'],'region_id':r['id'],
                        'bbox_convention':'full_page_aggregate','component_count':len(parts),'same_region':True}}
                    if c not in r['candidates']:r['candidates'].append(c);added+=1
            else:
                matches=[c for c in local if c.get('bbox') and c.get('kind')==r['kind'] and iou(r['bbox'],c['bbox'])>=.5]
                for c in matches:
                    c=copy.deepcopy(c);c.setdefault('evidence',{}).update(region_id=r['id'],source_sha256=r['source_sha256'],same_region=True)
                    if c not in r['candidates']:r['candidates'].append(c);added+=1
    for c in candidates:
        if not c.get('bbox') or not c.get('page'):
            unmatched.append({'candidate':c,'reason':'unknown_geometry_or_page_not_comparable'})
        elif c.get('kind') not in ['text','code'] and not any(r['page']==c['page'] and r['kind']==c['kind'] and iou(r['bbox'],c['bbox'])>=.5 for r in records):
            unmatched.append({'candidate':c,'reason':'new_component_needs_explicit_region_routing'})
    return added,unmatched

def import_parser(run,engine,path,source_sha256):
    from adapters import import_docling,import_mineru,import_paddle
    run=Path(run);m=load(run/'manifest.json')
    if source_sha256!=m['document']['sha256']:raise ValueError('Source declaration mismatch')
    candidates={'docling':import_docling,'mineru':import_mineru,'paddle':import_paddle}[engine](Path(path))
    for c in candidates:
        ev=c.get('evidence',{})
        if ev.get('source_sha256') and ev['source_sha256']!=source_sha256:raise ValueError('Parser source hash mismatch')
        ev['source_sha256']=source_sha256;c['evidence']=ev
    records=jsonl(run/'records.jsonl');old_counts={r['id']:len(r['candidates']) for r in records};added,unmatched=associate(records,candidates)
    if engine=='paddle':
        for r in records:
            if len(r['candidates'])>old_counts[r['id']]:
                done={c['engine'] for c in r['candidates'][old_counts[r['id']]:]}
                r['pending_engines']=[e for e in r.get('pending_engines',[]) if e not in done]
    target=run/'external_raw'/(file_sha(path)[:12]+'_'+Path(path).name)
    target.parent.mkdir(parents=True,exist_ok=True)
    if not target.exists():shutil.copy2(path,target)
    return publish(run,records,{'type':'parser_import','engine':engine,'raw_sha256':file_sha(path),'added_candidates':added,'unmatched':unmatched})

def export_cpt(run,out,tokenizer=None):
    from review_store import ReviewStore
    run=Path(run);out=Path(out)
    if out.exists():raise ValueError('Choose a fresh CPT version')
    manifest=load(run/'manifest.json');store=ReviewStore(run);records=[];offset=0
    while True:
        batch=store.list_records(limit=10000,offset=offset)
        if not batch:break
        records+=batch;offset+=len(batch)
    accepted=[];excluded=[];seen={}
    for r in records:
        if r['source_sha256']!=manifest['document']['sha256']:raise ValueError('Record/source manifest mismatch')
        review=r.get('latest_review')
        if not review or review['decision'] not in ['approve','correct'] or not r.get('human_verified'):
            excluded.append({'id':r['id'],'reason':'not_human_approved_or_stale'});continue
        if r['split']!='train':excluded.append({'id':r['id'],'reason':'protected_'+r['split']});continue
        # Re-check actual source assets at export time, not just at review time.
        for field,digest in [('render_path','render_sha256'),('crop_path','crop_sha256'),('context_path','context_sha256')]:
            if r.get(field) and file_sha(safe_path(run,r[field]))!=r[digest]:raise ValueError('Changed approved source asset')
        text=normalize(review['accepted_text']).strip();text=re.sub(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}','[EMAIL]',text)
        key=sha(canonical({'text':text,'pixel_sha256':r['image_quality']['pixel_sha256']}))
        if key in seen:excluded.append({'id':r['id'],'reason':'true_exact_text_and_image_duplicate','canonical_id':seen[key]});continue
        seen[key]=r['id'];accepted.append({'id':r['id'],'page':r['page'],'text':text,'source':{'document_sha256':r['source_sha256'],
            'render_sha256':r['render_sha256'],'crop_sha256':r['crop_sha256'],'bbox':r['bbox'],'group_id':r['group_id'],'split':r['split']},
            'human_review':review,'coverage_claim':'reviewed_region_only_not_complete_slide'})
    out.mkdir(parents=True);write_jsonl(out/'train.jsonl',[{'text':r['text']} for r in accepted]);write_jsonl(out/'train.metadata.jsonl',accepted)
    write_jsonl(out/'excluded.jsonl',excluded)
    manifest={'samples':len(accepted),'training_ready':bool(accepted),'human_approved_only':True,'machine_trusted_auto_exported':0,
        'holdout_excluded':True,'tokenizer':None,'all_pdf_knowledge_complete':False,'records_snapshot_sha256':file_sha(run/'records.jsonl')}
    if tokenizer and accepted:
        from transformers import AutoTokenizer
        tok=AutoTokenizer.from_pretrained(str(tokenizer),local_files_only=True,trust_remote_code=False)
        if tok.eos_token_id is None:raise ValueError('Tokenizer has no EOS')
        stream=[];spans=[]
        for row in accepted:
            ids=tok.encode(row['text'],add_special_tokens=False)+[tok.eos_token_id];start=len(stream);stream+=ids;spans.append({'id':row['id'],'start':start,'end':len(stream)})
        packs=[{'input_ids':stream[i:i+1024],'attention_mask':[1]*len(stream[i:i+1024]),'labels':stream[i:i+1024]} for i in range(0,len(stream),1024)]
        assert [i for p in packs for i in p['input_ids']]==stream
        write_jsonl(out/'train.packed.jsonl',packs);write_jsonl(out/'token_source_spans.jsonl',spans)
        manifest.update(tokenizer=str(tokenizer),eos_token_id=tok.eos_token_id,tokens=len(stream),sequences=len(packs),chat_template_applied=False,last_fragment_kept=True)
    write_json(out/'manifest.json',manifest);return manifest
