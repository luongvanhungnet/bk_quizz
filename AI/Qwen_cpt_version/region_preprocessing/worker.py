"""Colab region workers: specialized Paddle first, then batched Qwen VL."""
import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import time
from pathlib import Path
from validation import parse_json_output,validate_prediction,cache_is_valid


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path,data):
    path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8');tmp.replace(path)


def load(path):return json.loads(Path(path).read_text(encoding='utf-8'))


def cache_dir(out):return Path(os.environ.get('REGION_CACHE_DIR',str(out/'cache')))


def manifest(root):
    m=load(root/'manifest.json');c=m['config']
    for name,key in [('worker.py','worker_sha256'),('prompt.txt','prompt_sha256'),('validation.py','validation_sha256')]:
        if sha(root/name)!=c[key]:raise ValueError('Worker/prompt/schema hash mismatch')
    for r in m['requests']:
        p=(root/r['image']).resolve()
        if not p.is_relative_to(root.resolve()) or sha(p)!=r['input_file_sha256']:raise ValueError('Crop hash mismatch')
        identity={'engine':r['engine'],'raw_pixel_sha256':r['raw_pixel_sha256'],
                  'input_pixel_sha256':r['input_pixel_sha256'],'native_ocr':r.get('native_ocr'),'config':c}
        expected=hashlib.sha256(json.dumps(identity,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
        if expected!=r['cache_key']:raise ValueError('Configuration changed without rebuilding cache identities')
    return m


def raw_result(result):
    value=result.json
    if isinstance(value,str):value=json.loads(value)
    return value.get('res',value)


def pending(root,out,engines):
    m=manifest(root);jobs=[]
    for r in m['requests']:
        if r['engine'] not in engines:continue
        dest=out/'records'/f"{r['id']}.json";cached=cache_dir(out)/f"{r['cache_key']}.json"
        # Preserve failed attempts for this configuration; changed config gets a new key.
        if dest.exists() and load(dest).get('cache_key')==r['cache_key']:continue
        old=load(cached) if cached.exists() else None
        if cache_is_valid(old,r):
            save(dest,{**old,'id':r['id'],'cache_hit':True,'semantic_verified':False});continue
        jobs.append(r)
    return m,jobs


def finish(out,request,record):
    record.update(id=request['id'],engine=request['engine'],cache_key=request['cache_key'],
                  raw_pixel_sha256=request['raw_pixel_sha256'],semantic_verified=False)
    if record.get('status')=='ok':
        errors=validate_prediction(request['engine'],record.get('prediction'))
        record['structural_errors']=errors
        if errors:record['status']='invalid_structure'
    save(out/'records'/f"{request['id']}.json",record)
    if cache_is_valid(record,request):save(cache_dir(out)/f"{request['cache_key']}.json",record)


def paddle_stage(root,out):
    os.environ.setdefault('PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK','True')
    m,jobs=pending(root,out,{'formula','table'})
    if not jobs:print('No pending formula/table crops');return
    import paddle
    import numpy as np
    from paddleocr import FormulaRecognition,TableRecognitionPipelineV2
    if any(importlib.metadata.version(k)!=v for k,v in m['config']['paddle_versions_expected'].items()):
        raise ValueError('Paddle package versions differ from cache configuration')
    if not paddle.is_compiled_with_cuda() or paddle.device.cuda.device_count()<1:raise RuntimeError('GPU Paddle required')
    started=time.perf_counter();formula=None;table=None
    for r in jobs:
        start=time.perf_counter();record={'status':'ok','cache_hit':False,'gpu':paddle.device.cuda.get_device_name(0)}
        try:
            path=root/r['image']
            if r['engine']=='formula':
                if formula is None:formula=FormulaRecognition(model_name=m['config']['formula_model'],device='gpu:0')
                raw=raw_result(next(iter(formula.predict(str(path),batch_size=1))))
                record.update(raw=raw,prediction={'latex':raw.get('rec_formula'),'semantic_description':None})
            else:
                if not r.get('native_ocr'):raise ValueError('Table has no native cell text; needs OCR/manual review, never VLM fallback')
                if table is None:
                    table=TableRecognitionPipelineV2(device='gpu:0',use_doc_orientation_classify=False,
                        use_doc_unwarping=False,use_layout_detection=False,use_ocr_model=False)
                boxes=np.asarray([v['bbox'] for v in r['native_ocr']],dtype=np.float32)
                polys=np.asarray([[[b[0],b[1]],[b[2],b[1]],[b[2],b[3]],[b[0],b[3]]] for b in boxes])
                overall={'input_path':str(path),'page_index':None,'rec_texts':[v['text'] for v in r['native_ocr']],
                         'rec_boxes':boxes,'rec_polys':polys,'dt_polys':polys,
                         'rec_scores':np.ones(len(boxes),dtype=np.float32)}
                raw=raw_result(next(iter(table.predict(str(path),overall_ocr_res=overall,
                    use_ocr_model=False,use_layout_detection=False,use_table_orientation_classify=False))))
                html='\n'.join(t.get('pred_html','') for t in raw.get('table_res_list',[]))
                record.update(raw=raw,prediction={'html':html,'text_source':'native_pdf',
                    'note':'Synthetic score=1 is an API placeholder for native geometry, not calibrated OCR confidence.'})
        except Exception as exc:record.update(status='error',error_type=type(exc).__name__,error_message=str(exc)[:1500])
        record['elapsed_seconds']=time.perf_counter()-start;finish(out,r,record)
        print(r['engine'],r['id'],record['status'],flush=True)
    save(out/'paddle_runtime.json',{'seconds_including_model_initialization':time.perf_counter()-started,
        'python':platform.python_version(),'gpu':paddle.device.cuda.get_device_name(0),
        'versions':{k:importlib.metadata.version(k) for k in ['paddleocr','paddlex','paddlepaddle-gpu']}})


def vlm_stage(root,out):
    m,jobs=pending(root,out,{'vlm'});c=m['config']
    if not jobs:print('No pending VLM crops');return
    import torch
    from transformers import AutoProcessor,Qwen2_5_VLForConditionalGeneration
    from qwen_vl_utils import process_vision_info
    if not torch.cuda.is_available():raise RuntimeError('GPU Torch required')
    start=time.perf_counter()
    model=Qwen2_5_VLForConditionalGeneration.from_pretrained(c['vlm_model'],revision=c['vlm_revision'],
         torch_dtype=torch.float16,device_map={'':'cuda:0'},attn_implementation='sdpa',trust_remote_code=False).eval()
    processor=AutoProcessor.from_pretrained(c['vlm_model'],revision=c['vlm_revision'],
         min_pixels=64*28*28,max_pixels=c['max_visual_tokens']*28*28)
    processor.tokenizer.padding_side='left';torch.cuda.reset_peak_memory_stats()
    init=time.perf_counter()-start;prompt=(root/'prompt.txt').read_text(encoding='utf-8')
    jobs.sort(key=lambda r:(round(r['input_size'][0]/max(1,r['input_size'][1]),1),r['input_size'][0]*r['input_size'][1]))
    batch_size=c['vlm_batch_size'];batch_log=[]
    for offset in range(0,len(jobs),batch_size):
        batch=jobs[offset:offset+batch_size];started=time.perf_counter()
        torch.cuda.reset_peak_memory_stats()
        try:
            messages=[[{'role':'user','content':[{'type':'image','image':str(root/r['image'])},{'type':'text','text':prompt}]}] for r in batch]
            texts=[processor.apply_chat_template(msg,tokenize=False,add_generation_prompt=True) for msg in messages]
            images,videos=process_vision_info(messages)
            inputs=processor(text=texts,images=images,videos=videos,padding=True,return_tensors='pt').to('cuda')
            with torch.inference_mode():generated=model.generate(**inputs,max_new_tokens=c['max_new_tokens'],do_sample=False)
            sequences=generated[:,inputs.input_ids.shape[1]:]
            bodies=processor.batch_decode(sequences,skip_special_tokens=True,clean_up_tokenization_spaces=False)
            elapsed=time.perf_counter()-started
            for r,body,ids in zip(batch,bodies,sequences):
                # Detect each row's EOS, rather than treating a padded short row as truncated.
                eos=processor.tokenizer.eos_token_id
                truncated=not bool((ids==eos).any()) and sequences.shape[1]>=c['max_new_tokens']
                record={'status':'ok','raw_content':body,'cache_hit':False,'batch_size':len(batch),
                        'batch_wall_seconds':elapsed,'possibly_truncated':truncated,
                        'peak_allocated_vram_bytes':torch.cuda.max_memory_allocated()}
                try:
                    prediction,recovered=parse_json_output(body)
                    record.update(prediction=prediction,markdown_wrapper_removed=recovered)
                    if truncated:record['status']='truncated'
                except ValueError as exc:record.update(status='invalid_json',error_message=str(exc))
                finish(out,r,record)
            del inputs,generated,sequences
        except Exception as exc:
            elapsed=time.perf_counter()-started
            for r in batch:finish(out,r,{'status':'error','error_type':type(exc).__name__,'error_message':str(exc)[:1500],
                                        'batch_size':len(batch),'batch_wall_seconds':elapsed})
        batch_log.append({'ids':[r['id'] for r in batch],'wall_seconds':elapsed})
        torch.cuda.empty_cache();print('VLM batch',offset//batch_size+1,'/',math_ceil(len(jobs),batch_size),flush=True)
    save(out/'vlm_runtime.json',{'initialization_seconds':init,'batches':batch_log,
          'inference_wall_seconds':sum(r['wall_seconds'] for r in batch_log),
          'gpu':torch.cuda.get_device_name(0),'python':platform.python_version(),
          'versions':{k:importlib.metadata.version(k) for k in ['torch','transformers','qwen-vl-utils']},'config':c})


def math_ceil(n,d):return (n+d-1)//d


def collect(root,out):
    m=manifest(root);records=[]
    for r in m['requests']:
        p=out/'records'/f"{r['id']}.json"
        records.append(load(p) if p.exists() else {'id':r['id'],'engine':r['engine'],'cache_key':r['cache_key'],'status':'not_run'})
    save(out/'results.json',{'manifest_sha256':sha(root/'manifest.json'),'records':records,'semantic_acceptance':False})
    from collections import Counter
    save(out/'summary.json',{'budget':m['budget'],'requests':len(records),
          'statuses':{engine:dict(Counter(r['status'] for r in records if r['engine']==engine)) for engine in ['formula','table','vlm']},
          'semantic_accuracy':None,'note':'Structural validation and budget compliance do not establish knowledge coverage.'})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['paddle','vlm','collect'])
    p.add_argument('--input',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    {'paddle':paddle_stage,'vlm':vlm_stage,'collect':collect}[a.stage](a.input,a.out)
