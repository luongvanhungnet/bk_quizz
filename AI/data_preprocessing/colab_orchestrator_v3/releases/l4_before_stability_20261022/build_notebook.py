"""Build a small separately pinned runtime ZIP and a Drive-only notebook."""
import json
from pathlib import Path

from common import VERSION,atomic_json,digest,write_archive

ROOT=Path(__file__).resolve().parent


def build():
    files={p.name:p for p in ROOT.glob('*.py') if not p.name.startswith(('test_','build_'))}
    hashes={n:digest(p) for n,p in files.items()}
    archive=ROOT/'colab_orchestrator_v3_l4_runtime.zip'
    if archive.exists():archive.unlink()  # Only the explicitly named generated artifact.
    write_archive(archive,files,{'schema':VERSION},'runtime.json')
    cells=[]
    def md(text):cells.append({'cell_type':'markdown','metadata':{},'source':text.splitlines(True)})
    def code(text):
        compile(text,'colab','exec')
        cells.append({'cell_type':'code','metadata':{},'source':text.splitlines(True),'outputs':[],'execution_count':None})
    md('''# BKQuiz v5 — điều phối v3: L4 GPU · High-RAM · Python 3
Trong **Runtime → Change runtime type**, chọn **Python 3**, **L4 GPU** và **High-RAM** nếu có tùy chọn.
L4 có thể chỉ có một cấu hình RAM; notebook kiểm tra RAM vật lý thực tế ≥40 GiB và GPU đúng L4,
không coi metadata notebook là bằng chứng đã được cấp đúng máy.
Đặt 14 ZIP `v5_sequential_XX_of_14.zip` và `colab_orchestrator_v3_l4_runtime.zip` trong
**MyDrive/BKQuiz_cpt_data** bằng giao diện Google Drive. Không upload/download qua notebook.
Core v5 và Qwen2.5-VL-7B giữ nguyên. Kết quả VLM vẫn cần người kiểm duyệt.
Giữ BASE cũ để tiếp tục input chưa hoàn thành. Các lỗi đã lưu ở input 01/02 không tự sửa khi đổi GPU.
''')
    md('## 1. Kết nối Google Drive')
    code('''from google.colab import drive
from pathlib import Path
drive.mount('/content/drive')
INPUT_DIR=Path('/content/drive/MyDrive/BKQuiz_cpt_data')
BASE=Path('/content/drive/MyDrive/BKQuiz_v5_drive_v3')
WORK=Path('/content/bkquiz_v5_drive_v3')
BASE.mkdir(parents=True,exist_ok=True);WORK.mkdir(parents=True,exist_ok=True)
''')
    md('## 2. Xác minh runtime riêng; giữ nguyên các input v2')
    code('PINNED_RUNTIME='+repr(hashes)+'\nBOOTSTRAP_SHA256='+repr(digest(archive))+'''
import hashlib,json,sys,zipfile,shutil
def file_sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()
bootstrap=INPUT_DIR/'colab_orchestrator_v3_l4_runtime.zip'
assert file_sha(bootstrap)==BOOTSTRAP_SHA256,'Sai runtime ZIP hoặc notebook không cùng bản'
RUNTIME=Path('/content/bkquiz_v5_drive_v3_runtime');RUNTIME.mkdir(exist_ok=True)
with zipfile.ZipFile(bootstrap) as z:
    assert len(z.namelist())==len(set(z.namelist()))
    assert set(z.namelist())==set(PINNED_RUNTIME)|{'runtime.json'}
    for name,wanted in PINNED_RUNTIME.items():
        assert Path(name).name==name
        data=z.read(name);assert hashlib.sha256(data).hexdigest()==wanted,name
        (RUNTIME/name).write_bytes(data)
sys.path.insert(0,str(RUNTIME))
''')
    md('## 3. Kiểm tra đúng L4/High-RAM, kiểm kê input và cấu hình nhóm trang')
    code('''import os
from runtime_profile import PROFILE,check_hardware,check_environments
HARDWARE=check_hardware(BASE)
from drive_inputs import discover
from common import load
INPUTS=discover(INPUT_DIR)
BATCH_PAGES=20
KEEP_MODEL_RESIDENT=True  # Chọn False nếu thiếu RAM; không phải cài lại môi trường.
MAX_INPUTS=1  # Chạy thử một input; đổi thành None để xử lý toàn bộ phần còn lại.
DOC_HF_HOME=BASE/'docling_hf_cache_l4'  # Cache riêng, không xóa/ghi đè cache Docling lỗi trước đó.
os.environ['BKQUIZ_DOCLING_HF_HOME']=str(DOC_HF_HOME)
os.environ['BKQUIZ_RUNTIME_PROFILE']=PROFILE
PREVIOUS_BASE=None  # Nếu tiếp tục v2: Path('/content/drive/MyDrive/BKQuiz_v5_sequential')
if PREVIOUS_BASE is not None:
    from migrate_previous import migrate
    print(migrate(PREVIOUS_BASE,BASE,INPUTS,BATCH_PAGES))
for item in INPUTS:
    print(item['manifest']['bundle_index'],Path(item['path']).name,round(item['bytes']/1024**2,2),'MiB')
assert WORK.is_relative_to('/content') and not WORK.is_relative_to('/content/drive')
''')
    md('''## 4. Khôi phục môi trường và smoke test trước khi chạy dài
Giữ các phiên bản thư viện đã khóa; không cài CUDA toolkit/đổi wheel chỉ vì đổi T4 sang L4.
Kiểm tra thực tế: CUDA Paddle, OCR ảnh biết trước, layout, Torch/NF4, Docling một trang.
Docling dùng cache riêng trên Drive; lần đầu có thể tải lại trọng số. Cache lỗi cũ được giữ nguyên.
Nếu probe lỗi, dừng trước hàng đợi và lưu traceback trong `preflight_runs`. Smoke test không phải chấm chất lượng dataset.
''')
    code('''from env_setup import setup
ENVS=setup(BASE)
READINESS=check_environments(ENVS,INPUTS[0]['path'],BASE,WORK,DOC_HF_HOME)
print('Môi trường L4 sẵn sàng:',READINESS['all_passed'])
''')
    md('''## 5. Xử lý và lưu kết quả lên Drive — tải về máy sau, qua Google Drive
Không nhập DA_TAI. Chỉ chuyển input sau khi ZIP được sao chép và kiểm tra SHA-256 trên Drive.
Sau ngắt runtime, chạy lại từ cell 1 với cùng BASE và BATCH_PAGES. Nhóm đã checkpoint được dùng lại.
Heartbeat chỉ cho biết tiến trình còn chờ; telemetry mới ghi thời gian/tài nguyên của từng bước.
''')
    code('''from client import Session
if 'SESSION' in globals() and SESSION.process.poll() is None:
    assert getattr(SESSION,'runtime_profile',None)==PROFILE and getattr(SESSION,'docling_hf_home',None)==str(DOC_HF_HOME), 'SESSION cũ: khởi động lại runtime L4 và chạy notebook từ đầu; checkpoint Drive được giữ.'
    assert SESSION.batch_pages==BATCH_PAGES and SESSION.keep_model==KEEP_MODEL_RESIDENT, 'Đóng SESSION trước khi thay đổi cấu hình.'
if 'SESSION' not in globals() or SESSION.process.poll() is not None:
    SESSION=Session(ENVS['controller'],BASE,keep_model=KEEP_MODEL_RESIDENT,batch_pages=BATCH_PAGES,work=WORK)
processed=0
while True:
    state=load(BASE/'queue_state.json') if (BASE/'queue_state.json').exists() else {}
    expected=state.get('last_acknowledged_index',0)+1
    if expected>len(INPUTS):
        print('Đã lưu đủ kết quả trên Drive.');SESSION.close();break
    selected=INPUTS[expected-1]
    print('INPUT',expected,'/',len(INPUTS),selected['path'],flush=True)
    RESULT=SESSION.process_input(selected['path'])
    SESSION.commit(RESULT)
    print('ĐÃ LƯU DRIVE:',RESULT['archive'])
    print('SHA256:',RESULT['archive_sha256'])
    print('Chất lượng:',RESULT['summary'])
    processed+=1
    if MAX_INPUTS is not None and processed>=MAX_INPUTS:
        print('Đạt MAX_INPUTS; chạy lại cell 5 để tiếp tục, hoặc đổi MAX_INPUTS=None.');break
''')
    md('''## 6. Xem tiến độ/tài nguyên từ Drive (không cần tải kết quả qua kernel)
Mở Google Drive → BKQuiz_v5_drive_v3 → downloads để tải `v5_drive_results_*.zip`.
`latest_index.json` chứa số byte và SHA-256. `telemetry/` lưu các bước, thời gian, RAM và GPU;
đồng bộ khoảng 60 giây một lần. Bản telemetry cuối sau export cũng nằm trên Drive.
Nếu đổi KEEP_MODEL_RESIDENT hoặc BATCH_PAGES, đóng SESSION trước; batch size đã lưu không đổi giữa một queue.
''')
    code('''state=load(BASE/'queue_state.json') if (BASE/'queue_state.json').exists() else {}
print('Đã lưu và xác minh:',state.get('last_acknowledged_index',0),'/',len(INPUTS))
if (BASE/'downloads/latest_index.json').exists():print(load(BASE/'downloads/latest_index.json'))
print('Telemetry:',BASE/'telemetry')
''')
    nb={'nbformat':4,'nbformat_minor':5,'metadata':{'colab':{'name':'Colab_V5_L4_HighRAM.ipynb','gpuType':'L4','machine_shape':'hm'},
        'kernelspec':{'name':'python3','display_name':'Python 3'},'language_info':{'name':'python'},'accelerator':'GPU',
        'bkquiz_runtime':{'profile':'l4-highram-python3-20261021','minimum_system_ram_gib':40,'selection_is_hint_verified_at_runtime':True}},'cells':cells}
    path=ROOT/'Colab_V5_L4_HighRAM.ipynb';atomic_json(path,nb)
    atomic_json(ROOT/'Colab_V5_Drive_Queue.ipynb',nb)  # Current entry point, preserved old version under releases/.
    atomic_json(ROOT/'RUNTIME_RELEASE.json',{'schema':VERSION,'runtime_zip':archive.name,'runtime_zip_sha256':digest(archive),
                'files':hashes,'core_release':'5.0.0','input_schema':'v5-orchestrator-2-sequential','gpu_benchmark_executed':False,
                'runtime_profile':'l4-highram-python3-20261021','notebook':path.name})
    return path


if __name__=='__main__':print(build())
