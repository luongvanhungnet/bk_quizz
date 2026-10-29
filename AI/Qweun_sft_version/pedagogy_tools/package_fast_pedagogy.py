"""Separate fast Colab artifacts; never overwrite the user's running strict job."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

from pedagogy_core import SCHEMA,TEACHER,FAST_POLICY,atomic_json,canonical,file_sha,make_zip
from pedagogy_store import PedagogyStore
from package_pedagogy import build_packet,notebook,REQUIREMENTS

DRIVE_FOLDER="BKQuiz_CPT/SFT_PEDAGOGY_QWEN7B_FAST_20261025"


def fast_notebook(assets):
    nb=notebook(assets)
    cells=nb["cells"]
    def source(index,text):cells[index]["source"]=text.strip().splitlines(keepends=True)
    source(0,"""# BKQuiz · Qwen7B FAST · phiên tối đa 55 phút
Sinh theo batch, kiểm tra JSON/trích dẫn/trùng lặp trên CPU. Chỉ giải lại hai thứ tự và critic
cho câu rủi ro hoặc mẫu ngẫu nhiên 10%. Câu chưa được model kiểm tra lại vẫn phải duyệt thủ công.

Mặc định xử lý gói full, batch 2 và giới hạn 55 phút kể từ ô cấu hình, gồm cài thư viện/tải model.
Không cam kết xong 1.994 câu trong một phiên. Chạy lại để tiếp tục cache của bản FAST.
Cache và đầu ra bản strict cũ vẫn giữ nguyên, nhập kết quả cũ trên web vẫn được hỗ trợ.
Chọn Runtime → Change runtime type → T4 GPU (hoặc GPU CUDA ≥14 GiB).
""")
    source(2,"from pathlib import Path\nimport hashlib, json, subprocess, sys, zipfile, os, time\n"
           +"BASE=Path('/content/drive/MyDrive/"+DRIVE_FOLDER+"')\nASSETS="+repr(assets)+"\n"
           +"PACKET_KIND='full'  # 'pilot' =63 jobs, 'full' =1994 jobs\nMAX_JOBS=None  # 3 để chạy thử\nBATCH_SIZE=2  # T4: bắt đầu2, tự giảm nếu OOM\nSESSION_MINUTES=55\nRETRY_FAILED=False\n"
           +"assert 1<=BATCH_SIZE<=8 and 1<=SESSION_MINUTES<=55\nSESSION_STARTED=time.monotonic()\nDEADLINE=SESSION_STARTED+SESSION_MINUTES*60\n"
           +"def remaining():\n    value=DEADLINE-time.monotonic()\n    if value<=30: raise TimeoutError('Hết ngân sách phiên; chạy lại để tiếp tục')\n    return value\n"
           +"def budget_run(command, **kwargs):\n    return subprocess.run(command, timeout=remaining(), **kwargs)\n"
           +"assert BASE.is_dir(), f'Chưa thấy thư mục {BASE}'\nprint('Tối đa', SESSION_MINUTES, 'phút; model audit theo rủi ro +10% mẫu')\n")
    source(3,"".join(cells[3]["source"]).replace("{'pedagogy_core.py','teacher_runtime.py','requirements.txt','runtime_manifest.json'}",
           "{'pedagogy_core.py','teacher_runtime.py','teacher_fast_runtime.py','requirements.txt','runtime_manifest.json'}")
           .replace("/content/bkquiz_pedagogy_runtime","/content/bkquiz_pedagogy_fast_runtime"))
    setup="".join(cells[4]["source"])
    # The base notebook dedents its source; use an exact known statement guard.
    start=setup.index("subprocess.run([str(PYTHON), '-m', 'pip', 'install', '--quiet', 'torch==2.6.0',")
    end=setup.index("check=True)",start)+len("check=True)")
    setup=setup[:start]+"# Reuse Colab's working CUDA torch (including Python3.13 runtimes),\n# rather than downloading/replacing it on every run.\nbudget_run([str(PYTHON),'-c','import torch; assert torch.cuda.is_available(), \\\"Select a working Colab GPU runtime\\\"; print(\\\"CUDA torch\\\",torch.__version__)'],check=True)"+setup[end:]
    source(4,setup.replace("subprocess.run(","budget_run("))
    source(5,"""OUTPUT=BASE/'runs'/PACKET_KIND
OUTPUT.mkdir(parents=True,exist_ok=True)
# Model load is included in this remaining budget. Reserve90s for ZIP/download.
minutes=min(50,max(.01,(remaining()-90)/60))
command=[str(PYTHON),'-u',str(WORK/'teacher_fast_runtime.py'),'--input',str(input_zip),'--out',str(OUTPUT),
         '--batch-size',str(BATCH_SIZE),'--minutes',str(minutes)]
if MAX_JOBS is not None: command+=['--max-jobs',str(MAX_JOBS)]
if RETRY_FAILED: command+=['--retry-failed']
try:
    budget_run(command,env=env,cwd=str(WORK),check=True)
except subprocess.TimeoutExpired:
    print('Watchdog đã dừng phiên. Cache mỗi câu được giữ trên Drive; chạy lại để tiếp tục.')
""")
    source(6,"""from google.colab import files
candidates=list(OUTPUT.glob('pedagogy_results_*.zip'))+list(OUTPUT.glob('pedagogy_checkpoint.zip'))
# Do not silently download an old run as if this session succeeded.
recent=[p for p in candidates if p.stat().st_mtime>=time.time()-(time.monotonic()-SESSION_STARTED)-5]
if recent:
    result=max(recent,key=lambda p:p.stat().st_mtime)
    print('Kết quả thật đã hoàn thành:',result)
    print('Nhập ZIP tại http://127.0.0.1:8765/sft/pedagogy/ rồi duyệt từng câu.')
    files.download(str(result))
else:
    print('Phiên này chưa có ZIP mới. Cache còn trên Drive; kiểm tra log và chạy lại để tiếp tục.')
report=OUTPUT/'SESSION_REPORT.json'
if report.is_file(): print(report.read_text())
""")
    source(7,"""## Tiếp tục và duyệt
Chạy lại Run all với cùng gói để tiếp tục. Cache đã hoàn thành không sinh lại; draft đang chờ kiểm tra
được giữ riêng và chưa xuất. Mỗi30giây có log sinh token; sau mỗi batch có progress và checkpoint ZIP.
Câu rủi ro: multiple-select, ghép môn liên quan, retrieval yếu hoặc câu hỏi tính toán/có số.
10% mẫu ngẫu nhiên được chọn ổn định theo job ID, không thay đổi khi chạy lại.

Web phân biệt **chỉ kiểm tra CPU** và **đã kiểm tra thêm bằng model**. Cả hai đều chờ người dùng duyệt,
không có xác nhận chuyên gia tự động. Đáp án mâu thuẫn nguồn/trích dẫn bịa vẫn bị chặn.
Chỉ các câu bạn chấp nhận được xuất SFT; tỷ lệ train vẫn ưu tiên≥80% câu mới từ lý thuyết.
""")
    nb["metadata"]["colab"]["name"]="BKQuiz_Qwen7B_Fast.ipynb"
    for i,cell in enumerate(cells):
        cell["id"]="fast-"+str(i)
        if cell["cell_type"]=="code":compile("".join(cell["source"]),f"fast_cell_{i}","exec")
    return nb


def package_fast(workspace):
    store=PedagogyStore(workspace);root=Path(__file__).parent;out=store.workspace/"colab_fast";out.mkdir(exist_ok=True)
    runtime={name:(root/name).read_bytes() for name in ("pedagogy_core.py","teacher_runtime.py","teacher_fast_runtime.py")}
    hashes={k:hashlib.sha256(v).hexdigest() for k,v in runtime.items()}
    runtime["requirements.txt"]=REQUIREMENTS.encode()
    runtime["runtime_manifest.json"]=canonical({"schema":SCHEMA,"teacher":TEACHER,"verification_policy":FAST_POLICY,
                "files_sha256":{k:hashlib.sha256(v).hexdigest() for k,v in runtime.items()}})+b"\n"
    make_zip(out/"teacher_runtime.zip",runtime)
    pilot=json.loads((store.workspace/"pilot_job_ids.json").read_text(encoding="utf-8"))
    theory=[j for j in pilot if store.jobs[j]["task"]=="theory_to_quiz"][:2]
    enrich=[j for j in pilot if store.jobs[j]["task"]=="enrich_rationale"][:1]
    first=theory+enrich;pilot=first+[j for j in pilot if j not in first]
    packets={kind:build_packet(store,ids,"fast_"+kind,hashes,FAST_POLICY) for kind,ids in [("pilot",pilot),("full",list(store.jobs))]}
    assets={"runtime_sha256":file_sha(out/"teacher_runtime.zip"),**{kind+"_sha256":p["sha256"] for kind,p in packets.items()}}
    atomic_json(out/"BKQuiz_Qwen7B_Fast.ipynb",fast_notebook(assets))
    receipt={"schema":SCHEMA,"runtime":str(out/"teacher_runtime.zip"),"notebook":str(out/"BKQuiz_Qwen7B_Fast.ipynb"),**packets,
             "checksums":assets,"verification_policy":FAST_POLICY,"drive_folder":DRIVE_FOLDER,"gpu_benchmark_executed":False,
             "default_batch_size":2,"session_budget_minutes":55,"guarantee_all_jobs_under_one_hour":False}
    atomic_json(store.workspace/"FAST_COLAB_ASSETS.json",receipt);return receipt


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--workspace",type=Path,required=True)
    print(json.dumps(package_fast(p.parse_args().workspace),ensure_ascii=False,indent=2))
