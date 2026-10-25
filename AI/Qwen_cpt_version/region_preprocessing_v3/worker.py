"""Staged Qwen extraction, source-bound seed reuse and review-only collection."""
import argparse
from collections import Counter
import copy
import importlib.metadata
import json
import os
from pathlib import Path
import time
import traceback
from contracts import canonical,digest,file_hash,load,write_once,check_package
from validation import parse_json_output,validate_stage,validate_prediction
from quality import assess
from prompts import PROMPTS


def record_path(out,r):return out/'records'/(r['id']+'.json')


def finish(root,out,r,record):
    record=copy.deepcopy(record)
    record.update(id=r['id'],engine=r['engine'],cache_key=r['cache_key'],input_file_sha256=r['input_file_sha256'],
        raw_pixel_sha256=r['raw_pixel_sha256'],semantic_verified=False,destination='review_queue',
        source={k:r[k] for k in ['page','document_sha256','render_sha256','input_file_sha256']})
    pred=record.get('prediction');errors=validate_prediction(r['engine'],pred)
    record['structural_errors']=errors
    if record.get('status')=='ok' and errors:record['status']='invalid_structure'
    if not errors:
        context=load(root/r['context']);context['native_ocr']=r.get('native_ocr',[]);context['_image_path']=str(root/r['image'])
        record['quality']=assess(r['engine'],pred,context)
    else:record['quality']={'flags':['structural_validation_failed'],'semantic_verified':False,'destination':'review_queue','evidence_gate_pass':False}
    write_once(record_path(out,r),record)
    return record


def seed(root,out,m):
    for r in m['requests']:
        dest=record_path(out,r);path=root/'seeds'/(r['id']+'.json')
        if dest.exists():
            old=load(dest)
            if old.get('cache_key')!=r['cache_key']:raise ValueError('Output directory belongs to a different configuration')
            continue
        if path.exists():
            old=load(path)
            if old.get('cache_key')!=r['cache_key'] or old.get('semantic_verified') is not False:raise ValueError('Invalid seed identity/promotion')
            finish(root,out,r,{**old,'cache_hit':True})


def compose_graph(nodes,edges,attributes,kind):
    node_ids={n['id'] for n in nodes['nodes']};edge_ids={e['id'] for e in edges['edges']}
    if any(e['source'] not in node_ids or e['target'] not in node_ids for e in edges['edges']):raise ValueError('Dangling edge before attribute inference')
    if {a['edge_id'] for a in attributes['attributes']}!=edge_ids:raise ValueError('Attribute edge inventory mismatch')
    attr={a['edge_id']:a for a in attributes['attributes']};out=[];changes=[]
    for edge in edges['edges']:
        e=copy.deepcopy(edge);a=copy.deepcopy(attr[e['id']])
        if a['directed'] is True:
            target=a['arrow_target']
            if target not in [e['source'],e['target']]:raise ValueError('Arrow target is not an edge endpoint')
            if target==e['source']:
                before=[e['source'],e['target']];e['source'],e['target']=e['target'],e['source']
                changes.append({'edge_id':e['id'],'before':before,'after':[e['source'],e['target']],
                                'basis':'model_arrow_target_not_semantically_verified'})
        e['attributes']=a;out.append(e)
    return {'image_type':kind,'nodes':nodes['nodes'],'edges':out,
            'uncertain':nodes['uncertain']+edges['uncertain']+attributes['uncertain']},changes


class Qwen:
    def __init__(self,m):
        import torch
        from transformers import AutoProcessor,Qwen2_5_VLForConditionalGeneration,BitsAndBytesConfig
        self.torch=torch;self.config=m['config'];c=self.config
        expected={'torch':'2.6.0','transformers':'4.57.6','qwen-vl-utils':'0.0.14','bitsandbytes':'0.48.1'}
        if any(importlib.metadata.version(k).split('+')[0]!=v for k,v in expected.items()):raise ValueError('Unexpected VLM dependency versions')
        if not torch.cuda.is_available():raise RuntimeError('CUDA GPU required for Qwen NF4')
        quant=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type='nf4',bnb_4bit_use_double_quant=True,bnb_4bit_compute_dtype=torch.float16)
        started=time.perf_counter()
        self.model=Qwen2_5_VLForConditionalGeneration.from_pretrained(c['vlm_model'],revision=c['vlm_revision'],
            torch_dtype=torch.float16,device_map={'':'cuda:0'},attn_implementation='sdpa',quantization_config=quant,trust_remote_code=False).eval()
        self.processor=AutoProcessor.from_pretrained(c['vlm_model'],revision=c['vlm_revision'],min_pixels=64*28*28,max_pixels=c['max_visual_tokens']*28*28)
        self.processor.tokenizer.padding_side='left';self.initialization_seconds=time.perf_counter()-started

    def infer(self,image,prompt):
        from qwen_vl_utils import process_vision_info
        torch=self.torch;p=self.processor;torch.cuda.reset_peak_memory_stats()
        messages=[{'role':'user','content':[{'type':'image','image':str(image)},{'type':'text','text':prompt}]}]
        text=p.apply_chat_template(messages,tokenize=False,add_generation_prompt=True)
        images,videos=process_vision_info(messages)
        inputs=p(text=[text],images=images,videos=videos,padding=True,return_tensors='pt').to('cuda')
        with torch.inference_mode():generated=self.model.generate(**inputs,max_new_tokens=self.config['max_new_tokens'],do_sample=False)
        ids=generated[:,inputs.input_ids.shape[1]:]
        body=p.batch_decode(ids,skip_special_tokens=True,clean_up_tokenization_spaces=False)[0]
        truncated=not bool((ids==p.tokenizer.eos_token_id).any()) and ids.shape[1]>=self.config['max_new_tokens']
        peak=torch.cuda.max_memory_allocated();del inputs,generated,ids;torch.cuda.empty_cache()
        return body,truncated,peak


class LazyQwen:
    def __init__(self,m):self.manifest=m;self.loaded=None
    def infer(self,image,prompt):
        if self.loaded is None:self.loaded=Qwen(self.manifest)
        return self.loaded.infer(image,prompt)


def stage(root,out,r,name,upstream,model):
    key=digest(canonical({'request_cache_key':r['cache_key'],'stage':name,'upstream':upstream}))
    local=out/'stages'/f"{r['id']}_{name}.json"
    cache=Path(os.environ.get('REGION_V3_CACHE',str(out/'cache')))/(key+'.json')
    if local.exists():
        record=load(local)
        if record.get('stage_key')!=key:raise ValueError('Changed upstream stage under existing output; choose new attempt')
        return record
    if cache.exists():
        record=load(cache)
        if record.get('stage_key')==key and record.get('status')=='ok' and not validate_stage(name,record.get('prediction')):
            write_once(local,{**record,'cache_hit':True});return record
    context=load(root/r['context'])
    supplied={k:context.get(k) for k in ['native_local_context','native_anchors','vector_paths','native_graph_candidates','board_candidates']}
    prompt=PROMPTS[name]+'\nSource proposals (not gold):\n'+canonical(supplied)+'\nEarlier stage (verify against image):\n'+canonical(upstream)
    started=time.perf_counter();record={'stage_key':key,'stage':name,'cache_hit':False,'semantic_verified':False}
    try:
        body,truncated,peak=model.infer(root/r['image'],prompt)
        record.update(raw_content=body,possibly_truncated=truncated,peak_allocated_vram_bytes=peak)
        p,recovered=parse_json_output(body);errors=validate_stage(name,p)
        if not errors and name=='edges':
            node_ids={n['id'] for n in upstream['nodes']}
            if any(e['source'] not in node_ids or e['target'] not in node_ids for e in p['edges']):errors.append('dangling_edge_reference')
        if not errors and name=='attributes':
            expected={e['id']:e for e in upstream['edges']}
            if {a['edge_id'] for a in p['attributes']}!=set(expected):errors.append('attribute_edge_inventory_mismatch')
            else:
                for a in p['attributes']:
                    e=expected[a['edge_id']]
                    if a['directed'] is True and a['arrow_target'] not in [e['source'],e['target']]:errors.append('arrow_target_not_an_endpoint')
        record.update(prediction=p,markdown_wrapper_removed=recovered,structural_errors=errors,
                      status='truncated' if truncated else 'invalid_structure' if errors else 'ok')
    except Exception as exc:record.update(status='error',error_type=type(exc).__name__,error_message=str(exc),traceback=traceback.format_exc())
    record['elapsed_seconds']=time.perf_counter()-started;write_once(local,record)
    if record['status']=='ok':write_once(cache,record)
    return record


def vlm(root,out,m,scope):
    seed(root,out,m)
    if scope=='all':
        pilot=[r for r in m['requests'] if r['engine']=='vlm' and r['page'] in m['pilot_pages']]
        if any(not record_path(out,r).exists() or load(record_path(out,r)).get('status')!='ok' for r in pilot):
            raise RuntimeError('Run a structurally successful pilot before full inference; failed attempts are preserved')
    jobs=[r for r in m['requests'] if r['engine']=='vlm' and not record_path(out,r).exists() and (scope=='all' or r['page'] in m['pilot_pages'])]
    if not jobs:print('No pending VLM requests');return
    model=LazyQwen(m);attempt=time.time_ns();runtimes=[]
    for r in jobs:
        started=time.perf_counter();record={'status':'ok','cache_hit':False,'stage_files':[]}
        try:
            def call(name,upstream):
                rec=stage(root,out,r,name,upstream,model);record['stage_files'].append(f"stages/{r['id']}_{name}.json")
                if rec['status']!='ok':raise RuntimeError('Stage '+name+' failed; raw result preserved')
                return rec['prediction']
            if r['kind'] in ['graph','diagram','flowchart','unknown']:
                nodes=call('nodes',{})
                edges=call('edges',nodes)
                ids={n['id'] for n in nodes['nodes']}
                if any(e['source'] not in ids or e['target'] not in ids for e in edges['edges']):raise ValueError('Dangling edge; skipping attribute inference')
                attrs=call('attributes',{'nodes':nodes['nodes'],'edges':edges['edges']})
                pred,changes=compose_graph(nodes,edges,attrs,r['kind']);record['orientation_resolutions']=changes
            else:pred={'image_type':r['kind'],**call(r['kind'],{})}
            record['prediction']=pred
        except Exception as exc:record.update(status='error',error_message=str(exc),traceback=traceback.format_exc())
        record['elapsed_seconds']=time.perf_counter()-started
        finish(root,out,r,record);runtimes.append({'id':r['id'],'wall_seconds':record['elapsed_seconds']})
        print(r['id'],record['status'],flush=True)
    write_once(out/f'vlm_runtime_{attempt}.json',{'model':m['config'],'initialization_seconds':model.loaded.initialization_seconds if model.loaded else 0,
        'requests':runtimes,'gpu':model.loaded.torch.cuda.get_device_name(0) if model.loaded else 'cache_only','semantic_verified':False})


def specialists(root,out,m,device):
    seed(root,out,m)
    jobs=[r for r in m['requests'] if r['engine'] in ['formula','table'] and r['execution']=='inference' and not record_path(out,r).exists()]
    if not jobs:print('Specialists reused; no inference needed');return
    os.environ.setdefault('PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK','True')
    import paddle
    from paddleocr import FormulaRecognition
    from table_adapter import create_pipeline,predict_table
    expected={'paddleocr':'3.7.0','paddlex':'3.7.2',('paddlepaddle' if device=='cpu' else 'paddlepaddle-gpu'):'3.2.2'}
    if any(importlib.metadata.version(k)!=v for k,v in expected.items()):raise RuntimeError('Paddle version mismatch')
    if device!='cpu' and not paddle.is_compiled_with_cuda():raise RuntimeError('GPU Paddle unavailable')
    formula=None;table=None;started=time.perf_counter()
    # Table reruns are only allowed as a separate canary-sized task. Existing
    # validated native table outputs are reused in this release, not rerun.
    table_jobs=[r for r in jobs if r['engine']=='table']
    if len(table_jobs)>1:raise RuntimeError('Build one-table canary plan before expanding table reruns')
    for r in jobs:
        record={'status':'ok','cache_hit':False};begin=time.perf_counter()
        try:
            if r['engine']=='formula':
                if formula is None:
                    opts={'enable_mkldnn':False,'cpu_threads':4} if device=='cpu' else {}
                    formula=FormulaRecognition(model_name=m['config']['formula_model'],device=device,**opts)
                raw=next(iter(formula.predict(str(root/r['image']),batch_size=1))).json
                if isinstance(raw,str):raw=json.loads(raw)
                raw=raw.get('res',raw);record.update(raw=raw,prediction={'latex':raw.get('rec_formula'),'semantic_description':None})
            else:
                if table is None:table=create_pipeline(device)
                record['prediction']=predict_table(table,root/r['image'],r['native_ocr'])
        except Exception as exc:record.update(status='error',error_message=str(exc),traceback=traceback.format_exc())
        record['elapsed_seconds']=time.perf_counter()-begin;finish(root,out,r,record)
    write_once(out/f'paddle_runtime_{time.time_ns()}.json',{'device':device,'seconds':time.perf_counter()-started,'versions':expected})


def collect(root,out,m):
    seed(root,out,m);records=[]
    for r in m['requests']:
        path=record_path(out,r)
        records.append(load(path) if path.exists() else {'id':r['id'],'engine':r['engine'],'cache_key':r['cache_key'],'status':'not_run','semantic_verified':False})
    # Snapshot filenames, never rewrite earlier collection reports.
    result={'manifest_sha256':file_hash(root/'manifest.json'),'records':records,'semantic_acceptance':False}
    name='results_'+digest(canonical(result))[:12]+'.json';write_once(out/name,result)
    summary={'results_file':name,'requests':len(records),'statuses':dict(Counter(r['status'] for r in records)),
        'by_engine':{e:dict(Counter(r['status'] for r in records if r['engine']==e)) for e in ['formula','table','vlm']},
        'new_verified_CPT_samples':0,'review_only':True}
    write_once(out/('summary_'+digest(canonical(summary))[:12]+'.json'),summary)
    print(json.dumps(summary,ensure_ascii=True));return result


if __name__=='__main__':
    from collections import Counter
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['seed','specialists','vlm','collect']);p.add_argument('--input',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--scope',choices=['pilot','all'],default='pilot');p.add_argument('--device',default='gpu:0')
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    try:
        m=check_package(a.input)
        if a.stage=='seed':seed(a.input,a.out,m)
        elif a.stage=='vlm':vlm(a.input,a.out,m,a.scope)
        elif a.stage=='specialists':specialists(a.input,a.out,m,a.device)
        else:collect(a.input,a.out,m)
    except Exception as exc:
        write_once(a.out/f'stage_error_{time.time_ns()}.json',{'error':str(exc),'traceback':traceback.format_exc()});raise
