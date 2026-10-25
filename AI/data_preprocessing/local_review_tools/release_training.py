"""Versioned CPT export with explicit owner defaults and preserved review history."""
import hashlib
import json
import re
import argparse
from collections import Counter
from contextlib import closing
from datetime import datetime,timezone
from pathlib import Path
import sqlite3
import shutil
import unicodedata


def record_identity(record):
    fields=('id','machine_revision','source_sha256','render_sha256','crop_sha256','context_sha256')
    identity={key:record.get(key) for key in fields}
    encoded=json.dumps(record.get('proposed_text',''),ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')
    identity['proposal_sha256']=hashlib.sha256(encoded).hexdigest()
    return identity


def resolve_record(record,review,*,default_pass):
    split=record.get('split')
    if split!='train':return {'excluded':'protected_'+str(split)}
    if review:
        if review.get('identity')!=record_identity(record):return {'excluded':'stale_review'}
        decision=review.get('decision')
        if decision not in {'approve','correct'}:return {'excluded':'review_'+str(decision)}
        text=review.get('accepted_text','');acceptance='review_'+decision
    elif default_pass:
        text=record.get('proposed_text','');acceptance='owner_default_pass'
    else:return {'excluded':'not_reviewed'}
    text=unicodedata.normalize('NFC',text or '').strip()
    if not text:return {'excluded':'empty_text'}
    text=re.sub(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}','[EMAIL]',text)
    return {'text':text,'acceptance':acceptance,'human_verified':bool(review),
            'review_id':review.get('review_id') if review else None}


def sha_file(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda:source.read(4*1024*1024),b''):digest.update(block)
    return digest.hexdigest()


def write_json(path,value):
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def jsonl(path):
    with Path(path).open(encoding='utf-8-sig') as source:
        for line in source:
            if line.strip():yield json.loads(line)


def emit(target,value):
    target.write(json.dumps(value,ensure_ascii=False,separators=(',',':'))+'\n')


def has_vlm(record):
    return any(any(part in str(c.get('engine','')).lower() for part in ['vlm','qwen','vision_llm'])
               and c.get('status') in {'ok','success','completed','valid'} and isinstance(c.get('text'),str)
               and c['text'].strip() for c in record.get('candidates',[]))


def stage_release(workspace,out,*,default_pass,seed=20261023):
    workspace=Path(workspace).resolve();out=Path(out)
    out.mkdir(parents=True,exist_ok=False);(out/'snapshots').mkdir();(out/'audit').mkdir()
    catalog=json.loads((workspace/'review_catalog.json').read_text(encoding='utf-8'))
    write_json(out/'snapshots/review_catalog.json',catalog)
    policy={'schema':'bkquiz-owner-default-v1','created_utc':datetime.now(timezone.utc).isoformat(),
        'authorization':'tôi đã hoàn thành kiểm tra các kết quả VLM. các kết quả còn lại chưa từng được kiểm tra thì mặc định là đạt tiêu chuẩn.',
        'default_pass_never_reviewed':bool(default_pass),'explicit_rejections_preserved':True,
        'stale_and_deferred_reviews_excluded':True,'protected_splits_preserved':True,
        'automatic_human_review_events_created':0,'source_workspace':str(workspace),'sample_seed':seed}
    write_json(out/'policy.json',policy)
    counts=Counter();snapshots=[];pools={};quotas={'vlm_approved':6,'default_text':6,'default_visual_ocr':4,'default_table_formula':4,'vlm_rejected':4}
    with (out/'selection.jsonl').open('w',encoding='utf-8') as selected,(out/'excluded.jsonl').open('w',encoding='utf-8') as excluded,(out/'protected.jsonl').open('w',encoding='utf-8') as protected:
        for d in catalog['documents']:
            doc=d['document_id'];run=Path(d['run']).resolve()
            if not run.is_relative_to(workspace/'runs'):raise ValueError('Run escapes workspace')
            manifest=json.loads((run/'manifest.json').read_text(encoding='utf-8-sig'))
            if manifest['document']['sha256']!=d['source_sha256']:raise ValueError('Source manifest changed')
            latest={};database=run/'human_reviews.sqlite3';snapshot=out/'snapshots'/(doc+'.sqlite3')
            if database.is_file():
                with closing(sqlite3.connect(database.as_uri()+'?mode=ro',uri=True)) as source,closing(sqlite3.connect(snapshot)) as target:
                    source.backup(target)
                    counts['review_events']+=target.execute('SELECT COUNT(*) FROM reviews').fetchone()[0]
                    latest={rid:json.loads(payload) for rid,payload in target.execute('SELECT r.record_id,r.payload FROM reviews r JOIN (SELECT record_id,MAX(sequence) s FROM reviews GROUP BY record_id) x ON r.sequence=x.s')}
            path=run/'records.jsonl';before=sha_file(path);seen=set()
            for record in jsonl(path):
                rid=record['id']
                if rid in seen:raise ValueError('Duplicate region ID within course')
                seen.add(rid)
                if record['source_sha256']!=d['source_sha256']:raise ValueError('Record/source mismatch')
                review=latest.get(rid);resolved=resolve_record(record,review,default_pass=default_pass)
                identity=record_identity(record);vlm=has_vlm(record)
                counts['records']+=1;counts['kind_'+str(record.get('kind'))]+=1
                if vlm:counts['vlm_records']+=1
                if review:
                    counts['review_'+review['decision']]+=1
                    counts['review_current' if review.get('identity')==identity else 'review_stale']+=1
                else:counts['never_reviewed']+=1
                keys=['id','page','kind','bbox','proposed_text','native_text','render_path','render_sha256','crop_path',
                      'crop_sha256','context_path','context_sha256','split','machine_bucket','image_quality']
                row={'id':doc+':'+rid,'record_id':rid,'document_id':doc,'course':d['course'],'run':str(run),
                     'page':record['page'],'source_sha256':record['source_sha256'],'identity':identity,
                     'record':{k:record.get(k) for k in keys},'vlm':vlm,**resolved}
                if record.get('split') in {'development','holdout'}:
                    emit(protected,{**row,'text':(review.get('accepted_text') if review and review.get('identity')==identity and review.get('decision') in {'approve','correct'} else record.get('proposed_text')) or ''})
                if 'excluded' in resolved:
                    counts['excluded_'+resolved['excluded']]+=1
                    emit(excluded,{'id':row['id'],'reason':resolved['excluded'],'document_id':doc,'record_id':rid,'page':record['page']})
                else:
                    counts['selected']+=1;counts['accepted_'+resolved['acceptance']]+=1;emit(selected,row)
                pool=None
                if vlm and review and review.get('identity')==identity:
                    if review['decision']=='approve' and 'excluded' not in resolved:pool='vlm_approved'
                    elif review['decision']=='reject':pool='vlm_rejected'
                elif not review and 'excluded' not in resolved:
                    pool={'text':'default_text','code':'default_text','table':'default_table_formula','formula':'default_table_formula'}.get(record.get('kind'),'default_visual_ocr')
                if pool:
                    key=hashlib.sha256(f'{seed}|{pool}|{doc}|{rid}'.encode()).hexdigest()
                    bucket=pools.setdefault(pool,[]);bucket.append((key,row));bucket.sort(key=lambda x:x[0]);del bucket[quotas[pool]:]
            if sha_file(path)!=before:raise ValueError('Records changed while taking snapshot; choose a new release')
            snapshots.append({'document_id':doc,'records_sha256':before,'records':len(seen),
                              'review_database_sha256':sha_file(snapshot) if snapshot.exists() else None})
    samples=[]
    for pool in quotas:
        for key,row in pools.get(pool,[]):samples.append({'sample_id':f'S{len(samples)+1:02d}','stratum':pool,'random_key':key,**row})
    write_json(out/'audit/sample.json',{'seed':seed,'method':'smallest SHA256(seed,stratum,document,record), without replacement per stratum','quotas':quotas,'samples':samples})
    report={'counts':dict(counts),'documents':snapshots,'sample_size':len(samples),'policy_sha256':sha_file(out/'policy.json')}
    write_json(out/'stage_report.json',report)
    return report


def text_key(text):
    # Case and internal whitespace carry meaning in code and mathematics.
    return unicodedata.normalize('NFC',text).strip()


def shingles(text):
    words=re.findall(r'\w+',text_key(text))
    return {tuple(words[i:i+3]) for i in range(len(words)-2)} if len(words)>=20 else set()


def finalize_release(root,*,reuse_verified_draft=False):
    root=Path(root);findings=json.loads((root/'audit/findings.json').read_text(encoding='utf-8'))
    known_assets=set();cache_stamp=0;cache_manifest=None
    if (root/'colab/data/manifest.json').exists():
        if not reuse_verified_draft:raise FileExistsError('Choose a new release or explicitly refine an unpublished verified draft')
        if (root/'bundle_info.json').exists():raise ValueError('Do not overwrite a packaged release')
        old_validation=json.loads((root/'LOCAL_VALIDATION.json').read_text(encoding='utf-8'))
        if not old_validation['passed']:raise ValueError('Draft verification did not pass')
        draft=root/'draft_before_exact_dedup';draft.mkdir(exist_ok=False)
        for name in ['final_selection.jsonl','export_report.json','LOCAL_VALIDATION.json','colab/data/train.jsonl','colab/data/sources.jsonl','colab/data/manifest.json']:
            target=draft/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(root/name,target)
        cache_stamp=(root/'export_report.json').stat().st_mtime_ns
        cache_manifest=sha_file(draft/'colab/data/manifest.json')
        for row in jsonl(draft/'final_selection.jsonl'):
            for field in ['render','crop','context']:
                relative=row['record'].get(field+'_path');digest=row['record'].get(field+'_sha256')
                if relative and digest:known_assets.add((row['run'],relative,digest))
    quarantine={r['id'] for r in findings['findings'] if r['training_action']=='exclude'}
    protected=list(jsonl(root/'protected.jsonl'))
    protected_texts={text_key(r['text']) for r in protected if r.get('text','').strip()}
    protected_renders={r['record'].get('render_sha256') for r in protected}-{None}
    protected_near=[]
    for row in protected:
        phash=(row['record'].get('image_quality') or {}).get('phash');words=shingles(row.get('text',''))
        if phash and words:protected_near.append((int(phash,16),words))
    # Sort on disk: the full region inventory can exceed available desktop RAM.
    sort_db=sqlite3.connect(root/'export_sort.sqlite3')
    sort_db.execute('PRAGMA cache_size=-1024');sort_db.execute('PRAGMA temp_store=FILE')
    sort_db.execute('DROP TABLE IF EXISTS candidates')
    sort_db.execute('CREATE TABLE candidates(automatic,document,page,id,payload)')
    quarantine_texts=set();candidate_count=0
    for row in jsonl(root/'selection.jsonl'):
        sort_db.execute('INSERT INTO candidates VALUES(?,?,?,?,?)',(not row['human_verified'],row['document_id'],row['page'],row['id'],json.dumps(row,ensure_ascii=False)))
        if row['id'] in quarantine:quarantine_texts.add(text_key(row['text']))
        candidate_count+=1
        if candidate_count%1000==0:sort_db.commit()
    sort_db.commit()
    print(f'Sorted {candidate_count} candidates on disk',flush=True)
    counts=Counter();seen={};verified={};exclusions=[];kept_count=0;runs={};targets={};hashed_assets=0;reused_assets=0
    kept_file=(root/'final_selection.jsonl').open('w',encoding='utf-8')
    # Prefer a saved review over an identical owner-default transcript.
    cursor=sort_db.execute('SELECT payload FROM candidates ORDER BY automatic,document,page,id')
    for index,(payload,) in enumerate(cursor):
        row=json.loads(payload)
        record=row['record'];key=text_key(row['text']);reason=None
        if row['id'] in quarantine or key in quarantine_texts:reason='audit_quarantine'
        elif record.get('render_sha256') in protected_renders:reason='protected_same_page_image'
        elif key in protected_texts:reason='protected_exact_text'
        else:
            phash=(record.get('image_quality') or {}).get('phash')
            if phash:
                value=int(phash,16);candidates=[words for p,words in protected_near if (p^value).bit_count()<=4]
                if candidates:
                    words=shingles(row['text'])
                    if words and any(len(words&other)/len(words|other)>=.85 for other in candidates):reason='protected_near_duplicate'
        if reason is None and key in seen:reason='exact_duplicate'
        if reason:
            counts[reason]+=1;exclusions.append({'id':row['id'],'reason':reason,'canonical_id':seen.get(key)})
            continue
        if row['run'] not in runs:runs[row['run']]=Path(row['run']).resolve()
        run=runs[row['run']]
        for field in ['render','crop','context']:
            relative=record.get(field+'_path')
            if not relative:continue
            path_key=(row['run'],relative)
            if path_key not in targets:targets[path_key]=(run/relative).resolve()
            target=targets[path_key]
            if not target.is_relative_to(run):raise ValueError('Asset escapes run')
            expected=record.get(field+'_sha256')
            st=target.stat();asset_key=(st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns)
            if asset_key not in verified:
                if (row['run'],relative,expected) in known_assets and st.st_mtime_ns<=cache_stamp:
                    verified[asset_key]=expected;reused_assets+=1
                else:verified[asset_key]=sha_file(target);hashed_assets+=1
            if not expected or verified[asset_key]!=expected:raise ValueError('Changed source asset: '+str(target))
        seen[key]=row['id'];emit(kept_file,row);kept_count+=1;counts['kept_'+row['acceptance']]+=1
        if index and index%5000==0:print(f'Export checked {index}/{candidate_count} candidates; unique source assets {len(verified)}',flush=True)
    kept_file.close();cursor.close();sort_db.close()
    data=root/'colab/data';data.mkdir(parents=True,exist_ok=reuse_verified_draft)
    courses=Counter();accepted=Counter();characters=0
    with (data/'train.jsonl').open('w',encoding='utf-8') as text_file,(data/'sources.jsonl').open('w',encoding='utf-8') as source_file:
        for row in jsonl(root/'final_selection.jsonl'):
            text=row['text'];characters+=len(text);courses[row['course']]+=1;accepted[row['acceptance']]+=1
            emit(text_file,{'text':text})
            emit(source_file,{'id':row['id'],'page':row['page'],'document_id':row['document_id'],'course':row['course'],
                'record_id':row['record_id'],'text_sha256':hashlib.sha256(text.encode()).hexdigest(),
                'document_sha256':row['source_sha256'],'identity':row.get('identity'),
                'acceptance':row['acceptance'],'human_verified':row['human_verified'],
                'review_id':row.get('review_id'),'kind':row['record']['kind'],'split':'train','coverage_claim':'region_only'})
    with (root/'final_excluded.jsonl').open('w',encoding='utf-8') as f:
        for row in exclusions:emit(f,row)
    manifest={'schema':'bkquiz-cpt-owner-default-v1','samples':kept_count,'characters':characters,
        'courses':dict(courses),'acceptance':dict(accepted),'split':'existing_train_only',
        'validation_samples':0,'test_samples':0,'human_approved_only':False,
        'owner_default_policy_sha256':sha_file(root/'policy.json'),'spot_check_sha256':sha_file(root/'audit/findings.json'),
        'protected_splits_excluded':True,'global_duplicate_and_split_audit':{'exact_text':'NFC strip; case and internal whitespace preserved','same_render':True,
            'near_duplicate_rule':'pHash Hamming <=4 and word-trigram Jaccard >=0.85 with >=20 words; not exhaustive semantic dedup'},
        'files_sha256':{name:sha_file(root/'colab'/name) for name in ['data/train.jsonl','data/sources.jsonl']},
        'data_ready_for_owner_authorized_training':bool(kept_count),'corpus_accuracy_certified':False,
        'independent_generalization_test_available':False}
    write_json(data/'manifest.json',manifest)
    result={'samples':kept_count,'characters':characters,'counts':dict(counts),'courses':dict(courses),
        'unique_source_assets_sha256_verified':len(verified),'manual_reviews_changed':0,
        'original_records_changed':0,'manifest_sha256':sha_file(data/'manifest.json'),
        'new_source_assets_sha256_hashed':hashed_assets,'reused_verified_source_assets':reused_assets,
        'verified_draft_manifest_sha256':cache_manifest}
    write_json(root/'export_report.json',result)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',type=Path);parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--default-pass-never-reviewed',action='store_true')
    parser.add_argument('--finalize',action='store_true')
    parser.add_argument('--reuse-verified-draft',action='store_true')
    args=parser.parse_args()
    if args.finalize:result=finalize_release(args.out,reuse_verified_draft=args.reuse_verified_draft)
    else:
        if not args.workspace:parser.error('--workspace required for staging')
        result=stage_release(args.workspace,args.out,default_pass=args.default_pass_never_reviewed)
    print(json.dumps(result,ensure_ascii=False,indent=2))
