"""Build independent <=100-page units from the unchanged 14-input corpus plan."""
import argparse
import json
import math
from pathlib import Path
import shutil
import sys
import zipfile

from common import atomic_json,digest,load,rows,verify_release,write_archive

ROOT=Path(__file__).resolve().parent
ENGINE=ROOT.parent.parent/'Qwen_cpt_version/region_preprocessing_v5_official'
INPUT_SCHEMA='v5-unit-input-v1'


def partition(jobs, size=100):
    if size!=100:raise ValueError('This release requires 100-page units')
    documents={}
    for j in jobs:documents.setdefault(j['document_id'],j)
    units=[];parts=[];remaining=size
    def flush():
        nonlocal parts,remaining
        if not parts:return
        number=len(units)+1;unit_id=f'unit_{number:04d}'
        count=sum(p['last_page']-p['first_page']+1 for p in parts)
        budget=math.ceil(.05*count)
        allocations=[budget*(p['last_page']-p['first_page']+1)/count for p in parts]
        quotas=[math.floor(x) for x in allocations]
        for i in sorted(range(len(parts)),key=lambda i:(-(allocations[i]-quotas[i]),i))[:budget-sum(quotas)]:quotas[i]+=1
        for p,q in zip(parts,quotas):p.update(unit_id=unit_id,vlm_page_budget=q)
        units.append({'unit_id':unit_id,'bundle_index':number,'pages':count,'jobs':parts,'vlm_page_budget':budget})
        parts=[];remaining=size
    for did,j in documents.items():
        source_ranges=[x for x in jobs if x['document_id']==did]
        coverage=[p for x in sorted(source_ranges,key=lambda x:x['first_page']) for p in range(x['first_page'],x['last_page']+1)]
        if coverage!=list(range(1,j['source_pages']+1)):raise ValueError('Old plan has missing/duplicate source pages: '+did)
        first=1
        while first<=j['source_pages']:
            last=min(j['source_pages'],first+remaining-1)
            part={**j,'first_page':first,'last_page':last,'job_id':f'{did}_p{first:05d}-{last:05d}',
                  'legacy_job_ids':[x['job_id'] for x in source_ranges if x['first_page']<=last and x['last_page']>=first]}
            parts.append(part);remaining-=last-first+1;first=last+1
            if remaining==0:flush()
    flush()
    return units


def build(old_index,out):
    old_index,out=Path(old_index).resolve(),Path(out).resolve()
    if out.exists():raise FileExistsError('Inputs are immutable; choose a new output directory')
    old=load(old_index);plan=None
    for b in old['bundles']:
        path=Path(b['path'])
        print('VERIFY OLD INPUT',path.name,flush=True)
        if digest(path)!=b['sha256']:raise ValueError('Old input changed: '+str(path))
        with zipfile.ZipFile(path) as z:
            content=z.read('plan.json')
            import hashlib
            if hashlib.sha256(content).hexdigest()!=old['plan_sha256']:raise ValueError('Old plan changed')
            if plan is None:plan=json.loads(content)
    verify_release(ENGINE)
    if digest(ENGINE/'RELEASE.json')!=plan['release_manifest_sha256']:raise ValueError('Core release mismatch')
    units=partition(plan['jobs']);count=len(units)
    out.mkdir(parents=True);meta=out/'plan';meta.mkdir()
    jobs=[j for u in units for j in u['jobs']]
    for j in {j['document_id']:j for j in jobs}.values():
        if digest(j['source_path'])!=j['source_sha256']:raise ValueError('Original PDF changed')
    local_config={**plan['config'],'work_root':str(ROOT.parent/'workspaces/unit100_20261022'),
                  'unit_processing':True,'unit_pages':100}
    (meta/'jobs.jsonl').write_text(''.join(json.dumps(j,ensure_ascii=False)+'\n' for j in jobs),encoding='utf-8')
    atomic_json(meta/'config_snapshot.json',local_config)
    global_plan={**plan,'schema':INPUT_SCHEMA,'jobs':jobs,'config':local_config,'jobs_sha256':digest(meta/'jobs.jsonl'),
                 'bundle_count':count,'previous_plan_sha256':old['plan_sha256'],'sequence_required':False,
                 'unit_pages':100,'units':[{**u,'jobs':[j['job_id'] for j in u['jobs']]} for u in units]}
    atomic_json(meta/'plan.json',global_plan)
    common={f'engine/{n}':ENGINE/n for n in [*load(ENGINE/'RELEASE.json')['files'],'RELEASE.json']}
    common['plan.json']=meta/'plan.json'
    entries=[]
    for u in units:
        files=dict(common);fragments=[]
        staging=out/'_seed_metadata'/u['unit_id']
        for j in u['jobs']:
            files[f'sources/{j["source_sha256"]}.pdf']=Path(j['source_path'])
            if j['layout_required']:continue
            run=Path(j['run']);selected=[r for r in rows(run/'records.jsonl') if j['first_page']<=r['page']<=j['last_page']]
            pages=[p for p in rows(run/'document_pages.jsonl') if j['first_page']<=p['page']<=j['last_page']]
            if {p['page'] for p in pages}!=set(range(j['first_page'],j['last_page']+1)):raise ValueError('Seed has missing pages')
            frag=staging/j['job_id'];frag.mkdir(parents=True)
            for name,values in [('records.jsonl',selected),('document_pages.jsonl',pages)]:
                if name=='records.jsonl':
                    values=[{**r,'semantic_verified':False,'human_verified':False} for r in values]
                (frag/name).write_text(''.join(json.dumps(v,ensure_ascii=False)+'\n' for v in values),encoding='utf-8')
            prefix='seed_fragments/'+j['job_id']
            for p in frag.iterdir():files[prefix+'/'+p.name]=p
            for n in ['manifest.json','prepare_summary.json','classification.json','duplicate_candidates.json','benchmark_groups.json','benchmark_queue.jsonl']:
                if (run/n).exists():files[prefix+'/'+n]=run/n
            for n in {r[k] for r in selected for k in ['render_path','crop_path','context_path']}:
                files['seed_assets/'+j['document_id']+'/'+n]=run/n
            fragments.append({'job_id':j['job_id'],'document_id':j['document_id'],'prefix':prefix,
                              'records_sha256':digest(frag/'records.jsonl'),'pages':list(range(j['first_page'],j['last_page']+1))})
        path=out/f'v5_unit_{u["bundle_index"]:04d}_of_{count:04d}.zip'
        header={'schema':INPUT_SCHEMA,'bundle_id':u['unit_id'],'unit_id':u['unit_id'],
                'bundle_index':u['bundle_index'],'bundle_count':count,'pages':u['pages'],
                'jobs':[j['job_id'] for j in u['jobs']],'plan_sha256':digest(meta/'plan.json'),
                'seed_fragments':fragments,'sequence_required':False,'processing_limit_pages':100,
                'source_pdfs_are_originals':True,'human_verification_auto_created':False}
        write_archive(path,files,header,'bundle.json')
        entry={'unit_id':u['unit_id'],'bundle_index':u['bundle_index'],'path':str(path),'filename':path.name,
               'sha256':digest(path),'bytes':path.stat().st_size,'pages':u['pages'],
               'jobs':header['jobs'],'source_ranges':[{'document_id':j['document_id'],'course':j['course'],
                   'source_sha256':j['source_sha256'],'first_page':j['first_page'],'last_page':j['last_page']} for j in u['jobs']]}
        entries.append(entry);print('BUILT',path.name,'pages',u['pages'],'MiB',round(entry['bytes']/1024**2,2),flush=True)
    result={'schema':INPUT_SCHEMA,'bundle_count':count,'unit_pages':100,'pages':sum(u['pages'] for u in units),
            'documents':len({j['document_id'] for j in jobs}),'jobs':len(jobs),'plan_sha256':digest(meta/'plan.json'),
            'previous_index':str(old_index),'previous_plan_sha256':old['plan_sha256'],'bundles':entries,
            'total_bytes':sum(e['bytes'] for e in entries),'original_inputs_modified':False}
    atomic_json(out/'UPLOAD_INDEX.json',result)
    (out/'UPLOAD_LIST.md').write_text('# 134 gói độc lập, tối đa 100 trang xử lý/gói\n\n'+
        '\n'.join(f'- {e["filename"]}: {e["pages"]} trang; {e["bytes"]/1024**2:.2f} MiB' for e in entries)+'\n',encoding='utf-8')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--old-index',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();print(json.dumps({k:v for k,v in build(a.old_index,a.out).items() if k!='bundles'},indent=2))
