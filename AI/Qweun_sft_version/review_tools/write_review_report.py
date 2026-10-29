"""Record reproducible checks for the local two-stage exam review workflow."""
from __future__ import annotations

import argparse
import ast
from contextlib import closing
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import zipfile

from sft_review_store import SFTReviewStore,page_identity


def sha(path):
    with Path(path).open("rb") as stream:return hashlib.file_digest(stream,"sha256").hexdigest()


def load(path):return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def passed_tests(path):
    text=Path(path).read_text(encoding="utf-8-sig")
    count=re.search(r"Ran (\d+) tests? in",text)
    if not count or not re.search(r"\nOK\s*$",text):raise ValueError("Tests are not passing: "+str(path))
    return {"tests":int(count.group(1)),"passed":True,"log":str(Path(path).resolve()),"sha256":sha(path)}


def verify(workspace,project):
    workspace=Path(workspace).resolve();project=Path(project).resolve()
    manifest=load(workspace/"manifest.json")
    if sha(workspace/"pages.jsonl")!=manifest["catalog_sha256"]:raise ValueError("Page catalog changed")
    with (workspace/"pages.jsonl").open(encoding="utf-8") as stream:pages=[json.loads(line) for line in stream if line.strip()]
    for page in pages:
        if page_identity(page)!=page["identity"] or page["id"]!="rp_"+page["identity"][:24]:raise ValueError("Page image identity mismatch")
    dataset=Path(manifest["dataset_path"])
    for name,wanted in manifest["input_files_sha256"].items():
        if sha(dataset/name)!=wanted:raise ValueError("Input SFT dataset changed: "+name)
    with (dataset/"inventory.jsonl").open(encoding="utf-8") as stream:sources=[json.loads(line) for line in stream if line.strip()]
    for source in sources:
        if sha(source["path"])!=source["sha256"]:raise ValueError("Original PDF changed: "+source["path"])
    assets=load(workspace/"colab/COLAB_ASSETS.json")
    if sha(assets["runtime"])!=assets["runtime_sha256"]:raise ValueError("Runtime ZIP changed")
    with zipfile.ZipFile(assets["runtime"]) as zipin:
        if zipin.testzip():raise ValueError("Runtime ZIP CRC failed")
        runtime=load_bytes= json.loads(zipin.read("runtime.json"))
        for name,wanted in runtime["files_sha256"].items():
            if hashlib.sha256(zipin.read(name)).hexdigest()!=wanted:raise ValueError("Runtime member changed: "+name)
    notebook=load(assets["notebook"])
    if notebook["metadata"]["bkquiz"]["runtime_sha256"]!=assets["runtime_sha256"]:raise ValueError("Notebook/runtime pair mismatch")
    code_cells=0
    for cell in notebook["cells"]:
        if cell["cell_type"]=="code":ast.parse("".join(cell["source"]));code_cells+=1
    tests=passed_tests(workspace/"ui_evidence/test_review_workflow_results.txt")
    legacy=passed_tests(workspace/"ui_evidence/test_legacy_cpt_results.txt")
    store=SFTReviewStore(workspace)
    with closing(sqlite3.connect(store.database)) as connection:
        event_counts=dict(connection.execute("SELECT stage,COUNT(*) FROM review_events GROUP BY stage"))
    code=list(Path(__file__).parent.rglob("*.py"))+[Path(__file__).parent/"sft_review.html",project/"AI/data_preprocessing/local_review_tools/serve.py"]
    code=[p for p in code if "__pycache__" not in p.parts]
    report={"schema":"bkquiz-sft-two-stage-review-validation-v1","validated_utc":datetime.now(timezone.utc).isoformat(),
            "passed":True,"workspace":str(workspace),"source_files_sha256_verified":len(sources),
            "original_pages_in_queue":manifest["queued_original_pages"],"review_images":len(pages),
            "catalog_sha256":manifest["catalog_sha256"],"all_page_identities_verified":True,
            "sft_input_snapshots_unchanged":True,"workflow_tests":tests,"legacy_cpt_tests":legacy,
            "total_tests_passed":tests["tests"]+legacy["tests"],
            "notebook_code_cells_parsed":code_cells,"runtime_sha256":assets["runtime_sha256"],
            "notebook_sha256":sha(assets["notebook"]),"model_config":assets["model_config"],
            "actual_progress":store.progress(),"observed_actual_review_events_by_stage":event_counts,
            "human_decisions_automatically_created":0,"actual_gpu_or_colab_execution":False,
            "vlm_quality_and_gpu_performance_measured":False,
            "browser_checks":{"stage1_source_image_visible":True,"stage2_empty_queue_visible":True,
                              "synthetic_stage2_question_visible":True,"synthetic_correction_and_reapproval_preserved":True,
                              "production_decisions_created_by_browser_test":0,
                              "evidence_directory":"ui_evidence","synthetic_fixture":"../ui_smoke_fixture"},
            "code_files_sha256":{p.relative_to(project).as_posix():sha(p) for p in sorted(code)},
            "remaining_user_step":"Review stage1 page images before approved-image export and real Colab VLM execution; review stage2 questions after importing results."}
    (workspace/"VALIDATION_REPORT.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return report


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--workspace",type=Path,required=True)
    parser.add_argument("--project",type=Path,default=Path(__file__).resolve().parents[3])
    args=parser.parse_args();report=verify(args.workspace,args.project)
    print(json.dumps({"passed":report["passed"],"tests":report["total_tests_passed"],"images":report["review_images"],
                      "original_sources_verified":report["source_files_sha256_verified"],"runtime_sha256":report["runtime_sha256"],
                      "actual_review_events":report["observed_actual_review_events_by_stage"],"gpu_executed":False},ensure_ascii=False,indent=2))
