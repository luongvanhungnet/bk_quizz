"""UTF-8, immutable artifacts and source-bound snapshots."""
import hashlib
import json
from pathlib import Path
import unicodedata

def canonical(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def sha(v):return hashlib.sha256(v if isinstance(v,bytes) else v.encode('utf-8')).hexdigest()
def file_sha(p):return sha(Path(p).read_bytes())
def load(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def jsonl(p):return [json.loads(l) for l in Path(p).read_text(encoding='utf-8-sig').splitlines() if l.strip()]
def write_json(p,v):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def write_jsonl(p,rows):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(''.join(canonical(r)+'\n' for r in rows),encoding='utf-8')
def write_once(p,v):
    p=Path(p);data=json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False).encode('utf-8')
    p.parent.mkdir(parents=True,exist_ok=True)
    if p.exists():
        if p.read_bytes()!=data:raise ValueError('Immutable artifact exists: '+str(p))
    else:p.write_bytes(data)
def normalize(text):return unicodedata.normalize('NFC',text).replace('\u00a0',' ')
def safe_path(root,name):
    p=(Path(root)/name).resolve()
    if not p.is_relative_to(Path(root).resolve()):raise ValueError('Path outside run')
    return p
