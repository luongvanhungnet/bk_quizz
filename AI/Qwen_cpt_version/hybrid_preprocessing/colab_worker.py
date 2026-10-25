"""GPU workers run in separate Paddle / Torch environments in Colab."""
import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import time
from pathlib import Path


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    tmp.replace(path)


def json_result(result):
    value=result.json
    if isinstance(value,str):value=json.loads(value)
    return value.get('res',value)


def source(input_dir):
    manifest=json.loads((input_dir/'manifest.json').read_text(encoding='utf-8'))
    if sha(input_dir/'colab_worker.py')!=manifest['worker_sha256'] or sha(input_dir/'vlm_prompt.txt')!=manifest['vlm_prompt_sha256']:
        raise ValueError('Worker/prompt differs from packaged input')
    for item in manifest['requests']:
        target=(input_dir/item['image']).resolve()
        if not target.is_relative_to(input_dir.resolve()) or sha(target)!=item['render_sha256']:
            raise ValueError('Image path/hash mismatch')
    return manifest


def package_versions():
    names=['paddleocr','paddlex','paddlepaddle-gpu','torch','transformers','qwen-vl-utils']
    result={}
    for name in names:
        try:result[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:pass
    return result


def paddle_stage(input_dir,out):
    os.environ.setdefault('PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK','True')
    import paddle
    from PIL import Image
    from paddleocr import PaddleOCR,LayoutDetection,FormulaRecognition
    if not paddle.is_compiled_with_cuda() or paddle.device.cuda.device_count()<1:
        raise RuntimeError('GPU Paddle is required; no silent CPU fallback')
    paddle.set_device('gpu:0')
    manifest=source(input_dir);start=time.perf_counter()
    ocr=PaddleOCR(lang='vi',ocr_version='PP-OCRv3',device='gpu:0',
                  use_doc_orientation_classify=False,use_doc_unwarping=False,use_textline_orientation=False)
    layout=LayoutDetection(model_name='PP-DocLayout-M',device='gpu:0')
    formula=FormulaRecognition(model_name='PP-FormulaNet-S',device='gpu:0')
    # Audit the downloaded recognizer alphabet instead of trusting lang='vi'.
    import yaml,unicodedata
    alphabet_config=Path.home()/'.paddlex/official_models/latin_PP-OCRv3_mobile_rec/inference.yml'
    if alphabet_config.exists():
        chars=set(yaml.safe_load(alphabet_config.read_text(encoding='utf-8'))['PostProcess']['character_dict'])
        probes='ăâđêôơưàáảãạằắẳẵặầấẩẫậèéẻẽẹềếểễệìíỉĩịòóỏõọồốổỗộờớởỡợùúủũụừứửữựỳýỷỹỵ'
        missing=[c for c in probes if c not in chars and not all(v in chars for v in unicodedata.normalize('NFD',c))]
        audit={'config_sha256':sha(alphabet_config),'missing_vietnamese_characters':missing,'complete_for_probes':not missing}
    else:audit={'status':'not_measured','reason':'Recognizer config not found at expected cache location'}
    save(out/'ocr_alphabet_audit.json',audit)
    save(out/'paddle_runtime.json',{'initialization_seconds':time.perf_counter()-start,
         'packages':package_versions(),'python':platform.python_version(),
         'device':paddle.device.cuda.get_device_name(0),'formula_model':'PP-FormulaNet-S',
         'ocr_language':'vi','ocr_version':'PP-OCRv3','automatic_acceptance':False})
    for item in manifest['requests']:
        dest=out/'paddle'/f"page_{item['page']:04d}.json"
        if dest.exists():
            old=json.loads(dest.read_text(encoding='utf-8'))
            if old.get('status')=='ok' and old.get('manifest_sha256')==sha(input_dir/'manifest.json'):continue
        start=time.perf_counter();record={**item,'manifest_sha256':sha(input_dir/'manifest.json'),'verified':False}
        try:
            path=input_dir/item['image'];det=json_result(next(iter(layout.predict(str(path),batch_size=1))))
            text=json_result(next(iter(ocr.predict(str(path)))))
            formulas=[];ignored=[]
            scale=item['render_width']/item['page_size_pt'][0]
            def intersection_fraction(a,b):
                area=max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
                return area/max(1,(a[2]-a[0])*(a[3]-a[1]))
            with Image.open(path) as im:
                for b in det.get('boxes',[]):
                    if b['label']!='formula':continue
                    box=b['coordinate']
                    if any(intersection_fraction(box,[v*scale for v in code])>.65 for code in item['code_boxes_pt']):
                        ignored.append({'bbox_pixels':box,'reason':'overlaps_native_code'});continue
                    crop=out/'crops'/f"p{item['page']:04d}_f{len(formulas):03d}.png"
                    crop.parent.mkdir(parents=True,exist_ok=True)
                    clip=[max(0,int(box[0])-3),max(0,int(box[1])-3),min(im.width,int(box[2])+4),min(im.height,int(box[3])+4)]
                    if clip[2]<=clip[0] or clip[3]<=clip[1]:continue
                    im.crop(clip).save(crop)
                    rec=json_result(next(iter(formula.predict(str(crop),batch_size=1))))
                    latex=rec.get('rec_formula')
                    formulas.append({'bbox_pixels':clip,'crop':crop.relative_to(out).as_posix(),
                        'crop_sha256':sha(crop),'latex':latex,'semantic_description':None,
                        'semantic_verified':False,'raw':rec,'method':'PP-FormulaNet-S'})
            record.update(status='ok',layout=det,ocr=text,formulas=formulas,ignored_formula_candidates=ignored)
        except Exception as exc:record.update(status='error',error_type=type(exc).__name__,error_message=str(exc)[:1000])
        record['elapsed_seconds']=time.perf_counter()-start;save(dest,record)
        print('Paddle',item['page'],record['status'],round(record['elapsed_seconds'],2),flush=True)
    cache=Path.home()/'.paddlex/official_models'
    model_files={str(p.relative_to(cache)):sha(p) for p in cache.rglob('*') if p.is_file() and p.suffix in ['.yml','.yaml','.json','.pdiparams']}
    save(out/'paddle_model_files_sha256.json',model_files)


def vlm_stage(input_dir,out,revision):
    import torch
    from transformers import Qwen2_5_VLForConditionalGeneration,AutoProcessor
    from qwen_vl_utils import process_vision_info
    if not torch.cuda.is_available():raise RuntimeError('GPU Torch is required')
    manifest=source(input_dir);model_id='Qwen/Qwen2.5-VL-3B-Instruct'
    prompt=(input_dir/'vlm_prompt.txt').read_text(encoding='utf-8')
    start=time.perf_counter()
    model=Qwen2_5_VLForConditionalGeneration.from_pretrained(model_id,revision=revision,
        torch_dtype=torch.float16,device_map={'':'cuda:0'},attn_implementation='sdpa',trust_remote_code=False)
    processor=AutoProcessor.from_pretrained(model_id,revision=revision,min_pixels=256*28*28,max_pixels=1280*28*28)
    model.eval();torch.cuda.reset_peak_memory_stats()
    save(out/'vlm_runtime.json',{'initialization_seconds':time.perf_counter()-start,
         'packages':package_versions(),'python':platform.python_version(),'model_id':model_id,
         'revision_requested':revision,'revision_resolved':model.config._commit_hash,
         'dtype':'float16','device':torch.cuda.get_device_name(0),'max_visual_tokens':1280,
         'max_new_tokens':1536,'do_sample':False,'prompt_sha256':sha(input_dir/'vlm_prompt.txt')})
    for item in manifest['requests']:
        dest=out/'vlm'/f"page_{item['page']:04d}.json"
        if dest.exists():
            old=json.loads(dest.read_text(encoding='utf-8'))
            if old.get('status')=='ok' and old.get('revision')==revision and old.get('manifest_sha256')==sha(input_dir/'manifest.json') and old.get('prompt_sha256')==sha(input_dir/'vlm_prompt.txt'):continue
        start=time.perf_counter();record={**item,'manifest_sha256':sha(input_dir/'manifest.json'),
            'model_id':model_id,'revision':revision,'prompt_sha256':sha(input_dir/'vlm_prompt.txt'),'verified':False}
        try:
            messages=[{'role':'user','content':[{'type':'image','image':str(input_dir/item['image'])},{'type':'text','text':prompt}]}]
            template=processor.apply_chat_template(messages,tokenize=False,add_generation_prompt=True)
            images,videos=process_vision_info(messages)
            inputs=processor(text=[template],images=images,videos=videos,padding=True,return_tensors='pt').to('cuda')
            with torch.inference_mode():generated=model.generate(**inputs,max_new_tokens=1536,do_sample=False)
            ids=generated[:,inputs.input_ids.shape[1]:]
            content=processor.batch_decode(ids,skip_special_tokens=True,clean_up_tokenization_spaces=False)[0]
            record.update(raw_content=content,generated_tokens=ids.shape[1],possibly_truncated=ids.shape[1]>=1536)
            try:
                parsed=json.loads(content)
                required={'image_type','transcript','nodes','edges','tables','chart','formulas','observed_facts','uncertain'}
                if not isinstance(parsed,dict) or set(parsed)!=required or not isinstance(parsed['transcript'],str):raise ValueError('Schema mismatch')
                record.update(status='ok',prediction=parsed)
            except (ValueError,TypeError):record.update(status='invalid_json_or_schema')
            del inputs,generated,ids
        except Exception as exc:record.update(status='error',error_type=type(exc).__name__,error_message=str(exc)[:1000])
        record['elapsed_seconds']=time.perf_counter()-start
        record['peak_allocated_vram_bytes']=torch.cuda.max_memory_allocated()
        save(dest,record);torch.cuda.empty_cache()
        print('VLM',item['page'],record['status'],round(record['elapsed_seconds'],2),flush=True)


def collect(input_dir,out):
    manifest=source(input_dir);pages=[]
    for item in manifest['requests']:
        records={}
        for stage in ['paddle','vlm']:
            path=out/stage/f"page_{item['page']:04d}.json"
            records[stage]=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'status':'not_run'}
        pages.append({**item,'verified':False,**records})
    save(out/'results.json',{'schema_version':'it3170_hybrid_v1','manifest_sha256':sha(input_dir/'manifest.json'),
                          'pages':pages,'all_predictions_require_review':True})
    save(out/'summary.json',{'pages':len(pages),**{s:{status:sum(p[s]['status']==status for p in pages)
        for status in sorted({p[s]['status'] for p in pages})} for s in ['paddle','vlm']},
        'CER':None,'WER':None,'formula_accuracy':None,'diagram_fact_precision':None,
        'reason':'Independent source-checked ground truth is required'})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['paddle','vlm','collect'])
    p.add_argument('--input',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--revision',default='main');a=p.parse_args()
    if a.stage=='paddle':paddle_stage(a.input,a.out)
    elif a.stage=='vlm':vlm_stage(a.input,a.out,a.revision)
    else:collect(a.input,a.out)
