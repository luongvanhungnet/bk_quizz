"""Resumable local corpus preparation around the frozen v5 preprocessing engines.

No cloud inference starts automatically. A packet is one document and one source
page range; source IDs stay tied to the original PDF, never to its subset hash.
"""
import argparse
from collections import Counter
import csv
from datetime import datetime,timezone
import json
import math
from pathlib import Path
import re
import shutil
import sys
import zipfile
import pymupdf
from io_utils import load,jsonl,write_json,write_jsonl,file_sha,canonical,sha

def audit_event(root,event):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    with (root/'events.jsonl').open('a',encoding='utf-8') as f:
        f.write(canonical({'utc':datetime.now(timezone.utc).isoformat(),**event})+'\n')

def inventory(config,out):
    out=Path(out)
    if out.exists():raise FileExistsError('Inventory snapshots are immutable; choose another output')
    out.mkdir(parents=True);root=Path(config['source_root']).resolve()
    upstream=load(config['upstream_manifest']) if Path(config['upstream_manifest']).exists() else []
    by_hash={r['sha256']:r for r in upstream};cache={}
    for value in config.get('reuse_runs',[]):
        run=Path(value)
        if (run/'manifest.json').exists():cache[load(run/'manifest.json')['document']['sha256']]=str(run.resolve())
    rows=[];seen={}
    for path in sorted(root.rglob('*.pdf')):
        r={'path':str(path.resolve()),'filename':path.name,'bytes':path.stat().st_size,'course':path.stem.split('-',1)[0],
            'sha256':file_sha(path),'status':'ready','pages':None,'cached_run':None}
        r['document_id']=r['course'].lower()+'_'+r['sha256'][:12]
        try:
            with pymupdf.open(path) as pdf:
                r.update(pages=pdf.page_count,encrypted=bool(pdf.needs_pass))
                if pdf.needs_pass or not pdf.page_count:r['status']='blocked_encrypted_or_empty'
                elif config.get('sample_pdf_pages',True):
                    r['sample']=[{'page':p,'native_characters':len(pdf[p-1].get_text('text').strip()),'raster_images':len(pdf[p-1].get_images())}
                        for p in sorted({1,(pdf.page_count+1)//2,pdf.page_count})]
                    r['sample_scope']='first_middle_last_only'
        except Exception as e:r.update(status='blocked_unreadable',error=str(e))
        if r['sha256'] in seen:r.update(status='exact_duplicate_source',duplicate_of=seen[r['sha256']])
        else:seen[r['sha256']]=r['document_id']
        provenance=by_hash.get(r['sha256'])
        r['upstream_provenance']='matched_hash' if provenance else 'source_pdf_only'
        if provenance:r['upstream_group']=provenance['group'];r['original_parts']=len(provenance.get('parts',[]))
        r['cached_run']=cache.get(r['sha256']);r['pptx_pairing']='not_assumed_from_name'
        rows.append(r)
    write_jsonl(out/'documents.jsonl',rows)
    with (out/'documents.csv').open('w',encoding='utf-8-sig',newline='') as f:
        fields=['document_id','course','filename','pages','bytes','sha256','status','upstream_provenance','cached_run']
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)
    for key in ['upstream_manifest','upstream_page_map']:
        path=Path(config[key])
        if path.exists():shutil.copy2(path,out/(key+'.json'))
    summary={'source_root':str(root),'documents':len(rows),'pages':sum(r.get('pages') or 0 for r in rows),
        'bytes':sum(r['bytes'] for r in rows),'statuses':dict(Counter(r['status'] for r in rows)),
        'cached_documents':sum(bool(r['cached_run']) for r in rows),'upstream_hash_matches':sum(r['upstream_provenance']=='matched_hash' for r in rows),
        'source_files_modified':False,'native_sample_is_not_quality_benchmark':True,
        'excluded_roots':config.get('excluded_roots',[]),'documents_sha256':file_sha(out/'documents.jsonl')}
    write_json(out/'summary.json',summary);print(json.dumps(summary,ensure_ascii=False,indent=2));return rows

def plan(config,catalog,out):
    out=Path(out)
    if out.exists():raise FileExistsError('Plan snapshots are immutable')
    out.mkdir(parents=True);rows=jsonl(Path(catalog)/'documents.jsonl');jobs=[];size=config['pages_per_packet']
    if type(size) is not int or size<1:raise ValueError('pages_per_packet must be positive')
    for r in rows:
        if r['status']!='ready':continue
        run=r['cached_run'] or str((Path(config['work_root'])/'runs'/r['document_id']).resolve())
        # Preserve the existing IT3170 split/group metadata. New courses stay in
        # one split; global near-duplicate/split audit remains an export gate.
        split='preserve_existing' if r['cached_run'] else config.get('course_splits',{}).get(r['course'],'train')
        for first in range(1,r['pages']+1,size):
            last=min(r['pages'],first+size-1);job_id=f"{r['document_id']}_p{first:05d}-{last:05d}"
            jobs.append({'job_id':job_id,'document_id':r['document_id'],'course':r['course'],'source_path':r['path'],'source_sha256':r['sha256'],
                'source_pages':r['pages'],'first_page':first,'last_page':last,'run':run,'split_policy':split,
                'layout_required':not bool(r['cached_run']),'phases':['inference'] if r['cached_run'] else ['discovery','layout_materialization','inference'],
                'stage':'planned','semantic_verified':False})
    write_jsonl(out/'jobs.jsonl',jobs);write_json(out/'config_snapshot.json',config)
    summary={'documents':len({j['document_id'] for j in jobs}),'pages':sum(j['last_page']-j['first_page']+1 for j in jobs),
        'jobs':len(jobs),'pages_per_packet':size,'reused_documents':sum(bool(r['cached_run']) for r in rows),
        'new_documents_needing_layout':sum(not bool(r['cached_run']) and r['status']=='ready' for r in rows),
        'new_rendering_executed':False,'cloud_inference_executed':False,'jobs_sha256':file_sha(out/'jobs.jsonl'),
        'global_near_duplicate_and_split_audit_required_before_combined_cpt':True}
    write_json(out/'summary.json',summary);print(json.dumps(summary,ensure_ascii=False,indent=2));return jobs

def select_jobs(plan_path,document=None,job_id=None):
    jobs=jsonl(Path(plan_path)/'jobs.jsonl')
    if document:jobs=[j for j in jobs if j['document_id']==document or j['course'].lower()==document.lower()]
    if job_id:jobs=[j for j in jobs if j['job_id']==job_id]
    if not jobs:raise ValueError('No matching corpus job')
    return jobs

def check_source(job):
    if file_sha(job['source_path'])!=job['source_sha256']:raise ValueError('Source changed; create a fresh inventory/plan')

def prepare_documents(config,jobs):
    from prepare import prepare
    from workflow import publish
    done=set();result=[]
    for job in jobs:
        if job['document_id'] in done:continue
        done.add(job['document_id']);run=Path(job['run']);check_source(job)
        if (run/'manifest.json').exists():
            m=load(run/'manifest.json')
            if m['document']['sha256']!=job['source_sha256'] or not (run/'records.jsonl').exists():raise ValueError('Incompatible/incomplete existing run')
            state='reused'
        else:
            if run.exists():raise ValueError('Incomplete run retained; inspect and use a new work_root')
            prepare(Path(job['source_path']),run);state='prepared_native'
            records=jsonl(run/'records.jsonl')
            for r in records:
                r['group_id']='course:'+job['course'];r['split']=job['split_policy']
            publish(run,records,{'type':'course_group_assignment','course':job['course'],'split':job['split_policy'],'document_sha256':job['source_sha256']})
        row={'document_id':job['document_id'],'run':str(run),'state':state};result.append(row)
        audit_event(config['work_root'],{'action':'prepare_document',**row})
    return result

def package_job(config,job,phase):
    from package_cloud import package,wants_vlm
    check_source(job);run=Path(job['run']);m=load(run/'manifest.json');records=jsonl(run/'records.jsonl')
    if m['document']['sha256']!=job['source_sha256']:raise ValueError('Wrong prepared source')
    if phase=='inference' and job['layout_required'] and m.get('layout_inventory_status')!='ready':
        raise ValueError('Run discovery for every shard and materialize layout before inference; inventory is incomplete')
    output=Path(config['work_root'])/'packets'/phase/job['job_id']
    signature={'source':job['source_sha256'],'records':file_sha(run/'records.jsonl'),'phase':phase,'first':job['first_page'],'last':job['last_page']}
    output=output/sha(canonical(signature))[:12]
    if (output/'manifest.json').exists():
        if not (output/'v5_colab_input.zip').exists():raise ValueError('Incomplete packet retained; inspect before retry')
        return output/'v5_colab_input.zip'
    for r in records:
        if job['first_page']<=r['page']<=job['last_page']:
            for prefix in ['crop','context','render']:
                if file_sha(run/r[prefix+'_path'])!=r[prefix+'_sha256']:raise ValueError('Changed asset: '+r['id'])
    path=package(run,output,scope='all',model='7b',page_numbers=list(range(job['first_page'],job['last_page']+1)))
    pm=load(output/'manifest.json');pm.update(corpus_job=job,phase=phase,
        required_stages=['ocr','structure','docling'] if phase=='discovery' else ['ocr','formula','table','vlm'])
    if phase=='discovery':
        for q in pm['requests']:q['use_vlm']=False
    for q in pm['requests']:
        r=next(r for r in records if r['id']==q['id'])
        if r.get('specialist_disabled'):q['skip_specialist']=True
    if phase=='inference':
        scheduled={r['page'] for r in records if wants_vlm(r,'all')}
        if len(scheduled)>max(1,math.ceil(config['vlm_maximum_fraction']*m['document']['pages'])):raise ValueError('VLM page budget exceeded; retain unresolved regions for routing')
    write_json(output/'manifest.json',pm)
    # Manifest changed only to add job provenance/stage policy. Regenerate the
    # not-yet-published ZIP, keeping all machine inputs and source page numbers.
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(output.rglob('*')):
            if p.is_file() and p!=path:z.write(p,p.relative_to(output).as_posix())
    if path.stat().st_size>config['maximum_packet_bytes']:raise ValueError('Packet too large; lower pages_per_packet in a fresh plan')
    audit_event(config['work_root'],{'action':'package','job_id':job['job_id'],'phase':phase,'packet':str(path),'manifest_sha256':file_sha(output/'manifest.json')})
    return path

def merge_job(config,job,packet,results):
    from workflow import ingest_cloud
    from batch_layout import materialize
    pm=load(Path(packet)/'manifest.json')
    if pm.get('corpus_job',{}).get('job_id')!=job['job_id']:raise ValueError('Returned packet belongs to another corpus job')
    summary=ingest_cloud(job['run'],results,packet)
    if pm['phase']=='discovery':summary['layout']=materialize(job['run'],results,packet,config['vlm_target_fraction'],config['vlm_maximum_fraction'])
    audit_event(config['work_root'],{'action':'merge','job_id':job['job_id'],'phase':pm['phase'],'archive_sha256':file_sha(results),'summary':summary})
    return summary

def preflight(config,plan_path):
    jobs=select_jobs(plan_path);documents={j['document_id']:j for j in jobs};errors=[]
    for key,job in documents.items():
        try:check_source(job)
        except Exception as e:errors.append({'document_id':key,'error':str(e)})
        ranges=[j for j in jobs if j['document_id']==key]
        actual=[p for j in ranges for p in range(j['first_page'],j['last_page']+1)]
        if actual!=list(range(1,job['source_pages']+1)):errors.append({'document_id':key,'error':'Missing/duplicate/nonsequential source pages'})
    free=shutil.disk_usage(Path(config['work_root']).anchor).free
    if free<config.get('minimum_free_disk_bytes',0):errors.append({'error':'Insufficient configured free disk threshold','free_bytes':free})
    result={'documents':len(documents),'jobs':len(jobs),'source_pages':sum(j['source_pages'] for j in documents.values()),
        'source_hashes_valid':not any('document_id' in e for e in errors),'disk_free_bytes':free,'errors':errors,
        'preparation_ready':not errors,'cloud_inference_completed':False,'quality_certified':False,
        'combined_cpt_export_ready':False,'global_duplicate_and_split_audit_pending':True}
    write_json(Path(plan_path)/'preflight.json',result);print(json.dumps(result,ensure_ascii=False,indent=2))
    if errors:raise ValueError('Preflight failed; see preflight.json')
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path,required=True);s=p.add_subparsers(dest='action',required=True)
    q=s.add_parser('inventory');q.add_argument('--out',type=Path,required=True)
    q=s.add_parser('plan');q.add_argument('--catalog',type=Path,required=True);q.add_argument('--out',type=Path,required=True)
    q=s.add_parser('preflight');q.add_argument('--plan',type=Path,required=True)
    for action in ['prepare','package','merge','review']:
        q=s.add_parser(action);q.add_argument('--plan',type=Path,required=True);q.add_argument('--document');q.add_argument('--job-id')
        if action in ['prepare','package']:q.add_argument('--all-documents',action='store_true')
        if action=='package':q.add_argument('--phase',choices=['discovery','inference'],required=True)
        if action=='merge':q.add_argument('--packet',type=Path,required=True);q.add_argument('--results',type=Path,required=True)
        if action=='review':q.add_argument('--port',type=int,default=8765)
    args=p.parse_args();config=load(args.config)
    if args.action=='inventory':inventory(config,args.out);return
    if args.action=='plan':plan(config,args.catalog,args.out);return
    if args.action=='preflight':preflight(config,args.plan);return
    if not args.document and not args.job_id and not getattr(args,'all_documents',False):raise ValueError('Choose --document, --job-id or --all-documents')
    jobs=select_jobs(args.plan,args.document,args.job_id)
    if args.action=='prepare':print(prepare_documents(config,jobs))
    elif args.action=='package':
        for job in jobs:
            if args.phase=='discovery' and not job['layout_required']:continue
            print(package_job(config,job,args.phase))
    elif args.action=='merge':
        if len(jobs)!=1:raise ValueError('Merge exactly one --job-id')
        print(merge_job(config,jobs[0],args.packet,args.results))
    else:
        from review_app import ReviewHTTPServer
        server=ReviewHTTPServer(('127.0.0.1',args.port),Path(jobs[0]['run']),scope='vlm')
        print(f'Human VLM review: http://127.0.0.1:{args.port}',flush=True)
        try:server.serve_forever()
        except KeyboardInterrupt:pass
        finally:server.server_close()

if __name__=='__main__':main()
