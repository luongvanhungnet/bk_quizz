"""Verify imported page/asset coverage and publish the local course catalogue."""
from pathlib import Path
import argparse
from collections import Counter
from contextlib import closing
import hashlib
import json
import shutil
import sqlite3
import sys
import zipfile

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'colab_orchestrator_v5'))
sys.path.insert(0,str(ROOT.parent.parent/'Qwen_cpt_version/region_preprocessing_v5_0_1'))
from jsonl_adapter import read_jsonl
from review_app import successful_vlm_candidates
from ingest import digest,write_json


def check_pages(pages,source_pages):
    if len(pages)!=source_pages or {p['page'] for p in pages}!=set(range(1,source_pages+1)):
        raise ValueError('Incomplete/duplicate source pages')
    return len(pages)


def verify(workspace):
    index=ROOT.parent/'uploads_134_unit100_20261022'
    plan=json.loads((index/'plan/plan.json').read_text(encoding='utf-8'))
    jobs={j['document_id']:j for j in plan['jobs']}
    progress=json.loads((workspace/'unit_returns/import_progress.json').read_text(encoding='utf-8'))
    if not progress.get('complete') or len({e['unit_id'] for e in progress['units']})!=134:
        raise ValueError('Not all 134 units have been imported')
    documents=[];assets_checked={};asset_paths_checked={};source_shas=set();total_original_revisions_changed=0
    for did,job in jobs.items():
        run=workspace/'runs'/did
        records=read_jsonl(run/'records.jsonl');pages=read_jsonl(run/'document_pages.jsonl')
        manifest=json.loads((run/'manifest.json').read_text(encoding='utf-8'))
        count=check_pages(pages,job['source_pages'])
        if {r['page'] for r in records}!=set(range(1,job['source_pages']+1)):raise ValueError('Region page coverage differs')
        if len({r['id'] for r in records})!=len(records):raise ValueError('Duplicate region IDs')
        if manifest['document']['sha256']!=job['source_sha256'] or digest(job['source_path'])!=job['source_sha256']:
            raise ValueError('Original PDF source mismatch')
        for r in records:
            if r['source_sha256']!=job['source_sha256'] or r.get('human_verified') or r.get('semantic_verified'):
                raise ValueError('Invalid machine provenance/verification')
            for field in ['render','crop','context']:
                logical_key=(did,r[field+'_path'])
                if logical_key in asset_paths_checked:
                    if asset_paths_checked[logical_key]!=r[field+'_sha256']:raise ValueError('Conflicting repeated asset reference')
                    continue
                path=(run/r[field+'_path']).resolve()
                if not path.is_relative_to(run.resolve()):raise ValueError('Review asset escapes run')
                st=path.stat();key=(st.st_dev,st.st_ino,st.st_size)
                if key not in assets_checked:assets_checked[key]=digest(path)
                if assets_checked[key]!=r[field+'_sha256']:raise ValueError('Review asset hash mismatch')
                asset_paths_checked[logical_key]=r[field+'_sha256']
        existing={r['id']:r for r in records};changed=0
        for audit in (run/'unit_audit').glob('*/records.jsonl'):
            for before in read_jsonl(audit):
                after=existing[before['id']]
                if before.get('machine_revision')!=after.get('machine_revision'):changed+=1
                if before.get('proposed_text')!=after.get('proposed_text') or before.get('candidates')!=after.get('candidates'):
                    raise ValueError('Machine prediction changed during import')
        total_original_revisions_changed+=changed
        reviews=0;db=run/'human_reviews.sqlite3'
        if db.exists():
            with closing(sqlite3.connect(f'file:{db.as_posix()}?mode=ro',uri=True)) as connection:
                reviews=connection.execute('SELECT COUNT(*) FROM reviews').fetchone()[0]
        d={'document_id':did,'course':job['course'],'title':Path(job['source_path']).stem,
            'run':str(run.resolve()),'source_pdf':job['source_path'],'source_sha256':job['source_sha256'],
            'source_pages':job['source_pages'],'imported_pages':count,'records':len(records),
            'vlm_records':sum(bool(successful_vlm_candidates(r)) for r in records),
            'critical_records':sum(r.get('machine_bucket')=='critical' for r in records),
            'empty_records':sum(not (r.get('proposed_text') or '').strip() for r in records),
            'buckets':dict(Counter(r.get('machine_bucket') for r in records)),
            'existing_review_events':reviews,'machine_revisions_changed_on_publish':changed}
        documents.append(d);source_shas.add(job['source_sha256'])
        print(f'VERIFIED {job["course"]}: {count} pages, {len(records)} records, {d["vlm_records"]} VLM',flush=True)
    before_path=workspace/'unit_returns/existing_human_databases_before.json'
    dbs=json.loads(before_path.read_text(encoding='utf-8')) if before_path.exists() else []
    for db in dbs:
        if digest(db['path'])!=db['sha256']:raise ValueError('Pre-existing human database changed')
    catalog={'schema':'bkquiz-local-review-catalog-v1','workspace':str(workspace.resolve()),
        'totals':{'units':134,'documents':len(documents),'pages':sum(d['imported_pages'] for d in documents),
            'records':sum(d['records'] for d in documents),'vlm_records':sum(d['vlm_records'] for d in documents),
            'critical_records':sum(d['critical_records'] for d in documents),
            'empty_records':sum(d['empty_records'] for d in documents),'asset_objects_sha256_checked':len(assets_checked),
            'human_decisions_auto_created':0,'previous_human_databases_preserved':len(dbs),
            'machine_revisions_recomputed':total_original_revisions_changed},
        'documents':documents,'training_exported':False,'quality_certified':False,
        'raw_archives':str(workspace/'unit_returns/raw'),'all_raw_audit_files_retained_in_unit_zips':True}
    if len(documents)!=27 or catalog['totals']['pages']!=13314:raise ValueError('Corpus coverage does not match plan')
    write_json(workspace/'review_catalog.json',catalog)
    print(json.dumps(catalog['totals'],ensure_ascii=False),flush=True)
    return catalog


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',type=Path,default=ROOT.parent/'workspaces/unit100_v6_20261022')
    verify(parser.parse_args().workspace)
