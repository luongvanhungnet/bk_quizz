"""Rebind the completed local preparation to final v5 policy, without rerendering.

Only runs into a fresh directory; retains the original manifest/records and all
source assets. This is a release receipt, not a cloud/human inference result.
"""
import sys
from pathlib import Path
import shutil
from collections import Counter
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from io_utils import load,jsonl,write_json,write_jsonl,file_sha
from cross_validation import cross_validate
from models import validate_record
from review_store import ReviewStore

def build():
    source=ROOT/'runs/it3170_v5_candidate';target=ROOT/'runs/it3170_v5_20261020'
    resuming=target.exists()
    if resuming:
        if (ROOT/'evidence/release_build_receipt.json').exists():raise FileExistsError('Release already completed')
        if (target/'human_reviews.sqlite3').exists():raise ValueError('Do not resume over a review database')
        # A runtime restart may interrupt the asset verification. Resume only an
        # unchanged preparation copy; never replace an independently edited run.
        for p in source.rglob('*'):
            if not p.is_file() or p.name.startswith('human_reviews.sqlite3'):continue
            q=target/p.relative_to(source)
            if not q.is_file() or file_sha(p)!=file_sha(q):raise ValueError('Incomplete/modified preparation copy: '+str(q))
    if ReviewStore(source).stats()['reviewed']:raise ValueError('Candidate has human history; preserve it explicitly')
    if not resuming:shutil.copytree(source,target,ignore=shutil.ignore_patterns('human_reviews.sqlite3*'))
    shutil.copy2(source/'manifest.json',target/'sources/pre_release_manifest.json')
    rows=jsonl(target/'records.jsonl');checks=0
    for r in rows:
        for field,digest in [('render_path','render_sha256'),('crop_path','crop_sha256'),('context_path','context_sha256')]:
            if file_sha(target/r[field])!=r[digest]:raise ValueError('Changed source asset '+r['id'])
            checks+=1
        for c in r['candidates']:
            ev=c.get('evidence') or {}
            if c['engine']=='native':ev.update(region_id=r['id'],crop_sha256=r['crop_sha256']);c['evidence']=ev
        r['optional_engines']=['docling','mineru']
        r['pending_engines']=[e for e in r['pending_engines'] if e not in r['optional_engines']]
    rows=[validate_record(cross_validate(r)) for r in rows]
    write_jsonl(target/'records.jsonl',rows);write_jsonl(target/'machine_snapshots/release_initial.jsonl',rows)
    manifest=load(target/'manifest.json');manifest.update(asset_root=str(target),initial_records_sha256=file_sha(target/'records.jsonl'),
        release_derivation={'candidate_manifest_sha256':file_sha(source/'manifest.json'),'candidate_records_sha256':file_sha(source/'records.jsonl'),
            'rendering_reused':True,'policy_reclassified':True})
    write_json(target/'manifest.json',manifest)
    summary=load(target/'prepare_summary.json');summary.update(buckets=dict(Counter(r['machine_bucket'] for r in rows)),
        schema_validated_records=len(rows),asset_hash_checks=checks,human_verified=0)
    write_json(target/'prepare_summary.json',summary)
    receipt={'source':str(source),'target':str(target),'source_manifest_sha256':file_sha(source/'manifest.json'),
        'release_manifest_sha256':file_sha(target/'manifest.json'),'release_records_sha256':file_sha(target/'records.jsonl'),
        'summary':summary,'human_reviews_copied':0,'original_snapshots_preserved':True}
    write_json(ROOT/'evidence/release_build_receipt.json',receipt);print(receipt)

if __name__=='__main__':build()
