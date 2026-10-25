"""Bounded Qwen tasks, append-only retries/cache and review-only collection."""
import argparse
import copy
import gc
import importlib.metadata
import inspect
import json
import os
from pathlib import Path
import time
import traceback
from collections import Counter
from PIL import Image
from contracts import canonical,digest,file_hash,load,write_once,check_package
from schema import parse,validate_task
from prompts import prompt
from geometry import fit_image,parent_box
from validation import validate_prediction
from quality import assess


def empty_attribute(edge_id):
    return {'edge_id':edge_id,'directed':None,'weight':None,'highlighted':None,'arrow_target':None,'arrow_bbox':None,
            'weight_bbox':None,'highlight_bbox':None,'reference_bbox':None,'direction_basis':'unknown','native_quote':''}

def memory(torch):
    free,total=torch.cuda.mem_get_info()
    return {'allocated':torch.cuda.memory_allocated(),'reserved':torch.cuda.memory_reserved(),'free':free,'total':total}


class Qwen:
    def __init__(self,config):
        import torch
        from transformers import AutoProcessor,Qwen2_5_VLForConditionalGeneration,BitsAndBytesConfig
        expected={'torch':'2.6.0','transformers':'4.57.6','bitsandbytes':'0.48.1'}
        if any(importlib.metadata.version(k).split('+')[0]!=v for k,v in expected.items()):raise RuntimeError('Unexpected dependency versions')
        if not torch.cuda.is_available():raise RuntimeError('CUDA GPU required')
        self.torch=torch;self.config=config;self.telemetry={};self.initialization_seconds=0
        start=time.perf_counter()
        quant=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type='nf4',bnb_4bit_use_double_quant=True,bnb_4bit_compute_dtype=torch.float16)
        self.model=Qwen2_5_VLForConditionalGeneration.from_pretrained(config['vlm_model'],revision=config['vlm_revision'],
            torch_dtype=torch.float16,device_map={'':'cuda:0'},attn_implementation='sdpa',quantization_config=quant,trust_remote_code=False).eval()
        self.processor=AutoProcessor.from_pretrained(config['vlm_model'],revision=config['vlm_revision'],
            min_pixels=28*28,max_pixels=config['visual_tokens']*28*28)
        self.initialization_seconds=time.perf_counter()-start
        # Avoid materializing all prefill vocabulary logits when this pinned model
        # exposes the optimization. Telemetry records which path was used.
        signature=inspect.signature(self.model.forward).parameters
        self.keep_logits='logits_to_keep' if 'logits_to_keep' in signature else 'num_logits_to_keep' if 'num_logits_to_keep' in signature else None

    def infer(self,path,text,profile,max_new_tokens):
        torch=self.torch;p=self.processor;inputs=None;generated=None;ids=None;im=None
        torch.cuda.reset_peak_memory_stats();self.telemetry={'before':memory(torch),'profile':profile,'max_new_tokens':max_new_tokens,'logits_limit_argument':self.keep_logits}
        try:
            im=fit_image(Image.open(path),profile['visual_tokens'])
            messages=[{'role':'user','content':[{'type':'image'},{'type':'text','text':text}]}]
            chat=p.apply_chat_template(messages,tokenize=False,add_generation_prompt=True)
            tokens=p.tokenizer(chat,add_special_tokens=False)['input_ids']
            self.telemetry.update(source_image_size=list(Image.open(path).size),effective_image_size=list(im.size),text_tokens=len(tokens))
            if len(tokens)>self.config['max_text_tokens']:raise ValueError('Text token budget exceeded; split task, never truncate schema or source facts')
            # Use one image processor path, with the same cap at both resize steps.
            inputs=p(text=[chat],images=[im],padding=True,return_tensors='pt',min_pixels=28*28,max_pixels=profile['visual_tokens']*28*28)
            grid=inputs['image_grid_thw'].tolist();visual=sum(t*h*w//(p.image_processor.merge_size**2) for t,h,w in grid)
            self.telemetry.update(image_grid_thw=grid,visual_tokens=visual,input_tokens=int(inputs.input_ids.shape[1]))
            if visual>profile['visual_tokens']:raise ValueError('Processor exceeded visual budget')
            if inputs.input_ids.shape[1]+max_new_tokens>self.config['max_total_tokens']:raise ValueError('Total sequence budget exceeded')
            inputs=inputs.to('cuda:0');kwargs={self.keep_logits:1} if self.keep_logits else {}
            with torch.inference_mode():
                generated=self.model.generate(**inputs,max_new_tokens=max_new_tokens,do_sample=False,use_cache=True,**kwargs)
            ids=generated[:,inputs.input_ids.shape[1]:]
            result=p.batch_decode(ids,skip_special_tokens=True,clean_up_tokenization_spaces=False)[0]
            eos=p.tokenizer.eos_token_id;truncated=ids.shape[1]>=max_new_tokens and not bool((ids==eos).any())
            self.telemetry.update(output_tokens=int(ids.shape[1]),possibly_truncated=truncated)
            return result,truncated
        finally:
            self.telemetry['peak_allocated']=torch.cuda.max_memory_allocated()
            inputs=None;generated=None;ids=None;im=None
            gc.collect();torch.cuda.empty_cache()
            self.telemetry['after_cleanup']=memory(torch)


class LazyModel:
    def __init__(self,config):self.config=config;self.loaded=None
    @property
    def telemetry(self):return self.loaded.telemetry if self.loaded else {}
    def infer(self,*args):
        if self.loaded is None:self.loaded=Qwen(self.config)
        return self.loaded.infer(*args)


def valid_cached(record,task,payload,upstream_key):
    return (record.get('status')=='ok' and record.get('cache_key')==task['cache_key'] and record.get('upstream_key')==upstream_key
            and not validate_task(task['stage'],record.get('prediction'),payload) and record.get('semantic_verified') is False)

def resolve(out,task,root):
    payload=load(root/task['context']);candidates=[]
    for path in sorted((out/'attempts').glob('*/'+task['id']+'.json')):
        r=load(path)
        if r.get('cache_key')!=task['cache_key']:raise ValueError('Output task belongs to another package')
        candidates.append(r)
    # Successful immutable attempt is preferred; later failures never erase it.
    return next((r for r in reversed(candidates) if r['status']=='ok'),candidates[-1] if candidates else None)

def run_task(root,out,task,config,model,attempt,payload=None,upstream_key=''):
    payload=payload if payload is not None else load(root/task['context'])
    key=digest(canonical({'task':task['cache_key'],'upstream':upstream_key}))
    cache=Path(os.environ.get('REGION_V4_CACHE',str(out/'cache')))/(key+'.json')
    target=out/'attempts'/attempt/(task['id']+'.json')
    if cache.exists():
        cached=load(cache)
        if valid_cached(cached,task,payload,upstream_key):
            rec={**cached,'cache_hit':True};write_once(target,rec);return rec
    rec={'id':task['id'],'parent_id':task['parent_id'],'stage':task['stage'],'cache_key':task['cache_key'],
         'input_file_sha256':task['input_file_sha256'],'upstream_key':upstream_key,'cache_hit':False,
         'semantic_verified':False,'destination':'review_queue','attempts':[]}
    feedback='';start=time.perf_counter()
    for index in range(config['max_attempts_per_task']):
        profile={'visual_tokens':config['visual_tokens'] if index==0 else config['retry_visual_tokens']}
        step={'attempt':index+1,'effective_profile':profile,'effective_profile_sha256':digest(canonical(profile))};raw=None
        try:
            raw,truncated=model.infer(root/task['image'],prompt(task['stage'],payload,feedback),profile,task['max_new_tokens'])
            step.update(raw_content=raw,possibly_truncated=truncated)
            p,repairs,errors=parse(raw,task['stage']);errors+=validate_task(task['stage'],p,payload)
            step.update(prediction=p,repairs=repairs,structural_errors=sorted(set(errors)))
            if truncated:raise ValueError('Output token limit reached; incomplete result is not successful')
            if errors:raise ValueError(';'.join(sorted(set(errors))[:4]))
            step['status']='ok';rec.update(status='ok',prediction=p,repairs=repairs,
                reduced_resolution_retry=index>0,successful_profile=profile)
        except Exception as exc:
            step.update(status='error',error_type=type(exc).__name__,error_message=str(exc),traceback=traceback.format_exc())
            feedback=str(exc)[:250]
            if 'out of memory' in feedback.lower():feedback='Prior attempt exceeded memory. Keep response concise and follow the same schema.'
        step['telemetry']=copy.deepcopy(model.telemetry);rec['attempts'].append(step)
        if rec.get('status')=='ok':break
    if rec.get('status')!='ok':rec.update(status='error',error_message=rec['attempts'][-1]['error_message'])
    rec['elapsed_seconds']=time.perf_counter()-start;write_once(target,rec)
    if rec['status']=='ok':write_once(cache,rec)
    return rec


def map_attribute(a,clip):
    result={k:v for k,v in a.items() if k!='visible'}
    for k in ['weight_bbox','arrow_bbox','highlight_bbox','reference_bbox']:
        if result[k] is not None:result[k]=parent_box(result[k],clip)
    return result

def assemble(parent,tasks,outputs,root):
    available={t['id']:outputs.get(t['id']) for t in tasks};bad=[t['id'] for t in tasks if not available[t['id']] or available[t['id']]['status']!='ok']
    status='not_run' if all(not r for r in available.values()) else 'error' if bad else 'ok'
    rec={'id':parent['id'],'engine':'vlm','cache_key':parent['cache_key'],'input_file_sha256':parent['input_file_sha256'],
        'status':status,'failed_or_pending_tasks':bad,'semantic_verified':False,'destination':'review_queue','task_ids':[t['id'] for t in tasks],
        'source':{k:parent[k] for k in ['page','document_sha256','render_sha256','input_file_sha256']}}
    good=[(t,available[t['id']]['prediction']) for t in tasks if available[t['id']] and available[t['id']]['status']=='ok']
    uncertain=[];complete=True;changes=[]
    if parent['kind']=='state_tree':
        states=[];relations=[]
        for t,p in good:
            uncertain+=p['uncertain']
            if t['stage']=='board' and p['is_board']:
                states.append({'id':p['id'],'bbox':t['source_bbox'],'board_size':p['board_size'],'queens':p['queens'],'removed_cells':p['removed_cells']})
            elif t['stage']=='board':complete=False
            if t['stage']=='tree_links':relations=p['relations'];complete=complete and p['complete'] is True
        p={'image_type':'state_tree','states':states,'relations':relations,'uncertain':uncertain}
    else:
        nodes=[];edges=[];attributes={};accepted_nodes=set();accepted_edges=set();has_inventory=False
        for t,pred in good:
            uncertain+=pred['uncertain'];payload=load(root/t['context'])
            if t['stage']=='inventory':
                has_inventory=True;accepted_nodes.update(pred['node_ids']);accepted_edges.update(pred['edge_ids']);complete=complete and pred['complete'] is True
            if t['stage']=='nodes':nodes=[{**n,'bbox':parent_box(n['bbox'],t['source_bbox'])} for n in pred['nodes']]
            if t['stage']=='edges':edges=[{**e,'bbox':parent_box(e['bbox'],t['source_bbox'])} for e in pred['edges']]
            if t['stage']=='edge_attributes':
                for a in pred['attributes']:
                    attributes[a['edge_id']]={'attribute':map_attribute(a,t['source_bbox']),'visible':a['visible']}
        context=load(root/parent['context']);native=context.get('native_graph_candidates',{})
        if has_inventory:
            nodes=[{k:n[k] for k in ['id','label','bbox']} for n in native['nodes'] if n['id'] in accepted_nodes]
            edges=[{**{k:e[k] for k in ['id','source','target','bbox']}} for e in context['v4_edges'] if e['id'] in accepted_edges]
            # Inventory was chunked: a node/edge not accepted anywhere stays absent.
            complete=complete and all(t['stage']!='inventory' or available[t['id']] and available[t['id']]['status']=='ok' for t in tasks)
        else:complete=False # fallback does not independently prove whole-image coverage
        node_ids={n['id'] for n in nodes};final=[]
        for e in edges:
            if e['source'] not in node_ids or e['target'] not in node_ids:complete=False;continue
            item=attributes.get(e['id']);a=item['attribute'] if item else empty_attribute(e['id'])
            if item and item['visible'] is False:complete=False;continue
            if not item or item['visible'] is not True:uncertain.append('Edge visibility unresolved: '+e['id'])
            if a['directed'] is True and a['arrow_target']==e['source']:
                old=[e['source'],e['target']];e={**e,'source':e['target'],'target':e['source']}
                changes.append({'edge_id':e['id'],'before':old,'after':[e['source'],e['target']],'basis':'unverified_arrow_target'})
            final.append({**e,'attributes':a})
        p={'image_type':'graph','nodes':nodes,'edges':final,'uncertain':uncertain}
    rec.update(prediction=p,orientation_resolutions=changes,inventory_complete=complete)
    errors=validate_prediction('vlm',p);rec['structural_errors']=errors
    if errors and status=='ok':rec['status']='invalid_structure'
    context=load(root/parent['context']);context.update(_image_path=str(root/parent['image']),_inventory_complete=complete,_partial_task_failures=bad)
    rec['quality']=assess('vlm',p,context) if not errors else {'flags':['invalid_prediction'],'evidence_gate_pass':False,'semantic_verified':False}
    if any(available[t['id']] and available[t['id']].get('reduced_resolution_retry') for t in tasks):
        rec['quality']['flags']=sorted(set(rec['quality']['flags']+['reduced_resolution_retry_requires_review']));rec['quality']['evidence_gate_pass']=False
    return rec


def collect(root,out,m):
    outputs={t['id']:resolve(out,t,root) for t in m['tasks']};records=[]
    for r in m['requests']:
        if r['engine']!='vlm':
            s=copy.deepcopy(load(root/'seeds'/(r['id']+'.json')));s.update(cache_key=r['cache_key'],semantic_verified=False,destination='review_queue',cache_hit=True)
            context=load(root/r['context']);context.update(_image_path=str(root/r['image']),native_ocr=r.get('native_ocr',[]))
            errors=validate_prediction(r['engine'],s.get('prediction'));s['structural_errors']=errors
            s['quality']=assess(r['engine'],s['prediction'],context) if not errors else {'flags':['invalid_prediction'],'evidence_gate_pass':False,'semantic_verified':False}
            records.append(s)
        else:records.append(assemble(r,[t for t in m['tasks'] if t['parent_id']==r['id']],outputs,root))
    result={'manifest_sha256':file_hash(root/'manifest.json'),'records':records,'tasks':[r for r in outputs.values() if r], 'semantic_acceptance':False}
    name='results_'+digest(canonical(result))[:12]+'.json';write_once(out/name,result)
    summary={'result':name,'by_engine':{e:dict(Counter(r['status'] for r in records if r['engine']==e)) for e in ['formula','table','vlm']},
             'tasks':dict(Counter(r['status'] if r else 'not_run' for r in outputs.values())),'new_verified_CPT_samples':0}
    write_once(out/('summary_'+digest(canonical(summary))[:12]+'.json'),summary);print(json.dumps(summary));return result


def run(root,out,m,scope,model=None,retry_failed=False):
    if scope=='all':
        before=collect(root,out,m)
        pilot=[r for r in before['records'] if r['engine']=='vlm' and r['source']['page'] in m['pilot_pages']]
        if any(r['status']!='ok' for r in pilot):raise RuntimeError('All six pilot parents must be structurally successful before full run')
    selected=[t for t in m['tasks'] if scope=='all' or t['page'] in (m['canary_pages'] if scope=='canary' else m['pilot_pages'])]
    selected.sort(key=lambda t:(0 if t['page'] in m['canary_pages'] else 1,t['order']))
    model=model or LazyModel(m['config']);attempt=str(time.time_ns());started=time.perf_counter()
    for task in selected:
        prior=resolve(out,task,root)
        if prior and (prior['status']=='ok' or not retry_failed):continue
        payload=load(root/task['context']);upstream_key=''
        if task.get('depends_on'):
            dependency=next(t for t in m['tasks'] if t['id']==task['depends_on']);up=resolve(out,dependency,root)
            if not up or up['status']!='ok':continue
            upstream_key=digest(canonical(up['prediction']))
            if task['stage']=='edges':payload={**payload,'nodes':up['prediction']['nodes']}
            elif task['stage']=='edge_attributes':
                node_task=next(t for t in m['tasks'] if t['id']==dependency['depends_on']);nodes=resolve(out,node_task,root)['prediction']['nodes']
                i=task['chunk_index']*4;payload={**payload,'edges':up['prediction']['edges'][i:i+4],'nodes':nodes}
        if task['stage']=='edge_attributes' and not payload['edges']:
            rec={'id':task['id'],'parent_id':task['parent_id'],'stage':task['stage'],'cache_key':task['cache_key'],
                 'input_file_sha256':task['input_file_sha256'],'upstream_key':upstream_key,'status':'ok','prediction':{'attributes':[],'uncertain':[]},
                 'skipped_empty_chunk':True,'semantic_verified':False,'destination':'review_queue','attempts':[]}
            write_once(out/'attempts'/attempt/(task['id']+'.json'),rec)
        else:rec=run_task(root,out,task,m['config'],model,attempt,payload,upstream_key)
        print(task['id'],rec['status'],flush=True)
    write_once(out/('runtime_'+attempt+'.json'),{'wall_seconds_including_lazy_init':time.perf_counter()-started,
        'model_initialization_seconds':model.loaded.initialization_seconds if getattr(model,'loaded',None) else 0,
        'gpu':model.loaded.torch.cuda.get_device_name(0) if getattr(model,'loaded',None) else 'fake_or_cache_only',
        'scope':scope,'model_config':m['config']})
    return collect(root,out,m)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['collect','vlm']);parser.add_argument('--input',type=Path,required=True);parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--scope',choices=['canary','pilot','all'],default='pilot');parser.add_argument('--retry-failed',action='store_true')
    a=parser.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    try:
        manifest=check_package(a.input)
        if a.command=='collect':collect(a.input,a.out,manifest)
        else:run(a.input,a.out,manifest,a.scope,retry_failed=a.retry_failed)
    except Exception as exc:
        write_once(a.out/('run_error_'+str(time.time_ns())+'.json'),{'error':str(exc),'traceback':traceback.format_exc()});raise
