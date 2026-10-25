"""Read PDF annotations/widgets and cached font emphasis without extracting text.

Every source is isolated behind a bounded subprocess and verified before/after
the metadata read. Unknown evidence is explicit; it never means zero markings.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid

from colab_runtime.runtime import atomic_bytes, atomic_json


VERSION="sft-extra-pdf-features-v1"
EMPHASIS_FONT=re.compile(r"bold|italic|oblique|black|semibold|demibold",re.I)


def sha(path):
    with Path(path).open("rb") as stream:return hashlib.file_digest(stream,"sha256").hexdigest()


def read_jsonl(path):
    with Path(path).open(encoding="utf-8-sig") as stream:return [json.loads(line) for line in stream if line.strip()]


def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False)


def intersects(left,right):
    return (min(left[2],right[2])>max(left[0],right[0])
            and min(left[3],right[3])>max(left[1],right[1]))


def emphasis_features(row,page,bold_flag,italic_flag):
    if page is None:
        return {"emphasis_status":"unknown","native_emphasis_ratio":None,"emphasized_chars":None,
                "native_span_chars":None,"emphasis_error":"cached source page unavailable"}
    total=emphasized=unknown=flags_present=0
    for line in page.get("lines",[]):
        for span in line.get("spans",[]):
            text=span.get("text","");count=len(re.sub(r"\s","",text))
            if not count:continue
            box=span.get("bbox",line.get("bbox"))
            if box is None:
                unknown+=count;continue
            if row.get("tile_count",1)>1 and not intersects(row["bbox"],box):continue
            total+=count
            font=span.get("font","");flags=span.get("flags")
            if type(flags) is int:flags_present+=count
            if not font and type(flags) is not int:
                unknown+=count;continue
            if EMPHASIS_FONT.search(font) or (type(flags) is int and flags&(bold_flag|italic_flag)):
                emphasized+=count
    if total==0 and re.search(r"\S",page.get("text","")):
        unknown=max(unknown,len(re.sub(r"\s","",page["text"])))
    result={"emphasis_status":"unknown" if unknown else "ok","native_emphasis_ratio":None if unknown else emphasized/max(1,total),
            "emphasized_chars":emphasized,"native_span_chars":total,"unknown_emphasis_chars":unknown,
            "chars_with_font_flags":flags_present,"bold_flag":bold_flag,"italic_flag":italic_flag}
    if unknown:result["emphasis_error"]="some cached text spans lack font or geometry evidence"
    return result


def read_source_metadata(rows):
    import pymupdf
    source=Path(rows[0]["source_path"]);expected=rows[0]["source_sha256"]
    if any(row["source_path"]!=str(source) or row["source_sha256"]!=expected for row in rows):
        raise ValueError("conflicting source identities inside metadata job")
    if sha(source)!=expected:raise ValueError("original source hash differs before metadata read")
    results=[];by_page=defaultdict(list)
    for row in rows:by_page[row["page"]].append(row)
    with pymupdf.open(source) as document:
        if document.needs_pass:raise ValueError("source PDF requires a password")
        for page_number,page_rows in by_page.items():
            try:
                page=document[page_number-1]
                annotations=[list(annotation.rect*page.rotation_matrix) for annotation in (page.annots() or [])]
                widgets=[list(widget.rect*page.rotation_matrix) for widget in (page.widgets() or [])]
                for row in page_rows:
                    results.append({"page_id":row["id"],"identity":row["identity"],"metadata_status":"ok",
                                    "annotation_count":sum(intersects(row["bbox"],box) for box in annotations),
                                    "widget_count":sum(intersects(row["bbox"],box) for box in widgets)})
            except Exception as error:
                for row in page_rows:
                    results.append({"page_id":row["id"],"identity":row["identity"],"metadata_status":"error",
                                    "annotation_count":None,"widget_count":None,"metadata_error":f"{type(error).__name__}: {error}"})
    if sha(source)!=expected:raise ValueError("original source hash differs after metadata read")
    return {"rows":results,"source_sha256_before":expected,"source_sha256_after":expected,
            "pymupdf_version":pymupdf.VersionBind,
            "font_flag_constants":{"bold":pymupdf.TEXT_FONT_BOLD,"italic":pymupdf.TEXT_FONT_ITALIC}}


def run(workspace,out,timeout=60):
    import pymupdf
    workspace=Path(workspace).resolve();out=Path(out).resolve()
    if not out.is_relative_to(workspace):raise ValueError("Extra evidence must stay inside review workspace")
    out.mkdir(parents=True,exist_ok=True);temp=out/"extra_pdf_work";temp.mkdir(exist_ok=True)
    pages=read_jsonl(workspace/"pages.jsonl");by_source=defaultdict(list)
    for row in pages:by_source[row["source_id"]].append(row)
    manifest=json.loads((workspace/"manifest.json").read_text(encoding="utf-8"));dataset=Path(manifest["dataset_path"])
    results=[];source_results=[];started=time.monotonic()
    for index,(source_id,rows) in enumerate(by_source.items(),1):
        task=uuid.uuid4().hex;request=temp/(task+".request.json");response=temp/(task+".response.json")
        atomic_json(request,rows)
        try:
            completed=subprocess.run([sys.executable,"-X","utf8",str(Path(__file__).resolve()),"--worker",str(request),"--response",str(response)],
                                     capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=timeout)
            if completed.returncode or not response.is_file():raise RuntimeError(completed.stderr[-2000:] or "metadata worker returned no result")
            metadata=json.loads(response.read_text(encoding="utf-8"))
            if "error" in metadata:raise RuntimeError(metadata["error"])
            metadata_by_id={row["page_id"]:row for row in metadata["rows"]}
            source_status={"source_id":source_id,"status":"ok","pages":len(rows),
                           "source_sha256_before":metadata["source_sha256_before"],"source_sha256_after":metadata["source_sha256_after"]}
        except Exception as error:
            message=f"{type(error).__name__}: {error}"
            metadata_by_id={row["id"]:{"page_id":row["id"],"identity":row["identity"],"metadata_status":"error",
                "annotation_count":None,"widget_count":None,"metadata_error":message} for row in rows}
            source_status={"source_id":source_id,"status":"error","pages":len(rows),"error":message}
        finally:
            request.unlink(missing_ok=True);response.unlink(missing_ok=True)
        cached=None;cached_error=None
        try:
            cached_path=dataset/"extracted"/(source_id+".json")
            cached=json.loads(cached_path.read_text(encoding="utf-8"))
            if cached.get("sha256")!=rows[0]["source_sha256"]:raise ValueError("cached extraction source hash differs")
            cached_pages={page["page"]:page for page in cached.get("pages",[])}
        except Exception as error:
            cached_pages={};cached_error=f"{type(error).__name__}: {error}"
        for row in rows:
            result={"schema":"bkquiz-extra-pdf-features-v1","version":VERSION,"page_id":row["id"],"identity":row["identity"],
                    "source_id":source_id,"source_sha256":row["source_sha256"],"page":row["page"],"bbox":row["bbox"],
                    **metadata_by_id[row["id"]],
                    **emphasis_features(row,cached_pages.get(row["page"]),pymupdf.TEXT_FONT_BOLD,pymupdf.TEXT_FONT_ITALIC)}
            if cached_error:result["emphasis_error"]=cached_error
            result["status"]="ok" if result["metadata_status"]=="ok" and result["emphasis_status"]=="ok" else "unknown"
            results.append(result)
        source_results.append(source_status)
        atomic_json(out/"extra_pdf_progress.json",{"sources_complete":index,"sources_total":len(by_source),"pages_complete":len(results),
                                                  "seconds":round(time.monotonic()-started,2),"source_status":dict(Counter(r["status"] for r in source_results))})
        if index%25==0:print(json.dumps({"sources_complete":index,"sources_total":len(by_source),"pages_complete":len(results)}),flush=True)
    path=out/"extra_pdf_features.jsonl"
    atomic_bytes(path,("\n".join(canonical(row) for row in results)+"\n").encode("utf-8"))
    report={"schema":"bkquiz-extra-pdf-features-report-v1","version":VERSION,"sources":len(by_source),"pages":len(results),
            "status":dict(Counter(r["status"] for r in results)),"metadata_status":dict(Counter(r["metadata_status"] for r in results)),
            "emphasis_status":dict(Counter(r["emphasis_status"] for r in results)),
            "pages_with_annotations":sum((r["annotation_count"] or 0)>0 for r in results),
            "pages_with_widgets":sum((r["widget_count"] or 0)>0 for r in results),
            "pages_with_emphasis":sum((r["native_emphasis_ratio"] or 0)>0 for r in results),
            "unknown_source_count":sum(r["status"]!="ok" for r in source_results),
            "font_flag_constants":{"bold":pymupdf.TEXT_FONT_BOLD,"italic":pymupdf.TEXT_FONT_ITALIC},
            "source_checks":source_results,"output_path":str(path),"output_sha256":sha(path),"seconds":round(time.monotonic()-started,2),
            "human_review_events_created":0,"native_text_extraction_performed":False}
    atomic_json(out/"extra_pdf_report.json",report)
    print(json.dumps({k:v for k,v in report.items() if k!="source_checks"},ensure_ascii=False,indent=2),flush=True)
    return report


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--workspace",type=Path);parser.add_argument("--out",type=Path)
    parser.add_argument("--timeout",type=float,default=60);parser.add_argument("--worker",type=Path);parser.add_argument("--response",type=Path)
    args=parser.parse_args()
    if args.worker:
        try:value=read_source_metadata(json.loads(args.worker.read_text(encoding="utf-8")))
        except Exception as error:value={"error":f"{type(error).__name__}: {error}"}
        atomic_json(args.response,value)
    else:
        if args.workspace is None or args.out is None:parser.error("--workspace and --out are required")
        run(args.workspace,args.out,args.timeout)
