"""Merge independent unit snapshots by source/page; retain raw archives and human DBs."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import zipfile

from common import atomic_json,checked_extract,digest,load,rows,safe,verify_release
from unit_store import inspect_result

ROOT=Path(__file__).resolve().parent
ENGINE=ROOT.parent.parent/'Qwen_cpt_version/region_preprocessing_v5_official'


def import_units(index_path,archives,*,check_only=False,output_dir=None):
    index_path=Path(index_path).resolve();index=load(index_path)
    plan=load(index_path.parent/'plan/plan.json');by_doc={j['document_id']:j for j in plan['jobs']}
    if digest(index_path.parent/'plan/plan.json')!=index['plan_sha256']:raise ValueError('Local unit plan changed')
    verify_release(ENGINE);sys.path.insert(0,str(ENGINE))
    from jsonl_adapter import install as install_jsonl
    install_jsonl()
    from models import validate_record
    from workflow import publish
    output=Path(output_dir if output_dir is not None else plan['config']['work_root']);entries={e['unit_id']:e for e in index['bundles']}
    validated=[];seen={}
    for archive in archives:
        archive=Path(archive).resolve();sha=digest(archive)
        with zipfile.ZipFile(archive) as z:header=json.loads(z.read('return.json'))
        unit_id=header['unit_id'];entry=entries[unit_id]
        if unit_id in seen and seen[unit_id]!=sha:raise ValueError('Choose one result ZIP per unit')
        seen[unit_id]=sha;inspect_result(archive,entry,index['plan_sha256'])
        if check_only:validated.append((unit_id,sha));continue
        raw=output/'unit_returns/raw'/f'{unit_id}_{sha}.zip';raw.parent.mkdir(parents=True,exist_ok=True)
        if not raw.exists():shutil.copyfile(archive,raw)
        if digest(raw)!=sha:raise ValueError('Preserved raw archive mismatch')
        dest=output/'unit_returns/expanded'/sha[:20]
        if os.name=='nt':
            absolute=str(dest.resolve())
            dest=Path('\\\\?\\UNC\\'+absolute[2:] if absolute.startswith('\\\\') else '\\\\?\\'+absolute)
        m=checked_extract(raw,dest,'return.json')
        for did in m['runs']:
            job=by_doc[did];source=dest/'runs'/did;target=output/'runs'/did
            if digest(job['source_path'])!=job['source_sha256']:raise ValueError('Original local PDF changed')
            incoming=rows(source/'records.jsonl');pages=rows(source/'document_pages.jsonl')
            for r in incoming:validate_record(r)
            target.mkdir(parents=True,exist_ok=True)
            receipt={'type':'independent_unit_import','unit_id':unit_id,'archive_sha256':sha,
                     'source_sha256':job['source_sha256'],'human_decisions_auto_created':0}
            old_receipts=[load(p) for p in (target/'import_receipts').glob('*.json')]
            if any(r.get('archive_sha256')==sha for r in old_receipts):continue
            if any(r.get('unit_id')==unit_id and r.get('archive_sha256')!=sha for r in old_receipts):
                raise ValueError('Different result for an already imported unit; retained for explicit review')
            existing={r['id']:r for r in rows(target/'records.jsonl')} if (target/'records.jsonl').exists() else {}
            for r in incoming:
                if r['id'] in existing and existing[r['id']]!=r:raise ValueError('Unit import would overwrite an existing machine record')
                for field in ['render','crop','context']:
                    name=r[field+'_path'];origin=safe(source,name);dest_asset=safe(target,name)
                    if dest_asset.exists():
                        if digest(dest_asset)!=r[field+'_sha256']:raise ValueError('Unit import would overwrite an asset')
                    else:dest_asset.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(origin,dest_asset)
                existing[r['id']]=r
            existing_pages={p['page']:p for p in rows(target/'document_pages.jsonl')} if (target/'document_pages.jsonl').exists() else {}
            for p in pages:
                if p['page'] in existing_pages and existing_pages[p['page']]!=p:raise ValueError('Conflicting source-page metadata')
                existing_pages[p['page']]=p
            m_source=load(source/'manifest.json')
            manifest=load(target/'manifest.json') if (target/'manifest.json').exists() else m_source
            if manifest['document']['sha256']!=job['source_sha256']:raise ValueError('Existing run belongs to another source')
            manifest['document']['path']=job['source_path'];manifest['asset_root']=str(target)
            manifest.pop('processing_scope',None)
            covered=sorted(existing_pages);complete=covered==list(range(1,job['source_pages']+1))
            manifest.update(imported_source_pages=covered,document_layout_complete=False,
                            layout_inventory_status='unit_snapshots_imported_global_audit_pending',
                            full_document_page_coverage=complete,global_duplicate_and_split_audit_pending=True)
            atomic_json(target/'manifest.json',manifest)
            page_tmp=target/'document_pages.next'
            page_tmp.write_text(''.join(json.dumps(p,ensure_ascii=False)+'\n' for _,p in sorted(existing_pages.items())),encoding='utf-8')
            page_tmp.replace(target/'document_pages.jsonl')
            publish(target,sorted(existing.values(),key=lambda r:(r['page'],r['id'])),receipt)
            audit=target/'unit_audit'/unit_id
            if not audit.exists():
                audit.mkdir(parents=True)
                for name in ['manifest.json','records.jsonl','document_pages.jsonl','routing_summary.json','prepare_summary.json']:
                    if (source/name).exists():shutil.copyfile(source/name,audit/name)
        validated.append((unit_id,sha))
    return {'units_validated':len(validated),'check_only':check_only,'human_databases_modified':False,
            'training_exported':False,'output':str(output/'runs')}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--index',type=Path,required=True);p.add_argument('--results',type=Path,nargs='+',required=True)
    p.add_argument('--output',type=Path,default=ROOT.parent/'workspaces/unit100_v6_20261022')
    p.add_argument('--check-only',action='store_true');a=p.parse_args()
    print(json.dumps(import_units(a.index,a.results,check_only=a.check_only,output_dir=a.output),ensure_ascii=False,indent=2))
