"""Isolated Paddle worker: OCR, PP-StructureV3 tables/layout, FormulaNet crops.

Run with the Paddle venv, separately from Qwen/Torch. This process never imports
Torch, rewrites native text, repairs model facts, or marks candidates verified.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import re
import sys
import time
import traceback
import uuid
from adapters import file_hash, import_paddle, normalized_box, _crop_map


def jsonable(value):
    if isinstance(value,dict):
        return {str(k):jsonable(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):
        return [jsonable(v) for v in value]
    if hasattr(value,'tolist'):
        return jsonable(value.tolist())
    if hasattr(value,'item'):
        return jsonable(value.item())
    if isinstance(value,float) and not math.isfinite(value):
        return {'__nonfinite_float__':str(value)}
    if isinstance(value,Path):
        return str(value)
    return value


def result_dict(result):
    raw=result.json if hasattr(result,'json') else result
    raw=raw() if callable(raw) else raw
    if isinstance(raw,str):
        raw=json.loads(raw)
    raw=jsonable(raw)
    if not isinstance(raw,dict):
        raise ValueError('Paddle Result.json must be an object')
    return raw.get('res',raw)


def safe_path(root,value):
    root=Path(root).resolve();path=(root/str(value)).resolve()
    if not path.is_relative_to(root):
        raise ValueError('Task image must stay inside input root')
    return path


def safe_id(value):
    """Stable Windows filename; preserve original ID inside every record/evidence."""
    if not isinstance(value,str) or not value.strip():
        raise ValueError('Task id must be a nonempty string')
    slug=re.sub(r'[^A-Za-z0-9_-]','_',value)[:120]
    return slug+'_'+hashlib.sha256(value.encode('utf-8')).hexdigest()[:12]


def task_geometry(task,image_size):
    page=task.get('page')
    if isinstance(page,bool) or not isinstance(page,int) or page<1:
        raise ValueError('Task page must be a 1-based integer')
    crop=task.get('crop_bbox',task.get('bbox'))
    if crop is None and task.get('is_full_page') is True:
        crop=[0,0,1000,1000]
    if normalized_box(crop,units='normalized_1000') is None:
        raise ValueError('Task needs explicit normalized full-slide crop_bbox; unknown geometry cannot be guessed')
    return {'page':page,'image_width':image_size[0],'image_height':image_size[1],
            'crop_bbox':crop,'is_full_page':task.get('is_full_page') is True}


def create_pipeline(mode,device,lang,formula_model,ocr_version='PP-OCRv3'):
    from paddleocr import PaddleOCR,PPStructureV3,FormulaRecognition
    opts={'device':device,'enable_mkldnn':False,'cpu_threads':4} if device=='cpu' else {'device':device}
    if mode=='formula':
        return FormulaRecognition(model_name=formula_model,**opts)
    shared={'use_doc_orientation_classify':False,'use_doc_unwarping':False,
            'use_textline_orientation':False,'lang':lang,'ocr_version':ocr_version}
    if mode=='ocr':
        return PaddleOCR(**shared,**opts)
    if mode in {'table','structure'}:
        # Internal OCR owns its preprocessing result. Never inject an incomplete
        # overall_ocr_res (v1's doc_preprocessor_res integration failure).
        return PPStructureV3(**shared,use_table_recognition=mode=='table',
            use_formula_recognition=False,use_chart_recognition=False,
            use_seal_recognition=False,**opts)
    raise ValueError('Unknown Paddle mode')


def infer_task(task,root,out,*,mode,device='cpu',lang='vi',formula_model='PP-FormulaNet-S',ocr_version='PP-OCRv3',pipeline=None,versions=None):
    from PIL import Image
    out=Path(out);root=Path(root)
    identity=str(task.get('id',''))
    filename=safe_id(identity)
    output=out/'records'/f'{filename}_{mode}.json'
    image=safe_path(root,task['image'])
    image_hash=file_hash(image)
    expected_hash=task.get('input_file_sha256',task.get('crop_sha256'))
    if expected_hash and expected_hash!=image_hash:
        raise ValueError('Input image hash mismatch')
    versions=versions or {}
    config={'mode':mode,'device':device,'lang':lang,'ocr_version':ocr_version,'formula_model':formula_model,'versions':versions}
    fingerprint=hashlib.sha256(json.dumps({'task':task,'image_sha256':image_hash,'config':config},
        ensure_ascii=False,sort_keys=True,allow_nan=False).encode()).hexdigest()
    if output.exists():
        previous=json.loads(output.read_text(encoding='utf-8'))
        if previous.get('fingerprint')!=fingerprint:
            raise FileExistsError('Previous output has different input/config; choose a new attempt directory')
        return previous
    started=time.perf_counter()
    record={'id':identity,'page':task.get('page'),'mode':mode,'status':'pending','fingerprint':fingerprint,
            'input_file_sha256':image_hash,'config':config,'native_text':task.get('native_text',task.get('context')),
            'candidates':[],'semantic_verified':False}
    try:
        with Image.open(image) as im:
            frame=task_geometry(task,im.size)
        if mode=='formula' and task.get('kind')!='formula':
            raise ValueError('FormulaRecognition accepts only a region explicitly classified kind=formula')
        if mode=='table' and task.get('kind')!='table':
            raise ValueError('Table recognition accepts only kind=table')
        if pipeline is None:
            pipeline=create_pipeline(mode,device,lang,formula_model,ocr_version)
        raw=[result_dict(r) for r in pipeline.predict(str(image))]
        record['raw']=raw
        metadata={**frame,'source_sha256':task.get('source_sha256'),'source_file':task.get('source_file'),
                  'version':versions.get('paddleocr'),'backend_family':'paddle_ocr' if mode=='ocr' else 'paddle_structure',
                  'ocr_version':ocr_version,'lang':lang}
        # Import against an immutable raw snapshot, keeping exact original boxes.
        raw_path=out/'raw'/f'{filename}_{mode}.json'
        write_new(raw_path,{'records':[{'res':r,'metadata':metadata} for r in raw]})
        if mode=='formula':
            for r in raw:
                latex=r.get('rec_formula')
                if not isinstance(latex,str) or not latex.strip():
                    raise ValueError('FormulaNet produced empty/non-string rec_formula')
                record['candidates'].append({'page':frame['page'],'bbox':frame['crop_bbox'],'kind':'formula','text':latex,
                    'engine':'paddle_formula','status':'ok','confidence':None,
                    'evidence':{'source_sha256':task.get('source_sha256'),'parser_output_file':str(raw_path.resolve()),
                        'parser_output_sha256':file_hash(raw_path),'parser':'paddle_formula','parser_version':versions.get('paddleocr'),
                        'backend_family':'paddle_formula','model':formula_model,'geometry_status':'known',
                        'region_id':identity,'semantic_verified':False,'original':{'crop_bbox':frame['crop_bbox']}}})
        else:
            record['candidates']=import_paddle(raw_path)
            if mode=='table':
                # Retain OCR/layout candidates too; absence of an actual table
                # is reported as an error, never relabel a paragraph as a table.
                if not any(c['kind']=='table' and c['text'].strip() for c in record['candidates']):
                    raise ValueError('PP-StructureV3 found no nonempty table in the classified table crop')
            if not record['candidates']:
                raise ValueError('Paddle produced no spatial candidates')
            for c in record['candidates']:
                c['evidence']['region_id']=identity
        record['status']='ok'
    except ModuleNotFoundError as exc:
        record.update(status='unavailable',error=str(exc),traceback=traceback.format_exc())
    except Exception as exc:
        record.update(status='error',error=str(exc),traceback=traceback.format_exc())
    record['elapsed_seconds']=time.perf_counter()-started
    write_new(output,record)
    return record


def write_new(path,payload):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8') as f:
        json.dump(jsonable(payload),f,ensure_ascii=False,indent=2,allow_nan=False)


def run(plan_path,out,*,root=None,mode='ocr',device='cpu',lang='vi',formula_model='PP-FormulaNet-S',ocr_version='PP-OCRv3',limit=None,rerun_specialists=False):
    started=time.perf_counter()
    plan_path=Path(plan_path);out=Path(out);root=Path(root or plan_path.parent)
    payload=json.loads(plan_path.read_text(encoding='utf-8-sig'))
    tasks=payload if isinstance(payload,list) else payload.get('requests',payload.get('tasks',[]))
    if mode=='formula':
        tasks=[t for t in tasks if t.get('kind')=='formula']
    elif mode=='table':
        tasks=[t for t in tasks if t.get('kind')=='table']
    elif mode=='ocr':
        tasks=[t for t in tasks if t.get('kind') in {'text','code'} or t.get('ocr_requested') is True]
    if mode in {'formula','table'} and not rerun_specialists:
        tasks=[t for t in tasks if not (t.get('specialist_seed_valid') is True or t.get('skip_specialist') is True)]
    if limit is not None:
        tasks=tasks[:limit]
    versions={name:package_version(name) for name in ['paddleocr','paddlex','paddlepaddle','paddlepaddle-gpu']}
    expected={'paddleocr':'3.7.0','paddlex':'3.7.2','paddlepaddle' if device=='cpu' else 'paddlepaddle-gpu':'3.2.2'}
    # Explicit version mismatch becomes a durable diagnostic before any model load.
    mismatch={k:{'expected':v,'actual':versions.get(k)} for k,v in expected.items() if versions.get(k)!=v}
    if mismatch:
        diagnostic={'status':'unavailable' if any(versions.get(k) is None for k in mismatch) else 'error',
                    'error':'Paddle environment version mismatch','mismatch':mismatch,'versions':versions,'semantic_verified':False}
        write_new(out/f'environment_{time.time_ns()}_{uuid.uuid4().hex[:12]}.json',diagnostic)
        return diagnostic
    os.environ.setdefault('PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK','True')
    pipeline=None;records=[];initialization_error=None;initialization_seconds=0.0;actual_models={}
    # One model family per worker process; Colab calls separate worker subprocesses.
    for task in tasks:
        try:
            cached=out/'records'/f'{safe_id(task.get("id",""))}_{mode}.json'
            # Cached records still pass the fingerprint check in infer_task;
            # reusing them must not download/allocate model weights first.
            if pipeline is None and not cached.exists():
                if initialization_error:
                    raise RuntimeError('Model initialization previously failed in this worker; no repeated downloads: '+initialization_error)
                begin=time.perf_counter()
                try:
                    pipeline=create_pipeline(mode,device,lang,formula_model,ocr_version)
                    actual_models={k:v for k,v in getattr(pipeline,'_params',{}).items()
                                   if k.endswith('_model_name') and isinstance(v,str)}
                except Exception as exc:
                    initialization_error=str(exc)
                    raise
                finally:
                    initialization_seconds+=time.perf_counter()-begin
            records.append(infer_task(task,root,out,mode=mode,device=device,lang=lang,
                formula_model=formula_model,ocr_version=ocr_version,pipeline=pipeline,versions=versions))
        except Exception as exc:
            records.append({'id':task.get('id'),'page':task.get('page'),'mode':mode,'status':'error',
                'error':str(exc),'traceback':traceback.format_exc(),'candidates':[],'semantic_verified':False})
            write_new(out/'errors'/f'error_{time.time_ns()}_{uuid.uuid4().hex[:12]}.json',records[-1])
    result={'status':'ok' if all(r['status']=='ok' for r in records) else 'error',
            'request_count':len(tasks),'record_count':len(records),'versions':versions,'records':records,'semantic_verified':False,
            'mode':mode,'device':device,'lang':lang,'ocr_version':ocr_version,'formula_model':formula_model,
            'actual_model_names':actual_models,'initialization_seconds':initialization_seconds,'total_elapsed_seconds':time.perf_counter()-started}
    write_new(out/f'results_{time.time_ns()}_{uuid.uuid4().hex[:12]}.json',result)
    pipeline=None;gc.collect()
    return result


def package_version(name):
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan',type=Path,required=True);p.add_argument('--root',type=Path);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--mode',choices=['ocr','formula','table','structure'],default='ocr')
    p.add_argument('--device',default='cpu');p.add_argument('--lang',default='vi')
    p.add_argument('--ocr-version',choices=['PP-OCRv3','PP-OCRv5'],default='PP-OCRv3')
    p.add_argument('--rerun-specialists',action='store_true',help='Explicitly rerun specialist_seed_valid/skip_specialist regions')
    p.add_argument('--formula-model',default='PP-FormulaNet-S');p.add_argument('--limit',type=int)
    a=p.parse_args()
    result=run(a.plan,a.out,root=a.root,mode=a.mode,device=a.device,lang=a.lang,formula_model=a.formula_model,
               ocr_version=a.ocr_version,limit=a.limit,rerun_specialists=a.rerun_specialists)
    print(json.dumps({k:v for k,v in result.items() if k!='records'},ensure_ascii=False,indent=2))
    return 0 if result['status']=='ok' else 2


if __name__=='__main__':
    sys.exit(main())
