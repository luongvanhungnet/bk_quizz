"""Check local release artifacts. Does not run models or create human approvals."""
from pathlib import Path
from collections import Counter
import ast
import importlib.metadata
import json
import re
import zipfile
from io_utils import load,jsonl,file_sha,write_json
from review_store import ReviewStore
from models import validate_record
from metrics import evaluate_metrics
from package_cloud import wants_vlm

ROOT=Path(__file__).resolve().parent
def audit():
    run=__import__('dependency_paths').SEED_RUN;packet=ROOT/'cloud_packets/it3170_v5_pilot_11pages';pm=load(packet/'manifest.json')
    rows=jsonl(run/'records.jsonl')
    for row in rows:validate_record(row)
    with zipfile.ZipFile(packet/'v5_colab_input.zip') as z:
        assert z.testzip() is None
        for name,expected in pm['code_sha256'].items():assert file_sha(packet/name)==expected,name
        for q in pm['requests']:
            assert file_sha(packet/q['image'])==q['crop_sha256']
            assert file_sha(packet/q['vlm_image'])==q['vlm_image_sha256']
    assert len({r['id'] for r in rows})==len(rows)
    assert len(list((run/'assets/slides').glob('*.png')))==1060
    assert {r['page'] for r in rows}==set(range(1,1061))
    nb=load(ROOT/'Colab_Region_Preprocessing_V5.ipynb')
    for cell in nb['cells']:
        if cell['cell_type']=='code':ast.parse(''.join(cell['source']));assert cell['execution_count'] is None and not cell['outputs']
    log=(ROOT/'evidence/tests_release.txt').read_text(encoding='utf-8-sig')
    count=int(re.search(r'Ran (\d+) tests',log).group(1));assert re.search(r'^OK\s*$',log,re.M)
    prior=__import__('dependency_paths').V3/'manifest.json'
    assert load(prior)['document']['sha256']==load(run/'manifest.json')['document']['sha256']
    scheduled=[r for r in rows if wants_vlm(r,'all')]
    write_json(ROOT/'evidence/metrics_pending.json',evaluate_metrics([],[]))
    versions={}
    for name in ['pymupdf','Pillow','pydantic','ImageHash','python-pptx','paddleocr','paddlex','paddlepaddle','docling','mineru']:
        try:versions[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:versions[name]=None
    report={'date_client':'2026-10-20','run':str(run),'records':len(rows),'schema_valid_records':len(rows),
        'records_sha256':file_sha(run/'records.jsonl'),'review_stats':ReviewStore(run).stats(),
        'packet':{'path':str(packet),'manifest_sha256':file_sha(packet/'manifest.json'),'zip_sha256':file_sha(packet/'v5_colab_input.zip'),
            'zip_bytes':(packet/'v5_colab_input.zip').stat().st_size,'requests':len(pm['requests']),
            'by_kind':dict(Counter(q['kind'] for q in pm['requests'])),'vlm_images':sum(q['use_vlm'] for q in pm['requests']),
            'pages':sorted({q['page'] for q in pm['requests']}),'crc_valid':True,'code_and_image_hashes_valid':True},
        'all_scope_vlm_default':{'regions':len(scheduled),'pages':len({r['page'] for r in scheduled}),
            'page_percent':len({r['page'] for r in scheduled})/1060*100,'all_visuals_opt_in_required':True},
        'human_metrics_available':False,'Q':None,'empty_cpt_check':load(ROOT/'evidence/empty_cpt_check/manifest.json'),
        'notebook_cells_compile':True,'new_qwen_gpu_inference_executed':False,'docling_or_mineru_model_executed_locally':False,
        'tests':{'count':count,'passed':count,'log':'evidence/tests_release.txt'},'local_versions':versions,
        'v3_manifest_sha256':file_sha(prior),'code_sha256':{p.name:file_sha(p) for p in sorted(ROOT.glob('*.py'))}}
    write_json(ROOT/'evidence/release_validation.json',report)
    print(json.dumps({k:report[k] for k in ['records','review_stats','packet','all_scope_vlm_default','tests']},ensure_ascii=False,indent=2))
    return report

if __name__=='__main__':audit()
