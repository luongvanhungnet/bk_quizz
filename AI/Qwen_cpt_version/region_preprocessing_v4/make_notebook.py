"""Generate a resumeable Colab notebook using the previous Python-tagged env cache."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
cells=[]
def md(s):cells.append({'cell_type':'markdown','metadata':{},'source':s.splitlines(True)})
def code(s):cells.append({'cell_type':'code','metadata':{},'execution_count':None,'outputs':[],'source':s.splitlines(True)})
md('''# IT3170 region preprocessing v4 — Qwen2.5-VL-7B NF4
V4 uses bounded crop tasks, exact schema examples, board-by-board recognition, audited formatting repairs and at most two attempts per task.
Run canary pages 930/1042 before the remaining pilot. No unverified prediction is exported to CPT.
''')
code('''import sys, subprocess, json, hashlib, zipfile, time, os, shutil
from pathlib import Path
from google.colab import drive,files
assert (3,10)<=sys.version_info[:2]<=(3,13), 'Use a compatible Python 3.10-3.13 runtime'
subprocess.run(['nvidia-smi'],check=True)
drive.mount('/content/drive')
BASE=Path('/content/drive/MyDrive/BKQuiz_region_v4');BASE.mkdir(parents=True,exist_ok=True)
uploaded=files.upload() # Choose region_v4_input.zip
if 'region_v4_input.zip' not in uploaded:raise ValueError('Select the v4 input ZIP')
data=uploaded.pop('region_v4_input.zip');archive=BASE/('input_'+hashlib.sha256(data).hexdigest()[:12]+'.zip')
if archive.exists():assert archive.read_bytes()==data
else:archive.write_bytes(data)
del data,uploaded
with zipfile.ZipFile(archive) as z:
    if z.testzip():raise ValueError('Corrupt ZIP')
    RUN_HASH=hashlib.sha256(z.read('manifest.json')).hexdigest()
    WORK=Path('/content')/('it3170_v4_'+RUN_HASH[:12]);WORK.mkdir(exist_ok=True)
    for member in z.infolist():
        if not (WORK/member.filename).resolve().is_relative_to(WORK.resolve()):raise ValueError('Unsafe ZIP member')
    z.extractall(WORK)
sys.path.insert(0,str(WORK))
from contracts import check_package
MANIFEST=check_package(WORK)
OUT=BASE/('results_'+RUN_HASH[:12]);OUT.mkdir(exist_ok=True)
os.environ['REGION_V4_CACHE']=str(BASE/'task_cache')
NEEDS_PADDLE=False # Specialist outputs are source-bound seeds; do not reinstall Paddle.
print('Manifest:',RUN_HASH,'Parents:',len(MANIFEST['requests']),'Tasks:',len(MANIFEST['tasks']))
print('Persistent output:',OUT)
''')
md('''## Restore only the VLM environment
Reuses Python-matched archives in MyDrive/BKQuiz_preprocessing when compatible; checks locked dependencies afterwards.
No Paddle environment is required. Weights are separate from the environment archive.
''')
old=json.loads((ROOT.parent/'region_preprocessing_v3/IT3170_Region_V3_7B.ipynb').read_text(encoding='utf-8'))
setup=next(''.join(c['source']) for c in old['cells'] if c['cell_type']=='code' and ''.join(c['source']).startswith('PADDLE_ENV=Path'))
code(setup)
code('''def run(command,extra=None):
    env=dict(os.environ)
    env.setdefault('PYTORCH_CUDA_ALLOC_CONF','expandable_segments:True')
    subprocess.run([VLM_PY,str(WORK/'worker.py'),command,'--input',str(WORK),'--out',str(OUT)]+(extra or []),env=env,check=True)
run('collect')
''')
md('''## Memory canary: pages 930 and 1042
Actual CUDA telemetry is logged per attempt, including failures. First profile: 384 visual tokens, bounded text; retry: 256.
This does not guarantee success or semantic accuracy on T4. Read the collected result before proceeding.
''')
code('''run('vlm',['--scope','canary','--retry-failed'])
def latest():
    candidates=[json.loads(p.read_text()) for p in OUT.glob('results_*.json')]
    return max(candidates,key=lambda x:(sum(t['status']=='ok' for t in x['tasks']),len(x['tasks']),sum(r['status']!='not_run' for r in x['records'])))
CANARY=latest()
for r in CANARY['records']:
    if r['engine']=='vlm' and r['source']['page'] in MANIFEST['canary_pages']:
        print(r['id'],r['status'],r.get('quality',{}).get('flags'))
CANARY_OK=all(r['status']=='ok' for r in CANARY['records'] if r['engine']=='vlm' and r['source']['page'] in MANIFEST['canary_pages'])
print('Canary schema success:',CANARY_OK)
''')
md('''## Remaining pilot: 129, 494 and 812
Successful canary tasks are resumed from disk/cache. Do not bypass the canary failure gate by running the full batch.
''')
code('''if CANARY_OK:
    run('vlm',['--scope','pilot','--retry-failed'])
else:
    print('Stop expansion: download diagnostics below and inspect canary errors.')
PILOT=latest()
for r in PILOT['records']:
    if r['engine']=='vlm' and r['source']['page'] in MANIFEST['pilot_pages']:
        print(r['id'],r['status'],r.get('quality',{}).get('flags'))
''')
md('''## Optional full run
Set RUN_FULL=True only after source review of the pilot. Structural success does not verify graph facts or board states.
Retries are bounded per invocation; failed attempts are preserved. Do not repeatedly retry without inspecting their cause.
''')
code('''RUN_FULL=False
if RUN_FULL:run('vlm',['--scope','all','--retry-failed'])
else:print('Pilot only. Unexecuted tasks remain not_run.')
''')
md('''## Download results, including failures
Run this cell even if inference failed. All snapshots, task attempts, raw model output, repairs and telemetry are kept.
''')
code('''run('collect')
result_zip=BASE/('region_v4_results_'+RUN_HASH[:12]+'_'+str(time.time_ns())+'.zip')
with zipfile.ZipFile(result_zip,'w',zipfile.ZIP_DEFLATED) as z:
    for p in sorted(OUT.rglob('*')):
        if p.is_file():z.write(p,p.relative_to(OUT).as_posix())
print(result_zip)
files.download(str(result_zip))
''')
for i,c in enumerate(cells):c['id']=f'it3170-v4-{i:02d}'
nb={'nbformat':4,'nbformat_minor':5,'metadata':{'accelerator':'GPU','kernelspec':{'name':'python3','display_name':'Python 3','language':'python'}},'cells':cells}
target=ROOT/'IT3170_Region_V4_7B.ipynb';target.write_text(json.dumps(nb,ensure_ascii=False,indent=2),encoding='utf-8');print(target)
