"""Freeze portable teacher packets and a resumable, text-only Colab notebook."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import textwrap

from pedagogy_core import SCHEMA, TEACHER, atomic_json, canonical, digest, file_sha, make_zip
from pedagogy_store import PedagogyStore

REQUIREMENTS = "transformers==4.57.6\naccelerate==1.12.0\nbitsandbytes==0.48.1\n"
DRIVE_FOLDER = "BKQuiz_CPT/SFT_PEDAGOGY_QWEN7B_20261025"


def build_packet(store, selected, name, runtime_hashes,verification_policy=None):
    jobs=[store.jobs[j] for j in selected]
    context_ids={cid for job in jobs for cid in job["context_ids"]}
    members={"jobs.jsonl":b"".join(canonical(j)+b"\n" for j in jobs),
             "contexts.jsonl":b"".join(canonical(store.contexts[c])+b"\n" for c in sorted(context_ids)),
             "known_exam_questions.jsonl":(store.workspace/"known_exam_questions.jsonl").read_bytes()}
    manifest={"schema":SCHEMA,"teacher":TEACHER,"workspace_manifest_sha256":file_sha(store.workspace/"manifest.json"),
              "kind":name,"job_ids":selected,"runtime_files_sha256":runtime_hashes,
              "files_sha256":{k:hashlib.sha256(v).hexdigest() for k,v in members.items()},
              "source_contains_answer_key_for_enrichment_validation_only":True,"human_reviews_created":0}
    if verification_policy is not None:manifest["verification_policy"]=verification_policy
    manifest["packet_id"]="packet_"+digest(manifest)[:24]
    members["manifest.json"]=canonical(manifest)+b"\n"
    path=store.workspace/"packets"/("teacher_"+name+".zip")
    make_zip(path,members)
    atomic_json(store.workspace/"packets/manifests"/(manifest["packet_id"]+".json"),manifest)
    return {"path":str(path),"sha256":file_sha(path),"jobs":len(jobs),"packet_id":manifest["packet_id"]}


def notebook(assets):
    cells=[]
    def md(source):cells.append({"cell_type":"markdown","metadata":{},"source":textwrap.dedent(source).strip().splitlines(keepends=True)})
    def code(source):cells.append({"cell_type":"code","metadata":{},"source":textwrap.dedent(source).strip().splitlines(keepends=True),"outputs":[],"execution_count":None})
    md('''
    # BKQuiz · Qwen2.5-7B-Instruct → lời giải và câu hỏi từ lý thuyết
    Chọn **Runtime → Change runtime type → T4 GPU** (hoặc GPU CUDA ≥14 GiB).
    Teacher được cố định revision và chạy NF4. Student vẫn là Qwen3-1.7B cùng adapter CPT27.

    Mặc định chỉ chạy 3 jobs kiểm tra trước. Sau đó đổi `MAX_JOBS=None` để chạy hết gói pilot 63 jobs.
    Chỉ chuyển `PACKET_KIND="full"` sau khi xem chất lượng pilot; toàn bộ kế hoạch có 1.994 jobs.
    Mỗi job gồm bản nháp, hai lần giải độc lập đổi thứ tự lựa chọn và một lần tự kiểm tra.
    Cùng một model tự kiểm tra không tương đương chuyên gia độc lập. Mọi kết quả vẫn phải duyệt trên web.
    Bộ nhớ đệm và kết quả lưu trên Drive sau từng job; chạy lại để tiếp tục. Không cắt cụt nguồn/đáp án cho vừa token.
    ''')
    code('''
    from google.colab import drive
    drive.mount('/content/drive')
    ''')
    code("from pathlib import Path\nimport hashlib, json, subprocess, sys, zipfile, os\n"
         +"BASE = Path('/content/drive/MyDrive/"+DRIVE_FOLDER+"')\n"
         +"ASSETS = "+repr(assets)+"\n"
         +"PACKET_KIND = 'pilot'  # 'pilot' hoặc 'full'\nMAX_JOBS = 3  # None để chạy hết gói đã chọn\nRETRY_FAILED = False\n"
         +"assert BASE.is_dir(), f'Chưa có thư mục dữ liệu: {BASE}'\nprint('Drive:', BASE)\n")
    code('''
    # Kiểm tra tệp trước khi cài đặt hoặc thực thi mã từ gói đã đóng băng.
    def checked_file(name, expected):
        path = BASE / name
        with path.open('rb') as stream:
            actual = hashlib.file_digest(stream, 'sha256').hexdigest()
        if actual != expected:
            raise ValueError(f'SHA256 không khớp: {name}; tải lại đúng gói, không sửa hash trong notebook')
        return path
    runtime_zip = checked_file('teacher_runtime.zip', ASSETS['runtime_sha256'])
    input_zip = checked_file('teacher_' + PACKET_KIND + '.zip', ASSETS[PACKET_KIND + '_sha256'])
    WORK = Path('/content/bkquiz_pedagogy_runtime')
    WORK.mkdir(exist_ok=True)
    with zipfile.ZipFile(runtime_zip) as archive:
        expected = {'pedagogy_core.py','teacher_runtime.py','requirements.txt','runtime_manifest.json'}
        if set(archive.namelist()) != expected or any(i.file_size > 1024*1024 for i in archive.infolist()):
            raise ValueError('Gói runtime không hợp lệ')
        raw = {n: archive.read(n) for n in expected}
        manifest = json.loads(raw['runtime_manifest.json'])
        for name, wanted in manifest['files_sha256'].items():
            if hashlib.sha256(raw[name]).hexdigest() != wanted:
                raise ValueError('Runtime file bị thay đổi: ' + name)
        for name, body in raw.items():
            (WORK / name).write_bytes(body)
    print('Verified runtime/input:', runtime_zip.name, input_zip.name)
    ''')
    code('''
    # Môi trường riêng tránh ghi đè thư viện của kernel Colab đang chạy.
    VENV = Path('/content/bkquiz_pedagogy_venv')
    PYTHON = VENV / 'bin/python'
    if not PYTHON.exists():
        subprocess.run([sys.executable, '-m', 'venv', '--system-site-packages', str(VENV)], check=True)
    subprocess.run([str(PYTHON), '-m', 'pip', 'install', '--quiet', 'torch==2.6.0',
                    '--index-url', 'https://download.pytorch.org/whl/cu124'], check=True)
    # Không dùng vision/audio trong teacher văn bản này. Bỏ các bản hệ thống
    # khỏi kiểm tra optional dependency để tránh ABI mismatch với torch riêng.
    guard = WORK / 'sitecustomize.py'
    guard.write_text("import sys\\nimport importlib.util\\n_original = importlib.util.find_spec\\ndef _find(name, *args, **kwargs):\\n    if name.split('.')[0] in {'torchvision','torchaudio','librosa'}: return None\\n    return _original(name, *args, **kwargs)\\nimportlib.util.find_spec = _find\\n", encoding='utf-8')
    subprocess.run([str(PYTHON), '-m', 'pip', 'install', '--quiet', '-r', str(WORK/'requirements.txt')], check=True)
    env = dict(os.environ, PYTHONPATH=str(WORK), TOKENIZERS_PARALLELISM='false')
    subprocess.run([str(PYTHON), '-c', 'import torch, transformers, bitsandbytes; print(torch.__version__, transformers.__version__); assert torch.cuda.is_available(); print(torch.cuda.get_device_properties(0))'], env=env, check=True)
    ''')
    code('''
    OUTPUT = BASE / 'runs' / PACKET_KIND
    command = [str(PYTHON), '-u', str(WORK/'teacher_runtime.py'), '--input', str(input_zip), '--out', str(OUTPUT)]
    if MAX_JOBS is not None:
        command += ['--max-jobs', str(MAX_JOBS)]
    if RETRY_FAILED:
        command += ['--retry-failed']
    subprocess.run(command, env=env, cwd=str(WORK), check=True)
    ''')
    code('''
    from google.colab import files
    results = sorted(OUTPUT.glob('pedagogy_results_*.zip'), key=lambda p:p.stat().st_mtime)
    if not results:
        raise RuntimeError('Chưa có kết quả thật; kiểm tra GPU và log phía trên')
    print('Kết quả được lưu trên Drive:', results[-1])
    print('Tải ZIP này lên http://127.0.0.1:8765/sft/pedagogy/ để duyệt từng câu.')
    files.download(str(results[-1]))
    ''')
    md('''
    ## Duyệt và xuất SFT
    Tải `pedagogy_results_*.zip` lên màn hình duyệt trên máy Windows. Kiểm tra lý thuyết gốc,
    đáp án và giải thích từng phương án, sau đó chấp nhận/sửa/loại.
    Chỉ những bản mới nhất đã được người dùng chấp nhận mới có mặt trong bản xuất SFT.
    Train ưu tiên ≥80% câu hỏi mới từ lý thuyết, tối đa 20% câu hỏi cũ được bổ sung lời giải.
    Validation/test giữ theo nhóm trang và nhóm câu hỏi; các PDF này đã xuất hiện trong CPT.
    Notebook này **không huấn luyện student**, không tự ghi quyết định duyệt.
    ''')
    return {"nbformat":4,"nbformat_minor":5,"metadata":{"colab":{"name":"BKQuiz_Qwen7B_Pedagogy.ipynb"},
            "kernelspec":{"display_name":"Python 3","language":"python","name":"python3"},"accelerator":"GPU"},"cells":cells}


def package(workspace):
    store=PedagogyStore(workspace);root=Path(__file__).parent
    runtime={name:(root/name).read_bytes() for name in ("pedagogy_core.py","teacher_runtime.py")}
    runtime_hashes={name:hashlib.sha256(body).hexdigest() for name,body in runtime.items()}
    runtime["requirements.txt"]=REQUIREMENTS.encode()
    runtime["runtime_manifest.json"]=canonical({"schema":SCHEMA,"teacher":TEACHER,"files_sha256":{n:hashlib.sha256(b).hexdigest() for n,b in runtime.items()}})+b"\n"
    out=store.workspace/"colab";out.mkdir(exist_ok=True)
    runtime_path=out/"teacher_runtime.zip";make_zip(runtime_path,runtime)
    pilot_ids=json.loads((store.workspace/"pilot_job_ids.json").read_text(encoding="utf-8"))
    # The default three-job GPU check covers both tasks, rather than only the
    # first courses in alphabetical order.
    enrich=[identity for identity in pilot_ids if store.jobs[identity]["task"]=="enrich_rationale"]
    theory=[identity for identity in pilot_ids if store.jobs[identity]["task"]=="theory_to_quiz"]
    smoke=theory[:2]+enrich[:1]
    pilot_ids=smoke+[identity for identity in pilot_ids if identity not in smoke]
    pilot=build_packet(store,pilot_ids,"pilot",runtime_hashes)
    full=build_packet(store,list(store.jobs),"full",runtime_hashes)
    assets={"runtime_sha256":file_sha(runtime_path),"pilot_sha256":pilot["sha256"],"full_sha256":full["sha256"]}
    nb=notebook(assets)
    for index,cell in enumerate(nb["cells"]):
        if cell["cell_type"]=="code":compile("".join(cell["source"]),f"notebook_cell_{index}","exec")
    notebook_path=out/"BKQuiz_Qwen7B_Pedagogy.ipynb";atomic_json(notebook_path,nb)
    result={"schema":SCHEMA,"runtime":str(runtime_path),"notebook":str(notebook_path),"pilot":pilot,"full":full,"checksums":assets,
            "gpu_executed":False,"drive_folder":DRIVE_FOLDER}
    atomic_json(store.workspace/"COLAB_ASSETS.json",result)
    return result


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--workspace",type=Path,required=True)
    print(json.dumps(package(p.parse_args().workspace),ensure_ascii=False,indent=2))
