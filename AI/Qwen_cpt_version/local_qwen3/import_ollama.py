"""Import the exported model under a new Ollama tag, preserving base chat settings."""
import argparse
import hashlib
import json
import subprocess
import urllib.request
from pathlib import Path

URL='http://127.0.0.1:11434'

def parameter_signature(value):
    # /api/show prints parameter keys in an unspecified order.
    return sorted(tuple(line.split()) for line in (value or '').splitlines() if line.strip())
def api(path,payload=None):
    req=urllib.request.Request(URL+path,data=json.dumps(payload).encode() if payload is not None else None,
                               headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=30) as response:return json.load(response)


def validate_model(path):
    path=Path(path).resolve()
    if path.is_file():
        with path.open('rb') as f:
            if f.read(4)!=b'GGUF':raise ValueError('Expected a GGUF file')
        return path
    cfg=json.loads((path/'config.json').read_text(encoding='utf-8'))
    if cfg.get('model_type')!='qwen3':raise ValueError('Expected a Qwen3 full HF export, not an adapter directory')
    index=path/'model.safetensors.index.json'
    names=set(json.loads(index.read_text(encoding='utf-8'))['weight_map'].values()) if index.exists() else {'model.safetensors'}
    if not names:raise ValueError('Empty weight index')
    for name in names:
        weight=(path/name).resolve()
        if weight.parent!=path or not weight.is_file() or weight.stat().st_size==0:
            raise ValueError('Missing or invalid weight shard: '+name)
    if not (path/'tokenizer.json').is_file():raise ValueError('Download the complete export, including tokenizer.json')
    return path


def main(a):
    model_path=validate_model(a.model_path)
    if a.name==a.base:raise ValueError('Use a new tag; do not replace the original model')
    tags=api('/api/tags')['models']
    if any(m['name']==a.name for m in tags):raise ValueError('Target tag exists. Choose a new --name.')
    base=api('/api/show',{'model':a.base})
    if base['details'].get('quantization_level')!='Q4_K_M':raise ValueError('Expected original Q4_K_M baseline')
    if not base.get('template'):raise ValueError('Base chat template is missing')
    source_path=model_path
    if model_path.is_dir():
        if a.check_only:
            print('HF files present. Import requires HF -> GGUF -> Q4_K_M via convert_local.py; no Ollama --quantize flag.')
            return
        from convert_local import convert
        model_path=convert(model_path,Path(__file__).resolve().parent/'models/qwen3-it3170-cpt-Q4_K_M.gguf')
    lines=['FROM '+json.dumps(model_path.as_posix(),ensure_ascii=False),
           'TEMPLATE """'+base['template']+'"""']
    lines += ['PARAMETER '+line.strip() for line in base.get('parameters','').splitlines() if line.strip()]
    for key,instruction in [('system','SYSTEM'),('license','LICENSE')]:
        if base.get(key):lines.append(instruction+' """'+base[key]+'"""')
    a.work.mkdir(parents=True,exist_ok=True)
    modelfile=a.work/'Modelfile';modelfile.write_text('\n'.join(lines)+'\n',encoding='utf-8',newline='\n')
    command=['ollama','create',a.name,'-f',str(modelfile)]
    print('Command:',subprocess.list2cmdline(command))
    if a.check_only:return
    subprocess.run(command,check=True)
    imported=api('/api/show',{'model':a.name})
    if imported.get('template')!=base['template']:raise ValueError('Imported template differs; do not benchmark yet')
    if imported['details'].get('quantization_level')!='Q4_K_M':raise ValueError('Imported quantization differs from baseline')
    if parameter_signature(imported.get('parameters'))!=parameter_signature(base.get('parameters')):raise ValueError('Imported default parameters differ')
    evidence={'base_model':a.base,'cpt_model':a.name,'source_path':str(source_path),'gguf_path':str(model_path),
              'base_show':base,'cpt_show':imported,'template_sha256':hashlib.sha256(base['template'].encode()).hexdigest(),
              'tags_after':api('/api/tags')}
    (a.work/'import_record.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Ready: ollama run '+a.name)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--model-path',type=Path,required=True)
    p.add_argument('--base',default='qwen3:1.7b');p.add_argument('--name',default='qwen3-it3170-cpt:1.7b')
    p.add_argument('--work',type=Path,default=Path(__file__).resolve().parent/'imported')
    p.add_argument('--check-only',action='store_true');main(p.parse_args())
