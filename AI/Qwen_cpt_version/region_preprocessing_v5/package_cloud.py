"""Package same-region OCR/specialists and a single contextual image for VLM."""
from pathlib import Path
import shutil
import zipfile
import pymupdf
from io_utils import load,jsonl,file_sha,sha,canonical,write_json
from vlm_worker import PROMPT

ROOT=Path(__file__).resolve().parent
MODELS={'7b':('Qwen/Qwen2.5-VL-7B-Instruct','cc594898137f460bfe9f0759e9844b3ce807cfb5'),
        '3b':('Qwen/Qwen2.5-VL-3B-Instruct','66285546d2b821cf421d4f5eb2576359d3770cd3')}

def wants_vlm(record,scope,all_visuals=False,formula_crosscheck=False):
    if record['kind']=='formula':return formula_crosscheck and record['machine_bucket']!='trusted'
    if record['kind'] not in ['diagram','chart','image']:return False
    state=record.get('legacy_routing_state')
    # Review inventory is broader than the paid inference queue. Preserve the
    # 56-page IT3170 routing budget; pilot can deliberately inspect a reference.
    return all_visuals or scope=='pilot' or state in [None,'scheduled']

def package(run,out,scope='pilot',model='7b',formula_crosscheck=False,all_visuals=False,page_numbers=None):
    run=Path(run).resolve();out=Path(out).resolve()
    if out.exists():raise ValueError('Choose a new cloud package directory')
    m=load(run/'manifest.json')
    if file_sha(m['document']['path'])!=m['document']['sha256']:raise ValueError('Source PDF changed since preparation')
    records=jsonl(run/'records.jsonl');selected=[r for r in records if scope=='all' or r['page'] in m['pilot_pages']]
    if page_numbers is not None:
        if not page_numbers or any(type(p) is not int or p<1 or p>m['document']['pages'] for p in page_numbers):raise ValueError('Invalid source page selection')
        selected=[r for r in selected if r['page'] in set(page_numbers)]
    if not selected:raise ValueError('No records selected for cloud package')
    out.mkdir(parents=True)
    requests=[]
    for r in selected:
        image=r['crop_path'] or r['render_path'];context=r['context_path'] or image
        for name in {image,context}:
            target=out/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(run/name,target)
        use_vlm=wants_vlm(r,scope,all_visuals,formula_crosscheck)
        page_text=next((p['native_text'] for p in records if p['page']==r['page'] and p['kind'] in ['text','code']),'')
        q={'id':r['id'],'page':r['page'],'kind':r['kind'],'bbox':r['bbox'],'image':image,'crop_sha256':r['crop_sha256'],
            'source_sha256':r['source_sha256'],'render_sha256':r['render_sha256'],'machine_revision':r['machine_revision'],
            'use_vlm':bool(use_vlm),'vlm_image':context,'vlm_image_sha256':file_sha(out/context),'context_text':page_text[:240],
            'context_bbox':r['context_bbox'],
            'native_text':r['native_text'],'native_ocr':r.get('native_ocr',[]),'specialist_seed_available':any(c.get('engine') in ['paddle_formula','paddle_table'] and c['status']=='ok' for c in r['candidates']),
            'input_file_sha256':r['crop_sha256'],'is_full_page':r['bbox']==[0,0,1000,1000],
            'ocr_requested':r['kind'] in ['diagram','chart','image']}
        q['specialist_seed_valid']=q['specialist_seed_available']
        cached_failure=any(c.get('engine') in ['paddle_formula','paddle_table'] and c['status']!='ok'
            and (c.get('evidence') or {}).get('reuse_only')
            and (c.get('evidence') or {}).get('input_file_sha256')==r['crop_sha256'] for c in r['candidates'])
        q['skip_specialist']=bool(cached_failure or r.get('specialist_disabled'))
        q['specialist_cached_failure_deferred']=bool(cached_failure)
        requests.append(q)
    page_numbers=sorted({r['page'] for r in selected})
    with pymupdf.open(m['document']['path']) as pdf:
        subset=pymupdf.open()
        for page in page_numbers:subset.insert_pdf(pdf,from_page=page-1,to_page=page-1)
        subset.save(out/'parser_input.pdf',garbage=4,deflate=True);subset.close()
    runtime=['io_utils.py','vlm_worker.py','paddle_worker.py','adapters.py','parser_worker.py']
    for name in runtime:
        if not (ROOT/name).exists():raise ValueError('Runtime not ready: '+name)
        shutil.copy2(ROOT/name,out/name)
    config={'model':MODELS[model][0],'revision':MODELS[model][1],'quantization':'nf4','visual_tokens':512,'max_new_tokens':512,
            'prompt_sha256':sha(PROMPT),'runtime_sha256':sha(canonical({n:file_sha(out/n) for n in runtime})),
            'output':'plain_text','generation_calls_per_image':1}
    packet={'schema_version':'v5-cloud-input','document':m['document'],'source_run_manifest_sha256':file_sha(run/'manifest.json'),
        'vlm_config':config,'requests':requests,'pilot_pages':m['pilot_pages'],'scope':scope,'all_visuals_opt_in':all_visuals,
        'vlm_routing_policy':'pilot_or_prior_scheduled_only_unless_all_visuals','page_map':{str(i+1):p for i,p in enumerate(page_numbers)},
        'parser_input':'parser_input.pdf','parser_input_sha256':file_sha(out/'parser_input.pdf'),
        'code_sha256':{n:file_sha(out/n) for n in runtime}}
    write_json(out/'manifest.json',packet)
    archive=out/'v5_colab_input.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(out.rglob('*')):
            if p.is_file() and p!=archive:z.write(p,p.relative_to(out).as_posix())
    print(archive);return archive
