"""Verify all 134 archives, original PDFs, page scopes, seed assets and core hashes."""
import hashlib
import json
from pathlib import Path
import sys
import zipfile

from common import atomic_json,digest,load,verify_release
from unit_store import inspect_result

ROOT=Path(__file__).resolve().parent


def audit(folder):
    folder=Path(folder);index=load(folder/'UPLOAD_INDEX.json');plan=load(folder/'plan/plan.json')
    if digest(folder/'plan/plan.json')!=index['plan_sha256']:raise ValueError('Plan changed')
    jobs={j['job_id']:j for j in plan['jobs']};points=[];objects=0
    sources={j['source_sha256']:j for j in jobs.values()}
    for sha,j in sources.items():
        if digest(j['source_path'])!=sha:raise ValueError('Original source changed')
    for n,e in enumerate(index['bundles'],1):
        path=folder/e['filename']
        if digest(path)!=e['sha256']:raise ValueError('Input ZIP changed')
        with zipfile.ZipFile(path) as z:
            m=json.loads(z.read('bundle.json'));expected=m['files'];names=z.namelist()
            if len(names)!=len(set(names)) or set(names)!=set(expected)|{'bundle.json'}:raise ValueError('Input inventory mismatch')
            for name,wanted in expected.items():
                h=hashlib.sha256()
                with z.open(name) as src:
                    for block in iter(lambda:src.read(1024*1024),b''):h.update(block)
                if h.hexdigest()!=wanted:raise ValueError('Input member changed: '+name)
                objects+=1
            if expected['plan.json']!=index['plan_sha256'] or m['unit_id']!=e['unit_id']:raise ValueError('Wrong unit metadata')
            active=[jobs[j] for j in m['jobs']]
            scope={(j['source_sha256'],p) for j in active for p in range(j['first_page'],j['last_page']+1)}
            if len(scope)!=m['pages'] or m['pages']>100:raise ValueError('Input page limit violated')
            points.extend(scope)
            if sum(j['vlm_page_budget'] for j in active)>__import__('math').ceil(.05*m['pages']):raise ValueError('Unit budget violated')
            for f in m['seed_fragments']:
                from jsonl_adapter import loads_jsonl
                j=jobs[f['job_id']];prefix=f['prefix'];rs=loads_jsonl(z.read(prefix+'/records.jsonl'),str(z.filename)+'!'+prefix+'/records.jsonl')
                for r in rs:
                    if not j['first_page']<=r['page']<=j['last_page'] or r['source_sha256']!=j['source_sha256']:raise ValueError('Seed page escaped scope')
                    if r.get('human_verified') or r.get('semantic_verified'):raise ValueError('Machine input conveyed verification')
                    for field in ['crop','context','render']:
                        asset='seed_assets/'+j['document_id']+'/'+r[field+'_path']
                        if expected[asset]!=r[field+'_sha256']:raise ValueError('Seed asset identity changed')
        if n%10==0 or n==len(index['bundles']):print('AUDIT',n,'/',len(index['bundles']),flush=True)
    if len(points)!=len(set(points)) or len(points)!=index['pages']:raise ValueError('Duplicate or missing global pages')
    wanted={(j['source_sha256'],p) for j in sources.values() for p in range(1,j['source_pages']+1)}
    if set(points)!=wanted:raise ValueError('Corpus not completely covered')
    pre=load(folder/'precompleted_results/PRECOMPLETED_INDEX.json');by_id={e['unit_id']:e for e in index['bundles']}
    for e in pre['units']:
        path=folder/'precompleted_results'/e['filename']
        if digest(path)!=e['sha256']:raise ValueError('Precompleted ZIP changed')
        inspect_result(path,by_id[e['unit_id']],index['plan_sha256'])
    core=ROOT.parent.parent/'Qwen_cpt_version/region_preprocessing_v5_official';verified=verify_release(core)
    result={'schema':'unit100-audit-v1','input_archives':len(index['bundles']),'documents':len(sources),'pages':len(points),
            'full_units':sum(e['pages']==100 for e in index['bundles']),'last_unit_pages':index['bundles'][-1]['pages'],
            'input_members_verified':objects,'total_input_bytes':index['total_bytes'],'max_input_bytes':max(e['bytes'] for e in index['bundles']),
            'precompleted_units':len(pre['units']),'precompleted_pages':pre['reused_pages'],
            'pending_units_after_legacy_import':len(index['bundles'])-len(pre['units']),
            'pending_pages_after_legacy_import':index['pages']-pre['reused_pages'],
            'core_files_verified':len(verified['files']),'duplicate_pages':0,'missing_pages':0,
            'actual_Colab_executed':False,'source_pdfs_modified':False,'human_verification_created':False}
    atomic_json(ROOT/'INPUT_VALIDATION_20261022.json',result);return result


if __name__=='__main__':print(json.dumps(audit(sys.argv[1]),ensure_ascii=False,indent=2))
