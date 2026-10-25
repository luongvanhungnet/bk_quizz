"""Verify parent and task identities in a returned v4 archive, without promoting CPT."""
import argparse
from collections import Counter
import copy
import json
from pathlib import Path
import zipfile
from contracts import check_package,file_hash,load,write_once
from schema import validate_task
from validation import validate_prediction
from quality import assess
from worker import assemble

def import_results(a):
    if a.out.exists():raise ValueError('Choose a fresh review directory')
    m=check_package(a.run);requests={r['id']:r for r in m['requests']};tasks={t['id']:t for t in m['tasks']}
    with zipfile.ZipFile(a.results) as z:
        if z.testzip():raise ValueError('Corrupt result ZIP')
        candidates=[]
        for name in z.namelist():
            if name.startswith('results_') and name.endswith('.json'):
                s=json.loads(z.read(name))
                if s.get('manifest_sha256')!=file_hash(a.run/'manifest.json'):raise ValueError('Wrong manifest')
                candidates.append((name,s))
        if not candidates:raise ValueError('No v4 result snapshots')
        name,result=max(candidates,key=lambda v:(sum(t['status']=='ok' for t in v[1]['tasks']),sum(r['status']!='not_run' for r in v[1]['records']),v[0]))
        if len(result['records'])!=len(requests) or {r['id'] for r in result['records']}!=set(requests):raise ValueError('Parent inventory mismatch')
        if len({t['id'] for t in result['tasks']})!=len(result['tasks']):raise ValueError('Duplicate task results')
        output={t['id']:t for t in result['tasks']}
        for rid,r in output.items():
            if rid not in tasks:raise ValueError('Unknown result task')
            t=tasks[rid]
            if r['cache_key']!=t['cache_key'] or r['input_file_sha256']!=t['input_file_sha256'] or r['semantic_verified'] is not False:raise ValueError('Task identity/promotion mismatch')
            payload=load(a.run/t['context'])
            if t.get('depends_on') and t['stage']=='edges':payload['nodes']=output[t['depends_on']]['prediction']['nodes']
            elif t.get('depends_on') and t['stage']=='edge_attributes':
                dependency=tasks[t['depends_on']];up=output[dependency['id']]['prediction'];start=t['chunk_index']*4
                payload['edges']=up['edges'][start:start+4]
                payload['nodes']=output[dependency['depends_on']]['prediction']['nodes']
            if r['status']=='ok' and validate_task(t['stage'],r['prediction'],payload):raise ValueError('Successful task no longer validates')
        a.out.mkdir(parents=True);checked=[]
        for r in result['records']:
            q=requests[r['id']]
            if r['cache_key']!=q['cache_key'] or r['input_file_sha256']!=q['input_file_sha256'] or r.get('semantic_verified') is not False:raise ValueError('Parent identity/promotion mismatch')
            if q['engine']=='vlm':
                composed=assemble(q,[t for t in tasks.values() if t['parent_id']==q['id']],output,a.run)
                if r.get('prediction')!=composed.get('prediction') or r['status']!=composed['status']:raise ValueError('Parent differs from task evidence')
            elif r.get('prediction')!=load(a.run/'seeds'/(q['id']+'.json')).get('prediction'):raise ValueError('Reused specialist prediction changed')
            errors=validate_prediction(q['engine'],r.get('prediction'))
            context=load(a.run/q['context']);context.update(_image_path=str(a.run/q['image']),native_ocr=q.get('native_ocr',[]),
                _inventory_complete=r.get('inventory_complete'),_partial_task_failures=r.get('failed_or_pending_tasks',[]))
            quality=assess(q['engine'],r['prediction'],context) if not errors else {'flags':['invalid_or_missing_prediction'],'evidence_gate_pass':False}
            retry=any(output.get(t,{}).get('reduced_resolution_retry') for t in r.get('task_ids',[]))
            if retry:quality['flags']=sorted(set(quality['flags']+['reduced_resolution_retry_requires_review']));quality['evidence_gate_pass']=False
            checked.append({'request':q,'result':r,'structural_errors':errors,'quality':quality,'semantic_verified':False,'destination':'review_queue'})
        (a.out/'prediction_review.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in checked),encoding='utf-8')
        write_once(a.out/'results.json',result)
        write_once(a.out/'summary.json',{'archive_sha256':file_hash(a.results),'selected_snapshot':name,
            'by_engine':{e:dict(Counter(r['result']['status'] for r in checked if r['request']['engine']==e)) for e in ['formula','table','vlm']},
            'tasks':dict(Counter(t['status'] for t in output.values())),
            'heuristic_gate_pass':sum(r['result']['status']=='ok' and not r['structural_errors'] and r['quality']['evidence_gate_pass'] for r in checked),
            'flags':dict(Counter(f for r in checked for f in r['quality']['flags'])),'new_verified_CPT_samples':0})
    print(a.out)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--results',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    import_results(p.parse_args())
