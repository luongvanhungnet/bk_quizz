"""Read-only payload, byte identity and sequential dependency audit of the 14 real ZIPs."""
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from common import atomic_json,digest,load,rows


def audit():
    folder=ROOT.parent/'uploads_14_sequential_20261021';idx=load(folder/'UPLOAD_INDEX.json')
    plan=load(folder/'_build_metadata/plan.json');nb=load(ROOT/'Colab_V5_Sequential_14.ipynb')
    source=next(''.join(c['source']) for c in nb['cells'] if c['cell_type']=='code' and ''.join(c['source']).startswith('PINNED_RUNTIME='))
    pins=ast.literal_eval(ast.parse(source).body[0].value)
    seen={};source_hashes=set();jobs={j['job_id']:j for j in plan['jobs']};covered=[]
    asset_hashes={};seed_records={};seed_pages=set();cachekeys=set();done=[];runtime=None
    for i,b in enumerate(idx['bundles'],1):
        p=Path(b['path']);assert digest(p)==b['sha256']
        with zipfile.ZipFile(p) as z:
            m=json.loads(z.read('bundle.json'));assert m['bundle_index']==i
            assert set(z.namelist())==set(m['files'])|{'bundle.json'}
            assert len(z.namelist())==len(set(z.namelist()))
            current={n:h for n,h in m['files'].items() if n.startswith(('runtime/','engine/'))}
            if runtime is None:runtime=current
            assert current==runtime
            for n,wanted in m['files'].items():
                h=hashlib.sha256()
                with z.open(n) as f:
                    for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
                assert h.hexdigest()==wanted,n
                assert 'human_reviews.sqlite' not in n
                if n in seen:assert seen[n]==wanted,n
                seen[n]=wanted
                if n.startswith('sources/'):
                    assert Path(n).stem==wanted;assert wanted not in source_hashes;source_hashes.add(wanted)
                if n.startswith('seed_assets/'):asset_hashes[n]=wanted
                if n.startswith('vlm_seed_cache/'):cachekeys.add(Path(n).stem)
            for n,wanted in pins.items():assert m['files']['runtime/'+n]==wanted,(i,n)
            for frag in m['seed_fragments']:
                for r in [json.loads(l) for l in z.read(frag['prefix']+'/records.jsonl').decode('utf-8').splitlines()]:
                    assert r['id'] not in seed_records
                    seed_records[r['id']]=r;seed_pages.add(r['page'])
                    for prefix in ['crop','context','render']:
                        key='seed_assets/'+frag['document_id']+'/'+r[prefix+'_path']
                        assert seen.get(key)==r[prefix+'_sha256'],('future_dependency',i,r['id'],key)
            for jid in m['jobs']:
                j=jobs[jid];assert j['source_sha256'] in source_hashes,('future_source',i,jid)
                if j['layout_required']:
                    assert {x['job_id'] for x in plan['jobs'] if x['document_id']==j['document_id']}.issubset(set(m['jobs'])),('split_new_document',jid)
            covered+=m['jobs'];done+=m['completed_jobs']
        print('VERIFIED sequential',i,flush=True)
    assert Counter(covered)==Counter(jobs.keys())
    assert len(source_hashes)==27 and len(asset_hashes)==4490 and len(seed_records)==2245 and seed_pages==set(range(1,1061))
    legacy=ROOT.parent.parent/'Qwen_cpt_version/region_preprocessing_v5/runs/it3170_v5_20261020'
    for name,sha in asset_hashes.items():assert digest(legacy/name.split('/it3170_c6c829f14bf2/',1)[1])==sha
    original={r['id']:r for r in rows(legacy/'records.jsonl')};assert seed_records==original
    assert len(cachekeys)==7 and len(done)==1
    result={'schema':idx['schema'],'client_date':'2026-10-21','verified_inputs':14,'source_jobs':148,'source_pages':13314,'source_pdfs':27,
            'all_payload_hashes_valid':True,'runtime_matches_notebook':True,'no_future_input_dependencies':True,'whole_document_layout_routing_preserved':True,
            'cache_assets_byte_identical_to_v1':4490,'cached_source_records_identical':2245,'cached_source_pages':len(seed_pages),
            'vlm_cache_successes':len(cachekeys),'completed_jobs_seeded':[x['job_id'] for x in done],
            'size_before':idx['size_before'],'size_after':idx['size_after'],'variance_reduction_percent':idx['variance_reduction_percent'],
            'gpu_benchmark_executed':False}
    atomic_json(ROOT/'INPUT_VALIDATION_20261021.json',result)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return result


if __name__=='__main__':audit()
