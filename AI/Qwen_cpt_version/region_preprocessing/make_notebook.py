"""Produce a notebook for the region-only cloud stage, preserving the old pilot."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
cells=[]


def md(text):cells.append({'cell_type':'markdown','metadata':{},'source':text.splitlines(True)})


def code(text):cells.append({'cell_type':'code','metadata':{},'execution_count':None,'outputs':[],'source':text.splitlines(True)})


md('''# IT3170 — region routing, VLM dưới 5% số trang đầu vào
Chỉ diagram/graph mới gửi Qwen2.5-VL-3B. FormulaNet và Table Recognition chạy riêng.
Ngân sách áp dụng số trang chứa crop VLM được gửi inference, không phải tỷ lệ kiến thức đã xử lý.
Phần vượt ngân sách vẫn ở Review Queue trên máy. Xem routing_report.json trước khi chạy.
Chọn GPU runtime, ví dụ T4. Batch VLM mặc định 2; đây là cấu hình cần đo, chưa có cam kết tốc độ.
''')
code('''import sys, json, zipfile, hashlib, subprocess, os, time
from pathlib import Path
from google.colab import drive, files
subprocess.run(['nvidia-smi'], check=True)
drive.mount('/content/drive')
BASE=Path('/content/drive/MyDrive/BKQuiz_region_preprocessing')
BASE.mkdir(parents=True,exist_ok=True)
uploaded=files.upload()  # Chọn region_input.zip từ runs/it3170_regions_v4
assert 'region_input.zip' in uploaded
input_zip=BASE/'region_input.zip';input_zip.write_bytes(uploaded['region_input.zip']);del uploaded
WORK=Path('/content/it3170_regions');WORK.mkdir(exist_ok=True)
with zipfile.ZipFile(input_zip) as z:
    for entry in z.infolist():
        assert (WORK/entry.filename).resolve().is_relative_to(WORK.resolve())
    z.extractall(WORK)
MANIFEST=json.loads((WORK/'manifest.json').read_text())
RUN_HASH=hashlib.sha256((WORK/'manifest.json').read_bytes()).hexdigest()
OUT=BASE/('results_'+RUN_HASH[:12]);OUT.mkdir(exist_ok=True)
os.environ['REGION_CACHE_DIR']=str(BASE/'cache')
(OUT/'gpu_info.txt').write_text(subprocess.check_output(['nvidia-smi'],text=True))
print(json.dumps(MANIFEST['budget'],indent=2))
from collections import Counter
print('Crop requests:',dict(Counter(r['engine'] for r in MANIFEST['requests'])))
print('Persisted output:',OUT)
''')
md('''## Môi trường GPU
Tái sử dụng venv của notebook cũ nếu đúng phiên bản. Nếu phiên mới, cài lại thư viện; cache output theo hash nằm trên Drive.
Không cài đè môi trường Torch của Colab. Paddle và Torch chạy trong hai subprocess nối tiếp.
Native cell text được đưa vào Table Recognition; không dùng OCR Latin thiếu dấu để tự ghi đè chữ PDF.
''')
code('''PADDLE_ENV=Path('/content/it3170_paddle_env');VLM_ENV=Path('/content/it3170_vlm_env')
for env in [PADDLE_ENV,VLM_ENV]:
    if not (env/'bin/python').exists():subprocess.run([sys.executable,'-m','venv',str(env)],check=True)
PADDLE_PY=str(PADDLE_ENV/'bin/python');VLM_PY=str(VLM_ENV/'bin/python')
def versions_match(py,expected):
    probe="import importlib.metadata,json; print(json.dumps({k:importlib.metadata.version(k) for k in "+repr(list(expected))+"}))"
    result=subprocess.run([py,'-c',probe],capture_output=True,text=True)
    if result.returncode:return False
    actual=json.loads(result.stdout)
    return all(actual.get(k,'').split('+')[0]==v for k,v in expected.items())
start=time.perf_counter()
if not versions_match(PADDLE_PY,MANIFEST['config']['paddle_versions_expected']):
    subprocess.run([PADDLE_PY,'-m','pip','install','paddlepaddle-gpu==3.2.2',
                    '--index-url','https://www.paddlepaddle.org.cn/packages/stable/cu118/'],check=True)
    subprocess.run([PADDLE_PY,'-m','pip','install','paddleocr[doc-parser]==3.7.0','paddlex[ocr]==3.7.2','Pillow==11.3.0'],check=True)
vlm_versions={'torch':'2.6.0','torchvision':'0.21.0','transformers':'4.57.6',
              'accelerate':'1.12.0','qwen-vl-utils':'0.0.14'}
if not versions_match(VLM_PY,vlm_versions):
    subprocess.run([VLM_PY,'-m','pip','install','torch==2.6.0','torchvision==0.21.0',
                    '--index-url','https://download.pytorch.org/whl/cu124/'],check=True)
    subprocess.run([VLM_PY,'-m','pip','install','transformers==4.57.6','accelerate==1.12.0',
                    'qwen-vl-utils==0.0.14','Pillow==11.3.0'],check=True)
for name,py in [('paddle',PADDLE_PY),('vlm',VLM_PY)]:
    (OUT/(name+'_pip_freeze.txt')).write_text(subprocess.check_output([py,'-m','pip','freeze'],text=True))
(OUT/'installation_seconds.json').write_text(json.dumps({'seconds':time.perf_counter()-start}))
''')
md('''## FormulaNet và Table Recognition
Chạy chuyên biệt trên crop; không chạy lại OCR/layout toàn trang.
Bảng không có lớp chữ native sẽ báo lỗi để rà soát, không tự chuyển sang VLM.
Model này kiểm tra cấu trúc; kết quả vẫn phải đối chiếu để bảo đảm đúng ký hiệu/hàng/cột.
''')
code('''subprocess.run([PADDLE_PY,str(WORK/'worker.py'),'paddle','--input',str(WORK),'--out',str(OUT)],check=True)
''')
md('''## Batch VLM trên crop diagram/graph
FP16 + SDPA, padding trái, nhóm crop gần kích thước và tỷ lệ, batch 2, tối đa 768 visual token/crop và 1.024 token sinh.
Cache dùng hash crop gốc + crop sau resize + model revision + prompt + cấu hình/schema. Dùng lại cache không đồng nghĩa đã duyệt ngữ nghĩa.
Lỗi/OOM/cắt dở được lưu, không tự sửa câu trả lời hoặc tự chuyển nội dung chưa rõ vào train.
''')
code('''subprocess.run([VLM_PY,str(WORK/'worker.py'),'vlm','--input',str(WORK),'--out',str(OUT)],check=True)
''')
md('''## Tổng hợp, tải về và nhập kết quả
Kiểm tra lỗi trước; chỉ JSON hợp lệ và cấu trúc đúng mới vào cache thành công.
Mọi dự đoán mới đều semantic_verified=false. Node/cạnh thiếu hoặc bảng sai vẫn cần người đối chiếu.
''')
code('''subprocess.run([sys.executable,str(WORK/'worker.py'),'collect','--input',str(WORK),'--out',str(OUT)],check=True)
print((OUT/'summary.json').read_text())
result_zip=BASE/('region_results_'+RUN_HASH[:12]+'.zip')
with zipfile.ZipFile(result_zip,'w',zipfile.ZIP_DEFLATED) as z:
    for path in sorted(OUT.rglob('*')):
        if path.is_file():z.write(path,path.relative_to(OUT).as_posix())
print(result_zip)
files.download(str(result_zip))
''')
md('''Sau khi tải ZIP về, dùng `route.py merge --results ...` theo README. Cấu trúc hợp lệ chỉ là cổng kỹ thuật; không chứng minh kiến thức đúng.
Review Queue giữ cả trang chưa chạy vì ngân sách và các vùng chưa được nhận dạng chắc chắn.
Không dùng tỷ lệ VLM dưới 5% để báo đã xử lý đầy đủ PDF.
''')
for i,c in enumerate(cells):c['id']=f'region-{i:02d}'
notebook={'nbformat':4,'nbformat_minor':5,'metadata':{'accelerator':'GPU','kernelspec':{'name':'python3','display_name':'Python 3','language':'python'}},'cells':cells}
target=ROOT/'IT3170_Region_Routing.ipynb'
target.write_text(json.dumps(notebook,ensure_ascii=False,indent=2),encoding='utf-8')
print(target)
