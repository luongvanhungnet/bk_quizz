"""Reproduce the old integration error, then test the adapter on the failed tables."""
import hashlib
import importlib.metadata
import inspect
import json
import os
from pathlib import Path
import sys
import time
import traceback

os.environ.setdefault('PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK','True')
ROOT=Path(__file__).resolve().parent
from table_adapter import create_pipeline,native_ocr_result,predict_table
from validation import validate_prediction


def dump(path,data):path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')


def run():
    sys.stdout.reconfigure(encoding='utf-8')
    old=ROOT.parent/'region_preprocessing/runs/it3170_scored_v3'
    m=json.loads((old/'manifest.json').read_text(encoding='utf-8'))
    requests=[r for r in m['requests'] if r['engine']=='table']
    evidence=ROOT/'evidence';evidence.mkdir(exist_ok=True)
    dest=evidence/'table_cpu_regression';dest.mkdir(exist_ok=True)
    from paddlex.inference.pipelines.table_recognition import pipeline_v2,table_recognition_post_processing_v2
    files=[Path(inspect.getfile(module)) for module in [pipeline_v2,table_recognition_post_processing_v2]]
    dump(evidence/'paddle_compatibility.json',{'versions':{k:importlib.metadata.version(k) for k in ['paddleocr','paddlex','paddlepaddle']},
        'device':'cpu','python':sys.version,'files':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}})
    table=create_pipeline('cpu')
    # First canary already ran. Require its recorded structural success before batch.
    canary=json.loads((evidence/'table_canary_cpu.json').read_text(encoding='utf-8'))
    assert canary['id']==requests[0]['id'] and not validate_prediction('table',canary['prediction'])
    summary=[]
    for request in requests:
        target=dest/(request['id']+'.json')
        if target.exists():summary.append(json.loads(target.read_text(encoding='utf-8')));continue
        image=old/request['image'];record={'id':request['id'],'page':request['page'],'semantic_verified':False,
            'input_file_sha256':hashlib.sha256(image.read_bytes()).hexdigest(),
            'adapter_sha256':hashlib.sha256((ROOT/'table_adapter.py').read_bytes()).hexdigest(),
            'source_cache_key':request['cache_key']}
        # The original archives lack tracebacks. These are new CPU reproductions,
        # explicitly not claimed to be recovered historical Colab traces.
        try:
            legacy=dict(native_ocr_result(image,request['native_ocr']))
            for key in ['doc_preprocessor_res','model_settings','text_det_params','text_type','text_rec_score_thresh','return_word_box']:
                legacy.pop(key)
            next(iter(table.predict(str(image),overall_ocr_res=legacy,use_ocr_model=False,
                use_layout_detection=False,use_table_orientation_classify=False)))
            record['legacy_reproduction']={'status':'unexpected_success'}
        except Exception as exc:
            record['legacy_reproduction']={'status':'error','error_type':type(exc).__name__,
                'error_message':str(exc),'traceback':traceback.format_exc()}
        start=time.perf_counter()
        if request['id']==canary['id']:
            record['fixed']=dict(canary,reused_canary=True)
        else:
            try:
                pred=predict_table(table,image,request['native_ocr'])
                errors=validate_prediction('table',pred)
                record['fixed']={'status':'invalid_structure' if errors else 'ok','prediction':pred,
                                 'structural_errors':errors,'semantic_verified':False}
            except Exception as exc:
                record['fixed']={'status':'error','error_type':type(exc).__name__,'error_message':str(exc),'traceback':traceback.format_exc()}
        record['fixed']['elapsed_seconds_this_attempt']=time.perf_counter()-start
        dump(target,record);summary.append(record)
        print(request['id'],record['legacy_reproduction']['status'],record['fixed'].get('status','canary_ok'),flush=True)
    dump(evidence/'table_regression_summary.json',{'tables':len(summary),
        'old_missing_doc_preprocessor_reproduced':sum(r['legacy_reproduction'].get('error_message')=="'doc_preprocessor_res'" for r in summary),
        'new_structure_pass':sum(not validate_prediction('table',r['fixed'].get('prediction')) for r in summary),
        'semantic_verified':0,'historical_tracebacks_available':False,
        'reproduction_scope':'new CPU executions with pinned packages; old archive untouched'})


if __name__=='__main__':run()
