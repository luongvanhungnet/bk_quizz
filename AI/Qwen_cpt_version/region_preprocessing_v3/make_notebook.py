"""Build a pilot-first Colab notebook and reuse the already tested venv restoration."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent;cells=[]
def md(s):cells.append({'cell_type':'markdown','metadata':{},'source':s.splitlines(True)})
def code(s):cells.append({'cell_type':'code','metadata':{},'execution_count':None,'outputs':[],'source':s.splitlines(True)})
md('''# IT3170 preprocessing v3 — evidence-first Qwen2.5-VL-7B
Graph: nodes → edges → attributes, each with local evidence. State trees use boards/cells, not generic labels.
Native vectors and CV boards are proposals, not verified facts. All new results remain in Review Queue.
The default is the six-crop pilot on five difficult pages. Full inference is explicitly configured below, not automatic.
''')
code('''import sys, subprocess, json, hashlib, zipfile, shutil, os, time
from pathlib import Path
from google.colab import drive,files
assert (3,10)<=sys.version_info[:2]<=(3,13)
subprocess.run(['nvidia-smi'],check=True)
drive.mount('/content/drive')
BASE=Path('/content/drive/MyDrive/BKQuiz_region_v3');BASE.mkdir(parents=True,exist_ok=True)
uploaded=files.upload() # Select region_v3_input.zip
if 'region_v3_input.zip' not in uploaded:raise ValueError('Select the v3 input ZIP')
archive=BASE/('input_'+hashlib.sha256(uploaded['region_v3_input.zip']).hexdigest()[:12]+'.zip')
if not archive.exists():archive.write_bytes(uploaded['region_v3_input.zip'])
del uploaded
with zipfile.ZipFile(archive) as z:
    RUN_HASH=hashlib.sha256(z.read('manifest.json')).hexdigest()
    WORK=Path('/content')/('it3170_v3_'+RUN_HASH[:12]);WORK.mkdir(exist_ok=True)
    for info in z.infolist():
        if not (WORK/info.filename).resolve().is_relative_to(WORK.resolve()):raise ValueError('Unsafe ZIP member')
    z.extractall(WORK)
sys.path.insert(0,str(WORK))
from contracts import check_package
MANIFEST=check_package(WORK)
OUT=BASE/('results_'+RUN_HASH[:12]);OUT.mkdir(exist_ok=True)
os.environ['REGION_V3_CACHE']=str(BASE/'phase_cache')
NEEDS_PADDLE=any(r['engine'] in ['formula','table'] and r['execution']=='inference' and r['id']+'.json' not in MANIFEST['seed_sha256'] for r in MANIFEST['requests'])
print('Paddle inference needed:',NEEDS_PADDLE)
print('Pilot pages:',MANIFEST['pilot_pages'])
print('Output:',OUT)
''')
md('''## Environment
Restore the previous Python-matched venv archives. Paddle installation is skipped when all specialist outputs are seeded.
Model weights are separate from venv archives. Qwen uses NF4, FP16 compute and batch 1 on a CUDA GPU such as T4.
''')
old=json.loads((ROOT.parent/'region_preprocessing_v2/IT3170_Region_V2_7B.ipynb').read_text(encoding='utf-8'))
setup=next(''.join(c['source']) for c in old['cells'] if c['cell_type']=='code' and ''.join(c['source']).startswith('PADDLE_ENV=Path'))
setup=setup.replace('for env in [PADDLE_ENV,VLM_ENV]:','for env in ([PADDLE_ENV] if NEEDS_PADDLE else [])+[VLM_ENV]:')
setup=setup.replace('if not versions_match(PADDLE_PY,paddle_versions):','if NEEDS_PADDLE and not versions_match(PADDLE_PY,paddle_versions):')
setup=setup.replace("subprocess.run([PADDLE_PY,'-c','import paddle; paddle.utils.run_check(); assert paddle.is_compiled_with_cuda()'],check=True)",
                    "if NEEDS_PADDLE:subprocess.run([PADDLE_PY,'-c','import paddle; paddle.utils.run_check(); assert paddle.is_compiled_with_cuda()'],check=True)")
setup=setup.replace("for name,py in [('paddle',PADDLE_PY),('vlm',VLM_PY)]:","for name,py in ([('paddle',PADDLE_PY)] if NEEDS_PADDLE else [])+[('vlm',VLM_PY)]:")
setup=setup.replace("(BASE/'setup_seconds.json')","(OUT/('setup_seconds_'+str(time.time_ns())+'.json'))")
setup=setup.replace("(BASE/(name+'_freeze.txt'))","(OUT/(name+'_freeze_'+str(time.time_ns())+'.txt'))")
code(setup)
md('''## Specialist reuse and revalidation
Reuse original inference with source hashes; recompute v3 quality flags. Failed identical formula crops stay in review instead of being blindly retried.
''')
code('''def run(stage,python=sys.executable,extra=None):
    subprocess.run([python,str(WORK/'worker.py'),stage,'--input',str(WORK),'--out',str(OUT)]+(extra or []),check=True)
run('seed')
if NEEDS_PADDLE:run('specialists',PADDLE_PY)
run('collect')
''')
md('''## Pilot: four graphs plus two separate 4-Queens trees
Graph extraction is three stages. Every stage preserves raw output, elapsed time and independent cache identity.
A valid JSON/evidence gate never authorizes CPT export. Inspect arrow, weight and style evidence on the original crop.
''')
code('''run('vlm',VLM_PY,['--scope','pilot'])
run('collect')
for r in MANIFEST['requests']:
    if r['engine']=='vlm' and r['page'] in MANIFEST['pilot_pages']:
        path=OUT/'records'/(r['id']+'.json')
        record=json.loads(path.read_text()) if path.exists() else {'status':'not_run'}
        print(r['id'],record['status'],record.get('quality',{}).get('flags',[]))
''')
md('''## Optional remaining VLM crops
Keep RUN_FULL=False until the pilot has been assessed. Setting it true only runs extraction; it does not verify output or append anything to CPT.
The worker requires a structurally successful pilot. Quality flags still require source review.
''')
code('''RUN_FULL=False
if RUN_FULL:
    run('vlm',VLM_PY,['--scope','all'])
    run('collect')
else:
    print('Pilot only. Remaining VLM requests are honestly marked not_run.')
''')
md('''## Download snapshots, including errors
This cell can also be run after a failed pilot to download diagnostics. Earlier result snapshots remain intact.
''')
code('''run('collect')
result_zip=BASE/('region_v3_results_'+RUN_HASH[:12]+'_'+str(time.time_ns())+'.zip')
with zipfile.ZipFile(result_zip,'w',zipfile.ZIP_DEFLATED) as z:
    for p in sorted(OUT.rglob('*')):
        if p.is_file():z.write(p,p.relative_to(OUT).as_posix())
    for p in [BASE/'setup_seconds.json',BASE/'paddle_freeze.txt',BASE/'vlm_freeze.txt']:
        if p.exists():z.write(p,p.name)
print(result_zip);files.download(str(result_zip))
''')
for i,c in enumerate(cells):c['id']=f'it3170-v3-{i:02d}'
nb={'nbformat':4,'nbformat_minor':5,'metadata':{'accelerator':'GPU','kernelspec':{'name':'python3','display_name':'Python 3','language':'python'}},'cells':cells}
target=ROOT/'IT3170_Region_V3_7B.ipynb';target.write_text(json.dumps(nb,ensure_ascii=False,indent=2),encoding='utf-8');print(target)
