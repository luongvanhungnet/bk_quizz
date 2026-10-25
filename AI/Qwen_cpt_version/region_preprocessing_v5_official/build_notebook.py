"""Generate the reviewable v5 Colab notebook without executing cloud inference."""
import json
from pathlib import Path

cells=[]
def md(s):cells.append({'cell_type':'markdown','metadata':{},'source':s.splitlines(True)})
def code(s):
    compile(s,'colab_cell','exec')
    cells.append({'cell_type':'code','metadata':{},'source':s.splitlines(True),'outputs':[],'execution_count':None})

md('''# IT3170 preprocessing v5 — Native + OCR + VLM + Human Review

Chọn GPU runtime Python 3.10–3.13. Upload `v5_colab_input.zip` do local v5 tạo.
Mỗi ảnh VLM chỉ có **một lượt mô tả bằng văn bản tự nhiên**. Không yêu cầu JSON,
không ép liệt kê toàn bộ node/cạnh. Đầu ra luôn chưa được người xác minh.

Mặc định pilot 11 trang. Chạy toàn bộ phải tạo packet `--scope all`, rồi đặt
`RUN_ALL=True`. Kết quả thành công được cache theo hash; lỗi được lưu để xem lại.
Môi trường cũ được khôi phục từ `MyDrive/BKQuiz_preprocessing` nếu tương thích.
Docling/MinerU dùng môi trường riêng; không cài chung với Paddle hoặc Qwen.
''')
code('''import sys, subprocess, json, hashlib, zipfile, time, shutil, os, tarfile, uuid
from pathlib import Path
assert (3,10) <= sys.version_info[:2] <= (3,13), 'Chọn Python 3.10–3.13'
subprocess.run(['nvidia-smi'], check=True)
from google.colab import drive, files
drive.mount('/content/drive')
BASE=Path('/content/drive/MyDrive/BKQuiz_region_v5');BASE.mkdir(parents=True,exist_ok=True)
INPUT_ZIP=BASE/'v5_colab_input.zip'
# Đổi INPUT_ZIP nếu chạy một packet khác, tránh dùng nhầm ZIP đã lưu trên Drive.
if not INPUT_ZIP.exists():
    uploaded=files.upload()
    assert 'v5_colab_input.zip' in uploaded
    INPUT_ZIP.write_bytes(uploaded['v5_colab_input.zip']);del uploaded
def digest(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()
INPUT_SHA=digest(INPUT_ZIP);WORK=Path('/content')/('it3170_v5_'+INPUT_SHA[:12]);WORK.mkdir(exist_ok=True)
with zipfile.ZipFile(INPUT_ZIP) as z:
    assert z.testzip() is None
    for member in z.infolist():
        assert (WORK/member.filename).resolve().is_relative_to(WORK.resolve()), 'Unsafe ZIP path'
    z.extractall(WORK)
MANIFEST=json.loads((WORK/'manifest.json').read_text());RUN_HASH=digest(WORK/'manifest.json')
assert MANIFEST['schema_version']=='v5-cloud-input'
for name,expected in MANIFEST['code_sha256'].items():assert digest(WORK/name)==expected,name
assert digest(WORK/MANIFEST['parser_input'])==MANIFEST['parser_input_sha256']
for q in MANIFEST['requests']:
    assert digest(WORK/q['image'])==q['crop_sha256'],q['id']
    assert digest(WORK/q['vlm_image'])==q['vlm_image_sha256'],q['id']
OUT=BASE/('results_'+RUN_HASH[:12]);OUT.mkdir(exist_ok=True)
ATTEMPT=str(time.time_ns())+'_'+uuid.uuid4().hex[:8]
shutil.copy2(WORK/'manifest.json',OUT/('input_manifest_'+ATTEMPT+'.json'))
(OUT/('gpu_'+ATTEMPT+'.txt')).write_text(subprocess.check_output(['nvidia-smi'],text=True))
print('Input ZIP SHA256:',INPUT_SHA,'; packet:',RUN_HASH)
print('Packet scope:',MANIFEST['scope'],'; requests:',len(MANIFEST['requests']))
print('Persistent output:',OUT)
''')
md('''## Cấu hình

Mặc định chạy OCR và Docling trên pilot, tái dùng formula/table seed hợp lệ.
MinerU tùy chọn vì môi trường và tài nguyên bổ sung. Đây không phải điều kiện để
OCR/VLM tiếp tục. `RERUN_SPECIALISTS=True` mới bỏ qua seed hợp lệ.
`RETRY_VLM_ERRORS=True` mới cho chạy lại lỗi VLM đã lưu; không có retry tự động.
''')
code('''RUN_ALL=False
RUN_OCR=True
RUN_DOCLING=True
RUN_MINERU=False
RUN_FORMULA=True       # Worker bỏ qua seed đã hợp lệ; chỉ xử lý vùng còn lỗi/thiếu.
RUN_TABLE=True         # 16 bảng đã có seed sẽ được tái sử dụng.
RERUN_SPECIALISTS=False
RETRY_VLM_ERRORS=False
assert RUN_ALL or MANIFEST['scope']=='pilot', 'Packet all cần RUN_ALL=True'
assert not RUN_ALL or MANIFEST['scope']=='all', 'Tạo packet --scope all trước'
SCOPE='all' if RUN_ALL else 'pilot'
STAGES=[];ENV_OK={}
os.environ['HF_HOME']=str(BASE/'hf_cache')
os.environ['PADDLE_PDX_CACHE_HOME']=str(BASE/'paddle_cache')
os.environ['V5_VLM_CACHE']=str(BASE/'vlm_success_cache')
os.environ['PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK']='True'
os.environ['TOKENIZERS_PARALLELISM']='false'
def stage(name,command,env=None):
    log=OUT/(name+'_'+ATTEMPT+'_'+uuid.uuid4().hex[:8]+'.log');start=time.perf_counter()
    print('START',name,flush=True)
    try:
        with log.open('w') as f:
            p=subprocess.run([str(x) for x in command],cwd=WORK,env=env,stdout=f,stderr=subprocess.STDOUT)
        status='ok' if p.returncode==0 else 'error';error=None;rc=p.returncode
    except Exception as exc:
        status='error';error=repr(exc);rc=None;log.write_text(error)
    row={'name':name,'status':status,'returncode':rc,'seconds':time.perf_counter()-start,'error':error,'log':log.name}
    STAGES.append(row);print(row,flush=True)
    print(log.read_text(errors='replace')[-3000:])
    return status=='ok'
''')
md('''## Môi trường và cache

Không gọi `python -m venv` phụ thuộc gói `ensurepip` của hệ thống. Dùng uv để
tạo venv khi không thể khôi phục. Archive cũ chỉ là cache: Python minor, wheel,
CUDA và kiểm tra import phải tương thích. Các môi trường không tương thích được
đổi tên để giữ lại chẩn đoán. Cài đặt thất bại không được ghi là suy luận thành công.
''')
code('''subprocess.run([sys.executable,'-m','pip','install','uv==0.13.3'],check=True)
UV=shutil.which('uv');assert UV
ENV_CACHE=Path('/content/drive/MyDrive/BKQuiz_preprocessing')
PY_TAG=f'py{sys.version_info.major}{sys.version_info.minor}'
def runnable(env):
    py=env/'bin/python'
    return py.exists() and subprocess.run([str(py),'-c','import sys;assert sys.version_info[:2]=='+repr(sys.version_info[:2])],capture_output=True).returncode==0
def ensure_env(name,restore=False):
    env=Path('/content')/name
    if runnable(env):return env
    if env.exists() or env.is_symlink():env.rename(env.with_name(name+'_broken_'+ATTEMPT))
    archive=ENV_CACHE/f'{name}_{PY_TAG}_v1.tar.gz'
    if restore and archive.exists():
        local=Path('/content')/archive.name;shutil.copy2(archive,local)
        with tarfile.open(local) as tar:
            for member in tar.getmembers():
                parts=Path(member.name).parts
                assert parts and not Path(member.name).is_absolute() and '..' not in parts and parts[0]==name
        subprocess.run(['tar','-xzf',str(local),'-C','/content'],check=True)
    if not runnable(env):
        if env.exists():env.rename(env.with_name(name+'_incompatible_'+ATTEMPT))
        subprocess.run([UV,'venv','--python',sys.executable,'--seed',str(env)],check=True)
    return env
def matches(py,expected):
    src='import importlib.metadata as m,json;print(json.dumps({k:m.version(k).split("+")[0] for k in '+repr(list(expected))+'}))'
    p=subprocess.run([str(py),'-c',src],capture_output=True,text=True)
    return p.returncode==0 and json.loads(p.stdout)==expected
def install(py,args):
    return stage('install_'+Path(py).parents[1].name,[UV,'pip','install','--python',py,*args])
def freeze(name,py):
    p=subprocess.run([UV,'pip','freeze','--python',str(py)],capture_output=True,text=True)
    (OUT/(name+'_freeze_'+ATTEMPT+'.txt')).write_text(p.stdout+p.stderr)
PADDLE_PY=ensure_env('it3170_paddle_env',restore=True)/'bin/python'
VLM_PY=ensure_env('it3170_vlm_env',restore=True)/'bin/python'
if RUN_OCR or RUN_FORMULA or RUN_TABLE:
    expected={'paddleocr':'3.7.0','paddlex':'3.7.2','paddlepaddle-gpu':'3.2.2'}
    ok=matches(PADDLE_PY,expected)
    if not ok:
        ok=install(PADDLE_PY,['paddlepaddle-gpu==3.2.2','--index-url','https://www.paddlepaddle.org.cn/packages/stable/cu118/'])
        if ok:ok=install(PADDLE_PY,['paddleocr[doc-parser]==3.7.0','paddlex[ocr]==3.7.2','Pillow==11.3.0'])
    ENV_OK['paddle']=ok and stage('probe_paddle',[PADDLE_PY,'-c','import paddle;assert paddle.is_compiled_with_cuda();paddle.utils.run_check()'])
    freeze('paddle',PADDLE_PY)
expected={'torch':'2.6.0','torchvision':'0.21.0','transformers':'4.57.6','accelerate':'1.12.0','bitsandbytes':'0.48.1'}
ok=matches(VLM_PY,expected)
if not ok:
    ok=install(VLM_PY,['torch==2.6.0','torchvision==0.21.0','--index-url','https://download.pytorch.org/whl/cu124/'])
    if ok:ok=install(VLM_PY,['transformers==4.57.6','accelerate==1.12.0','bitsandbytes==0.48.1','Pillow==11.3.0'])
ENV_OK['vlm']=ok and stage('probe_vlm',[VLM_PY,'-c','import torch,bitsandbytes;assert torch.cuda.is_available();print(torch.ones(1,device="cuda"))'])
freeze('vlm',VLM_PY)
''')
md('''## OCR và specialist

Mỗi mode chạy một subprocess. Seed hợp lệ được worker bỏ qua; raw và stack trace
được giữ. FormulaNet chỉ nhận `kind=formula`, bảng chỉ nhận `kind=table`.
''')
code('''if ENV_OK.get('paddle'):
    for mode,enabled in [('ocr',RUN_OCR),('formula',RUN_FORMULA),('table',RUN_TABLE)]:
        if not enabled:continue
        cmd=[PADDLE_PY,'paddle_worker.py','--plan',WORK/'manifest.json','--root',WORK,'--out',OUT/('paddle_'+mode),'--mode',mode,'--device','gpu:0','--lang','vi']
        if RERUN_SPECIALISTS and mode!='ocr':cmd+=['--rerun-specialists']
        stage('paddle_'+mode,cmd)
else:print('Paddle chưa sẵn sàng; xem log, tiếp tục engine khác.')
''')
md('''## Parser đối chiếu độc lập

Docling native layout không được đếm như một OCR độc lập. MinerU dùng CLI
`mineru-kit parse --tier standard`; adapter kiểm tra `--help` trước khi chạy.
Nếu package hiện có không cung cấp CLI đó, ghi `unavailable` để điều tra, không
tự chuyển sang backend VLM khác. Hai môi trường dưới đây chưa được chạy model
thật trên máy local lúc triển khai v5.
''')
code('''for engine,enabled,package_name,env_name in [('docling',RUN_DOCLING,'docling==2.140.0','it3170_docling_v5_env'),('mineru',RUN_MINERU,'mineru==4.0.12','it3170_mineru_v5_env')]:
    if not enabled:continue
    try:
        py=ensure_env(env_name)/'bin/python'
        module=package_name.split('==')[0];version=package_name.split('==')[1]
        ok=matches(py,{module:version}) or install(py,[package_name,'Pillow==11.3.0'])
        if ok:
            child_env=dict(os.environ);child_env['PATH']=str(py.parent)+os.pathsep+child_env.get('PATH','')
            # Keep parser allocations isolated; Qwen only loads after this process exits.
            child_env['CUDA_VISIBLE_DEVICES']=''
            stage('parser_'+engine,[py,'parser_worker.py','--input',WORK,'--out',OUT/(engine+'_'+ATTEMPT),'--engine',engine],env=child_env)
        freeze(engine,py)
    except Exception as exc:
        STAGES.append({'name':'parser_'+engine,'status':'error','error':repr(exc)})
        print(engine,repr(exc))
''')
md('''## VLM — một ảnh, một lượt, văn bản tự nhiên

Model/revision trong packet, mặc định Qwen2.5-VL-7B-Instruct NF4, SDPA.
Tối đa 512 visual tokens và 512 output tokens. Không yêu cầu model tự kiểm
chứng, JSON, schema đồ thị hay suy luận nhiều vòng. Nếu init lỗi, worker dừng
tải model lặp lại; lỗi một ảnh không cản ảnh sau. Luôn cần người đối chiếu nguồn.
''')
code('''if ENV_OK.get('vlm'):
    cmd=[VLM_PY,'vlm_worker.py','--input',WORK,'--out',OUT/'vlm','--scope',SCOPE]
    if RETRY_VLM_ERRORS:cmd+=['--retry-errors']
    stage('vlm',cmd)
else:print('VLM chưa sẵn sàng; vẫn đóng gói logs/kết quả đã có.')
''')
md('''## Lưu chẩn đoán và tải kết quả

Chạy ô này cả khi một engine lỗi. Mã thoát 0 chưa đủ để gọi parser thành công;
summary bên dưới cũng đọc status JSON. ZIP không cấp quyền xuất CPT: nhập về
local, dùng app kiểm duyệt rồi mới export.
''')
code('''summaries=[]
for path in sorted(OUT.rglob('*.json')):
    if path.name.startswith(('parser_candidates_','vlm_results_','results_','environment_')):
        try:
            item=json.loads(path.read_text())
            row={'file':str(path.relative_to(OUT)),'status':item.get('status'),'records':item.get('record_count')}
            if 'observations' in item:
                row.update(observations=len(item['observations']),errors=sum(r['status']!='ok' for r in item['observations']),not_run=len(item.get('not_run_ids',[])))
            summaries.append(row)
        except Exception as exc:summaries.append({'file':str(path),'status':'invalid_json','error':repr(exc)})
status={'packet_manifest_sha256':RUN_HASH,'stages':STAGES,'engine_outputs':summaries,'semantic_verified':False,'human_verified':False}
(OUT/('stage_status_'+ATTEMPT+'.json')).write_text(json.dumps(status,ensure_ascii=False,indent=2))
archive=BASE/('region_v5_results_'+RUN_HASH[:12]+'_'+ATTEMPT+'.zip')
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
    for path in sorted(OUT.rglob('*')):
        if path.is_file():z.write(path,path.relative_to(OUT).as_posix())
print(json.dumps(status,ensure_ascii=False,indent=2));print('Saved:',archive,'SHA256:',digest(archive))
files.download(str(archive))
''')

notebook={'nbformat':4,'nbformat_minor':5,'metadata':{'colab':{'name':'Colab_Region_Preprocessing_V5.ipynb'},'accelerator':'GPU','kernelspec':{'name':'python3','display_name':'Python 3'},'language_info':{'name':'python'}},'cells':cells}
out=Path(__file__).with_name('Colab_Region_Preprocessing_V5.ipynb')
out.write_text(json.dumps(notebook,ensure_ascii=False,indent=1),encoding='utf-8')
print(out)
