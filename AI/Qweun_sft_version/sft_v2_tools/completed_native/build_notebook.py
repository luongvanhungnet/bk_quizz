"""A two-file, ready-to-run Colab SFT handoff; no teacher preprocessing."""
from __future__ import annotations
import argparse
import ast
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"pedagogy_tools"))
from pedagogy_core import atomic_json,file_sha

DRIVE_FOLDER="BKQuiz_CPT/SFT_COMPLETED_NATIVE_20261025"
NOTEBOOK="BKQuiz_Qwen3_1_7B_Completed_SFT.ipynb"


def notebook(bundle):
    cells=[]
    def add(kind,text):
        cell={"id":"sft-"+str(len(cells)),"cell_type":kind,"metadata":{},"source":text.strip().splitlines(keepends=True)}
        if kind=="code":ast.parse(text);cell.update(execution_count=None,outputs=[])
        cells.append(cell)
    md=lambda text:add("markdown",text)
    code=lambda text:add("code",text)
    md("""# BKQuiz · SFT trực tiếp Qwen3-1.7B từ các trang đã hoàn tất
**361 câu /181trang; train281, validation40, test40.** Loại toàn bộ trang còn cần LLM/VLM/duyệt thủ công.
Không chạy teacher7B, OCR, VLM hoặc sinh thêm lời giải. Chọn **Runtime → Change runtime type → T4 GPU**.

ZIP đã chứa dataset tokenized, tokenizer và adapter CPT27 đúng hash. Chỉ base Qwen3-1.7B được tải từ HuggingFace
theo revision cố định. SFT train tiếp chính adapter CPT27,1epoch; output là adapter hoàn chỉnh CPT+SFT.
T4 dùng FP16, BF16 chỉ dùng nếu GPU hỗ trợ native. Người dùng tự chạy GPU.

Dữ liệu huấn luyện biên soạn Q&A nguồn thành quiz JSON, có nhiều lời giải ngắn dẫn đáp án nguồn.
Chưa phải bộ dạy đọc lý thuyết rồi tự tạo câu mới và lời giải sâu. Đáp án nguồn không phải expert gold.
""")
    code("""from google.colab import drive
drive.mount('/content/drive')
from pathlib import Path
""")
    code("import hashlib, json, os, sys, subprocess, shutil, zipfile, stat\nfrom pathlib import PurePosixPath\n"
         +"DRIVE_ROOT=Path('/content/drive/MyDrive/"+DRIVE_FOLDER+"')\n"
         +"ZIP_PATH=DRIVE_ROOT/'bkquiz_completed_sft_20261025.zip'\nEXPECTED_ZIP_SHA256="+repr(bundle["sha256"])+"\n"
         +"RUN_NAME='sft_completed_native_20261025_001'\nRESUME_TRAIN=True\nRUN_SMOKE=False  # tùy chọn kiểm tra2steps; không dùng adapter smoke làm kết quả cuối\nEVALUATE_TEST=False  # test được giữ riêng; chỉ bật khi cần đánh giá cuối\n"
         +"assert ZIP_PATH.is_file(), f'Chưa tìm thấy {ZIP_PATH}'\n")
    code("""def file_sha(path):
    with Path(path).open('rb') as stream: return hashlib.file_digest(stream,'sha256').hexdigest()
LOCAL_ZIP=Path('/content/bkquiz_completed_sft_20261025.zip')
shutil.copyfile(ZIP_PATH,LOCAL_ZIP)
assert file_sha(LOCAL_ZIP)==EXPECTED_ZIP_SHA256, 'ZIP/notebook không cùng bản; tải lại đúng hai tệp'
WORK=Path('/content/bkquiz_completed_sft_'+EXPECTED_ZIP_SHA256[:12])
WORK.mkdir(exist_ok=True)
with zipfile.ZipFile(LOCAL_ZIP) as archive:
    infos=archive.infolist(); names=[entry.filename for entry in infos]
    assert len(names)==len(set(names)) and len(names)<250, 'ZIP trùng hoặc quá nhiều file'
    assert sum(i.file_size for i in infos)<512*1024*1024, 'ZIP vượt ngân sách'
    for entry in infos:
        name=entry.filename; rel=PurePosixPath(name)
        assert not rel.is_absolute() and '..' not in rel.parts and '\\\\' not in name and ':' not in name
        assert stat.S_IFMT(entry.external_attr>>16)!=stat.S_IFLNK and entry.file_size<128*1024*1024
        assert (WORK/name).resolve().is_relative_to(WORK.resolve())
    manifest=json.loads(archive.read('manifest.json'))
    assert set(names)=={'manifest.json',*manifest['files_sha256']}, 'File ZIP không khớp registry'
    archive.extractall(WORK)
for name,wanted in manifest['files_sha256'].items():
    assert file_sha(WORK/name)==wanted, 'File bị thay đổi: '+name
assert manifest['schema']=='bkquiz-completed-sft-v1'
assert manifest['source_policy']=='completed_native_pages_only' and manifest['no_pending_llm_vlm_manual_pages']
print('Đã kiểm tra ZIP và mọi file. Split:',manifest['counts'])
print('CPT adapter có sẵn trong:',WORK/'assets/cpt_adapter')
""")
    md("""## Môi trường và kiểm tra dữ liệu
Dùng CUDA torch có sẵn trong Colab và venv riêng. Các thư viện còn lại được khóa phiên bản.
Kiểm tra mọi hash, các trang bị loại, split và mask assistant trước khi tải trọng số model.
""")
    bootstrap=Path(__file__).with_name('colab_bootstrap.py').read_text(encoding='utf-8')
    code(bootstrap+"\n"+"""VENV=Path('/content/bkquiz_completed_sft_venv')
PYTHON=ensure_colab_venv(VENV)
RUNTIME=WORK/'runtime'
# Teacher không dùng trong notebook này; tắt optional vision/audio imports
# để tránh ABI của thư viện hệ thống không liên quan với torch Colab.
(RUNTIME/'sitecustomize.py').write_text("import importlib.util\\n_original=importlib.util.find_spec\\ndef _find(name,*args,**kwargs):\\n    if name.split('.')[0] in {'torchvision','torchaudio','librosa'}:return None\\n    return _original(name,*args,**kwargs)\\nimportlib.util.find_spec=_find\\n",encoding='utf-8')
ENV=dict(os.environ,PYTHONPATH=str(RUNTIME),TOKENIZERS_PARALLELISM='false')
run_logged([str(PYTHON),'-m','pip','install','-r',str(RUNTIME/'requirements.txt')],env=ENV,log_path=WORK/'dependency_install.log')
subprocess.run([str(PYTHON),'-c','import torch; assert torch.cuda.is_available(), "Select GPU runtime"; print(torch.__version__,torch.cuda.get_device_properties(0))'],env=ENV,check=True)
def launch(*args):
    subprocess.run([str(PYTHON),'-u',str(RUNTIME/'train_sft.py'),*map(str,args)],env=ENV,cwd=str(RUNTIME),check=True)
launch('--data',WORK,'--mode','preflight')
""")
    md("""## Huấn luyện
Mặc định1epoch, LR2e-5, batch1, accumulation8, khoảng36optimizersteps.
Lưu checkpoint mỗi5steps, validation để chọn checkpoint; không tự dùng test.
Giữ RUN_NAME và RESUME_TRAIN=True để tiếp tục cùng dữ liệu, code và thư viện.
Khi đổi dữ liệu/cấu hình/thư viện, chọn RUN_NAME mới. Thời gian train thực tế cần đo trên GPU của bạn.
""")
    code("""RUN_DIR=DRIVE_ROOT/'runs'/RUN_NAME
RUN_DIR.mkdir(parents=True,exist_ok=True)
if RUN_SMOKE:
    SMOKE=RUN_DIR/'smoke'
    args=['--data',WORK,'--output',SMOKE,'--mode','smoke']
    if RESUME_TRAIN and (SMOKE/'run_identity.json').is_file(): args+=['--resume','latest']
    launch(*args)
TRAIN=RUN_DIR/'train'
args=['--data',WORK,'--output',TRAIN,'--mode','train']
if RESUME_TRAIN and (TRAIN/'run_identity.json').is_file(): args+=['--resume','latest']
if EVALUATE_TEST: args+=['--evaluate-test']
launch(*args)
""")
    code("""from google.colab import files
REPORT=TRAIN/'completed.json'
assert REPORT.is_file(), 'Chưa train xong; giữ RUN_NAME để resume checkpoint'
result=json.loads(REPORT.read_text())
assert result['status']=='completed' and result['mode']=='train' and result['adapter_weights_changed']
print(json.dumps(result,ensure_ascii=False,indent=2))
OUTPUT_ZIP=TRAIN/result['bundle_name']
bundle_info=json.loads((TRAIN/'RESULT_BUNDLE.json').read_text())
assert file_sha(OUTPUT_ZIP)==bundle_info['sha256'], 'ZIP kết quả không khớp hash'
print('Adapter CPT+SFT:',TRAIN/'adapter')
print('Kết quả luôn lưu trên Drive:',OUTPUT_ZIP)
files.download(str(OUTPUT_ZIP))
""")
    md("""## Dùng kết quả
`sft_completed_adapter.zip` chứa adapter đã tiếp tục từ CPT27, tokenizer, metrics và nguồn gốc.
Nạp adapter mới một lần lên đúng base Qwen3-1.7B; không chồng thêm adapter CPT cũ.
Đây là adapter PEFT, chưa phải full weights/GGUF. Chưa tự thay model đang phục vụ.
Nếu Colab bị ngắt, kết nối GPU rồi Run all lại; dùng checkpoint đầy đủ cùng RUN_NAME.
Nếu bị ngắt trước checkpoint đầu tiên, chọn RUN_NAME mới vì chưa có trạng thái optimizer để resume.
""")
    return {"nbformat":4,"nbformat_minor":5,"metadata":{"colab":{"name":NOTEBOOK,"gpuType":"T4"},
            "kernelspec":{"display_name":"Python3","language":"python","name":"python3"},"accelerator":"GPU"},"cells":cells}


def build(release):
    release=Path(release);bundle=json.loads((release/"BUNDLE_INFO.json").read_text(encoding="utf-8"))
    if file_sha(bundle["archive"])!=bundle["sha256"]:raise ValueError("Frozen training ZIP changed")
    nb=notebook(bundle)
    # Validate both notebook source and literal child Python passed through -c.
    for cell in nb["cells"]:
        if cell["cell_type"]!="code":continue
        tree=ast.parse("".join(cell["source"]))
        for node in ast.walk(tree):
            if isinstance(node,ast.List):
                for i,value in enumerate(node.elts[:-1]):
                    if isinstance(value,ast.Constant) and value.value=="-c" and isinstance(node.elts[i+1],ast.Constant):
                        ast.parse(node.elts[i+1].value)
    path=release/NOTEBOOK;atomic_json(path,nb)
    result={"notebook":str(path.resolve()),"notebook_sha256":file_sha(path),"archive":bundle["archive"],"archive_sha256":bundle["sha256"],"drive_folder":DRIVE_FOLDER,
            "training_executed":False,"counts":bundle["counts"]}
    atomic_json(release/"COLAB_HANDOFF.json",result);return result


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--release",type=Path,required=True)
    print(json.dumps(build(p.parse_args().release),ensure_ascii=False,indent=2))
