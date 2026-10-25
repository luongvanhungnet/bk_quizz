"""Build the Colab GPU pilot notebook using only the standard library."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
cells=[]


def md(text):cells.append({'cell_type':'markdown','metadata':{},'source':text.splitlines(True)})


def code(text):cells.append({'cell_type':'code','metadata':{},'source':text.splitlines(True),'execution_count':None,'outputs':[]})


md('''# IT3170 — thử pipeline CPU Windows + GPU Colab Pro
Phần này chạy PaddleOCR tiếng Việt, PP-FormulaNet-S và Qwen2.5-VL-3B-Instruct.
Trên Colab chọn **Runtime → Change runtime type → GPU**. T4 16 GB là mục tiêu thử, không phải cam kết luôn có GPU hoặc đủ RAM cho mọi trang.

Notebook mặc định 12 trang được chọn để kiểm tra kỹ thuật, không đại diện thống kê cho toàn bộ 1.060 trang.
Mọi kết quả là **ứng viên chưa xác minh**. Không tự đưa VLM/OCR vào train.
Hai môi trường Paddle và Torch chạy bằng hai subprocess riêng để giải phóng VRAM giữa các giai đoạn.
''')
code('''import sys, subprocess, json, hashlib, zipfile, time, shutil, os
from pathlib import Path
assert (3,10) <= sys.version_info[:2] <= (3,12), "Chọn runtime Python 3.10–3.12 cho bộ wheel đã khóa"
subprocess.run(["nvidia-smi"], check=True)
from google.colab import drive, files
drive.mount('/content/drive')
BASE = Path('/content/drive/MyDrive/BKQuiz_preprocessing')
BASE.mkdir(parents=True, exist_ok=True)
INPUT_ZIP = BASE / 'colab_input.zip'
if not INPUT_ZIP.exists():
    uploaded = files.upload()  # Chọn colab_input.zip từ đợt chạy local
    assert 'colab_input.zip' in uploaded
    INPUT_ZIP.write_bytes(uploaded['colab_input.zip'])
    del uploaded
WORK = Path('/content/it3170_hybrid')
WORK.mkdir(exist_ok=True)
with zipfile.ZipFile(INPUT_ZIP) as z:
    for member in z.infolist():
        assert (WORK / member.filename).resolve().is_relative_to(WORK.resolve())
    z.extractall(WORK)
manifest_bytes = (WORK/'manifest.json').read_bytes()
RUN_HASH = hashlib.sha256(manifest_bytes).hexdigest()
OUT = BASE / ('results_' + RUN_HASH[:12])
OUT.mkdir(exist_ok=True)
(OUT/'gpu_info.txt').write_text(subprocess.check_output(['nvidia-smi'], text=True))
print('Input SHA256:', hashlib.sha256(INPUT_ZIP.read_bytes()).hexdigest())
print('Pages:', json.loads(manifest_bytes)['pilot_pages'])
print('Persistent output:', OUT)
''')
md('''## Cài môi trường riêng
Lần đầu cần tải thư viện GPU và khoảng vài GB trọng số VLM; thời gian tải không phải thời gian inference.
Không cài đè Torch có sẵn của Colab. Các wheel CUDA 11.8/12.4 yêu cầu driver GPU tương thích; nếu cài hoặc kiểm tra GPU thất bại thì dừng, không tự chuyển sang CPU.
''')
code('''PADDLE_ENV = Path('/content/it3170_paddle_env')
VLM_ENV = Path('/content/it3170_vlm_env')
for env in [PADDLE_ENV, VLM_ENV]:
    if not (env/'bin/python').exists():
        subprocess.run([sys.executable, '-m', 'venv', str(env)], check=True)
PADDLE_PY = str(PADDLE_ENV/'bin/python')
VLM_PY = str(VLM_ENV/'bin/python')
start = time.perf_counter()
subprocess.run([PADDLE_PY, '-m', 'pip', 'install', 'paddlepaddle-gpu==3.2.2',
               '--index-url', 'https://www.paddlepaddle.org.cn/packages/stable/cu118/'], check=True)
subprocess.run([PADDLE_PY, '-m', 'pip', 'install', 'paddleocr[doc-parser]==3.7.0',
               'Pillow==11.3.0'], check=True)
subprocess.run([VLM_PY, '-m', 'pip', 'install', 'torch==2.6.0', 'torchvision==0.21.0',
               '--index-url', 'https://download.pytorch.org/whl/cu124'], check=True)
subprocess.run([VLM_PY, '-m', 'pip', 'install', 'transformers==4.57.6', 'accelerate==1.12.0',
               'qwen-vl-utils==0.0.14', 'Pillow==11.3.0', 'numpy==1.26.4'], check=True)
for name, py in [('paddle', PADDLE_PY), ('vlm', VLM_PY)]:
    frozen = subprocess.check_output([py, '-m', 'pip', 'freeze'], text=True)
    (OUT/(name+'_pip_freeze.txt')).write_text(frozen)
(OUT/'installation_seconds.json').write_text(json.dumps({'seconds':time.perf_counter()-start}))
''')
md('''## OCR + phát hiện vùng + công thức
PaddleOCR dùng `lang=vi`, PP-OCRv3 để tránh mặc định lấy recognizer Latin v5 đã thiếu dấu trong lần kiểm tra trước.
PP-DocLayout-M định vị vùng công thức trước khi PP-FormulaNet-S đọc vùng cắt. Vùng chồng lên mã native được giữ riêng, không thay mã bằng LaTeX.
Bước này không phải một bộ nhận dạng bảng chuyên dụng; bảng sẽ có ứng viên từ VLM và cần kiểm tra cấu trúc hàng/cột.
''')
code('''start = time.perf_counter()
subprocess.run([PADDLE_PY, str(WORK/'colab_worker.py'), 'paddle', '--input', str(WORK), '--out', str(OUT)], check=True)
print('Paddle process seconds:', time.perf_counter()-start)
print((OUT/'paddle_runtime.json').read_text())
''')
md('''## VLM — Qwen2.5-VL 3B
Khóa revision HF, FP16, batch 1, SDPA, tối đa 1.280 visual token/ảnh và 1.536 output token.
Giới hạn ảnh giúp kiểm soát VRAM nhưng có thể làm chữ nhỏ khó đọc; trường hợp đó cần crop vùng rồi xử lý lại có ghi cấu hình mới.
Không dùng output VLM để tự sửa toàn bộ văn bản gốc.
''')
code('''VLM_REVISION = '66285546d2b821cf421d4f5eb2576359d3770cd3'
start = time.perf_counter()
subprocess.run([VLM_PY, str(WORK/'colab_worker.py'), 'vlm', '--input', str(WORK),
                '--out', str(OUT), '--revision', VLM_REVISION], check=True)
print('VLM process seconds:', time.perf_counter()-start)
print((OUT/'vlm_runtime.json').read_text())
''')
md('''## Tổng hợp và tải kết quả
Kiểm tra summary: lỗi, invalid JSON hoặc trang chưa chạy vẫn được ghi lại. CER/WER, Formula Accuracy và Diagram Fact Precision chưa được gán khi chưa có ground truth.
ZIP giữ ứng viên, output thô, công thức, ảnh crop và thông số chạy để đối chiếu trên máy.
''')
code('''subprocess.run([sys.executable, str(WORK/'colab_worker.py'), 'collect', '--input', str(WORK), '--out', str(OUT)], check=True)
print((OUT/'summary.json').read_text())
ZIP_OUT = BASE / ('colab_results_' + RUN_HASH[:12] + '.zip')
with zipfile.ZipFile(ZIP_OUT, 'w', zipfile.ZIP_DEFLATED) as z:
    for path in sorted(OUT.rglob('*')):
        if path.is_file(): z.write(path, path.relative_to(OUT).as_posix())
print('Result:', ZIP_OUT, 'SHA256:', hashlib.sha256(ZIP_OUT.read_bytes()).hexdigest())
files.download(str(ZIP_OUT))
''')
md('''## Đưa về máy
Chạy lệnh `local_pipeline.py merge` trong README để kiểm tra hash nguồn và tạo hàng đợi rà soát.
Sau khi đối chiếu ảnh, cung cấp `reviewed_annotations.jsonl` có trang, hash PDF/ảnh, reviewer, evidence, verified=true và text đã kiểm tra.
Chỉ các bản chép đã xác minh mới được đóng gói vào `reviewed_cpt/`. Các trang còn lại được giữ trong dữ liệu audit.
''')
notebook={'nbformat':4,'nbformat_minor':5,'metadata':{'colab':{'name':'IT3170_Hybrid_Preprocessing.ipynb'},
          'accelerator':'GPU','kernelspec':{'display_name':'Python 3','language':'python','name':'python3'}},'cells':cells}
for i,cell in enumerate(cells):cell['id']=f'it3170-{i:02d}'
(ROOT/'IT3170_Hybrid_Preprocessing.ipynb').write_text(json.dumps(notebook,ensure_ascii=False,indent=2),encoding='utf-8')
print(ROOT/'IT3170_Hybrid_Preprocessing.ipynb')
