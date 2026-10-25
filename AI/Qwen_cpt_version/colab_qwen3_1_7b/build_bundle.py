"""Build a small, allowlisted Colab upload from existing accepted course data."""
import hashlib
import json
import shutil
import unicodedata
import zipfile
from pathlib import Path
from data_utils import load,save,sha,read_jsonl,write_jsonl

ROOT=Path(__file__).resolve().parent


def notebook(zip_hash):
    cells=[]
    def md(text):cells.append({'id':f'cell_{len(cells):02d}','cell_type':'markdown','metadata':{},'source':text.splitlines(True)})
    def code(text):cells.append({'id':f'cell_{len(cells):02d}','cell_type':'code','execution_count':None,'metadata':{},'outputs':[],'source':text.splitlines(True)})
    md('''# CPT Qwen3 1.7B — Thuật toán ứng dụng (IT3170)
QLoRA, causal next-token loss trên text đã kiểm định. Không dùng chat template trong train.

Chọn **Runtime → Change runtime type → Python 3 → GPU**. T4 là cấu hình khởi đầu; GPU thực tế tùy Colab cấp.
Upload `qwen3_it3170_colab.zip` vào **MyDrive/BKQuiz_CPT/** trước khi chạy. Notebook không tự upload dữ liệu hay model lên Hugging Face.
Chạy từng cell theo thứ tự. Chi tiết: `HUONG_DAN_COLAB.md` trong gói.''')
    code('''from google.colab import drive
drive.mount('/content/drive')
from pathlib import Path
DRIVE_ROOT = Path('/content/drive/MyDrive/BKQuiz_CPT')
ZIP_PATH = DRIVE_ROOT / 'qwen3_it3170_colab.zip'
assert ZIP_PATH.is_file(), f'Upload gói ZIP vào {ZIP_PATH}'
''')
    code(f'''import hashlib, zipfile, shutil, os
EXPECTED_ZIP_SHA256 = '{zip_hash}'
LOCAL_ZIP = Path('/content/qwen3_it3170_colab.zip')
shutil.copyfile(ZIP_PATH, LOCAL_ZIP)
assert hashlib.sha256(LOCAL_ZIP.read_bytes()).hexdigest() == EXPECTED_ZIP_SHA256, 'ZIP khác bản notebook: dùng đúng cặp ZIP/notebook được tạo cùng lần.'
WORK = Path('/content/qwen3_it3170_colab')
with zipfile.ZipFile(LOCAL_ZIP) as z:
    for info in z.infolist():
        target = (Path('/content') / info.filename).resolve()
        assert target.is_relative_to(WORK.resolve()), 'Đường dẫn ZIP không hợp lệ'
    z.extractall('/content')
os.chdir(WORK)
print('Workspace:', WORK)
''')
    code('''import subprocess, sys
subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', '-r', 'requirements-colab.txt'], check=True)
subprocess.run(['nvidia-smi'], check=True)
subprocess.run([sys.executable, '-c', "import torch,transformers,peft,bitsandbytes; assert torch.cuda.is_available(); print('torch',torch.__version__,'transformers',transformers.__version__,'GPU',torch.cuda.get_device_name(0))"], check=True)
''')
    md('''## Kiểm tra dữ liệu và tokenize lại
Chỉ 264 mẫu đã chấp nhận; không dùng JSONL token Qwen2.5 cũ. In số token Qwen3 thực tế, EOS và số sequence sau packing.
Toàn bộ dữ liệu thuộc train; không có held-out validation/test.''')
    code('''PREPARED = Path('/content/qwen3_it3170_prepared')
subprocess.run([sys.executable, 'prepare.py', '--out', str(PREPARED)], check=True)
import json
stats = json.loads((PREPARED / 'manifest.json').read_text())
print(json.dumps(stats, indent=2, ensure_ascii=False))
''')
    md('''## Đặt tên đợt chạy và resume
Đặt tên mới cho mỗi thí nghiệm. Giữ nguyên tên để resume. Checkpoint, optimizer và adapter lưu trên Drive.
Nếu chưa có checkpoint hoàn chỉnh sau lỗi, dùng tên mới. Không đổi config, dữ liệu hay phiên bản thư viện khi resume.''')
    code('''RUN_NAME = 'it3170_qwen3_1_7b_cpt_001'
RUN_DIR = DRIVE_ROOT / 'runs' / RUN_NAME
RUN_DIR.mkdir(parents=True, exist_ok=True)
RESUME_SMOKE = False  # True chỉ khi tiếp tục smoke đã bị ngắt.
RESUME_TRAIN = False  # True khi tiếp tục lượt train đã bị ngắt.
def launch(script, *arguments):
    subprocess.run([sys.executable, script, *map(str, arguments)], check=True)
''')
    md('''## Smoke test: 2 optimizer steps
Chạy thử GPU, loss, backward và lưu checkpoint. Adapter smoke nằm riêng; lượt CPT bên dưới khởi tạo lại từ checkpoint gốc.''')
    code('''smoke_args = ['--prepared', PREPARED, '--output', RUN_DIR / 'smoke', '--mode', 'smoke']
if RESUME_SMOKE: smoke_args += ['--resume', 'latest']
if (RUN_DIR / 'smoke/completed.json').exists():
    print('Smoke đã hoàn thành; giữ nguyên kết quả.')
else:
    launch('train.py', *smoke_args)
''')
    md('''## Baseline quiz trước CPT
Xuất cùng sáu prompt đã dùng trước đây. Đây là task probe theo nguồn; chưa phải held-out test. Không dùng file này để train.
Baseline và adapter đều suy luận bằng Hugging Face NF4, nên so cặp này với nhau; không so trực tiếp tốc độ/điểm với Ollama Q4_K_M.''')
    code('''if not (RUN_DIR / 'baseline_quiz.json').exists():
    launch('probe.py', '--out', RUN_DIR / 'baseline_quiz.json')
else:
    print('Giữ baseline đã có.')
''')
    md('''## CPT chính thức: 1 epoch trên tập đã làm sạch
Mặc định LR=2e-5, sequence=1024, batch=1, accumulation=4, LoRA r=8. Tập nhỏ nên số optimizer steps ít.
Đây là CPT bằng adapter QLoRA, không cập nhật toàn bộ trọng số nền. Không tự tăng hàng chục epoch chỉ để giảm training loss.''')
    code('''train_args = ['--prepared', PREPARED, '--output', RUN_DIR / 'train', '--mode', 'train']
if RESUME_TRAIN: train_args += ['--resume', 'latest']
if (RUN_DIR / 'train/completed.json').exists():
    print('Lượt train đã hoàn thành; chọn RUN_NAME mới nếu làm thí nghiệm khác.')
else:
    launch('train.py', *train_args)
print((RUN_DIR / 'train/completed.json').read_text())
''')
    md('''## Sau CPT: xuất quiz để chấm và xem log
So từng câu với baseline/gold: key, một lựa chọn đúng, đủ dữ kiện, lời giải, nguồn, JSON. JSON hợp lệ không tự chứng minh kiến thức đúng.
`train_diagnostic_loss` đo trên chính tập train; không phải validation loss.''')
    code('''ADAPTER = RUN_DIR / 'train/adapter'
if not (RUN_DIR / 'after_cpt_quiz.json').exists():
    launch('probe.py', '--adapter', ADAPTER, '--out', RUN_DIR / 'after_cpt_quiz.json')
for name in ['train_results.json', 'train_diagnostic_results.json']:
    print(name, (RUN_DIR / 'train' / name).read_text())
before = json.loads((RUN_DIR / 'baseline_quiz.json').read_text())
after = json.loads((RUN_DIR / 'after_cpt_quiz.json').read_text())
assert all(before[k] == after[k] for k in ['model_id', 'revision', 'config', 'prompts_sha256', 'quantization', 'compute_dtype']), 'Baseline/adapter khác cấu hình hoặc dtype: cần tạo lại cặp probe khớp nhau.'
for a, b in zip(before['results'], after['results']):
    print(a['case_id'], 'JSON trước/sau:', a['strict_json_object'], b['strict_json_object'])
print('Adapter và toàn bộ checkpoint:', RUN_DIR)
''')
    md('''## Tùy chọn: xuất model Hugging Face độc lập
Chỉ chạy khi cần, tốn thêm RAM và khoảng vài GB Drive. Merge vào model FP16 mới tải từ revision gốc; không merge trực tiếp vào trọng số 4-bit.
Đầu ra là model HF, chưa phải GGUF cho Ollama. Có thể dùng adapter cùng base mà không cần merge.''')
    code('''EXPORT_MERGED = False
if EXPORT_MERGED:
    launch('merge_adapter.py', '--adapter', ADAPTER, '--out', RUN_DIR / 'merged_hf_fp16')
''')
    md('''Khi Colab bị ngắt: kết nối GPU mới, chạy lại các cell mount/extract/install/prepare, giữ RUN_NAME, đặt RESUME_TRAIN=True (hoặc RESUME_SMOKE=True) rồi tiếp tục. Script chọn checkpoint hoàn chỉnh mới nhất.

Chưa có bằng chứng model tốt hơn cho đến khi chấm nội dung trước/sau và kiểm tra trên tài liệu độc lập. Sau khi xong, ngắt runtime để dừng tiêu thụ compute units.''')
    return {'nbformat':4,'nbformat_minor':5,'metadata':{'colab':{'name':'Qwen3_1_7B_IT3170_CPT.ipynb'},
             'kernelspec':{'name':'python3','display_name':'Python 3'},'language_info':{'name':'python'},'accelerator':'GPU'},'cells':cells}


def main():
    source=ROOT.parent/'data_preprocessing/outputs/it3170'
    validation=load(source/'validation.json');quality=load(source/'quality_report.json')
    if not validation['passed']:raise ValueError('Source dataset has not passed validation')
    rows=read_jsonl(source/'cpt/train.jsonl');metadata=read_jsonl(source/'cpt/train.metadata.jsonl')
    if len(rows)!=len(metadata) or len(rows)!=validation['training_samples']:raise ValueError('Source counts changed')
    if sum(len(r['text']) for r in rows)!=quality['cpt_characters']:raise ValueError('Source text statistics changed')
    projected=[]
    for row,meta in zip(rows,metadata):
        if row['text']!=meta['text'] or meta['quality']['status']!='accepted' or meta['split']!='train':
            raise ValueError('Unaccepted or mismatched source record')
        if unicodedata.normalize('NFC',row['text'])!=row['text']:raise ValueError('Expected NFC source text')
        if meta['source']['document_sha256']!=quality['source_sha256']:raise ValueError('Source PDF identity mismatch')
        original=meta['source']['original']
        projected.append({'id':meta['id'],'page':meta['page'],'document_sha256':quality['source_sha256'],
                          'original_source_id':original['source_id'],'original_page':original['source_page'],
                          'text_sha256':hashlib.sha256(row['text'].encode()).hexdigest(),'quality_status':'accepted'})
    write_jsonl(ROOT/'data/train.jsonl',rows);write_jsonl(ROOT/'data/sources.jsonl',projected)
    save(ROOT/'data/manifest.json',{'course':'Thuật toán ứng dụng','course_code':'IT3170',
         'samples':len(rows),'characters':quality['cpt_characters'],'source_pdf_sha256':quality['source_sha256'],
         'source_pages':quality['pages_total'],'needs_review_pages_excluded':quality['status_counts']['needs_review'],
         'files_sha256':{f:sha(ROOT/f) for f in ['data/train.jsonl','data/sources.jsonl']},
         'upstream_validation_sha256':sha(source/'validation.json'),
         'split':'document_group_train_only','validation_samples':0,'test_samples':0,
         'excluded':['raw PDF/images','review queue','Qwen2.5 packed token IDs','generated quiz answers']})
    probes=ROOT.parents[1]/'qwen_quiz_evaluation/runs/2026-10-17'
    (ROOT/'probes').mkdir(exist_ok=True)
    for name in ['prompts.json','gold.json','rubric.json']:
        shutil.copyfile(probes/name,ROOT/'probes'/name)
    names=['config.json','requirements-colab.txt','data_utils.py','prepare.py','train.py','probe.py','merge_adapter.py','HUONG_DAN_COLAB.md',
           'data/train.jsonl','data/sources.jsonl','data/manifest.json','probes/prompts.json','probes/gold.json','probes/rubric.json']
    archive=ROOT/'qwen3_it3170_colab.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for name in names:z.write(ROOT/name,'qwen3_it3170_colab/'+name)
    save(ROOT/'Qwen3_1_7B_IT3170_CPT.ipynb',notebook(sha(archive)))
    save(ROOT/'bundle_info.json',{'archive':archive.name,'sha256':sha(archive),'bytes':archive.stat().st_size,
         'samples':len(rows),'files':{name:sha(ROOT/name) for name in names}})
    print('Built:',archive,'samples:',len(rows),'bytes:',archive.stat().st_size)


if __name__=='__main__':main()
