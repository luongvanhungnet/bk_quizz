"""Run the existing six prompts against original and imported CPT Ollama models."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
from compare_exports import compare,load,PROBES,BENCH
sys.path.insert(0,str(BENCH))
from run_benchmark import api,completion,MAIN
from import_ollama import parameter_signature


def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def main(a):
    cases=load(PROBES/'prompts.json')
    protocol=load(BENCH/'runs/2026-10-17/protocol.json')
    tags=api(MAIN,'/api/tags')['models']
    if a.base==a.cpt:raise ValueError('Two different model tags are required')
    models=[]
    for name in [a.base,a.cpt]:
        tag=next((m for m in tags if m['name']==name),None)
        if not tag:raise ValueError('Import the model first: '+name)
        show=api(MAIN,'/api/show',{'model':name})
        if show['details'].get('quantization_level')!='Q4_K_M':raise ValueError('Both models must be Q4_K_M')
        models.append({'name':name,'digest':tag['digest'],'show':show})
    if models[0]['show']['template']!=models[1]['show']['template']:
        raise ValueError('Chat templates differ; import with import_ollama.py first')
    if parameter_signature(models[0]['show'].get('parameters'))!=parameter_signature(models[1]['show'].get('parameters')):
        raise ValueError('Model defaults differ')
    active=api(MAIN,'/api/ps')['models']
    if any(m['name'] not in [a.base,a.cpt] for m in active):
        raise ValueError('Another model is loaded. Finish other inference work before this benchmark.')
    identity={'models':models,'options':protocol['options'],'prompts_sha256':hashlib.sha256((PROBES/'prompts.json').read_bytes()).hexdigest()}
    a.out.mkdir(parents=True,exist_ok=True)
    snapshot=a.out/'run_identity.json'
    if snapshot.exists() and load(snapshot)!=identity:raise ValueError('Existing run differs: choose a new --out')
    save(snapshot,identity)
    for m in models:
        api(MAIN,'/api/generate',{'model':m['name'],'keep_alive':0},timeout=60)
    template_hash=hashlib.sha256(models[0]['show']['template'].encode()).hexdigest()
    exports=[]
    for variant,m in zip(['before','after'],models):
        dest=a.out/'responses'/variant;dest.mkdir(parents=True,exist_ok=True)
        api(MAIN,'/api/generate',{'model':m['name'],'keep_alive':0},timeout=60)
        warm=dest/'warmup.json'
        if not warm.exists():completion(MAIN,m['name'],[{'role':'user','content':'Chỉ trả lời OK.'}],protocol,warm,True)
        try:
            results=[]
            for case in cases:
                path=dest/(case['id']+'.json')
                live=api(MAIN,'/api/tags')['models']
                if not any(x['name']==m['name'] and x['digest']==m['digest'] for x in live):raise ValueError('Model changed mid-run')
                if path.exists():
                    r=load(path)
                    if r.get('messages_sha256')!=case['messages_sha256'] or r.get('model_digest')!=m['digest']:
                        raise ValueError('Cached request identity mismatch')
                else:
                    r=completion(MAIN,m['name'],case['messages'],protocol,path)
                    r.update(messages_sha256=case['messages_sha256'],model_digest=m['digest'],case_id=case['id'])
                    save(path,r)
                results.append({'case_id':case['id'],'messages_sha256':case['messages_sha256'],
                                'content':r['content'],'seconds':r['elapsed_seconds'],'request_status':r['status']})
                print(m['name'],case['id'],r['status'],flush=True)
            export={'model_id':'qwen3-1.7b-local-deployment-comparison',
                    'revision':'upstream-equivalence-not-proven-for-installed-tag',
                    'ollama_model_name':m['name'],'model_digest':m['digest'],
                    'config':{'options':protocol['options'],'think':False,'template_sha256':template_hash},
                    'quantization':'Q4_K_M','compute_dtype':'Ollama CPU num_gpu=0',
                    'adapter':None if variant=='before' else 'CPT merged into weights',
                    'prompts_sha256':identity['prompts_sha256'],'results':results}
            export_path=a.out/(variant+'.json');save(export_path,export);exports.append(export_path)
        finally:
            api(MAIN,'/api/generate',{'model':m['name'],'keep_alive':0},timeout=60)
    report=a.out/'comparison'
    if not (report/'REPORT.md').exists():compare(exports[0],exports[1],report)
    else:print('Existing report preserved:',report/'REPORT.md')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--base',default='qwen3:1.7b')
    p.add_argument('--cpt',default='qwen3-it3170-cpt:1.7b');p.add_argument('--out',type=Path,required=True)
    main(p.parse_args())
