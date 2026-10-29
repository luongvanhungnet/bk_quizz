"""Run existing local Qwen weights only; preserve every raw completion and failure."""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import os
import platform
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

from build_suite import RUN,save,sha

MAIN='http://127.0.0.1:11434'
HELPER='http://127.0.0.1:11435'
OLD=Path(r'D:\ollama_models')
BIN=Path(r'C:\Users\hungw\AppData\Local\Programs\Ollama\ollama.exe')

def now():return dt.datetime.now(dt.timezone(dt.timedelta(hours=7))).isoformat()
def api(base,path,payload=None,timeout=20):
    data=json.dumps(payload,ensure_ascii=False).encode('utf-8') if payload is not None else None
    req=urllib.request.Request(base+path,data=data,headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=timeout) as r:return json.load(r)

def discover():
    current=api(MAIN,'/api/tags')['models'];old_rows=[]
    for p in (OLD/'manifests').rglob('*'):
        if not p.is_file():continue
        manifest=json.loads(p.read_text(encoding='utf-8'))
        parts=p.relative_to(OLD/'manifests').parts
        if len(parts)<4 or 'qwen' not in parts[-2].lower():continue
        layers=[manifest['config']]+manifest['layers']
        complete=all((OLD/'blobs'/r['digest'].replace(':','-')).is_file() and
                     (OLD/'blobs'/r['digest'].replace(':','-')).stat().st_size==r['size'] for r in layers)
        old_rows.append({'name':parts[-2]+':'+parts[-1],'digest':hashlib.sha256(p.read_bytes()).hexdigest(),
                         'manifest':str(p),'complete':complete,'size':sum(r['size'] for r in layers)})
    known={m['digest'] for m in current};extra=[r for r in old_rows if r['complete'] and r['digest'] not in known]
    return current,old_rows,extra

def start_helper(log_path):
    try:
        api(HELPER,'/api/version',timeout=2)
        raise RuntimeError('Port 11435 is already occupied; refusing to reuse an unowned server.')
    except urllib.error.URLError:pass
    env=os.environ.copy();env.update(OLLAMA_HOST='127.0.0.1:11435',OLLAMA_MODELS=str(OLD),OLLAMA_NUM_PARALLEL='1',OLLAMA_MAX_LOADED_MODELS='1',OLLAMA_NOPRUNE='true',OLLAMA_NO_CLOUD='true')
    with log_path.open('ab') as log:
        proc=subprocess.Popen([str(BIN),'serve'],env=env,stdout=log,stderr=log,
                              creationflags=subprocess.CREATE_NO_WINDOW)
    save(RUN/'temporary_server_starting.json',{'pid':proc.pid,'endpoint':HELPER,'started_at':now()})
    try:
        for _ in range(20):
            if proc.poll() is not None:raise RuntimeError('Temporary Ollama server exited during startup')
            try:
                api(HELPER,'/api/version',timeout=10);return proc
            except (urllib.error.URLError,TimeoutError):time.sleep(.5)
        raise RuntimeError('Temporary server did not become ready')
    except Exception:
        proc.terminate();raise

def completion(base,model,messages,protocol,path,warmup=False):
    options=dict(protocol['options'])
    if warmup:options['num_predict']=8
    request={'model':model,'messages':messages,'stream':True,'think':False,'keep_alive':'5m','options':options}
    request_hash=sha(json.dumps(request,ensure_ascii=False,sort_keys=True,separators=(',',':')))
    record={'model':model,'endpoint':base,'started_at':now(),'request':request,'request_sha256':request_hash,
            'warmup':warmup,'content':'','thinking':'','chunks':0}
    start=time.perf_counter();first=None;final={}
    try:
        req=urllib.request.Request(base+'/api/chat',data=json.dumps(request,ensure_ascii=False).encode('utf-8'),headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=protocol['timeout_seconds']) as response:
            with path.with_suffix('.stream.jsonl').open('w',encoding='utf-8',newline='\n') as stream:
                for line in response:
                    if not line.strip():continue
                    chunk=json.loads(line);stream.write(json.dumps(chunk,ensure_ascii=False)+'\n');stream.flush()
                    record['chunks']+=1
                    msg=chunk.get('message',{})
                    if first is None and (msg.get('content') or msg.get('thinking')):first=time.perf_counter()-start
                    record['content']+=msg.get('content','');record['thinking']+=msg.get('thinking','')
                    if chunk.get('error'):raise RuntimeError(chunk['error'])
                    if chunk.get('done'):final=chunk
                    if time.perf_counter()-start>protocol['timeout_seconds']:raise TimeoutError('Common wall-time budget exceeded')
        if not final.get('done'):raise RuntimeError('Stream ended without terminal response')
        record.update(status='ok',response_metadata={k:v for k,v in final.items() if k!='message'})
    except Exception as exc:
        record.update(status='error',error_type=type(exc).__name__,error=str(exc))
        if isinstance(exc,urllib.error.HTTPError):record['error_body']=exc.read().decode('utf-8',errors='replace')[:4000]
    record.update(elapsed_seconds=round(time.perf_counter()-start,4),time_to_first_token_seconds=round(first,4) if first is not None else None,
                  completed_at=now(),content_sha256=sha(record['content']))
    save(path,record)
    return record

def run():
    protocol=json.loads((RUN/'protocol.json').read_text(encoding='utf-8'))
    prompts=json.loads((RUN/'prompts.json').read_text(encoding='utf-8'))
    for name,expected in protocol['artifacts_sha256'].items():
        if sha((RUN/name).read_text(encoding='utf-8'))!=expected:raise ValueError('Frozen suite/rubric changed: '+name)
    current,old,extra=discover();helper=None
    save(RUN/'runtime_before.json',{'main_version':api(MAIN,'/api/version'),'models_running':api(MAIN,'/api/ps'),
                                   'python':platform.python_version(),'platform':platform.platform(),'time':now()})
    if api(MAIN,'/api/ps')['models']:raise RuntimeError('Another model is running on the main server; do not contaminate its work.')
    try:
        if extra:
            helper=start_helper(RUN/'temporary_server.log')
            save(RUN/'temporary_server.json',{'pid':helper.pid,'endpoint':HELPER,'models_path':str(OLD),'started_at':now()})
        models=[{**m,'endpoint':MAIN,'storage_root':str(Path.home()/'.ollama/models')} for m in current if 'qwen' in m['name'].lower()]
        helper_tags=api(HELPER,'/api/tags')['models'] if helper else []
        save(RUN/'legacy_server_tags.json',helper_tags)
        for row in extra:
            found=next((m for m in helper_tags if m['name']==row['name']),None)
            if not found:raise RuntimeError('Complete legacy model not visible to temporary server: '+row['name'])
            if found['digest'] not in {m['digest'] for m in models}:
                models.append({**found,'endpoint':HELPER,'storage_root':str(OLD)})
        models.sort(key=lambda m:(m['size'],m['name']))
        for i,m in enumerate(models):
            m['eval_id']=f'M{i+1:02d}'
            show=api(m['endpoint'],'/api/show',{'model':m['name']})
            save(RUN/'model_details'/f'{m["eval_id"]}.json',show)
            m['template_sha256']=sha(show.get('template',''));m['parameters']=show.get('parameters','')
        save(RUN/'inventory.json',{'models':models,'legacy_manifests':old,'legacy_duplicate_manifests':[r for r in old if r['digest'] in {m['digest'] for m in current}],
             'excluded_tokenizer_only':'C:/Users/hungw/.cache/huggingface/hub/models--Qwen--Qwen2.5-7B has tokenizer/config only; no model weights.',
             'search_roots':['C:/Users/hungw/.ollama/models','D:/ollama_models','C:/Users/hungw/.cache/huggingface','D:/AI','D:/BKQuiz/AI','D:/Download'],
             'additional_weight_search':'No other Qwen GGUF/safetensors/checkpoint weights found in the inspected model/project/download roots.',
             'order':'ascending stored bytes; sequential model groups','captured_at':now()})
        print('Models:',', '.join(m['name'] for m in models),flush=True)
        for m in models:
            dest=RUN/'responses'/m['eval_id'];dest.mkdir(parents=True,exist_ok=True)
            print('START',m['eval_id'],m['name'],flush=True)
            warm_path=dest/'warmup.json'
            if not warm_path.exists():
                warm=completion(m['endpoint'],m['name'],[{'role':'user','content':'Chỉ trả lời OK.'}],protocol,warm_path,True)
                print('WARMUP',m['name'],warm['status'],warm['elapsed_seconds'],flush=True)
            for case in prompts:
                path=dest/f'{case["id"]}.json'
                if path.exists():
                    previous=json.loads(path.read_text(encoding='utf-8'))
                    if previous.get('messages_sha256')!=case['messages_sha256'] or previous.get('model_digest')!=m['digest']:
                        raise ValueError('Incompatible cached run: '+str(path))
                    continue
                live=api(m['endpoint'],'/api/tags')['models']
                if not any(x['digest']==m['digest'] and x['name']==m['name'] for x in live):raise RuntimeError('Model changed during evaluation')
                result=completion(m['endpoint'],m['name'],case['messages'],protocol,path)
                result.update(case_id=case['id'],messages_sha256=case['messages_sha256'],model_digest=m['digest'],eval_id=m['eval_id'])
                save(path,result)
                print(m['name'],case['id'],result['status'],str(result['elapsed_seconds'])+'s',
                      'tokens='+str(result.get('response_metadata',{}).get('eval_count')),flush=True)
            api(m['endpoint'],'/api/generate',{'model':m['name'],'keep_alive':0},timeout=60)
        save(RUN/'run_complete.json',{'completed_at':now(),'models':len(models),'prompts_per_model':len(prompts),
                                    'expected_responses':len(models)*len(prompts),'suite_hashes':protocol['artifacts_sha256']})
    finally:
        if helper:
            try:
                for model in api(HELPER,'/api/ps')['models']:api(HELPER,'/api/generate',{'model':model['name'],'keep_alive':0},timeout=60)
            except Exception:pass
            helper.terminate()
            try:helper.wait(timeout=15)
            except subprocess.TimeoutExpired:helper.kill()
            save(RUN/'temporary_server_stopped.json',{'pid':helper.pid,'stopped_at':now()})

if __name__=='__main__':run()
