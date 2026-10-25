"""Content identities and append-only files shared by local and cloud commands."""
import hashlib
import json
from pathlib import Path


def canonical(value):return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False)
def digest(data):return hashlib.sha256(data if isinstance(data,bytes) else data.encode('utf-8')).hexdigest()
def file_hash(p):return digest(Path(p).read_bytes())
def load(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def write_once(p,value):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    data=json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False).encode('utf-8')
    if p.exists():
        if p.read_bytes()!=data:raise ValueError('Refusing to overwrite audit: '+str(p))
    else:p.write_bytes(data)


def identity(r,config):
    return digest(canonical({k:r.get(k) for k in ['engine','kind','input_pixel_sha256','native_ocr','context_sha256']}|{'config':config}))


def check_package(root):
    root=Path(root).resolve();m=load(root/'manifest.json')
    def safe(name):
        path=(root/name).resolve()
        if not path.is_relative_to(root):raise ValueError('Path outside package')
        return path
    for name,sha in m['code_sha256'].items():
        if file_hash(safe(name))!=sha:raise ValueError('Changed package code/evidence: '+name)
    ids=set()
    for r in m['requests']:
        if r['id'] in ids:raise ValueError('Duplicate request ID')
        ids.add(r['id'])
        for field,key in [('image','input_file_sha256'),('context','context_sha256')]:
            if file_hash(safe(r[field]))!=r[key]:raise ValueError('Changed request source '+field)
        if r['cache_key']!=identity(r,m['config']):raise ValueError('Stale inference identity')
    for name,sha in m['seed_sha256'].items():
        if file_hash(safe('seeds/'+name))!=sha:raise ValueError('Changed seed')
    return m
