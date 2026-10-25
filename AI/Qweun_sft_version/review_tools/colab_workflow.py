"""Export authorized stage-one images and import VLM output for round two."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import time
import zipfile

from colab_runtime.runtime import MODEL_CONFIG, PROMPT, PROTOCOL, canonical, digest, file_sha, atomic_bytes, atomic_json, load, verified_zip, parse_response

ROOT = Path(__file__).resolve().parent
REQUIREMENTS = "transformers==4.57.6\naccelerate==1.12.0\nbitsandbytes==0.48.1\nPillow==11.3.0\n"


def _vlm_pages(store):
    """Native/OCR text routes never enter the GPU queue."""
    method=getattr(store,"vlm_eligible_pages",None)
    return method() if method is not None else store.selected_pages()


def _verify_vlm_permission(store,job,image_sha256):
    method=getattr(store,"verify_vlm_page",None)
    automatic=job.get("stage1_decision")=="auto_vlm"
    if method is not None:
        try:
            value=method(job["page_id"],image_sha256,
                         routing_policy_id=job.get("routing_policy_id") if automatic else None,
                         routing_identity=job.get("routing_identity") if automatic else None,
                         routing_policy_sha256=job.get("routing_policy_sha256") if automatic else None)
        except ValueError as error:
            raise ValueError("Stage1 permission is no longer current: "+str(error)) from error
    else:
        value=store.get_page(job["page_id"])
    if (value.get("identity")!=job["identity"] or value.get("image_sha256")!=image_sha256
            or value.get("status") not in ({"approve","auto_vlm"} if automatic else {"approve"})):
        raise ValueError("Stage1 permission changed; export the current selection again")
    if automatic and value.get("status")=="auto_vlm":
        for field in ["routing_policy_id","routing_policy_sha256","routing_identity"]:
            if value.get(field)!=job.get(field):raise ValueError("Automatic routing provenance changed")
    return value


def _write_immutable(path, data):
    import os
    import uuid
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temporary=path.with_name(path.name+"."+uuid.uuid4().hex+".partial")
    try:
        temporary.write_bytes(data)
        try:os.link(temporary,path)
        except FileExistsError:
            if file_sha(path)!=hashlib.sha256(data).hexdigest():raise ValueError("Immutable artifact already differs: "+str(path))
    finally:
        if temporary.exists():temporary.unlink()


def _archive(path, files, expected_sha=None, before_publish=None):
    """Deterministic streamed ZIP: one MiB buffer, even with thousands of images."""
    import uuid
    import os
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+"."+uuid.uuid4().hex+".partial")
    try:
        with zipfile.ZipFile(temporary,"w",zipfile.ZIP_DEFLATED,compresslevel=6) as zipout:
            for name,data in sorted(files.items()):
                info=zipfile.ZipInfo(name,date_time=(2026,10,24,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
                actual=hashlib.sha256()
                with zipout.open(info,"w") as destination:
                    if isinstance(data,Path):
                        with data.open("rb") as source:
                            for block in iter(lambda:source.read(1024*1024),b""):
                                actual.update(block);destination.write(block)
                    else:
                        actual.update(data);destination.write(data)
                if expected_sha is not None and actual.hexdigest()!=expected_sha.get(name):
                    raise ValueError("Export source changed while packaging: "+name)
        if before_publish is not None:before_publish()
        try:os.link(temporary,path)
        except FileExistsError:
            if file_sha(path)!=file_sha(temporary):raise ValueError("Immutable artifact already differs: "+str(path))
    finally:
        if temporary.exists():temporary.unlink()
    return path


def _cell(kind, text):
    value = {"cell_type": kind, "metadata": {}, "source": text.splitlines(keepends=True)}
    if kind == "code": value.update(execution_count=None, outputs=[])
    return value


def prepare_colab_assets(workspace):
    workspace = Path(workspace).resolve(); output = workspace / "colab"; output.mkdir(parents=True, exist_ok=True)
    runtime = ROOT / "colab_runtime/runtime.py"
    files = {"runtime.py": runtime.read_bytes(), "requirements.txt": REQUIREMENTS.encode()}
    runtime_manifest = {"schema": "bkquiz-sft-vlm-runtime-v1", "protocol": PROTOCOL, "model_config": MODEL_CONFIG,
                        "archive_format":"deterministic-stream-v2",
                        "prompt_sha256": hashlib.sha256(PROMPT.encode()).hexdigest(),
                        "files_sha256": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()},
                        "inherited_pins_from": "AI/data_preprocessing/colab_orchestrator_v5/env_setup.py and official core/package_cloud.py",
                        "actual_gpu_inference_tested": False}
    files["runtime.json"] = canonical(runtime_manifest) + b"\n"
    runtime_id = digest(runtime_manifest)[:16]
    archive = output / ("sft_vlm_runtime_" + runtime_id + ".zip")
    _archive(archive, files)
    runtime_sha = file_sha(archive)
    cells = [
        _cell("markdown", "# BKQuiz — Tách chữ đề thi sau duyệt ảnh đợt 1\n\nChỉ chạy những ZIP do nút **Xuất ảnh đủ điều kiện sang Colab** tạo ra. Input chỉ gồm ảnh được người dùng chọn hoặc được định tuyến auto_vlm bởi chính sách OCR đã được người dùng cho phép. Ảnh cần duyệt tay, tạm hoãn và bị loại không thuộc input; trang đã có native/OCR text không gửi sang VLM. Sau VLM, dùng **Nhập ZIP kết quả VLM** ở web để duyệt **từng câu hỏi đợt 2**. Notebook không tạo phê duyệt và không xuất SFT tự động.\n\nNếu đổi lựa chọn ảnh sau lần xuất, hãy xuất input mới và chuyển các input ZIP cũ ra khỏi thư mục Colab inputs trước khi chạy. Kết quả từ ảnh đã bị thu hồi quyết định hoặc không còn khớp chính sách tự động sẽ không được nhập.\n\nChọn **L4 + High-RAM**, dùng runtime sạch. Bật Omit code cell output when saving. Trọng số và các phiên bản kế thừa từ pipeline CPT; ngân sách OCR toàn trang mới chưa được đo trên GPU."),
        _cell("code", "from google.colab import drive\nfrom pathlib import Path\nimport hashlib,json,os,subprocess,sys,zipfile\ndrive.mount('/content/drive')\nBASE=Path('/content/drive/MyDrive/BKQuiz_SFT_EXAMS')\nINPUTS=BASE/'inputs'\nRESULTS=BASE/'results'\nBASE.mkdir(parents=True,exist_ok=True)\nINPUTS.mkdir(exist_ok=True)\nRESULTS.mkdir(exist_ok=True)\nprint('Đặt runtime ZIP ở',BASE,'và các ZIP ảnh đã duyệt ở',INPUTS)\n"),
        _cell("code", f"RUNTIME=BASE/{archive.name!r}\nEXPECTED_SHA={runtime_sha!r}\nassert RUNTIME.is_file(), 'Chưa upload runtime ZIP đúng cặp notebook'\nassert hashlib.sha256(RUNTIME.read_bytes()).hexdigest()==EXPECTED_SHA, 'Runtime ZIP sai hash'\nLOCAL=Path('/content/bkquiz_sft_vlm_runtime')\nLOCAL.mkdir(exist_ok=True)\nwith zipfile.ZipFile(RUNTIME) as z:\n    assert set(z.namelist())=={{'runtime.py','requirements.txt','runtime.json'}}\n    m=json.loads(z.read('runtime.json'))\n    for name,wanted in m['files_sha256'].items():\n        body=z.read(name)\n        assert hashlib.sha256(body).hexdigest()==wanted\n        (LOCAL/name).write_bytes(body)\n    (LOCAL/'runtime.json').write_bytes(z.read('runtime.json'))\nassert list(INPUTS.glob('sft_*.zip')), 'Chưa có ảnh được duyệt/xuất; dừng trước khi cài hoặc nạp model'\nprint('Runtime và input đã có; chưa chạy inference')\n"),
        _cell("code", "# Venv riêng giữ các package Colab hiện tại không bị ghi đè.\nENV=Path('/content/bkquiz_sft_vlm_env')\nPY=ENV/'bin/python'\nif not PY.exists(): subprocess.run([sys.executable,'-m','venv','--system-site-packages',str(ENV)],check=True)\nsubprocess.run([str(PY),'-m','pip','install','torch==2.6.0','torchvision==0.21.0','--index-url','https://download.pytorch.org/whl/cu124/'],check=True)\nsubprocess.run([str(PY),'-m','pip','install','-r',str(LOCAL/'requirements.txt')],check=True)\nsubprocess.run([str(PY),'-c',\"import torch; assert torch.cuda.is_available(), 'Cần GPU CUDA'; p=torch.cuda.get_device_properties(0); print(p.name,p.total_memory); assert p.total_memory>=20*1024**3, 'Chọn L4 hoặc GPU có >=20GiB VRAM'\"],check=True)\nsubprocess.run(['nvidia-smi'],check=True)\n"),
        _cell("markdown", "## Chạy và tiếp tục\n\nMỗi ảnh là một request OCR có deadline; model GPU được giữ qua các batch. Cache chỉ dùng lại khi ảnh, identity, prompt và cấu hình đều khớp. Kết quả lỗi giữ raw output; không tự sửa/giải câu hỏi. Nếu timeout hoặc lỗi nạp model, queue dừng và ghi lỗi rõ ràng. Chạy lại bỏ qua cache đã có; chỉ đặt `RETRY_ERRORS=True` sau khi đã xử lý nguyên nhân. ZIP `_results_...zip` trong results là thứ nhập vào web. Không xem cache/thành công máy là câu đã đạt."),
        _cell("code", "RETRY_ERRORS=False\nMAX_BATCHES=None  # Đặt 1 để thử một gói trước.\ncommand=[str(PY),str(LOCAL/'runtime.py'),'--inputs',str(INPUTS),'--out',str(RESULTS)]\nif RETRY_ERRORS: command+=['--retry-errors']\nif MAX_BATCHES is not None: command+=['--max-batches',str(MAX_BATCHES)]\nenv=os.environ.copy(); env['HF_HOME']='/content/bkquiz_sft_models'\nsubprocess.run(command,check=True,env=env)\nprint('Kết quả lưu ở',RESULTS,'; tải ZIP kết quả về và nhập lại web duyệt đợt 2')\n"),
    ]
    notebook = {"nbformat": 4, "nbformat_minor": 5, "metadata": {"kernelspec": {"display_name": "Python 3", "name": "python3"},
                 "colab": {"name": "BKQuiz_SFT_Exams_VLM_Round2.ipynb", "private_outputs": True},
                 "bkquiz": {"protocol": PROTOCOL, "runtime_sha256": runtime_sha, "gpu_executed": False}}, "cells": cells}
    notebook_path = output / "BKQuiz_SFT_Exams_VLM_Round2.ipynb"
    atomic_json(notebook_path, notebook)
    guide = f"""# Hai đợt duyệt đề thi\n\n1. Trên web cũ, mở mục Đề thi SFT / Đợt 1, đối chiếu ảnh và chọn **Dùng ảnh này cho VLM**, **Loại ảnh** hoặc **Tạm hoãn**. Ảnh được chọn thủ công và ảnh auto_vlm theo chính sách được phép mới được xuất; native/OCR text được xử lý trực tiếp, không gửi lại cho VLM.\n2. Bấm **Xuất ảnh đủ điều kiện sang Colab**. Các ZIP trong `colab/exports/` chứa ảnh và manifest đã khóa hash, mỗi gói tối đa 100 ảnh và 128 MiB. Bộ xuất ghi ZIP theo luồng, không nạp tất cả ảnh đã chọn vào RAM. Không upload `assets/` hoặc PDF gốc lên Colab.\n3. Upload `{archive.name}` vào `MyDrive/BKQuiz_SFT_EXAMS`, upload các ZIP ảnh đã duyệt vào `MyDrive/BKQuiz_SFT_EXAMS/inputs`. Mở `BKQuiz_SFT_Exams_VLM_Round2.ipynb`, chọn L4 + High-RAM và chạy từng cell.\n4. ZIP kết quả trong `MyDrive/BKQuiz_SFT_EXAMS/results` có dạng `sft_*_results_*.zip`. Tải ZIP về máy và bấm **Nhập ZIP kết quả VLM** ở web.\n5. Đợt 2 so ảnh nguồn với câu đã tách. Chọn **Chấp nhận câu hỏi**, sửa hoặc **Loại câu hỏi**; câu không có khóa đáp án vẫn giữ trạng thái thiếu, VLM không tự giải. Chỉ câu được duyệt đợt 2 mới thuộc đầu vào xuất SFT sau này.\n\nNếu đổi lựa chọn ảnh sau lần xuất, hãy xuất input mới và chuyển các ZIP input đã cũ ra khỏi thư mục Colab `inputs` trước khi chạy. Không tự xóa PDF gốc hoặc lịch sử duyệt. Input là snapshot tại lúc xuất; importer sẽ từ chối kết quả của ảnh đã bị thu hồi quyết định hoặc đổi hash.\n\nRuntime: {MODEL_CONFIG['model']} revision {MODEL_CONFIG['revision']}, NF4/SDPA; torch2.6.0, torchvision0.21.0, transformers4.57.6, accelerate1.12.0, bitsandbytes0.48.1, Pillow11.3.0. Đổi tác vụ từ mô tả vùng sang OCR toàn trang dùng ngân sách visual_tokens2048/max_new_tokens4096, được ghi riêng và **chưa chạy GPU để đo chất lượng/tốc độ**.\n\nRuntime SHA-256: `{runtime_sha}`. Không upload/chạy model nếu không có ảnh được phép theo quyết định thủ công hoặc chính sách định tuyến tự động đã chốt. Các API xuất/nhập không tự tạo quyết định con người. ZIP lỗi, input không biết nguồn, ảnh đổi hash hoặc ảnh không còn được duyệt sẽ bị từ chối. Kết quả máy, lỗi và raw output được lưu để đối chiếu, không ghi đè review CPT trước đây.\n"""
    atomic_bytes(output/"HUONG_DAN_COLAB.md",guide.encode("utf-8"))
    descriptor = {"notebook": str(notebook_path), "runtime": str(archive), "runtime_sha256": runtime_sha,
                  "guide": str(output / "HUONG_DAN_COLAB.md"), "model_config": MODEL_CONFIG, "gpu_executed": False}
    atomic_json(output / "COLAB_ASSETS.json", descriptor)
    return descriptor


def export_approved(workspace, out=None, max_images=100, max_bytes=128*1024*1024):
    from sft_review_store import SFTReviewStore
    workspace = Path(workspace).resolve(); out = Path(out).resolve() if out is not None else workspace / "colab/exports"
    if not 1 <= max_images <= 100 or not 1024 <= max_bytes <= 128*1024*1024:
        raise ValueError("Batch budgets exceed approved export policy")
    assets = prepare_colab_assets(workspace)
    store = SFTReviewStore(workspace)
    selected = sorted(_vlm_pages(store), key=lambda p: (p["source_id"],p["page"],p.get("tile_index",0),p["id"]))
    if not selected:
        return {"status": "awaiting_stage1", "approved_images": 0, "batches": [], "colab_assets": assets}
    prepared = []
    for page in selected:
        automatic=page.get("status")=="auto_vlm"
        if automatic:
            from review_render import ReviewRenderer
            if "renderer" not in locals():renderer=ReviewRenderer(workspace)
            renderer.ensure_image(page)
        image = Path(page.get("image_path", workspace / "assets" / (page["id"] + ".png")))
        image_sha=file_sha(image);image_bytes=image.stat().st_size
        if not automatic and image_sha != page.get("image_sha256"): raise ValueError("Approved image changed")
        if image_bytes > max_bytes: raise ValueError("A single approved image exceeds batch byte budget")
        job = {key: page[key] for key in ["source_id","source_sha256","page","bbox","identity","course"]}
        job.update(page_id=page["id"], id=page["id"], tile_index=page.get("tile_index",0),tile_count=page.get("tile_count",1),
                   relative_path=page.get("relative_path",""),image="images/"+page["id"]+".png",image_sha256=image_sha,stage1_decision="auto_vlm" if automatic else "approve")
        if automatic:
            job.update(automatic=True,human_verified=False)
            for field in ["routing_policy_id","routing_policy_sha256","routing_identity"]:
                if not page.get(field):raise ValueError("Automatic VLM route lacks policy provenance")
                job[field]=page[field]
        _verify_vlm_permission(store,job,image_sha)
        prepared.append((job,image,image_bytes))
    chunks=[];chunk=[];size=0
    for item in prepared:
        if chunk and (len(chunk)>=max_images or size+item[2]>max_bytes): chunks.append(chunk);chunk=[];size=0
        chunk.append(item);size+=item[2]
    if chunk:chunks.append(chunk)
    # The human may revoke a decision while file bytes are being read. Re-check before publication.
    for job,_,_ in prepared:
        _verify_vlm_permission(store,job,job["image_sha256"])
    batches=[]
    registry=workspace/"colab/exports/manifests";registry.mkdir(parents=True,exist_ok=True)
    out.mkdir(parents=True,exist_ok=True)
    for chunk in chunks:
        jobs=[x[0] for x in chunk]
        base={"schema":"bkquiz-sft-vlm-input-v1","protocol":PROTOCOL,"model_config":MODEL_CONFIG,
              "prompt_sha256":hashlib.sha256(PROMPT.encode()).hexdigest(),"jobs":jobs,"archive_format":"deterministic-stream-v2",
              "files_sha256":{job["image"]:job["image_sha256"] for job in jobs},"human_decisions_created":0}
        automatic_policies={job["routing_policy_id"]:job["routing_policy_sha256"] for job in jobs if job["stage1_decision"]=="auto_vlm"}
        if automatic_policies:base["automatic_stage1_policies"]=automatic_policies
        batch_id="sft_"+digest(base)[:24];manifest={**base,"batch_id":batch_id}
        manifest_bytes=canonical(manifest)+b"\n"
        files={job["image"]:image for job,image,_ in chunk};files["manifest.json"]=manifest_bytes
        def assert_current():
            for job in jobs:
                _verify_vlm_permission(store,job,job["image_sha256"])
        expected_sha={**manifest["files_sha256"],"manifest.json":hashlib.sha256(manifest_bytes).hexdigest()}
        archive=out/(batch_id+".zip");_archive(archive,files,expected_sha,assert_current)
        _write_immutable(registry/(batch_id+".json"),manifest_bytes)
        batches.append({"batch_id":batch_id,"archive":str(archive),"archive_sha256":file_sha(archive),
                        "input_manifest_sha256":hashlib.sha256(manifest_bytes).hexdigest(),"images":len(jobs),"image_bytes":sum(size for _,_,size in chunk)})
    report={"status":"exported","approved_images":len(selected),"batches":batches,"colab_assets":assets,
            "only_current_explicit_stage1_approvals":all(job["stage1_decision"]=="approve" for job,_,_ in prepared),
            "only_current_authorized_stage1_permissions":True,
            "human_approved_images":sum(job["stage1_decision"]=="approve" for job,_,_ in prepared),
            "automatically_routed_images":sum(job["stage1_decision"]=="auto_vlm" for job,_,_ in prepared),"human_decisions_created":0}
    index=out/"EXPORT_INDEX.json";atomic_json(index,report);report["index_path"]=str(index)
    return report


def import_results(workspace, archive):
    from sft_review_store import SFTReviewStore, question_identity
    workspace=Path(workspace).resolve();archive=Path(archive).resolve()
    members=verified_zip(archive,max_files=1000,max_bytes=256*1024*1024)
    if "result_manifest.json" not in members or "input_manifest.json" not in members:raise ValueError("Result manifests missing")
    result_manifest=json.loads(members["result_manifest.json"]);input_manifest=json.loads(members["input_manifest.json"])
    if result_manifest.get("schema")!="bkquiz-sft-vlm-result-v1" or result_manifest.get("protocol")!=PROTOCOL:raise ValueError("Unknown result protocol")
    batch_id=result_manifest.get("batch_id")
    if not isinstance(batch_id,str) or not batch_id.startswith("sft_") or any(c not in "sft_0123456789abcdef" for c in batch_id):raise ValueError("Invalid batch identifier")
    registered=workspace/"colab/exports/manifests"/(batch_id+".json")
    if not registered.is_file() or registered.read_bytes()!=members["input_manifest.json"]:raise ValueError("Result does not belong to a known approved export")
    if hashlib.sha256(members["input_manifest.json"]).hexdigest()!=result_manifest.get("input_manifest_sha256"):raise ValueError("Input manifest hash changed")
    if input_manifest.get("batch_id")!=batch_id or input_manifest.get("protocol")!=PROTOCOL:raise ValueError("Input identity mismatch")
    if result_manifest.get("model_config")!=MODEL_CONFIG or result_manifest.get("prompt_sha256")!=hashlib.sha256(PROMPT.encode()).hexdigest():raise ValueError("Result model/prompt provenance changed")
    expected=result_manifest.get("files_sha256",{})
    if set(members)!=set(expected)|{"result_manifest.json"}:raise ValueError("Unexpected/missing return members")
    for name,wanted in expected.items():
        if hashlib.sha256(members[name]).hexdigest()!=wanted:raise ValueError("Return hash mismatch: "+name)
    store=SFTReviewStore(workspace)
    jobs={j["page_id"]:j for j in input_manifest["jobs"]}
    completed=result_manifest.get("completed_page_ids",[]);not_run=result_manifest.get("not_run_page_ids",[])
    if not isinstance(completed,list) or not isinstance(not_run,list) or len(set(completed))!=len(completed) or set(completed)&set(not_run) or set(completed)|set(not_run)!=set(jobs):raise ValueError("Result job coverage mismatch")
    result_paths={"results/"+identity+".json" for identity in completed}
    if set(expected)!={"input_manifest.json"}|result_paths:raise ValueError("Unexpected result object paths")
    rows=[];failed=[];empty=[]
    for page_id in completed:
        job=jobs[page_id];_verify_vlm_permission(store,job,job["image_sha256"])
        path="results/"+page_id+".json";result=json.loads(members[path]);result_sha=hashlib.sha256(members[path]).hexdigest()
        if (result.get("page_id")!=page_id or result.get("page_identity")!=job["identity"] or result.get("image_sha256")!=job["image_sha256"] or result.get("source_sha256")!=job["source_sha256"]):raise ValueError("Individual result identity mismatch")
        if result.get("protocol")!=PROTOCOL or result.get("model_config")!=MODEL_CONFIG or result.get("prompt_sha256")!=input_manifest["prompt_sha256"]:raise ValueError("Individual model/prompt provenance mismatch")
        if result.get("status")!="ok":
            failed.append({"page_id":page_id,"error":result.get("error","unknown failure"),"result_file":path});continue
        parsed=parse_response(result.get("raw",""))
        if parsed!=result.get("parsed"):raise ValueError("Parsed output differs from preserved raw response")
        if not parsed["questions"]:empty.append({"page_id":page_id,"flags":parsed.get("flags",[]),"result_file":path})
        for index,question in enumerate(parsed["questions"]):
            transformed=json.loads(json.dumps(question,ensure_ascii=False))
            transformed["flags"]=list(dict.fromkeys(transformed.get("flags",[])+["page:"+str(flag) for flag in parsed.get("flags",[])]))
            row={"id":"qv_"+digest({"page_id":page_id,"result_sha256":result_sha,"index":index})[:24],
                 "page_id":page_id,"image_sha256":job["image_sha256"],"result_sha256":result_sha,"question":transformed,
                 "source_id":job["source_id"],"source_sha256":job["source_sha256"],"page":job["page"],"bbox":job["bbox"],
                 "vlm_model_config":MODEL_CONFIG,"prompt_sha256":input_manifest["prompt_sha256"],
                 "machine_original_question":question,"human_verified":False}
            if job.get("stage1_decision")=="auto_vlm":
                for field in ["routing_policy_id","routing_policy_sha256","routing_identity"]:row[field]=job[field]
            row["identity"]=question_identity(row);rows.append(row)
    archive_sha=file_sha(archive)
    retained=workspace/"colab/returns"/(batch_id+"_"+archive_sha[:16]);retained.mkdir(parents=True,exist_ok=True)
    _write_immutable(retained/"original_result.zip",archive.read_bytes())
    for name,data in members.items():_write_immutable(retained/name,data)
    receipt=store.import_questions(rows,batch_id+":"+archive_sha) if rows else None
    report={"schema":"bkquiz-sft-vlm-import-v1","batch_id":batch_id,"archive_sha256":archive_sha,"imported_questions":receipt.get("imported",0) if receipt else 0,"questions_in_archive":len(rows),
            "failed_pages":failed,"no_question_pages":empty,"not_run_page_ids":not_run,"store_receipt":receipt,
            "human_decisions_created":0,"retained_directory":str(retained),"round2_approval_required":True}
    report_path=retained/"import_report.json";atomic_json(report_path,report);report["report_path"]=str(report_path)
    atomic_json(workspace/"colab/LATEST_IMPORT.json",report)
    return report


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--workspace",type=Path,required=True)
    sub=parser.add_subparsers(dest="command",required=True)
    sub.add_parser("prepare");sub.add_parser("export")
    importer=sub.add_parser("import");importer.add_argument("--archive",type=Path,required=True)
    args=parser.parse_args()
    value=prepare_colab_assets(args.workspace) if args.command=="prepare" else export_approved(args.workspace) if args.command=="export" else import_results(args.workspace,args.archive)
    print(json.dumps(value,ensure_ascii=False,indent=2))
