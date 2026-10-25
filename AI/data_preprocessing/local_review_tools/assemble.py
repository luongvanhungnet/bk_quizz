"""Assemble verified unit snapshots once per course, retaining all machine output."""
from pathlib import Path
import argparse
from collections import Counter
import hashlib
import json
import os
import sys
import time
import zipfile

from ingest import digest,link_copy,publish_preserved,safe,write_json

ROOT=Path(__file__).resolve().parent
RUNTIME=ROOT.parent/'colab_orchestrator_v5'
CORE=ROOT.parent.parent/'Qwen_cpt_version/region_preprocessing_v5_official'
sys.path.insert(0,str(RUNTIME));sys.path.insert(0,str(CORE))
from common import verify_release
from unit_store import inspect_result
from jsonl_adapter import read_jsonl
from models import validate_record
from io_utils import canonical,sha,write_once


def merge_records(shards):
    values={}
    for shard in shards:
        for r in shard:
            if r['id'] in values and values[r['id']]!=r:raise ValueError('Conflicting immutable region: '+r['id'])
            values[r['id']]=r
    return sorted(values.values(),key=lambda r:(r['page'],r['id']))


def assemble(workspace):
    workspace=Path(workspace).resolve();verify_release(CORE)
    index_path=ROOT.parent/'uploads_134_unit100_20261022/UPLOAD_INDEX.json'
    index=json.loads(index_path.read_text(encoding='utf-8'))
    plan_path=index_path.parent/'plan/plan.json'
    if digest(plan_path)!=index['plan_sha256']:raise ValueError('Plan changed')
    plan=json.loads(plan_path.read_text(encoding='utf-8'));jobs={j['document_id']:j for j in plan['jobs']}
    entries={e['unit_id']:e for e in index['bundles']}
    inventory=json.loads((workspace/'unit_returns/download_inventory.json').read_text(encoding='utf-8'))
    if not inventory.get('complete') or len(inventory['units'])!=134:raise ValueError('Incomplete Drive extraction')
    old_path=workspace/'unit_returns/import_progress.json'
    previous=json.loads(old_path.read_text(encoding='utf-8')) if old_path.exists() else {'units':[]}
    completed={e['unit_id']:e for e in previous['units']}
    prepared_path=workspace/'unit_returns/assembly_progress.json'
    prepared=json.loads(prepared_path.read_text(encoding='utf-8')) if prepared_path.exists() else {'units':[]}
    staged={e['unit_id']:e for e in prepared['units']}
    known_assets={};verified_paths={};verified_sources=set();units=[]
    for number,e in enumerate(sorted(inventory['units'],key=lambda e:e['unit_id']),1):
        started=time.monotonic();uid=e['unit_id'];archive=Path(e['archive']);wanted=e['sha256']
        print(f'PREPARE {number}/134 {uid}',flush=True)
        with zipfile.ZipFile(archive) as z:
            header=json.loads(z.read('return.json'));logical=header['logical_files']
            trusted=(completed.get(uid) or staged.get(uid) or {}).get('archive_sha256')==wanted
            if trusted:
                for did in header['runs']:
                    audit=workspace/'runs'/did/'unit_audit'/uid
                    if not (audit/'records.jsonl').is_file():raise ValueError('Checkpoint audit missing')
            else:
                inspect_result(archive,entries[uid],index['plan_sha256'])
                if digest(archive)!=wanted:raise ValueError('Downloaded unit ZIP changed')
                raw=workspace/'unit_returns/raw'/f'{uid}_{wanted}.zip';raw.parent.mkdir(parents=True,exist_ok=True)
                if not raw.exists():link_copy(archive,raw)
                elif digest(raw)!=wanted:raise ValueError('Preserved raw ZIP changed')
                for did in header['runs']:
                    job=jobs[did];run=workspace/'runs'/did;run.mkdir(parents=True,exist_ok=True)
                    if did not in verified_sources:
                        if digest(job['source_path'])!=job['source_sha256']:raise ValueError('Original PDF changed')
                        verified_sources.add(did)
                    prefix='runs/'+did+'/'
                    read=lambda n:z.read('objects/'+logical[prefix+n])
                    records=[json.loads(line) for line in read('records.jsonl').decode('utf-8-sig').split('\n') if line.strip()]
                    for r in records:
                        validate_record(r)
                        for field in ['render','crop','context']:
                            name=r[field+'_path'];expected=r[field+'_sha256'];target=safe(run,name)
                            if target in verified_paths:
                                if verified_paths[target]!=expected:raise ValueError('Conflicting asset identity')
                                continue
                            if target.exists():
                                if digest(target)!=expected:raise ValueError('Existing review asset changed')
                            else:
                                target.parent.mkdir(parents=True,exist_ok=True)
                                if expected in known_assets:link_copy(known_assets[expected],target)
                                else:
                                    data=read(name)
                                    if hashlib.sha256(data).hexdigest()!=expected:raise ValueError('Asset source changed')
                                    temp=target.with_name(target.name+'.extracting');temp.write_bytes(data);os.replace(temp,target)
                            verified_paths[target]=expected;known_assets.setdefault(expected,target)
                    audit=run/'unit_audit'/uid;audit.mkdir(parents=True,exist_ok=True)
                    for name in ['manifest.json','records.jsonl','document_pages.jsonl','routing_summary.json','prepare_summary.json']:
                        if prefix+name not in logical:continue
                        data=read(name);target=audit/name
                        if target.exists():
                            if target.read_bytes()!=data:raise ValueError('Existing unit audit changed')
                        else:target.write_bytes(data)
                    receipt={'type':'independent_unit_import','unit_id':uid,'archive_sha256':wanted,
                        'source_sha256':job['source_sha256'],'human_decisions_auto_created':0}
                    key=sha(canonical(receipt))[:16]
                    write_once(run/'import_receipts'/(key+'.json'),receipt)
            item={'unit_id':uid,'archive_sha256':wanted,'seconds':round(time.monotonic()-started,2)}
            units.append(item);write_json(prepared_path,{'units':units,'all_units_prepared':len(units)==134,
                'human_decisions_auto_created':0,'training_exported':False})
            print(f'PREPARED {number}/134 {uid}: {item["seconds"]}s',flush=True)
    for did,job in jobs.items():
        run=workspace/'runs'/did;audits=sorted((run/'unit_audit').glob('unit_*'))
        records=merge_records(read_jsonl(p/'records.jsonl') for p in audits)
        pages={}
        for p in audits:
            for page in read_jsonl(p/'document_pages.jsonl'):
                if page['page'] in pages and pages[page['page']]!=page:raise ValueError('Conflicting source-page metadata')
                pages[page['page']]=page
        if set(pages)!=set(range(1,job['source_pages']+1)):raise ValueError('Incomplete course pages: '+did)
        manifest=json.loads((audits[0]/'manifest.json').read_text(encoding='utf-8'))
        manifest['document']['path']=job['source_path'];manifest['asset_root']=str(run)
        manifest.pop('processing_scope',None)
        manifest.update(imported_source_pages=sorted(pages),document_layout_complete=False,
            layout_inventory_status='unit_snapshots_imported_global_audit_pending',
            full_document_page_coverage=True,global_duplicate_and_split_audit_pending=True)
        write_json(run/'manifest.json',manifest)
        temp=run/'document_pages.next';temp.write_text(''.join(json.dumps(p,ensure_ascii=False)+'\n' for _,p in sorted(pages.items())),encoding='utf-8');os.replace(temp,run/'document_pages.jsonl')
        receipt={'type':'complete_course_local_assembly','source_sha256':job['source_sha256'],
            'units':[p.name for p in audits],'machine_predictions_preserved':True,
            'human_decisions_auto_created':0}
        publish_preserved(run,records,receipt)
        print(f'ASSEMBLED {job["course"]}: {len(pages)} pages / {len(records)} records',flush=True)
    write_json(old_path,{'units':units,'complete':True,'human_decisions_auto_created':0,
        'training_exported':False,'import_mode':'verified_archives_original_predictions_single_course_publish'})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',type=Path,default=ROOT.parent/'workspaces/unit100_v6_20261022')
    assemble(parser.parse_args().workspace)
