import json
from pathlib import Path
from common import digest

ROOT=Path(__file__).resolve().parent


def build():
    cells=[]
    def md(s):cells.append({'cell_type':'markdown','metadata':{},'source':s.splitlines(True)})
    def code(s):
        compile(s,'notebook','exec')
        cells.append({'cell_type':'code','metadata':{},'source':s.splitlines(True),'outputs':[],'execution_count':None})
    md('''# BKQuiz v5 — 14 input cân bằng, xử lý từng file
Upload 01 → xử lý → tải ZIP kết quả → xác nhận DA_TAI → upload 02, tiếp tục đến 14.
Không cần upload trước cả 14 file. Phải dùng bộ `v5_sequential_XX_of_14.zip` mới, đúng thứ tự.
Giữ nguyên model/prompt v5 và kiểm duyệt VLM bằng người. Chọn GPU và RAM đủ để giữ model
trên CPU giữa hai input; đặt KEEP_MODEL_RESIDENT=False nếu muốn giải phóng model sau mỗi input.
''')
    md('## 1. Kết nối Drive — không upload trong cell này')
    code('''from google.colab import drive
from pathlib import Path
drive.mount('/content/drive')
BASE=Path('/content/drive/MyDrive/BKQuiz_v5_sequential')
BASE.mkdir(parents=True,exist_ok=True)
print(BASE)
''')
    md('''## 2. Nhập một file input
File đầu là 01. Khi tiếp tục phiên bị ngắt, mặc định dùng lại input đang chờ xử lý/tải từ Drive.
INPUT_FILE chỉ dùng để chỉ rõ một đường dẫn trên Drive; để None để hiện hộp thoại khi cần.
''')
    code('''import hashlib,json,zipfile,sys,time
from google.colab import files
INPUT_FILE=None
def file_sha(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def next_index():
    p=BASE/'queue_state.json'
    return json.loads(p.read_text()).get('last_acknowledged_index',0)+1 if p.exists() else 1
def upload_one(path=None):
    expected=next_index()
    assert expected<=14,'Đã xác nhận đủ 14 kết quả'
    state_path=BASE/'queue_state.json'
    state=json.loads(state_path.read_text()) if state_path.exists() else {}
    previous=state.get('received_inputs',{}).get(str(expected))
    if path is None and previous and Path(previous['path']).exists():
        path=Path(previous['path'])
        assert file_sha(path)==previous['sha256']
        print('Tiếp tục input đang xử lý/chờ tải:',expected)
    elif path is None:
        uploaded=files.upload()
        assert len(uploaded)==1,'Chỉ chọn MỘT input cho lượt này'
        name,data=next(iter(uploaded.items()));assert Path(name).name==name
        sha=hashlib.sha256(data).hexdigest();path=BASE/'inputs'/sha/name
        path.parent.mkdir(parents=True,exist_ok=True)
        if path.exists():assert file_sha(path)==sha
        else:path.write_bytes(data)
        del uploaded,data
    path=Path(path)
    with zipfile.ZipFile(path) as z:m=json.loads(z.read('bundle.json'))
    assert m['schema']=='v5-orchestrator-2-sequential','Chọn bộ input tuần tự mới'
    assert m['bundle_index']==expected,f'Cần input {expected:02d}'
    print('Selected input',expected,'/',m['bundle_count'],round(path.stat().st_size/1024**2,2),'MiB')
    return path
INPUT=upload_one(INPUT_FILE)
''')
    md('## 3. Xác minh mã điều phối')
    hashes={p.name:digest(p) for p in ROOT.glob('*.py') if not p.name.startswith('test_') and p.name!='build_notebook.py'}
    code('PINNED_RUNTIME='+repr(hashes)+'''
RUNTIME=Path('/content/bkquiz_v5_sequential_runtime');RUNTIME.mkdir(exist_ok=True)
with zipfile.ZipFile(INPUT) as z:
    for name,wanted in PINNED_RUNTIME.items():
        data=z.read('runtime/'+name);assert hashlib.sha256(data).hexdigest()==wanted,name
        (RUNTIME/name).write_bytes(data)
sys.path.insert(0,str(RUNTIME))
''')
    md('## 4. Cài/khôi phục môi trường một lần — nằm ngoài vòng upload')
    code('''from env_setup import setup
ENVS=setup(BASE)
KEEP_MODEL_RESIDENT=True
print(ENVS)
''')
    md('''## 5. Xử lý từng input và tải kết quả trước khi nhập input tiếp
Khi trình duyệt đã lưu ZIP kết quả, gõ **DA_TAI**. Nếu chưa tải xong, không xác nhận.
Gõ **DUNG** để dừng tại kết quả hiện tại; lần tiếp tục sẽ đề nghị tải lại kết quả đó.
Notebook chỉ biết yêu cầu tải và xác nhận do bạn nhập, không tự kiểm tra thư mục Downloads.
Môi trường cài một lần. Daemon sống xuyên các lần upload; Qwen tạm chuyển sang CPU
để nhường GPU cho Paddle rồi trở lại GPU khi cần, không đọc lại checkpoint model từ Drive.
''')
    code('''from client import Session
if 'SESSION' not in globals() or SESSION.process.poll() is not None:
    SESSION=Session(ENVS['controller'],BASE,keep_model=KEEP_MODEL_RESIDENT)
while True:
    RESULT=SESSION.process_input(INPUT)
    archive=Path(RESULT['archive'])
    assert file_sha(archive)==RESULT['archive_sha256']
    print('Xong input',RESULT['bundle_index'],'; kết quả:',archive)
    files.download(str(archive))
    answer=input('Sau khi ZIP đã tải xong: nhập DA_TAI để sang input tiếp; DUNG để dừng: ').strip().upper()
    if answer!='DA_TAI':
        print('Chưa mở upload tiếp. Kết quả được giữ trên Drive để tải lại.');break
    SESSION.acknowledge(RESULT)
    if RESULT['bundle_index']==RESULT['bundle_count']:
        print('Đã xử lý và xác nhận tải đủ 14 kết quả.');SESSION.close();break
    INPUT=upload_one()
''')
    md('''## Sau khi tải kết quả
Giữ 14 ZIP `v5_results_upload_XX_*.zip`. Nhập về máy bằng importer v2 theo README.
Mỗi ZIP có audit, gói con và snapshot; riêng IT3170 snapshot tăng dần theo các phần cache đã nhận.
Không trộn các file input cũ `v5_upload_...` hoặc notebook v1 vào BASE này.
Sau reset runtime, chạy lại từ cell 1; input trước và checkpoint trên Drive được khôi phục,
model cần nạp lại cho runtime mới. Lỗi vẫn được giữ để rà soát, không tự chấp nhận VLM vào CPT.
''')
    nb={'nbformat':4,'nbformat_minor':5,'metadata':{'colab':{'name':'Colab_V5_Sequential_14.ipynb'},
        'kernelspec':{'name':'python3','display_name':'Python 3'},'accelerator':'GPU'},'cells':cells}
    path=ROOT/'Colab_V5_Sequential_14.ipynb';path.write_text(json.dumps(nb,ensure_ascii=False,indent=1),encoding='utf-8');return path


if __name__=='__main__':print(build())
