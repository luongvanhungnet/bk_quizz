"""Pinned llama.cpp conversion on Windows: HF -> F16 GGUF -> Q4_K_M.

Uses an isolated CPU-only Python environment, never changes training packages.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parent
TAG='b6500'


def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def download(url,path,expected=None):
    if path.exists():
        if expected and sha(path)!=expected:raise ValueError('Cached download checksum differs: '+str(path))
        return
    temporary=path.with_suffix(path.suffix+'.partial')
    with urllib.request.urlopen(url,timeout=120) as response,temporary.open('wb') as f:
        shutil.copyfileobj(response,f,length=4*1024*1024)
    if expected and sha(temporary)!=expected:raise ValueError('Downloaded checksum differs: '+str(path))
    temporary.replace(path)


def extract(archive,dest):
    dest.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        for info in z.infolist():
            if not (dest/info.filename).resolve().is_relative_to(dest.resolve()):
                raise ValueError('Unsafe archive member')
        z.extractall(dest)


def setup():
    tools=ROOT/'tools'/TAG;tools.mkdir(parents=True,exist_ok=True)
    release_file=tools/'release.json'
    if release_file.exists():release=json.loads(release_file.read_text(encoding='utf-8'))
    else:
        with urllib.request.urlopen('https://api.github.com/repos/ggml-org/llama.cpp/releases/tags/'+TAG,timeout=30) as r:
            release=json.load(r)
        release_file.write_text(json.dumps(release,indent=2),encoding='utf-8')
    asset=next(a for a in release['assets'] if a['name']==f'llama-{TAG}-bin-win-cpu-x64.zip')
    digest=asset.get('digest') or ''
    expected=digest.removeprefix('sha256:') if digest.startswith('sha256:') else None
    binary_zip=tools/asset['name']
    download(asset['browser_download_url'],binary_zip,expected)
    binary_dir=tools/'bin'
    if not list(binary_dir.rglob('llama-quantize.exe')):extract(binary_zip,binary_dir)
    executable=next(binary_dir.rglob('llama-quantize.exe'))
    source_zip=tools/'source.zip'
    download(f'https://codeload.github.com/ggml-org/llama.cpp/zip/refs/tags/{TAG}',source_zip)
    source_dir=tools/('llama.cpp-'+TAG)
    if not (source_dir/'convert_hf_to_gguf.py').is_file():extract(source_zip,tools)
    env=tools/'.venv';python=env/'Scripts/python.exe'
    packages={'torch':'2.6.0+cpu','transformers':'4.57.6','numpy':'1.26.4',
              'sentencepiece':'0.2.0','safetensors':'0.7.0','protobuf':'4.25.8','mistral-common':'1.8.3'}
    marker=tools/'environment_ready.json'
    if not marker.exists() or json.loads(marker.read_text(encoding='utf-8'))!=packages:
        if not python.is_file():subprocess.run(['uv','venv',str(env),'--python','3.11'],check=True)
        subprocess.run(['uv','pip','install','--python',str(python),'torch==2.6.0',
                        '--index-url','https://download.pytorch.org/whl/cpu'],check=True)
        subprocess.run(['uv','pip','install','--python',str(python),
                        *[f'{name}=={v}' for name,v in packages.items() if name!='torch']],check=True)
        marker.write_text(json.dumps(packages,indent=2),encoding='utf-8')
    return python,source_dir/'convert_hf_to_gguf.py',executable,{
        'llama_cpp_tag':TAG,'source_archive_sha256':sha(source_zip),
        'binary_archive_sha256':sha(binary_zip),'github_asset_digest':digest,'packages':packages}


def convert(model,out,threads=4):
    if threads<1:raise ValueError('threads must be positive')
    model=Path(model).resolve();out=Path(out).resolve();out.parent.mkdir(parents=True,exist_ok=True)
    names=['config.json','tokenizer.json','tokenizer_config.json']
    index=model/'model.safetensors.index.json'
    if index.exists():names+=['model.safetensors.index.json']+sorted(set(json.loads(index.read_text(encoding='utf-8'))['weight_map'].values()))
    else:names+=['model.safetensors']
    inputs={name:sha(model/name) for name in names}
    record=out.with_suffix('.conversion.json')
    if out.exists():
        if record.exists():
            existing=json.loads(record.read_text(encoding='utf-8'))
            if existing['inputs_sha256']==inputs and existing['q4_sha256']==sha(out):
                print('Reusing verified GGUF:',out,flush=True);return out
        raise ValueError('Output exists without matching conversion evidence; choose another --out')
    python,converter,quantize,tools=setup()
    f16=out.with_name(out.stem+'.f16.gguf')
    if f16.exists():raise ValueError('F16 intermediate exists without completed conversion; choose a new --out')
    print('Converting HF -> F16 GGUF (CPU, lazy/temp-file mode)',flush=True)
    # Keep the multi-GB tensor spool on the output drive, not Windows' C: TEMP.
    with tempfile.TemporaryDirectory(prefix='gguf-spool-',dir=out.parent) as spool:
        conversion_env=os.environ.copy()
        conversion_env.update(TEMP=spool,TMP=spool,TMPDIR=spool)
        subprocess.run([str(python),str(converter),str(model),'--outfile',str(f16),
                        '--outtype','f16','--use-temp-file'],check=True,env=conversion_env)
    print('Quantizing F16 GGUF -> Q4_K_M',flush=True)
    subprocess.run([str(quantize),str(f16),str(out),'Q4_K_M',str(threads)],check=True)
    record.write_text(json.dumps({'inputs_sha256':inputs,'source_model':str(model),
                      'q4_sha256':sha(out),'f16_sha256':sha(f16),'quantization':'Q4_K_M',
                      'tools':tools},ensure_ascii=False,indent=2),encoding='utf-8')
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--model-path',type=Path,required=True)
    p.add_argument('--out',type=Path,default=ROOT/'models/qwen3-it3170-cpt-Q4_K_M.gguf')
    p.add_argument('--threads',type=int,default=4);a=p.parse_args()
    print(convert(a.model_path,a.out,a.threads))
