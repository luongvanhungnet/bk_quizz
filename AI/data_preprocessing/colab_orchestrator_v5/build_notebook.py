"""Pinned L4 notebook for 134 independent, final-ZIP transactions."""
from pathlib import Path
from common import atomic_json,digest,write_archive

ROOT=Path(__file__).resolve().parent
REVISION='v6-jsonl-unicode-l4-20261023'
NAME='Colab_V6_L4_134_Units_JSONL_Fix.ipynb'
RUNTIME='colab_orchestrator_v5_v6_jsonl_runtime.zip'


def build(index_path=None):
    index_path=Path(index_path or ROOT.parent/'uploads_134_unit100_20261022/UPLOAD_INDEX.json')
    precompleted_index=index_path.parent/'precompleted_results/PRECOMPLETED_INDEX.json'
    precompleted_sha=digest(precompleted_index) if precompleted_index.exists() else None
    files={p.name:p for p in ROOT.glob('*.py') if not p.name.startswith(('build_','test_','audit_'))}
    pins={n:digest(p) for n,p in files.items()};archive=ROOT/RUNTIME
    if archive.exists():archive.unlink()
    write_archive(archive,files,{'schema':'v5-unit-runtime-v1','revision':REVISION},'runtime.json')
    cells=[]
    def md(s):cells.append({'cell_type':'markdown','metadata':{},'source':s.splitlines(True)})
    def code(s):
        compile(s,'colab','exec');cells.append({'cell_type':'code','metadata':{},'source':s.splitlines(True),'outputs':[],'execution_count':None})
    md('''# BKQuiz v6 — 134 gói độc lập · tối đa 100 trang/gói · L4/High-RAM/Python 3
133 gói đầu có 100 trang, gói cuối 14 trang; tổng 13.314 trang / 27 tài liệu.
Chạy xong một gói → đóng ZIP trên `/content` → kiểm SHA-256 trên Drive → ghi biên nhận → gói tiếp.
Sau khi khởi động lại, quét kết quả đã lưu và chỉ chạy gói còn thiếu/hỏng. Không phục hồi tiến trình nội bộ của gói dở. Lọc nền có bằng chứng trước crop/OCR; giới hạn số vùng/dung lượng; merge có tiến độ và deadline. Core v5.0.0 giữ nguyên, adapter v6 được lưu trong ZIP kết quả.
Gói ở ranh giới có thể chứa hai học phần. PDF gốc được giữ nguyên để bảo toàn hash;
**phạm vi native/render/OCR/model chỉ là các trang trong manifest, tối đa 100 trang cộng lại**.

Đặt 134 ZIP `v5_unit_XXXX_of_0134.zip` và `UPLOAD_INDEX.json` vào **MyDrive/BKQuiz_cpt_data/inputs_134**.
Nếu có thư mục `precompleted_results`, upload cùng để dùng lại các gói phủ đủ trang từ kết quả v3 đã kiểm hash.
Đặt `colab_orchestrator_v5_v6_jsonl_runtime.zip` vào **MyDrive/BKQuiz_cpt_data**.
Đã sửa bộ đọc JSONL cho U+0085/U+2028/U+2029; giữ nguyên ký tự nguồn và 134 input. BASE cũ và ZIP hoàn chỉnh tiếp tục dùng được.
Upload bằng giao diện Drive; không có widget upload/download notebook. Giữ nguyên 14 input và kết quả cũ.
Chỉ vận hành một phiên ghi cùng BASE. Tạo bản notebook riêng; không lưu output vào notebook.
''')
    md('## 1. Kết nối Drive')
    code('''from google.colab import drive
from pathlib import Path
drive.mount('/content/drive')
INPUT_ROOT=Path('/content/drive/MyDrive/BKQuiz_cpt_data')
INPUT_DIR=INPUT_ROOT/'inputs_134'
BASE=Path('/content/drive/MyDrive/BKQuiz_v6_unit100')
WORK=Path('/content/bkquiz_v6_units')
BASE.mkdir(parents=True,exist_ok=True);WORK.mkdir(parents=True,exist_ok=True)
''')
    md('## 2. Xác minh và nạp runtime')
    code('PINNED_RUNTIME='+repr(pins)+'\nRUNTIME_SHA256='+repr(digest(archive))+'\nINDEX_SHA256='+repr(digest(index_path))+'\nPRECOMPLETED_SHA256='+repr(precompleted_sha)+'''
import sys,json,hashlib,zipfile
def file_sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()
runtime_zip=INPUT_ROOT/'colab_orchestrator_v5_v6_jsonl_runtime.zip'
assert file_sha(runtime_zip)==RUNTIME_SHA256,'Notebook và runtime không cùng phiên bản'
assert file_sha(INPUT_DIR/'UPLOAD_INDEX.json')==INDEX_SHA256,'Sai index 134 input'
if PRECOMPLETED_SHA256 is not None and (INPUT_DIR/'precompleted_results/PRECOMPLETED_INDEX.json').exists():
    assert file_sha(INPUT_DIR/'precompleted_results/PRECOMPLETED_INDEX.json')==PRECOMPLETED_SHA256,'Thiếu/sai index tái sử dụng kết quả cũ'
RUNTIME=Path('/content/bkquiz_v6_units_runtime')
loaded=any(getattr(m,'__file__',None) and Path(m.__file__).resolve().parent==RUNTIME.resolve() for m in list(sys.modules.values()) if m is not None)
if loaded and globals().get('_UNIT_RUNTIME_SHA')!=RUNTIME_SHA256:
    raise RuntimeError('Kernel đang giữ runtime cũ; đóng phiên trước, restart runtime rồi nạp lại.')
if not loaded and any(n in sys.modules for n in ['common','client','unit_queue','orchestrator']):
    raise RuntimeError('Kernel đã import bộ điều phối khác; restart runtime trước khi dùng bản 134 gói.')
RUNTIME.mkdir(exist_ok=True)
with zipfile.ZipFile(runtime_zip) as z:
    assert set(z.namelist())==set(PINNED_RUNTIME)|{'runtime.json'}
    assert len(z.namelist())==len(set(z.namelist()))
    for name,wanted in PINNED_RUNTIME.items():
        assert Path(name).name==name
        data=z.read(name);assert hashlib.sha256(data).hexdigest()==wanted,name
        (RUNTIME/name).write_bytes(data)
sys.path.insert(0,str(RUNTIME));_UNIT_RUNTIME_SHA=RUNTIME_SHA256
''')
    md('## 3. Kiểm tra máy và cấu hình')
    code('''import os
from common import load,atomic_json
from runtime_profile import PROFILE,check_hardware,check_environments
from unit_store import read_index
HARDWARE=check_hardware(BASE)
INDEX=read_index(INPUT_DIR)
MAX_UNITS=None  # None: xử lý liên tiếp tất cả gói còn thiếu; đặt 1 để chạy thử.
KEEP_MODEL_RESIDENT=True
os.environ['BKQUIZ_RUNTIME_PROFILE']=PROFILE
os.environ['BKQUIZ_RUNTIME_REVISION']='v6-jsonl-unicode-l4-20261023'
MODEL_ROOT=Path('/content/bkquiz_v6_models')
os.environ['BKQUIZ_MODEL_ROOT']=str(MODEL_ROOT)
DOC_HF_HOME=MODEL_ROOT/'docling_hf'
from model_cache import restore,seal
print(restore(BASE,MODEL_ROOT))
os.environ['BKQUIZ_CPU_TIMEOUT_SECONDS']='900'
os.environ['BKQUIZ_MODEL_TIMEOUT_SECONDS']='900'
os.environ['BKQUIZ_COMMAND_TIMEOUT_SECONDS']='10800'
PREVIOUS_BASE=Path('/content/drive/MyDrive/BKQuiz_v5_unit100')  # Chỉ đọc kết quả gói hoàn chỉnh, không sửa BASE cũ
REUSE_PRECOMPLETED=True  # Giữ kết quả cũ; bản ghi được đánh dấu legacy, không nhận là đã chạy policy v6.
os.environ['BKQUIZ_DOCLING_HF_HOME']=str(DOC_HF_HOME)
atomic_json(BASE/'unit_runtime_config.json',{'input_dir':str(INPUT_DIR),'plan_sha256':INDEX['plan_sha256'],
    'precompleted_dir':str(INPUT_DIR/'precompleted_results') if PRECOMPLETED_SHA256 is not None and REUSE_PRECOMPLETED and (INPUT_DIR/'precompleted_results/PRECOMPLETED_INDEX.json').exists() else None,
    'previous_base':str(PREVIOUS_BASE) if PREVIOUS_BASE is not None else None, 'preprocessing_version':'6.0.0'})
available=[e for e in INDEX['bundles'] if Path(e['path']).is_file()]
assert available,'Chưa có ZIP input trong inputs_134'
print('Input đã có trên Drive:',len(available),'/',INDEX['bundle_count'],'; tổng trang:',INDEX['pages'])
''')
    md('''## 4. Môi trường một lần / phiên, smoke test trước xử lý
Tái sử dụng venv còn tương thích. Model chạy từ /content; Docling cache được đóng ZIP và kiểm hash trên Drive sau smoke test. Lần đầu cache local mới có thể cần tải trọng số. Chưa nạp Qwen lớn ở bước này.
Giữ Qwen qua nhiều gói; model được chuyển về RAM CPU giữa các lượt cần Paddle.
''')
    code('''from env_setup import setup
ENVS=setup(BASE)
READINESS=check_environments(ENVS,available[0]['path'],BASE,WORK,DOC_HF_HOME)
print('Preflight:',READINESS['all_passed'])
print('Sealed Docling cache:',seal(BASE,MODEL_ROOT))
''')
    md('''## 5. Kiểm tra tiến độ và xử lý gói thiếu
Lần đầu mỗi lượt chạy cell này sẽ kiểm tra biên nhận và SHA-256 của ZIP kết quả trên Drive.
Gói đã lưu ZIP nhưng runtime ngắt trước lúc ghi biên nhận được nhận lại, không inference lại.
Gói thiếu/hỏng hoặc chỉ có `.partial`/`.next` vẫn là chưa hoàn thành; gói đó chạy lại từ input.
Gói khác đã lưu không bị xóa. Kiểm tra SHA của nhiều kết quả có thể mất thời gian I/O, không phải VLM.
''')
    code((ROOT/'COLAB_AUTO_SKIP_CELL.txt').read_text(encoding='utf-8').replace(
        "EXCLUDED_UNITS = {'unit_0025'}", 'EXCLUDED_UNITS = set()'))
    md('''## 6. Xem tiến độ và tải kết quả bằng Google Drive
**MyDrive/BKQuiz_v6_unit100/results/unit_XXXX/** chứa ZIP kết quả từng gói.
`receipts/unit_XXXX.json` chỉ được ghi sau khi ZIP được lưu/kiểm hash trên Drive.
`queue_state.json` là bản tổng hợp; khi chạy lại sẽ đối chiếu ZIP thực tế.
`telemetry/live_status.json`, `events_*.jsonl` và `current_attempt.json` giúp theo dõi bước đang chạy.
Nếu chỉ giao diện Connecting mà VM tiếp tục lưu ZIP, ZIP đó vẫn được nhận lại lần sau.
Không bấm chạy phiên thứ hai cùng BASE khi phiên cũ còn hoạt động.
''')
    code('''print(load(BASE/'queue_state.json') if (BASE/'queue_state.json').exists() else 'Chưa bắt đầu')
if (BASE/'current_attempt.json').exists():print(load(BASE/'current_attempt.json'))
if (BASE/'telemetry/live_status.json').exists():print(load(BASE/'telemetry/live_status.json'))
print('Kết quả:',BASE/'results')
''')
    nb={'nbformat':4,'nbformat_minor':5,'metadata':{'colab':{'name':NAME,'gpuType':'L4','machine_shape':'hm','private_outputs':True},
        'accelerator':'GPU','kernelspec':{'name':'python3','display_name':'Python 3'},'language_info':{'name':'python'},
        'bkquiz_runtime':{'revision':REVISION,'unit_pages':100,'resume_policy':'complete_ZIP_receipts_only'}},'cells':cells}
    atomic_json(ROOT/NAME,nb)
    atomic_json(ROOT/'RUNTIME_RELEASE.json',{'schema':'v5-unit-runtime-v1','revision':REVISION,'runtime_zip':RUNTIME,
        'runtime_zip_sha256':digest(archive),'files':pins,'notebook':NAME,'index_sha256':digest(index_path),
        'precompleted_index_sha256':precompleted_sha,'core_release':'5.0.0','preprocessing_version':'6.0.0','actual_Colab_executed':False})
    return ROOT/NAME


if __name__=='__main__':print(build())
