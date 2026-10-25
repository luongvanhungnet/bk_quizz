"""Generate v2 Colab runner: fixed 3B pilot first, then matched NF4 7B."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
cells=[]
def md(s):cells.append({'cell_type':'markdown','metadata':{},'source':s.splitlines(True)})
def code(s):cells.append({'cell_type':'code','metadata':{},'execution_count':None,'outputs':[],'source':s.splitlines(True)})

md('''# IT3170 preprocessing v2 — Qwen2.5-VL-7B
Giữ nguyên kết quả cũ. Ưu tiên sửa schema/bảng trước khi so model.
3B và 7B dùng cùng prompt/crop, NF4, FP16 compute, batch 1, 768 visual token và 2.048 token đầu ra.
Chọn GPU T4 hoặc tốt hơn. Chưa benchmark VRAM/thời gian 7B trên máy này; lỗi OOM được lưu, không tự đổi model/config.
Mọi kết quả mới vẫn phải vào Review Queue. JSON hợp lệ không chứng minh kiến thức đúng.
''')
code('''import sys, subprocess, json, hashlib, zipfile, shutil, os, time
from pathlib import Path
from google.colab import drive, files
assert (3,10) <= sys.version_info[:2] <= (3,13)
subprocess.run(['nvidia-smi'],check=True)
drive.mount('/content/drive')
BASE=Path('/content/drive/MyDrive/BKQuiz_region_v2');BASE.mkdir(parents=True,exist_ok=True)
uploaded=files.upload() # Chọn đồng thời region_v2_3B_input.zip và region_v2_7B_input.zip
PACKAGES={};OUTPUTS={}
for size in ['3B','7B']:
    name=f'region_v2_{size}_input.zip'
    if name in uploaded:(BASE/name).write_bytes(uploaded[name])
    archive=BASE/name
    if not archive.exists():raise FileNotFoundError(name)
    with zipfile.ZipFile(archive) as z:
        identity=hashlib.sha256(z.read('manifest.json')).hexdigest()
        work=Path('/content')/('it3170_v2_'+size+'_'+identity[:12]);work.mkdir(exist_ok=True)
        for info in z.infolist():
            if not (work/info.filename).resolve().is_relative_to(work.resolve()):raise ValueError('Unsafe ZIP path')
        z.extractall(work)
    PACKAGES[size]=work
    OUTPUTS[size]=BASE/('results_'+size+'_'+identity[:12]);OUTPUTS[size].mkdir(exist_ok=True)
del uploaded
os.environ['REGION_CACHE_DIR']=str(BASE/'cache_v2')
print('Kết quả lưu tại:',OUTPUTS)
''')
md('''## Khôi phục venv và cài phần còn thiếu
Tìm hai archive đã lưu ở MyDrive/BKQuiz_preprocessing. Chỉ phục hồi khi Python major/minor khớp.
Không coi thư mục tồn tại là môi trường hoạt động. Nếu tạo mới, tránh phụ thuộc ensurepip của Ubuntu.
NF4 cần bitsandbytes 0.48.1; model weights vẫn tải nếu cache chưa có.
''')
code('''PADDLE_ENV=Path('/content/it3170_paddle_env');VLM_ENV=Path('/content/it3170_vlm_env')
ENV_CACHE=Path('/content/drive/MyDrive/BKQuiz_preprocessing')
tag=f'py{sys.version_info.major}{sys.version_info.minor}'
setup_start=time.perf_counter()
def runnable(env):
    py=env/'bin/python'
    if not py.exists():return False
    return subprocess.run([str(py),'-c','import pip'],capture_output=True).returncode==0
for env in [PADDLE_ENV,VLM_ENV]:
    if runnable(env):continue
    if env.exists() or env.is_symlink():env.rename(env.with_name(env.name+'_broken_'+str(time.time_ns())))
    archive=ENV_CACHE/f'{env.name}_{tag}_v1.tar.gz'
    if archive.exists():
        local=Path('/content')/archive.name;shutil.copy2(archive,local)
        listing=subprocess.check_output(['tar','-tzf',str(local)],text=True).splitlines()
        if any(Path(n).is_absolute() or '..' in Path(n).parts or Path(n).parts[0]!=env.name for n in listing):raise ValueError('Unsafe venv archive')
        subprocess.run(['tar','-xzf',str(local),'-C','/content'],check=True)
    if not runnable(env):
        if env.exists():env.rename(env.with_name(env.name+'_incompatible_'+str(time.time_ns())))
        subprocess.run([sys.executable,'-m','venv','--without-pip',str(env)],check=True)
        subprocess.run([sys.executable,'-m','pip','--python',str(env/'bin/python'),'install','pip==25.2'],check=True)
PADDLE_PY=str(PADDLE_ENV/'bin/python');VLM_PY=str(VLM_ENV/'bin/python')
def versions_match(py,expected):
    source="import importlib.metadata as m,json;print(json.dumps({k:m.version(k).split('+')[0] for k in "+repr(list(expected))+"}))"
    p=subprocess.run([py,'-c',source],capture_output=True,text=True)
    return p.returncode==0 and json.loads(p.stdout)==expected
paddle_versions={'paddleocr':'3.7.0','paddlex':'3.7.2','paddlepaddle-gpu':'3.2.2'}
if not versions_match(PADDLE_PY,paddle_versions):
    subprocess.run([PADDLE_PY,'-m','pip','install','paddlepaddle-gpu==3.2.2','--index-url','https://www.paddlepaddle.org.cn/packages/stable/cu118/'],check=True)
    subprocess.run([PADDLE_PY,'-m','pip','install','paddleocr[doc-parser]==3.7.0','paddlex[ocr]==3.7.2','Pillow==11.3.0'],check=True)
vlm_versions={'torch':'2.6.0','torchvision':'0.21.0','transformers':'4.57.6','accelerate':'1.12.0','qwen-vl-utils':'0.0.14'}
if not versions_match(VLM_PY,vlm_versions):
    subprocess.run([VLM_PY,'-m','pip','install','torch==2.6.0','torchvision==0.21.0','--index-url','https://download.pytorch.org/whl/cu124/'],check=True)
    subprocess.run([VLM_PY,'-m','pip','install','transformers==4.57.6','accelerate==1.12.0','qwen-vl-utils==0.0.14','Pillow==11.3.0'],check=True)
if not versions_match(VLM_PY,{'bitsandbytes':'0.48.1'}):
    subprocess.run([VLM_PY,'-m','pip','install','bitsandbytes==0.48.1'],check=True)
subprocess.run([PADDLE_PY,'-c','import paddle; paddle.utils.run_check(); assert paddle.is_compiled_with_cuda()'],check=True)
subprocess.run([VLM_PY,'-c','import torch,bitsandbytes; assert torch.cuda.is_available(); print(torch.ones(1,device="cuda"))'],check=True)
(BASE/'setup_seconds.json').write_text(json.dumps({'seconds':time.perf_counter()-setup_start}))
for name,py in [('paddle',PADDLE_PY),('vlm',VLM_PY)]:
    (BASE/(name+'_freeze.txt')).write_text(subprocess.check_output([py,'-m','pip','freeze'],text=True))
''')
md('''## P0: table canary, rồi mới batch specialist
Tái sử dụng bảng đã sửa và kiểm thử trên CPU nếu seed có hash hợp lệ. Nếu không có seed, chạy đúng một bảng và chặn batch khi canary lỗi.
Full traceback lưu trong record. Công thức chỉ chạy các crop đã qua định tuyến v2; seed còn hợp lệ được dùng lại.
''')
code('''def run_worker(size,stage,python,extra=None):
    work=PACKAGES[size];out=OUTPUTS[size]
    subprocess.run([python,str(work/'worker.py'),stage,'--input',str(work),'--out',str(out)]+(extra or []),check=True)
run_worker('7B','table-canary',PADDLE_PY)
run_worker('7B','paddle',PADDLE_PY)
''')
md('''## Baseline 3B với prompt đã sửa: 5 trang khó
Đây là lượt chạy mới có chủ đích vì prompt đã đổi. Output 3B cũ đã tái kiểm định ở local, không chạy lại 56 crop cũ.
Chỉ so model sau khi qua canary bảng và cổng schema của baseline. Nếu lỗi, dừng và giữ kết quả để điều tra.
''')
code('''run_worker('3B','vlm',VLM_PY)
run_worker('3B','collect',sys.executable)
baseline=json.loads((OUTPUTS['3B']/'results.json').read_text())
baseline_bad=[r['id'] for r in baseline['records'] if r['status']!='ok']
if baseline_bad:raise RuntimeError('Baseline schema chưa đạt; chưa chạy 7B. Xem records: '+str(baseline_bad))
''')
md('''## 7B trên cùng 5 trang khó, sau đó mới mở rộng 56 trang
NF4 để giảm VRAM cho T4. Cả hai model cùng cấu hình lượng tử hóa; không so 3B FP16 với 7B NF4 như cùng điều kiện.
Nếu OOM hoặc schema lỗi, dừng ở pilot và đọc record; không tự nâng verified hoặc đổi cấu hình cùng cache key.
''')
code('''hard_pages=[129,494,812,930,1042]
run_worker('7B','vlm',VLM_PY,['--pages']+list(map(str,hard_pages)))
run_worker('7B','collect',sys.executable)
production=json.loads((OUTPUTS['7B']/'results.json').read_text())
manifest=json.loads((PACKAGES['7B']/'manifest.json').read_text())
by_id={r['id']:r for r in manifest['requests']}
bad=[r['id'] for r in production['records'] if r['engine']=='vlm' and by_id[r['id']]['page'] in hard_pages and r['status']!='ok']
if bad:raise RuntimeError('Pilot 7B chưa đạt schema; dừng trước full VLM: '+str(bad))
''')
code('''for size in ['3B','7B']:
    subprocess.run([sys.executable,str(PACKAGES[size]/'semantic_eval.py'),
        '--results',str(OUTPUTS[size]/'results.json'),'--manifest',str(PACKAGES[size]/'manifest.json'),
        '--out',str(OUTPUTS[size]/'semantic_diagnostics.json')],check=True)
    print(size,(OUTPUTS[size]/'semantic_diagnostics.json').read_text())
print('Trang 129 và highlight chưa có gold đầy đủ: cần đối chiếu ảnh; metric này không phê duyệt CPT.')
''')
code('''# Tiếp tục các crop VLM còn lại; 5 crop pilot hợp lệ được tái sử dụng.
run_worker('7B','vlm',VLM_PY)
run_worker('7B','collect',sys.executable)
print((OUTPUTS['7B']/'summary.json').read_text())
''')
md('''## Xuất kết quả để review
ZIP gồm baseline và production, giữ log và raw output. Không tự export prediction thành CPT.
Nếu cell trước dừng vì lỗi, vẫn có thể chạy riêng cell này để tải kết quả chẩn đoán.
''')
code('''for size in ['3B','7B']:
    run_worker(size,'collect',sys.executable)
archive=BASE/('region_v2_results_'+hashlib.sha256((PACKAGES['7B']/'manifest.json').read_bytes()).hexdigest()[:12]+'.zip')
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
    for size,out in OUTPUTS.items():
        for p in sorted(out.rglob('*')):
            if p.is_file():z.write(p,size+'/'+p.relative_to(out).as_posix())
    for p in [BASE/'setup_seconds.json',BASE/'paddle_freeze.txt',BASE/'vlm_freeze.txt']:
        if p.exists():z.write(p,p.name)
print(archive);files.download(str(archive))
''')
for i,cell in enumerate(cells):cell['id']=f'v2-{i:02d}'
nb={'nbformat':4,'nbformat_minor':5,'metadata':{'accelerator':'GPU','kernelspec':{'name':'python3','display_name':'Python 3','language':'python'}},'cells':cells}
(ROOT/'IT3170_Region_V2_7B.ipynb').write_text(json.dumps(nb,ensure_ascii=False,indent=2),encoding='utf-8')
print(ROOT/'IT3170_Region_V2_7B.ipynb')
