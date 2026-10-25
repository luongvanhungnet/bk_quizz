"""L4/High-RAM checks and isolated smoke tests before a long corpus run."""
import argparse
import csv
import gc
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import time
import traceback
import zipfile

from common import atomic_json,copy_verified,digest,load,safe,verify_release

PROFILE='l4-highram-python3-20261021'
MIN_RAM=40*1024**3
MIN_GPU_MIB=20*1024


def validate_hardware(info):
    errors=[]
    if info['system']!='Linux':errors.append('This profile requires the Linux Colab hosted runtime')
    if not (3,10)<=tuple(info['python'][:2])<=(3,13):errors.append('Use Python 3, minor 3.10–3.13 for the locked wheels')
    if len(info['gpus'])!=1 or not re.search(r'\bL4\b',info['gpus'][0]['name'] if info['gpus'] else ''):
        errors.append('Select L4 GPU under Runtime > Change runtime type')
    if info['ram_total_bytes']<MIN_RAM:errors.append('High-RAM profile requires at least 40 GiB physical system RAM')
    if info['ram_available_bytes']<12*1024**3:errors.append('Less than 12 GiB RAM available; stop old workers or start a fresh session')
    if info['gpus']:
        if info['gpus'][0]['memory_total_mib']<MIN_GPU_MIB:errors.append('L4 profile requires at least 20 GiB GPU memory')
        if info['gpus'][0]['memory_free_mib']<12*1024:errors.append('Less than 12 GiB GPU memory free before starting')
    return errors


def check_hardware(base):
    info={'profile':PROFILE,'system':platform.system(),'python':list(sys.version_info[:3]),'python_executable':sys.executable,
          'ram_total_bytes':0,'ram_available_bytes':0,'gpus':[],'unix':time.time()}
    try:
        mem={x.split(':')[0]:int(x.split()[1])*1024 for x in Path('/proc/meminfo').read_text().splitlines()}
        info.update(ram_total_bytes=mem['MemTotal'],ram_available_bytes=mem['MemAvailable'])
        raw=subprocess.check_output(['nvidia-smi','--query-gpu=name,memory.total,memory.free,driver_version','--format=csv,noheader,nounits'],text=True,timeout=15)
        for row in csv.reader(raw.splitlines()):
            name,total,free,driver=[x.strip() for x in row]
            info['gpus'].append({'name':name,'memory_total_mib':int(total),'memory_free_mib':int(free),'driver':driver})
    except Exception as exc:info['collection_error']=repr(exc)
    info['errors']=validate_hardware(info);info['passed']=not info['errors']
    atomic_json(Path(base)/'hardware_profile.json',info)
    print(json.dumps(info,ensure_ascii=False,indent=2))
    if info['errors']:raise RuntimeError('Runtime profile mismatch: '+'; '.join(info['errors']))
    return info


def safetensors_header(path):
    path=Path(path);size=path.stat().st_size
    with path.open('rb') as f:
        prefix=f.read(8);length=int.from_bytes(prefix,'little')
        if len(prefix)!=8 or not 2<=length<=min(100_000_000,size-8):
            raise ValueError('Invalid/oversized safetensors header length')
        header=json.loads(f.read(length))
    if not isinstance(header,dict):raise ValueError('Safetensors header is not an object')
    for name,value in header.items():
        if name=='__metadata__':continue
        start,end=value['data_offsets']
        if not 0<=start<=end<=size-8-length:raise ValueError('Safetensors tensor offsets outside file')
    return {'bytes':size,'header_bytes':length,'tensors':len(header)-('__metadata__' in header),'validation':'structural_only_not_semantic_or_full_checksum'}


def audit_docling_cache(root):
    repo=Path(root)/'hub/models--docling-project--docling-layout-heron';files=[]
    for path in repo.glob('snapshots/*/*.safetensors'):
        row={'path':str(path)}
        try:row.update(safetensors_header(path),valid=True,sha256=digest(path))
        except Exception as exc:row.update(valid=False,error=repr(exc),sha256=digest(path))
        files.append(row)
    return {'root':str(root),'files':files,'invalid_files':sum(not f['valid'] for f in files),
            'note':'No matching local file means not inspected, not proof the cache is valid.'}


def stage_engine(archive,target):
    target=Path(target);target.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        bundle=json.loads(z.read('bundle.json'));plan_bytes=z.read('plan.json')
        import hashlib
        if hashlib.sha256(plan_bytes).hexdigest()!=bundle['plan_sha256']:raise ValueError('Input plan changed')
        plan=json.loads(plan_bytes);release=z.read('engine/RELEASE.json')
        if hashlib.sha256(release).hexdigest()!=plan['release_manifest_sha256']:raise ValueError('Input engine release changed')
        for name,wanted in {**json.loads(release)['files'],'RELEASE.json':plan['release_manifest_sha256']}.items():
            data=z.read('engine/'+name)
            if hashlib.sha256(data).hexdigest()!=wanted:raise ValueError('Input engine source changed: '+name)
            path=safe(target,name);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    verify_release(target);return target


def probe(role,engine,assets):
    sys.path.insert(0,str(engine));import io_utils
    io_utils.file_sha=digest
    assets=Path(assets);assets.mkdir(parents=True,exist_ok=True)
    if role=='controller':
        import pymupdf
        doc=pymupdf.open();page=doc.new_page(width=800,height=240)
        page.insert_text((45,75),'BKQUIZ OCR TEST 12345',fontsize=28)
        page.insert_text((45,135),'Graph algorithms and data preprocessing.',fontsize=24)
        doc.save(assets/'probe.pdf');page.get_pixmap(matrix=pymupdf.Matrix(2,2)).save(assets/'probe.png');doc.close()
        return {'status':'ok','source':'generated_ascii_smoke_fixture_not_training_data'}
    if role in {'paddle','structure'}:
        import paddle,paddle_worker
        if not paddle.is_compiled_with_cuda():raise RuntimeError('Paddle wheel has no CUDA support')
        paddle.set_device('gpu:0');x=paddle.ones([32,32],dtype='float32');value=float(paddle.sum(paddle.matmul(x,x)).numpy())
        mode='ocr' if role=='paddle' else 'structure'
        pipeline=paddle_worker.create_pipeline(mode,'gpu:0','vi','PP-FormulaNet-S','PP-OCRv3')
        raw=[paddle_worker.result_dict(r) for r in pipeline.predict(str(assets/'probe.png'))]
        if not raw:raise RuntimeError('Paddle smoke produced no prediction')
        if role=='paddle':
            strings=[]
            def visit(v):
                if isinstance(v,dict):
                    for k,x in v.items():
                        if k=='rec_texts' and isinstance(x,list):strings.extend(t for t in x if isinstance(t,str))
                        else:visit(x)
                elif isinstance(v,list):
                    for x in v:visit(x)
            visit(raw);text=' '.join(strings)
            if '12345' not in text or not re.search(r'ocr|test',text,re.I):raise RuntimeError('OCR smoke did not read the known fixture: '+text[:300])
        else:text=None
        return {'status':'ok','mode':mode,'text':text,'cuda_build':paddle.version.cuda(),'cuda_matmul_sum':value}
    if role=='vlm':
        import torch,bitsandbytes as bnb
        if not torch.cuda.is_available():raise RuntimeError('Torch CUDA unavailable')
        layer=bnb.nn.Linear4bit(64,64,bias=False,compute_dtype=torch.float16,quant_type='nf4').to('cuda')
        with torch.inference_mode():value=layer(torch.ones((1,64),device='cuda',dtype=torch.float16))
        if not torch.isfinite(value).all():raise RuntimeError('NF4 CUDA smoke produced nonfinite output')
        result={'status':'ok','cuda_build':torch.version.cuda,'gpu':torch.cuda.get_device_name(),
                'compute_capability':list(torch.cuda.get_device_capability()),'nf4_forward':True,
                'scope':'CUDA/NF4 kernel smoke; full Qwen generation is not tested here'}
        del layer,value;gc.collect();torch.cuda.empty_cache();return result
    if role=='docling':
        from docling.document_converter import DocumentConverter,PdfFormatOption
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        converter=DocumentConverter(format_options={InputFormat.PDF:PdfFormatOption(pipeline_options=PdfPipelineOptions(
            do_ocr=False,do_table_structure=True,do_formula_enrichment=False,do_code_enrichment=False))})
        result=converter.convert(str(assets/'probe.pdf'));payload=result.document.export_to_dict()
        if not payload.get('pages'):raise RuntimeError('Docling smoke produced no pages')
        return {'status':'ok','pages':len(payload['pages']),'hf_home':os.environ.get('HF_HOME'),'device':'cpu'}
    raise ValueError('Unknown smoke role')


def check_environments(envs,archive,base,work,docling_hf_home):
    base,work=Path(base),Path(work);run=work/'preflight'/str(time.time_ns());run.mkdir(parents=True,exist_ok=True)
    engine=stage_engine(archive,run/'engine');assets=run/'assets';results=[]
    shared=Path(os.environ.get('BKQUIZ_SHARED_CACHE','/content/drive/MyDrive/BKQuiz_region_v5'))
    audit={'previous_cache':audit_docling_cache(shared/'hf_cache'),'selected_cache':audit_docling_cache(docling_hf_home)}
    atomic_json(run/'cache_audit.json',audit)
    if audit['selected_cache']['invalid_files']:
        copy_verified(run/'cache_audit.json',base/'preflight_runs'/run.name/'cache_audit.json')
        raise RuntimeError('Selected Docling cache has structurally invalid weights. Choose a fresh DOC_HF_HOME; existing files were preserved.')
    for role,env_role in [('controller','controller'),('paddle','paddle'),('structure','paddle'),('vlm','vlm'),('docling','docling')]:
        output=run/(role+'.json');log=run/(role+'.log');start=time.monotonic()
        child_env={**os.environ,'HF_HOME':str(docling_hf_home if role=='docling' else shared/'hf_cache'),
                   'PADDLE_PDX_CACHE_HOME':str(shared/'paddle_cache'),'PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK':'True',
                   'TOKENIZERS_PARALLELISM':'false','PYTHONUNBUFFERED':'1'}
        if role=='docling':
            child_env['CUDA_VISIBLE_DEVICES']=''
            child_env['HF_HUB_CACHE']=str(Path(docling_hf_home)/'hub')
            child_env.pop('TRANSFORMERS_CACHE',None)
        print('PREFLIGHT',role,flush=True)
        from orchestrator import heartbeat
        with log.open('w',encoding='utf-8') as f,heartbeat('preflight '+role):
            process=subprocess.run([envs[env_role],str(Path(__file__)),'--role',role,'--engine',str(engine),
                                    '--assets',str(assets),'--output',str(output)],stdout=f,stderr=subprocess.STDOUT,env=child_env)
        result=load(output) if output.exists() else {'status':'error','error':'Probe process exited without JSON','exit_code':process.returncode}
        result.update(role=role,seconds=time.monotonic()-start,exit_code=process.returncode);results.append(result)
        atomic_json(run/'summary.json',{'profile':PROFILE,'checks':results,'all_passed':False,'qwen_generation_tested':False})
        for p in [log,output,run/'summary.json',run/'cache_audit.json']:
            if p.exists():copy_verified(p,base/'preflight_runs'/run.name/p.name,replace=p.name=='summary.json',quiet=True)
        if process.returncode or result['status']!='ok':
            raise RuntimeError('Preflight failed for '+role+': '+result.get('error','see log')+'; diagnostics: '+str(base/'preflight_runs'/run.name))
    audit['selected_cache_after']=audit_docling_cache(docling_hf_home)
    atomic_json(run/'cache_audit.json',audit)
    copy_verified(run/'cache_audit.json',base/'preflight_runs'/run.name/'cache_audit.json',replace=True,quiet=True)
    if audit['selected_cache_after']['invalid_files']:raise RuntimeError('Docling cache audit failed after the smoke test; diagnostics retained')
    summary={'profile':PROFILE,'checks':results,'all_passed':True,'qwen_generation_tested':False,'docling_hf_home':str(docling_hf_home),
             'docling_weights':audit['selected_cache_after']['files']}
    atomic_json(run/'summary.json',summary);copy_verified(run/'summary.json',base/'preflight_runs'/run.name/'summary.json',replace=True,quiet=True)
    return summary


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--role',required=True);p.add_argument('--engine',type=Path,required=True)
    p.add_argument('--assets',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    try:result=probe(a.role,a.engine,a.assets)
    except Exception as exc:result={'status':'error','error':str(exc),'traceback':traceback.format_exc()}
    atomic_json(a.output,result)
    if result['status']!='ok':raise SystemExit(1)
