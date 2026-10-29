"""Build a pinned Qwen3 1.7B CPT bundle from the reviewed 27-course release."""
import argparse
import ast
import json
from pathlib import Path
import shutil
import zipfile
from release_training import sha_file,write_json

ROOT=Path(__file__).resolve().parent
ARCHIVE='bkquiz_cpt_27courses_20261023.zip'
NOTEBOOK='BKQuiz_Qwen3_1_7B_CPT_27courses.ipynb'
PACKAGE='bkquiz_cpt_27courses'


def notebook(zip_hash):
    cells=[]
    def add(kind,source):
        cell={'id':f'cell_{len(cells):02d}','cell_type':kind,'metadata':{},'source':source.splitlines(True)}
        if kind=='code':ast.parse(source);cell.update(execution_count=None,outputs=[])
        cells.append(cell)
    def md(source):add('markdown',source)
    def code(source):add('code',source)
    md('''# BKQuiz: CPT Qwen3 1.7B — 27 học phần
Chọn **Python 3 / GPU**, ưu tiên L4. Dữ liệu và model khác nhau: Qwen3 1.7B là model train; VLM preprocessing đã chạy trước đó.

Đặt `bkquiz_cpt_27courses_20261023.zip` trong **MyDrive/BKQuiz_CPT**. Chạy các cell theo thứ tự.
Đợt này giữ các quyết định VLM đã lưu; dữ liệu chưa từng duyệt được chấp nhận theo chỉ thị chủ dữ liệu. Xem `AUDIT_REPORT.md` trong ZIP để biết giới hạn chất lượng.
Đây là **QLoRA CPT dự đoán token tiếp theo**, 1 epoch, không áp dụng chat template, không phải SFT hỏi–đáp hoặc full-parameter training.''')
    code('''from google.colab import drive
drive.mount('/content/drive')
from pathlib import Path
DRIVE_ROOT = Path('/content/drive/MyDrive/BKQuiz_CPT')
ZIP_PATH = DRIVE_ROOT / 'bkquiz_cpt_27courses_20261023.zip'
assert ZIP_PATH.is_file(), f'Chưa tìm thấy {ZIP_PATH}'
''')
    code(f'''import hashlib, json, zipfile, shutil, os, subprocess, sys
EXPECTED_ZIP_SHA256 = '{zip_hash}'
LOCAL_ZIP = Path('/content/{ARCHIVE}')
shutil.copyfile(ZIP_PATH, LOCAL_ZIP)
def file_sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024*1024), b''): digest.update(block)
    return digest.hexdigest()
assert file_sha(LOCAL_ZIP) == EXPECTED_ZIP_SHA256, 'ZIP/notebook không cùng bản.'
WORK = Path('/content/{PACKAGE}')
with zipfile.ZipFile(LOCAL_ZIP) as archive:
    for entry in archive.infolist():
        assert (Path('/content') / entry.filename).resolve().is_relative_to(WORK.resolve()), 'Đường dẫn ZIP không hợp lệ'
    archive.extractall('/content')
os.chdir(WORK)
bundle = json.loads((WORK / 'bundle_manifest.json').read_text())
for name, digest in bundle['files_sha256'].items():
    assert file_sha(WORK / name) == digest, f'File bị thay đổi: {{name}}'
data = json.loads((WORK / 'data/manifest.json').read_text())
assert data['data_ready_for_owner_authorized_training'] and data['protected_splits_excluded']
print('Mẫu:', data['samples'], '| Học phần:', len(data['courses']), '| Ký tự:', data['characters'])
print('Chấp nhận:', data['acceptance'])
''')
    md('''## Môi trường và GPU
Tạo venv riêng, dùng PyTorch CUDA có sẵn của Colab và khóa các thư viện còn lại. Không cài Ollama.
Chạy kiểm thử dữ liệu trước khi nạp model. Nếu GPU hoặc môi trường lỗi, cell dừng trước train.''')
    code('''VENV = Path('/content/bkquiz_cpt_venv')
if not (VENV / 'bin/python').exists():
    subprocess.run([sys.executable, '-m', 'venv', '--system-site-packages', str(VENV)], check=True)
PYTHON = str(VENV / 'bin/python')
subprocess.run([PYTHON, '-m', 'pip', 'install', '-q', '-r', 'requirements-colab.txt'], check=True)
subprocess.run([PYTHON, '-m', 'unittest', 'discover', '-s', '.', '-p', 'test_data.py', '-v'], check=True)
subprocess.run(['nvidia-smi'], check=True)
subprocess.run([PYTHON, '-c', "import torch,transformers,peft,bitsandbytes; from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig, Trainer, TrainingArguments; from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training; from packaging.version import Version; assert torch.cuda.is_available(), 'Chon GPU runtime'; assert Version(torch.__version__.split('+')[0])>=Version('2.6'); print('GPU:',torch.cuda.get_device_name(0),'torch:',torch.__version__,'transformers:',transformers.__version__)"], check=True)
def launch(script, *arguments):
    subprocess.run([PYTHON, script, *map(str, arguments)], check=True)
''')
    md('''## Tokenize và packing
Tokenizer đúng revision Qwen3; EOS phân cách mẫu. Packing giữ token cuối, mask padding bằng vị trí, labels chưa shift.
Chỉ xuất các split train đã có; không chia ngẫu nhiên trang thành test mới. Không có phép đo tổng quát hóa độc lập trong notebook này.''')
    code('''PREPARED = Path('/content/bkquiz_cpt_prepared')
launch('prepare.py', '--out', PREPARED)
stats = json.loads((PREPARED / 'manifest.json').read_text())
print(json.dumps(stats, indent=2, ensure_ascii=False))
cfg = json.loads((WORK / 'config.json').read_text())
import math
print('Optimizer steps/epoch:', math.ceil(stats['packed_sequences'] / (cfg['batch_size'] * cfg['gradient_accumulation_steps'])))
''')
    md('''## Tên đợt train và tiếp tục checkpoint
Giữ nguyên RUN_NAME khi tiếp tục. Đổi tên khi đổi dữ liệu, cấu hình hoặc làm thí nghiệm mới.
Checkpoint và adapter nằm trên Drive; 25 optimizer steps lưu một checkpoint, giữ hai bản gần nhất.''')
    code('''RUN_NAME = 'cpt_27courses_20261023_001'
RUN_DIR = DRIVE_ROOT / 'runs' / RUN_NAME
RUN_DIR.mkdir(parents=True, exist_ok=True)
identity = {'zip_sha256': EXPECTED_ZIP_SHA256, 'dataset_manifest_sha256': file_sha(WORK / 'data/manifest.json')}
identity_path = RUN_DIR / 'bundle_identity.json'
if identity_path.exists():
    assert json.loads(identity_path.read_text()) == identity, 'RUN_NAME thuộc dữ liệu/code khác; chọn tên mới.'
else:
    identity_path.write_text(json.dumps(identity, indent=2))
RESUME_SMOKE = False
RESUME_TRAIN = False  # True khi tiếp tục cùng đợt bị ngắt.
''')
    md('''## Smoke test: 2 optimizer steps
Kiểm tra loss hữu hạn, gradient, LoRA đổi trọng số và checkpoint. Lượt train chính khởi tạo lại từ model gốc; không dùng adapter smoke.''')
    code('''smoke_args = ['--prepared', PREPARED, '--output', RUN_DIR / 'smoke', '--mode', 'smoke']
if RESUME_SMOKE: smoke_args += ['--resume', 'latest']
if not (RUN_DIR / 'smoke/completed.json').exists(): launch('train.py', *smoke_args)
smoke = json.loads((RUN_DIR / 'smoke/completed.json').read_text())
assert math.isfinite(smoke['metrics']['train_loss'])
assert smoke['lora_changed_vs_initial'] is not False
print(smoke)
''')
    md('''## CPT chính thức: 1 epoch
QLoRA NF4, sequence 1024, batch 1, accumulation 8, LR 2e-5, cosine, warmup 3%, r=8.
Chẩn đoán loss trước/sau dùng cùng tối đa 64 sequence train: chỉ đo mức khớp tập train, không phải validation/test.''')
    code('''assert (RUN_DIR / 'smoke/completed.json').is_file(), 'Smoke test chưa hoàn thành.'
train_args = ['--prepared', PREPARED, '--output', RUN_DIR / 'train', '--mode', 'train']
if RESUME_TRAIN: train_args += ['--resume', 'latest']
if not (RUN_DIR / 'train/completed.json').exists(): launch('train.py', *train_args)
result = json.loads((RUN_DIR / 'train/completed.json').read_text())
print(json.dumps(result, indent=2))
ADAPTER = RUN_DIR / 'train/adapter'
assert (ADAPTER / 'adapter_model.safetensors').is_file()
print('Adapter đã lưu:', ADAPTER)
''')
    md('''## Tùy chọn: quiz trước/sau và model HF đã merge
Probe chỉ là cùng sáu tình huống IT3170 có sẵn, không phải benchmark độc lập. Mặc định tắt để tập trung train.
Merge cần thêm RAM/dung lượng Drive; adapter có thể dùng trực tiếp cùng base, không bắt buộc merge.''')
    code('''RUN_PROBES = False
EXPORT_MERGED = False
if RUN_PROBES:
    if not (RUN_DIR / 'baseline_quiz.json').exists(): launch('probe.py', '--out', RUN_DIR / 'baseline_quiz.json')
    if not (RUN_DIR / 'after_cpt_quiz.json').exists(): launch('probe.py', '--adapter', ADAPTER, '--out', RUN_DIR / 'after_cpt_quiz.json')
if EXPORT_MERGED:
    launch('merge_adapter.py', '--adapter', ADAPTER, '--out', RUN_DIR / 'merged_hf_fp16')
''')
    md('''Khi Colab bị ngắt: kết nối lại GPU, chạy lại mount/extract/install/prepare, giữ RUN_NAME và đặt RESUME_TRAIN=True.
Trainer chỉ nhận checkpoint đầy đủ, cùng data/config/code/thư viện. Adapter smoke không phải kết quả cuối.
Chạy xong thì ngắt runtime. Notebook không tự đẩy model lên Hugging Face và không sửa dữ liệu preprocessing hay lịch sử duyệt.''')
    return {'nbformat':4,'nbformat_minor':5,'metadata':{'colab':{'name':NOTEBOOK,'gpuType':'L4'},
        'kernelspec':{'name':'python3','display_name':'Python 3'},'language_info':{'name':'python'},'accelerator':'GPU'},'cells':cells}


def build(root):
    root=Path(root);package=root/'colab'
    if not (package/'data/manifest.json').is_file():raise ValueError('Finalize the reviewed dataset first')
    names=['data_utils.py','prepare.py','train.py','probe.py','merge_adapter.py','requirements-colab.txt','config.json','test_data.py']
    for name in names:shutil.copyfile(ROOT/'training_runtime'/name,package/name)
    (package/'probes').mkdir(exist_ok=True)
    for name in ['prompts.json','gold.json','rubric.json']:
        shutil.copyfile(ROOT.parent.parent/'Qwen_cpt_version/colab_qwen3_1_7b/probes'/name,package/'probes'/name)
        names.append('probes/'+name)
    names+=['data/train.jsonl','data/sources.jsonl','data/manifest.json']
    for name in ['AUDIT_REPORT.md','HUONG_DAN_COLAB.md','policy.json','audit/findings.json']:
        target=package/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(root/name,target);names.append(name)
    if (root/'LOCAL_VALIDATION.json').exists():
        shutil.copyfile(root/'LOCAL_VALIDATION.json',package/'LOCAL_VALIDATION.json');names.append('LOCAL_VALIDATION.json')
    for name in names:
        if name.endswith('.py'):ast.parse((package/name).read_text(encoding='utf-8'))
    hashes={name:sha_file(package/name) for name in names}
    write_json(package/'bundle_manifest.json',{'files_sha256':hashes,'upstream_training_runtime':'Qwen_cpt_version/colab_qwen3_1_7b; adapted streaming preparation and bounded diagnostic',
        'model_id':'Qwen/Qwen3-1.7B','actual_gpu_training_executed_locally':False})
    names.append('bundle_manifest.json')
    archive=root/ARCHIVE
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for name in names:z.write(package/name,PACKAGE+'/'+name)
    digest=sha_file(archive);write_json(root/NOTEBOOK,notebook(digest))
    info={'archive':ARCHIVE,'notebook':NOTEBOOK,'sha256':digest,'bytes':archive.stat().st_size,
        'files':{name:sha_file(package/name) for name in names},'notebook_sha256':sha_file(root/NOTEBOOK)}
    write_json(root/'bundle_info.json',info)
    return info


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--release',type=Path,required=True)
    args=parser.parse_args();print(json.dumps(build(args.release),ensure_ascii=False,indent=2))
