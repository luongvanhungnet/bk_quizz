"""Derive the corpus runner from the tested v5 notebook without changing VLM logic."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
def build():
    nb=json.loads((ROOT/'Colab_Region_Preprocessing_V5.ipynb').read_text(encoding='utf-8'))
    for cell in nb['cells']:
        source=''.join(cell['source'])
        if cell['cell_type']=='markdown':
            source=source.replace('IT3170 preprocessing v5','Data preprocessing v5 chính thức')
            source=source.replace('Mặc định pilot 11 trang. Chạy toàn bộ phải tạo packet `--scope all`, rồi đặt\n`RUN_ALL=True`.',
                'Chạy từng packet trong kế hoạch corpus. Mỗi packet chỉ chứa một học phần và tối đa 100 trang.\nPha `discovery` chạy layout/OCR; pha `inference` chỉ chạy các model đã được định tuyến.')
        else:
            if 'INPUT_ZIP=BASE/' in source:
                start=source.index("BASE=Path(");end=source.index('def digest(path):')
                source=source[:start]+'''BASE=Path('/content/drive/MyDrive/BKQuiz_preprocessing_v5');BASE.mkdir(parents=True,exist_ok=True)
# Set an EXACT packet path on Drive, or leave None and upload one ZIP each run.
# Do not silently reuse a previous file named v5_colab_input.zip.
INPUT_ZIP=None
if INPUT_ZIP is None:
    uploaded=files.upload();assert len(uploaded)==1, 'Chọn đúng một packet ZIP'
    name,data=next(iter(uploaded.items()));assert name.lower().endswith('.zip')
    uploaded_sha=hashlib.sha256(data).hexdigest()
    INPUT_ZIP=BASE/'incoming'/uploaded_sha/'v5_colab_input.zip';INPUT_ZIP.parent.mkdir(parents=True,exist_ok=True)
    if INPUT_ZIP.exists():assert hashlib.sha256(INPUT_ZIP.read_bytes()).hexdigest()==uploaded_sha
    else:INPUT_ZIP.write_bytes(data)
    del uploaded,data
else:INPUT_ZIP=Path(INPUT_ZIP)
'''+source[end:]
            if 'RUN_ALL=False' in source:
                start=source.index('RUN_ALL=False');end=source.index('RERUN_SPECIALISTS=False')
                source=source[:start]+'''PHASE=MANIFEST.get('phase','pilot')
REQUIRED=MANIFEST.get('required_stages',['ocr','docling','formula','table','vlm'])
RUN_ALL=MANIFEST['scope']=='all'
RUN_OCR='ocr' in REQUIRED
RUN_STRUCTURE='structure' in REQUIRED
RUN_DOCLING='docling' in REQUIRED
RUN_MINERU=False
RUN_FORMULA='formula' in REQUIRED
RUN_TABLE='table' in REQUIRED
RUN_VLM=any(q.get('use_vlm') for q in MANIFEST['requests'])
print('Phase:',PHASE,'; VLM requests:',sum(bool(q.get('use_vlm')) for q in MANIFEST['requests']))
'''+source[end:]
                source=source.replace("os.environ['HF_HOME']=str(BASE/'hf_cache')", "SHARED_CACHE=Path('/content/drive/MyDrive/BKQuiz_region_v5')\nos.environ['HF_HOME']=str(SHARED_CACHE/'hf_cache')")
                source=source.replace("str(BASE/'paddle_cache')","str(SHARED_CACHE/'paddle_cache')").replace("str(BASE/'vlm_success_cache')","str(SHARED_CACHE/'vlm_success_cache')")
            if "ensure_env('it3170_paddle_env'" in source:
                source=source.replace("PADDLE_PY=ensure_env('it3170_paddle_env',restore=True)/'bin/python'", "PADDLE_PY=(ensure_env('it3170_paddle_env',restore=True)/'bin/python') if (RUN_OCR or RUN_STRUCTURE or RUN_FORMULA or RUN_TABLE) else Path('/content/it3170_paddle_env/bin/python')")
                source=source.replace("VLM_PY=ensure_env('it3170_vlm_env',restore=True)/'bin/python'", "VLM_PY=(ensure_env('it3170_vlm_env',restore=True)/'bin/python') if RUN_VLM else Path('/content/it3170_vlm_env/bin/python')")
                source=source.replace('if RUN_OCR or RUN_FORMULA or RUN_TABLE:', 'if RUN_OCR or RUN_STRUCTURE or RUN_FORMULA or RUN_TABLE:')
                index=source.index("expected={'torch'")
                source=source[:index]+'if RUN_VLM:\n'+''.join('    '+line if line.strip() else line for line in source[index:].splitlines(True))
            if "for mode,enabled in [('ocr',RUN_OCR)" in source:
                source=source.replace("[('ocr',RUN_OCR),('formula',RUN_FORMULA),('table',RUN_TABLE)]", "[('ocr',RUN_OCR),('structure',RUN_STRUCTURE),('formula',RUN_FORMULA),('table',RUN_TABLE)]")
                source=source.replace("cmd=[PADDLE_PY,'paddle_worker.py','--plan',WORK/'manifest.json'", "plan=WORK/'manifest.json'\n        if mode=='structure':\n            plan=WORK/'structure_plan.json'\n            structure={**MANIFEST,'requests':[q for q in MANIFEST['requests'] if q['is_full_page']]}\n            plan.write_text(json.dumps(structure,ensure_ascii=False))\n        cmd=[PADDLE_PY,'paddle_worker.py','--plan',plan")
            if "if ENV_OK.get('vlm'):" in source:
                source=source.replace("if ENV_OK.get('vlm'):","if RUN_VLM and ENV_OK.get('vlm'):")
                source=source.replace("else:print('VLM chưa sẵn sàng; vẫn đóng gói logs/kết quả đã có.')", "else:print('Không có VLM được định tuyến hoặc môi trường chưa sẵn sàng; vẫn giữ diagnostics.')")
            compile(source,'corpus_notebook_cell','exec');cell['execution_count']=None;cell['outputs']=[]
        cell['source']=source.splitlines(True)
    nb['metadata']['colab']['name']='Colab_V5_Official_Corpus.ipynb'
    target=ROOT/'Colab_V5_Official_Corpus.ipynb';target.write_text(json.dumps(nb,ensure_ascii=False,indent=1),encoding='utf-8')
    print(target)

if __name__=='__main__':build()
