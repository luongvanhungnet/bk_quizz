"""Produce a notebook with separate Drive, input, setup, execution and download cells."""
import json
from pathlib import Path
from common import digest

ROOT = Path(__file__).resolve().parent


def build():
    cells = []
    def md(source):
        cells.append({'cell_type': 'markdown', 'metadata': {}, 'source': source.splitlines(True)})
    def code(source):
        compile(source, '<notebook>', 'exec')
        cells.append({'cell_type': 'code', 'metadata': {}, 'source': source.splitlines(True), 'outputs': [], 'execution_count': None})
    md('''# BKQuiz v5 — điều phối toàn corpus trên Colab
14 gói upload chứa 148 gói con / 27 PDF / 13.314 trang. Upload đủ 14 gói trước khi chạy.
Giữ nguyên Qwen2.5-VL-7B NF4 và prompt v5. Không xuất nội dung VLM chưa được người duyệt vào CPT.
Chọn GPU; các bước cài đặt chỉ thực hiện khi môi trường chưa đúng phiên bản. Khi runtime bị reset,
chạy lại các cell; tiến độ và kết quả nằm trên Drive. Model cần nạp lại khi runtime đã mất.
''')
    md('## 1. Kết nối Google Drive — cell này chỉ kết nối và đặt thư mục')
    code('''from google.colab import drive
from pathlib import Path
drive.mount('/content/drive')
BASE=Path('/content/drive/MyDrive/BKQuiz_v5_orchestrator')
BASE.mkdir(parents=True,exist_ok=True)
print('Persistent queue:',BASE)
''')
    md('''## 2. Nhập input — độc lập với kết nối Drive
Mặc định chọn 14 file `v5_upload_XX_of_14.zip` trong một lần mở hộp thoại.
Nếu đã upload các file vào Drive, đặt `INPUT_DIR` thành đường dẫn thư mục đó.
Cell này chỉ đăng ký file; chưa cài môi trường và chưa gọi model. Lần tiếp tục có thể đặt
`REUSE_REGISTERED=True` để giữ danh sách cũ. Không tự chọn file ZIP cũ ngoài danh sách.
''')
    code('''import hashlib,json,shutil,zipfile,sys,os,subprocess,time
from google.colab import files
INPUT_DIR=None # Ví dụ '/content/drive/MyDrive/BKQuiz_inputs_14'
REUSE_REGISTERED=False # Đổi True khi tiếp tục cùng bộ 14 file đã đăng ký
def file_sha(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()
registry=BASE/'selected_inputs.json'
if REUSE_REGISTERED:
    INPUTS=[Path(p) for p in json.loads(registry.read_text())]
elif INPUT_DIR is not None:
    INPUTS=sorted(Path(INPUT_DIR).glob('v5_upload_*_of_14.zip'))
else:
    uploaded=files.upload()
    assert len(uploaded)==14,'Chọn đúng 14 file v5_upload_XX_of_14.zip'
    INPUTS=[]
    for name,data in uploaded.items():
        assert Path(name).name==name and name.lower().endswith('.zip')
        sha=hashlib.sha256(data).hexdigest()
        dest=BASE/'inputs'/sha/name;dest.parent.mkdir(parents=True,exist_ok=True)
        if dest.exists():assert file_sha(dest)==sha
        else:dest.write_bytes(data)
        INPUTS.append(dest)
    del uploaded,data
assert len(INPUTS)==14,'Cần đủ 14 gói upload; không dùng ZIP 100 trang từ notebook cũ'
manifests=[]
for path in INPUTS:
    with zipfile.ZipFile(path) as z:manifests.append(json.loads(z.read('bundle.json')))
assert {m['bundle_index'] for m in manifests}==set(range(1,15))
assert len({m['plan_sha256'] for m in manifests})==1
registry.write_text(json.dumps([str(p) for p in INPUTS],indent=2))
print('Registered:',len(INPUTS),'upload files; plan',manifests[0]['plan_sha256'])
''')
    md('## 3. Nạp mã điều phối và kiểm tra hash — chưa chạy model')
    hashes = {p.name: digest(p) for p in ROOT.glob('*.py') if not p.name.startswith('test_') and p.name != 'build_notebook.py'}
    code('PINNED_RUNTIME='+repr(hashes)+'''
RUNTIME=Path('/content/bkquiz_v5_orchestrator_runtime');RUNTIME.mkdir(exist_ok=True)
with zipfile.ZipFile(INPUTS[0]) as z:
    for name,expected in PINNED_RUNTIME.items():
        data=z.read('runtime/'+name)
        assert hashlib.sha256(data).hexdigest()==expected,name
        (RUNTIME/name).write_bytes(data)
sys.path.insert(0,str(RUNTIME))
print('Coordinator runtime verified')
''')
    md('''## 4. Cài/khôi phục môi trường một lần
Dùng lại `it3170_paddle_env`, `it3170_vlm_env`, `it3170_docling_v5_env` nếu tương thích.
Các bản sao `*_py313_v1.tar.gz` trên Drive được kiểm tra và dùng lại khi phù hợp.
Cell này chạy trước hàng đợi, không nằm trong vòng lặp từng gói.
''')
    code('''from env_setup import setup
ENVS=setup(BASE)
print(json.dumps(ENVS,indent=2))
''')
    md('''## 5. Chạy toàn bộ hàng đợi
Native/render -> OCR -> layout Paddle + Docling -> đối chiếu/routing theo toàn học phần ->
OCR vùng hình + FormulaNet + Table -> một worker Qwen cho toàn hàng đợi -> lưu kết quả.
Paddle và Qwen không giữ model GPU đồng thời. Mỗi vùng được cache riêng; lỗi được lưu để rà soát.
Không cần upload lại khi Colab bị ngắt: giữ nguyên BASE, dùng lại danh sách input ở cell 2 rồi chạy tiếp.
''')
    code('''command=[ENVS['controller'],str(RUNTIME/'orchestrator.py'),'--base',str(BASE),'--inputs',str(registry)]
# Stream output trực tiếp để theo dõi heartbeat và lỗi; nhật ký vẫn lưu trên Drive.
completed=subprocess.run(command)
print('Coordinator exit code:',completed.returncode)
print('Summary:',BASE/'summary.json')
assert completed.returncode==0,'Xem log và queue_state.json; phần đã hoàn thành vẫn được giữ để chạy tiếp'
''')
    md('''## 6. Xem kết quả / tải xuống — không upload lại input
Có 14 ZIP kết quả trên Drive. Không cần tải tất cả bằng trình duyệt cùng lúc.
Đặt `DOWNLOAD_INDEX=1` để tải file thứ nhất, `2` cho thứ hai, hoặc `None` để chỉ xem danh sách.
Sau khi tải, dùng `import_returns.py` theo README để nhập vào máy và duyệt VLM.
''')
    code('''DOWNLOAD_INDEX=None
result_index=json.loads((BASE/'downloads/latest_index.json').read_text())
for i,item in enumerate(result_index['files'],1):print(i,item['path'],round(item['bytes']/1024**2,2),'MiB')
if DOWNLOAD_INDEX is not None:
    assert 1<=DOWNLOAD_INDEX<=len(result_index['files'])
    files.download(result_index['files'][DOWNLOAD_INDEX-1]['path'])
''')
    notebook = {'nbformat': 4, 'nbformat_minor': 5, 'metadata': {'colab': {'name': 'Colab_V5_Orchestrator_14_Uploads.ipynb'},
                'kernelspec': {'name': 'python3', 'display_name': 'Python 3'}, 'accelerator': 'GPU'}, 'cells': cells}
    target = ROOT / 'Colab_V5_Orchestrator_14_Uploads.ipynb'
    target.write_text(json.dumps(notebook,ensure_ascii=False,indent=1),encoding='utf-8')
    return target


if __name__ == '__main__':
    print(build())
