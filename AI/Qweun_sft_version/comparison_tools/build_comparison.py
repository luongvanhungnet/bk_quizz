"""Build an immutable four-way Colab handoff without changing the SFT release."""
from __future__ import annotations
import ast
from collections import defaultdict, deque
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

HERE = Path(__file__).resolve().parent
SFT = HERE.parent
RELEASE = SFT / "datasets/sft_completed_native_20261025/payload"
OUTPUT = SFT / "model_comparisons/four_way_20261025"
DRIVE_FOLDER = "BKQuiz_CPT/MODEL_COMPARISON_4WAYS_20261025"
NOTEBOOK = "BKQuiz_Compare_Base_CPT_SFT_CPTSFT.ipynb"


def sha(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)+"\n", encoding="utf-8")


def lines(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()]


def sft_only_source(source):
    source = source[source.index("from __future__"):]
    source = '"""Fresh LoRA SFT from the pinned base. CPT tensors are never loaded."""\n' + source
    def replace(old, new):
        nonlocal source
        if source.count(old) != 1:
            raise ValueError("Frozen trainer template changed: " + old[:80])
        source = source.replace(old, new)
    replace('from peft import PeftModel,prepare_model_for_kbit_training,get_peft_model_state_dict',
            'from peft import LoraConfig,get_peft_model,prepare_model_for_kbit_training,get_peft_model_state_dict')
    replace('from safetensors.torch import load_file', '# Starting LoRA is fresh; no CPT weight loader is imported.')
    start = source.index('    adapter=verify_adapter(args.data)')
    end = source.index('    def adapter_digest():', start)
    source = source[:start] + '''    lora_cfg=LoraConfig(r=8,lora_alpha=16,lora_dropout=.05,bias="none",task_type="CAUSAL_LM",
        target_modules=["down_proj","gate_proj","v_proj","o_proj","k_proj","up_proj","q_proj"],init_lora_weights=True)
    model=get_peft_model(model,lora_cfg)
    model.print_trainable_parameters()
    trainables=[(name,p) for name,p in model.named_parameters() if p.requires_grad]
    if not trainables or any("lora_" not in name for name,p in trainables):raise ValueError("Only fresh LoRA may be trainable")
    if sum(p.numel() for _,p in trainables)!=8716288:raise ValueError("LoRA architecture differs from CPT+SFT")
    initial=get_peft_model_state_dict(model)
    b_weights=[p for name,p in initial.items() if "lora_B" in name]
    if not b_weights or any(torch.count_nonzero(p).item()!=0 for p in b_weights):raise ValueError("Fresh LoRA B must start at zero")
    del initial,b_weights;gc.collect()
''' + source[end:]
    replace('"cpt_adapter_sha256":CPT_HASHES,"continuation":"continue_same_cpt27_adapter_trainable",',
            '"cpt_adapter_sha256":None,"continuation":"fresh_lora_on_base","variant":"sft","cpt_weights_loaded":False,')
    replace('cpt_adapter="verified bundled CPT27"', 'cpt_adapter="not loaded; fresh SFT-only LoRA"')
    replace('print_json("verified_cpt_start",', 'print_json("verified_fresh_base_start",')
    replace('raise RuntimeError("No CPT adapter weight changed during SFT")', 'raise RuntimeError("No fresh SFT adapter weight changed")')
    start = source.index('    save(output/"MODEL_PROVENANCE.json",')
    end = source.index('    bundle_name=', start)
    source = source[:start] + '''    save(output/"MODEL_PROVENANCE.json",{"variant":"sft","base_model":MODEL_ID,"base_revision":MODEL_REVISION,
         "cpt_weights_loaded":False,"continuation_method":"fresh_lora_on_base",
         "output_adapter_contains":"SFT-only update; load once on pinned base",
         "initial_lora_tensor_sha256":initial_digest,"final_adapter_tensor_sha256":final_digest,
         "dataset_manifest_sha256":report["dataset_manifest_sha256"],"test_used_for_training_or_selection":False})
    (output/"LOAD_ADAPTER.md").write_text("SFT-only fresh LoRA. Load once on pinned Qwen3-1.7B base; no CPT weights were loaded.\\n",encoding="utf-8")
''' + source[end:]
    replace('else"sft_completed_adapter.zip"', 'else"sft_only_adapter.zip"')
    ast.parse(source)
    if "PeftModel.from_pretrained" in source or "load_file(" in source:
        raise ValueError("SFT-only trainer must not load CPT weights")
    return source


def build_tasks():
    metas = lines(RELEASE/"test.metadata.jsonl")
    chats = lines(RELEASE/"test.messages.jsonl")
    originals = {q["id"]: q for q in lines(RELEASE/"source_questions.jsonl")}
    tasks = []
    for meta, chat in zip(metas, chats):
        q = originals[meta["id"]]
        labels = [chr(65+i) for i in range(len(q["options"]))]
        gold = [labels[i] for i, o in enumerate(q["options"]) if o["correct"] is True]
        if not gold or len(gold) == len(labels):
            raise ValueError("Invalid source answer set")
        text = "Học phần: " + meta["course"] + "\n" + q["prompt"] + "\n" + "\n".join(
            label + ". " + option["text"] for label, option in zip(labels, q["options"]))
        closed = [{"role": "system", "content": 'Trả lời câu hỏi trắc nghiệm. Chọn tất cả đáp án đúng. Chỉ trả JSON {"correct_labels":["A"]}, dùng nhãn lựa chọn trong câu hỏi. Không giải thích.'},
                  {"role": "user", "content": text}]
        tasks.append({"id": meta["id"], "course": meta["course"], "gold_labels": gold, "valid_labels": labels,
                      "closed_book_messages": closed, "grounded_messages": chat["messages"][:-1],
                      "reference_question": json.loads(chat["messages"][-1]["content"])["questions"][0],
                      "source_key_expert_verified": False})
    # Fixed round robin across courses, within-course SHA order; never model-score selection.
    groups = defaultdict(list)
    for task in tasks:
        groups[task["course"]].append(task["id"])
    queues = [deque(sorted(ids, key=lambda x: hashlib.sha256(x.encode()).hexdigest())) for _, ids in sorted(groups.items())]
    order = []
    while any(queues):
        for queue in queues:
            if queue:
                order.append(queue.popleft())
    return tasks, order


def make_notebook(bundle_sha):
    cells = []
    def add(kind, text):
        if kind == "code":
            ast.parse(text)
        cell = {"cell_type": kind, "id": "compare-"+str(len(cells)), "metadata": {}, "source": text.strip().splitlines(keepends=True)}
        if kind == "code":
            cell.update(execution_count=None, outputs=[])
        cells.append(cell)
    md = lambda text: add("markdown", text)
    code = lambda text: add("code", text)
    md('''# BKQuiz: Base · CPT · SFT · CPT+SFT
Chọn **Runtime → Change runtime type → T4 GPU**, rồi **Run all**.

Notebook tạo nhánh **SFT-only từ base** (281 train,40 validation, cùng1epoch/cấu hình)
vì ZIP bạn gửi là **CPT+SFT**. Không train lại CPT hoặc CPT+SFT. Mỗi adapter nạp riêng lên cùng base Qwen3-1.7B pinned revision.

Đánh giá cả4 trên cùng40 test: assistant NLL/PPL; chọn đáp án đóng sách; sinh quiz JSON theo ngữ cảnh.
Mặc định sinh quiz trên12 câu phủ các học phần, có thể đổi thành40 trước lần chạy đầu.
Test không dùng chọn checkpoint. Một seed và40 test chỉ là đối chứng nhỏ, có tài liệu cùng nguồn với train.
Đáp án nguồn chưa phải expert gold; JSON hợp lệ chưa chứng minh lời giải sâu. Không dùng teacher/VLM.

Kết quả lưu Drive, cache từng câu để tiếp tục. Không có cam kết hoàn thành dưới1h; thời gian sinh2048tokens/câu phụ thuộc GPU và đầu ra.
''')
    code("from google.colab import drive\ndrive.mount('/content/drive')\nfrom pathlib import Path\n")
    code("import os, sys, json, hashlib, shutil, zipfile, stat\nfrom pathlib import PurePosixPath\n"
         + f"DRIVE_ROOT=Path('/content/drive/MyDrive/{DRIVE_FOLDER}')\n"
         + f"EXPECTED_ZIP_SHA256={bundle_sha!r}\n"
         + "ZIP_PATH=DRIVE_ROOT/'bkquiz_four_way_input.zip'\n"
         + "RUN_NAME='four_way_20261025_001'\nGENERATION_COUNT=12  # 12 hoặc40; thay RUN_NAME nếu đổi sau khi đã chạy\n"
         + "assert GENERATION_COUNT in (12,40)\nassert ZIP_PATH.is_file(), str(ZIP_PATH)\n")
    code('''def file_sha(path):
    with Path(path).open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()
LOCAL_ZIP=Path('/content/bkquiz_four_way_input.zip')
shutil.copyfile(ZIP_PATH,LOCAL_ZIP)
assert file_sha(LOCAL_ZIP)==EXPECTED_ZIP_SHA256, 'ZIP/notebook không cùng bản'
WORK=Path('/content/bkquiz_four_way_'+EXPECTED_ZIP_SHA256[:12])
WORK.mkdir(exist_ok=True)
with zipfile.ZipFile(LOCAL_ZIP) as z:
    infos=z.infolist(); names=[i.filename for i in infos]
    assert len(names)==len(set(names)) and len(names)<300
    assert sum(i.file_size for i in infos)<512*1024*1024
    for i in infos:
        rel=PurePosixPath(i.filename)
        assert not rel.is_absolute() and '..' not in rel.parts and ':' not in i.filename and chr(92) not in i.filename
        assert stat.S_IFMT(i.external_attr>>16)!=stat.S_IFLNK and i.file_size<128*1024*1024
        assert (WORK/i.filename).resolve().is_relative_to(WORK.resolve())
    m=json.loads(z.read('comparison_manifest.json'))
    assert set(names)=={'comparison_manifest.json',*m['files_sha256']}
    z.extractall(WORK)
for name,wanted in m['files_sha256'].items():
    assert file_sha(WORK/name)==wanted, name
RUNTIME=WORK/'runtime'
RUN=DRIVE_ROOT/'runs'/RUN_NAME
RUN.mkdir(parents=True,exist_ok=True)
''')
    md("## Môi trường\nDùng bootstrap pip đã sửa, giữ CUDA torch của Colab. Log cài đặt được lưu đầy đủ.")
    bootstrap = (SFT/"sft_v2_tools/completed_native/colab_bootstrap.py").read_text(encoding="utf-8")
    code(bootstrap + '\n' + '''VENV=Path('/content/bkquiz_four_way_venv')
PYTHON=ensure_colab_venv(VENV)
(RUNTIME/'sitecustomize.py').write_text("import importlib.util\\n_original=importlib.util.find_spec\\ndef _find(name,*args,**kwargs):\\n    if name.split('.')[0] in {'torchvision','torchaudio','librosa'}:return None\\n    return _original(name,*args,**kwargs)\\nimportlib.util.find_spec=_find\\n",encoding='utf-8')
ENV=dict(os.environ,PYTHONPATH=str(RUNTIME),TOKENIZERS_PARALLELISM='false')
run_logged([PYTHON,'-m','pip','install','-r',RUNTIME/'requirements.txt'],env=ENV,log_path=RUN/'setup.log')
run_logged([PYTHON,'-c','import torch; assert torch.cuda.is_available(), "Select GPU runtime"; print(torch.__version__,torch.cuda.get_device_properties(0))'],env=ENV,log_path=RUN/'setup.log')
def launch(script,*args):
    run_logged([PYTHON,'-u',RUNTIME/script,*map(str,args)],env=ENV,cwd=RUNTIME,log_path=RUN/'execution.log')
launch('evaluate_four_way.py','--root',WORK,'--mode','preflight')
''')
    md('''## Tạo đối chứng SFT-only
Fresh LoRA rank8/alpha16/dropout0,05; không nạp trọng số CPT. Cùng seed42, LR2e-5,
batch1, accumulation8,1epoch, chọn checkpoint theo validation. Khoảng36steps.
Giữ RUN_NAME để resume checkpoint đầy đủ. Nếu chưa tới checkpoint đầu tiên thì cần RUN_NAME mới.
''')
    code('''SFT_ONLY=RUN/'sft_only_training'
args=['--data',WORK/'data','--output',SFT_ONLY,'--mode','train']
if (SFT_ONLY/'run_identity.json').is_file(): args+=['--resume','latest']
launch('train_sft.py',*args)
''')
    md('''## Đánh giá bốn bản
Mỗi bản chạy trong một process riêng, cùng NF4, FP16 trên T4, greedy và tắt thinking.
Cache từng câu; không sửa JSON đầu ra rồi chấm lại. Nếu ngắt, Run all với cùng RUN_NAME.
NLL sử dụng ngữ cảnh có đáp án nguồn. MCQ chỉ thấy câu hỏi và phương án, không thấy đáp án/lời giải.
''')
    code('''EVAL=RUN/'evaluation'
for variant in ('base','cpt','sft','cpt_sft'):
    print('\\n===== ĐÁNH GIÁ',variant,'=====',flush=True)
    launch('evaluate_four_way.py','--root',WORK,'--output',EVAL,'--sft-run',SFT_ONLY,
           '--mode','evaluate','--variant',variant,'--generation-count',GENERATION_COUNT)
launch('evaluate_four_way.py','--root',WORK,'--output',EVAL,'--sft-run',SFT_ONLY,'--mode','report')
''')
    code('''from IPython.display import Markdown,display
display(Markdown((EVAL/'COMPARISON.md').read_text(encoding='utf-8')))
from google.colab import files
print('Kết quả lưu tại:',EVAL/'four_way_results.zip')
files.download(str(EVAL/'four_way_results.zip'))
''')
    md('''## Đọc kết quả
Gửi lại **four_way_results.zip** để phân tích ưu/nhược từng bản và duyệt lời giải.
ZIP gồm bảng số đo, output nguyên văn, identity/hash, gói đánh giá blind và adapter SFT-only mới.
Duyệt blind_review.json trước khi mở blind_review_key.json. Cần xem nội dung trước khi kết luận model nào tốt nhất.
Không tự thay model đang phục vụ. Không phải đo hiệu năng GGUF.
''')
    result = {"nbformat": 4, "nbformat_minor": 5, "metadata": {"colab": {"name": NOTEBOOK, "gpuType": "T4"},
        "kernelspec": {"display_name": "Python3", "language": "python", "name": "python3"}, "accelerator": "GPU"}, "cells": cells}
    for cell in cells:
        if cell["cell_type"] == "code":
            tree = ast.parse("".join(cell["source"]))
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.startswith("import torch;"):
                    ast.parse(node.value)
    return result


def build():
    out = OUTPUT
    out.mkdir(parents=True, exist_ok=True)
    work = out/"input"
    work.mkdir(exist_ok=True)
    shutil.copytree(RELEASE, work/"data", dirs_exist_ok=True)
    runtime = work/"runtime"
    runtime.mkdir(exist_ok=True)
    for name in ("sft_contract.py", "config.json", "requirements.txt"):
        shutil.copyfile(RELEASE/"runtime"/name, runtime/name)
    (runtime/"train_sft.py").write_text(sft_only_source((RELEASE/"runtime/train_sft.py").read_text(encoding="utf-8")), encoding="utf-8")
    for name in ("evaluate_four_way.py", "scoring.py"):
        shutil.copyfile(HERE/name, runtime/name)
    # Reuse the audited schema without project-only imports or filesystem dependencies.
    tree = ast.parse((SFT/"data_preparation/validate_release.py").read_text(encoding="utf-8"))
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in {"normalized_option", "validate_output"}]
    (runtime/"quiz_schema.py").write_text('from __future__ import annotations\nimport re, unicodedata\nfrom typing import Any\n\n'+"\n\n".join(ast.unparse(n) for n in nodes)+"\n", encoding="utf-8")
    adapter = work/"models/cpt_sft"
    adapter.mkdir(parents=True, exist_ok=True)
    done = load(out/"returned_cpt_sft/completed.json")
    for name in ("adapter_config.json", "adapter_model.safetensors"):
        source = out/"returned_cpt_sft/adapter"/name
        assert sha(source) == done["outputs_sha256"]["adapter/"+name]
        shutil.copyfile(source, adapter/name)
    for name in ("MODEL_PROVENANCE.json", "completed.json", "run_identity.json"):
        shutil.copyfile(out/"returned_cpt_sft"/name, work/("returned_"+name))
    tasks, order = build_tasks()
    save(work/"tasks.json", tasks)
    registry = {p.relative_to(work).as_posix(): sha(p) for p in sorted(work.rglob("*")) if p.is_file() and p.name != "comparison_manifest.json" and "__pycache__" not in p.parts}
    # Frozen registry is the authority for exact original training data.
    assert sha(work/"data/manifest.json") == "b2cc6f3ae9dbfe89b9991dd5fed0c4ae5bc78277be063c78c86521a6fe13c010"
    save(work/"comparison_manifest.json", {"schema": "bkquiz-four-way-input-v1", "files_sha256": registry,
        "returned_archive_sha256": "c159fbf222c5339b5914d37eb1bc968376d23afb9207a4fd1671dc852c76a613",
        "variants": {"base": "pinned Qwen3-1.7B", "cpt": "verified CPT27 adapter",
                     "sft": "fresh LoRA trained from base by this notebook", "cpt_sft": "user returned combined adapter"},
        "protocol": {"seed": 42, "quantization": "NF4 double quant", "thinking": False, "do_sample": False,
                     "mcq_max_new_tokens": 128, "quiz_max_new_tokens": 2048, "test_count": 40,
                     "test_used_for_selection": False, "nll": "assistant-only; per-example and token weighted",
                     "grounded_selection": "fixed round robin by course, hashed ID within course", "mcq_option_order": "original"},
        "generation_order": order, "semantic_judge": None})
    archive = out/"bkquiz_four_way_input.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for name in ["comparison_manifest.json", *sorted(registry)]:
            z.write(work/name, name)
    save(out/NOTEBOOK, make_notebook(sha(archive)))
    receipt = {"archive": str(archive), "archive_sha256": sha(archive), "size_bytes": archive.stat().st_size,
               "notebook": str(out/NOTEBOOK), "notebook_sha256": sha(out/NOTEBOOK), "drive_folder": DRIVE_FOLDER,
               "gpu_comparison_executed": False, "sft_only_training_executed": False}
    save(out/"COLAB_HANDOFF.json", receipt)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    build()
