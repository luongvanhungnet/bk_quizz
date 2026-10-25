"""Append-only source identities, including low-level crop tasks."""
import hashlib
import json
from pathlib import Path

def canonical(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def digest(v):return hashlib.sha256(v if isinstance(v,bytes) else v.encode('utf-8')).hexdigest()
def file_hash(p):return digest(Path(p).read_bytes())
def load(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def write_once(p,value):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);data=json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False).encode('utf-8')
    if p.exists():
        if p.read_bytes()!=data:raise ValueError('Refusing to overwrite: '+str(p))
    else:p.write_bytes(data)
def identity(r,config):return digest(canonical({'engine':r['engine'],'kind':r['kind'],'input_file_sha256':r['input_file_sha256'],'context_sha256':r['context_sha256'],'config':config}))
def task_identity(t,config):return digest(canonical({k:t.get(k) for k in ['parent_id','stage','input_file_sha256','context_sha256','max_new_tokens','source_bbox','depends_on','chunk_index']}|{'config':config}))
def check_package(root):
    root=Path(root).resolve();m=load(root/'manifest.json')
    def safe(name):
        p=(root/name).resolve()
        if not p.is_relative_to(root):raise ValueError('Unsafe package path')
        return p
    for name,sha in m['code_sha256'].items():
        if file_hash(safe(name))!=sha:raise ValueError('Changed runtime '+name)
    ids=set()
    for r in m['requests']:
        if r['id'] in ids:raise ValueError('Duplicate parent')
        ids.add(r['id'])
        if r['cache_key']!=identity(r,m['config']):raise ValueError('Parent identity changed')
        for field,sha in [('image','input_file_sha256'),('context','context_sha256')]:
            if file_hash(safe(r[field]))!=r[sha]:raise ValueError('Changed parent evidence')
    tasks=set()
    for t in m['tasks']:
        if t['id'] in tasks or t['parent_id'] not in ids:raise ValueError('Task inventory')
        tasks.add(t['id'])
        for field,sha in [('image','input_file_sha256'),('context','context_sha256')]:
            if file_hash(safe(t[field]))!=t[sha]:raise ValueError('Changed task evidence')
        if t['cache_key']!=task_identity(t,m['config']):raise ValueError('Task identity changed')
    if any(t.get('depends_on') and t['depends_on'] not in tasks for t in m['tasks']):raise ValueError('Unknown dependency')
    for name,sha in m['seed_sha256'].items():
        if file_hash(safe('seeds/'+name))!=sha:raise ValueError('Changed seed')
    return m
