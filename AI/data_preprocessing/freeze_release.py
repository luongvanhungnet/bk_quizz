"""Create the first official v5 release; never overwrite an existing release."""
import hashlib
import json
import re
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parent
SOURCE=ROOT.parent/'Qwen_cpt_version/region_preprocessing_v5'
TARGET=ROOT.parent/'Qwen_cpt_version/region_preprocessing_v5_official'
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def freeze():
    if TARGET.exists():raise FileExistsError('Release is immutable; publish a new version instead')
    test_log=SOURCE/'evidence/tests_official_v5_20261021.txt'
    log=test_log.read_text(encoding='utf-8-sig')
    if not re.search(r'^OK\s*$',log,re.M) or 'FAILED (' in log:raise ValueError('Official tests have not passed')
    test_count=int(re.search(r'Ran (\d+) tests',log).group(1))
    TARGET.mkdir();names=[]
    for p in sorted(SOURCE.iterdir()):
        if p.is_file() and p.suffix in ['.py','.md','.txt','.ipynb']:
            shutil.copy2(p,TARGET/p.name);names.append(p.name)
    for p in sorted((SOURCE/'web').iterdir()):
        if p.is_file():
            q=TARGET/'web'/p.name;q.parent.mkdir(exist_ok=True);shutil.copy2(p,q);names.append(q.relative_to(TARGET).as_posix())
    for p in [ROOT/'SPEC_V5_OFFICIAL.md',ROOT/'RUNBOOK_CORPUS.md']:
        shutil.copy2(p,TARGET/p.name);names.append(p.name)
    (TARGET/'README.md').write_text('''# Data preprocessing v5.0.0 — official snapshot

Use `D:/BKQuiz/AI/data_preprocessing/manage.py` as the canonical entry point.
This snapshot is immutable and contains code, tests, notebooks, specifications
and dependency evidence; source documents and historical runs remain external.

- [Official specification](SPEC_V5_OFFICIAL.md)
- [Corpus runbook](RUNBOOK_CORPUS.md)
- [Canonical workspace](D:/BKQuiz/AI/data_preprocessing/README.md)

Do not edit files here. Publish a new release and update CURRENT.json after
validation when behavior must change. Official designation is not a guarantee
that machine predictions are correct or that the full corpus has been processed.
''',encoding='utf-8')
    q=TARGET/'validation/tests_official_v5_20261021.txt';q.parent.mkdir(exist_ok=True);shutil.copy2(test_log,q);names.append(q.relative_to(TARGET).as_posix())
    evidence=SOURCE/'evaluations/colab_24f2f2d02890_20261021/raw'
    for p in sorted(evidence.glob('*_freeze_*.txt')):
        q=TARGET/'environment_evidence'/p.name;q.parent.mkdir(exist_ok=True);shutil.copy2(p,q);names.append(q.relative_to(TARGET).as_posix())
    metadata={'version':'5.0.0','pipeline':'v5','status':'OFFICIAL_BASELINE','client_date':'2026-10-21',
        'source':str(SOURCE),'scope':'data preprocessing; official designation is not an accuracy certification',
        'vlm_model':'Qwen/Qwen2.5-VL-7B-Instruct','vlm_output':'one plain-language observation per image',
        'human_review_scope':'successful_nonempty_vlm_outputs_only','files':{n:digest(TARGET/n) for n in sorted(names)},
        'validation':{'python_tests_passed':test_count,'test_log_sha256':digest(test_log)},
        'source_data_included':False,'existing_runs_preserved':True,'full_corpus_cloud_inference_completed':False}
    (TARGET/'RELEASE.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
    current={'pipeline':'v5','version':'5.0.0','release_path':'../Qwen_cpt_version/region_preprocessing_v5_official',
        'release_manifest_sha256':digest(TARGET/'RELEASE.json'),'specification':'SPEC_V5_OFFICIAL.md'}
    (ROOT/'CURRENT.json').write_text(json.dumps(current,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(current,ensure_ascii=False,indent=2))

if __name__=='__main__':freeze()
