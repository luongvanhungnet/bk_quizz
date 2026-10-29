"""Prove narrow native PDF page-number footers without changing source text."""
from __future__ import annotations

import argparse
from collections import Counter,defaultdict
import hashlib
import json
import math
from pathlib import Path

from colab_runtime.runtime import atomic_bytes,atomic_json
from sft_review_store import canonical_hash,file_sha256


REVISION="native-page-number-footer-v2-separated-template"


def _footer_candidate(page,native,extracted,text):
    def reject(reason):return None,reason
    if page.get("tile_count",1)!=1 or page.get("tile_index",0)!=0:return reject("clipped_or_multiple_tiles")
    width,height=extracted.get("width"),extracted.get("height")
    if any(type(v) not in {float,int} or not math.isfinite(v) or v<=0 for v in (width,height)):
        return reject("unknown_page_dimensions")
    expected=[0.,0.,float(width),float(height)]
    if len(page.get("bbox",[]))!=4 or any(abs(float(left)-right)>.01 for left,right in zip(page["bbox"],expected)):
        return reject("not_full_source_page")
    if native.get("image_count",1)!=0:return reject("raster_image_present")
    lines=[line for line in extracted.get("lines",[]) if isinstance(line.get("text"),str) and line["text"].strip()]
    if not lines:return reject("no_native_physical_lines")
    def valid_box(box):
        return (isinstance(box,list) and len(box)==4 and all(type(v) in {float,int} and math.isfinite(v) for v in box)
                and 0<=box[0]<box[2]<=width and 0<=box[1]<box[3]<=height)
    if any(not valid_box(line.get("bbox")) for line in lines):return reject("invalid_native_line_geometry")
    last=max(lines,key=lambda line:(line["bbox"][1],line["bbox"][3],line["bbox"][0]))
    footer=str(page["page"])
    if last["text"].strip()!=footer:return reject("last_native_physical_line_is_not_page_number")
    box=last["bbox"]
    if box[1]<.9*height or box[3]-box[1]>min(30.,.05*height):return reject("footer_not_narrow_bottom_line")
    other=[line for line in lines if line is not last]
    closest=max([line["bbox"][3] for line in other] or [0])
    gap=box[1]-closest
    minimum_gap=max(12.,1.5*(box[3]-box[1]))
    if gap<minimum_gap:return reject("footer_not_separated_from_source_content")
    physical=[line.strip() for line in text.splitlines() if line.strip()]
    if not physical or physical[-1]!=footer or physical.count(footer)!=1:
        return reject("footer_not_unique_exact_last_text_line")
    proof={"schema":"bkquiz-native-footer-proof-v1","revision":REVISION,"page_id":page["id"],
           "identity":page["identity"],"source_id":page["source_id"],"source_sha256":page["source_sha256"],
           "page":page["page"],"page_bbox":page["bbox"],"source_width":width,"source_height":height,
           "footer_text":footer,"footer_bbox":box,"native_text_sha256":hashlib.sha256(text.encode("utf-8")).hexdigest(),
           "physical_native_line_count":len(lines),"closest_other_line_bottom":closest,"vertical_gap_points":gap,
           "minimum_vertical_gap_points":minimum_gap,
           "checks":{"full_source_page":True,"exact_source_page_number":True,"last_physical_native_line":True,
                     "unique_exact_last_text_line":True,"bottom_ten_percent":True,"no_content_overlap":True},
           "human_verified":False,"human_review_events_created":0}
    return proof,None


def identify_footer(page,native,extracted,text,position_evidence=None):
    """Require a separated central footer or a repeated source footer template."""
    proof,reason=_footer_candidate(page,native,extracted,text)
    if proof is None:return None,reason
    box=proof["footer_bbox"];width=proof["source_width"];height=proof["source_height"]
    central=abs((box[0]+box[2])/2-width/2)<=.15*width
    position={"kind":"central_footer","center_distance_fraction":abs((box[0]+box[2])/2-width/2)/width}
    if not central:
        evidence=position_evidence or {}
        support=evidence.get("source_pages",[])
        valid=(evidence.get("source_sha256")==page["source_sha256"] and isinstance(support,list)
               and all(type(v) is int and v>0 for v in support) and len(set(support))>=3
               and page["page"] in support
               and type(evidence.get("anchor_left_fraction")) in {float,int}
               and type(evidence.get("anchor_top_fraction")) in {float,int}
               and abs(box[0]/width-evidence["anchor_left_fraction"])<=.005
               and abs(box[1]/height-evidence["anchor_top_fraction"])<=.005)
        if not valid:return None,"offcenter_footer_without_consistent_source_template"
        position=dict(evidence,kind="consistent_source_footer_template",source_page_count=len(set(support)))
    proof["position_evidence"]=position
    proof["checks"]["central_or_repeated_source_footer_position"]=True
    return proof,None


def build(workspace,evidence_dir=None):
    workspace=Path(workspace).resolve();out=Path(evidence_dir or workspace/"auto_triage_20261025").resolve()
    if not out.is_relative_to(workspace):raise ValueError("Footer evidence must remain within the review workspace")
    manifest=json.loads((workspace/"manifest.json").read_text(encoding="utf-8-sig"))
    dataset=Path(manifest["dataset_path"])
    with (workspace/"pages.jsonl").open(encoding="utf-8-sig") as stream:pages=[json.loads(line) for line in stream if line.strip()]
    with (out/"native_features.jsonl").open(encoding="utf-8-sig") as stream:native={row["page_id"]:row for row in map(json.loads,stream)}
    by_source=defaultdict(list)
    for page in pages:by_source[page["source_id"]].append(page)
    records=[];rejections=Counter()
    for source_id,rows in by_source.items():
        extraction_path=dataset/"extracted"/(source_id+".json")
        body=extraction_path.read_bytes();document=json.loads(body);extraction_sha=hashlib.sha256(body).hexdigest()
        extracted={p["page"]:p for p in document.get("pages",[])}
        if document.get("sha256")!=rows[0]["source_sha256"]:
            rejections["cached_extraction_source_hash_mismatch"]+=len(rows);continue
        pending=[];candidates=[]
        for page in rows:
            n=native[page["id"]]
            if n.get("identity")!=page["identity"]:raise ValueError("Native evidence identity changed")
            if n.get("image_count",1)!=0 or n.get("native_chars",0)<1:
                rejections["not_native_only_text_page"]+=1;continue
            text_path=(workspace/n["text_path"]).resolve()
            if not text_path.is_relative_to(workspace) or file_sha256(text_path)!=n["text_sha256"]:
                raise ValueError("Native source text changed: "+page["id"])
            text=text_path.read_text(encoding="utf-8-sig")
            candidate,reason=_footer_candidate(page,n,extracted.get(page["page"],{}),text)
            if candidate is None:rejections[reason]+=1;continue
            pending.append((page,n,text,candidate));candidates.append(candidate)
        for page,n,text,candidate in pending:
            left=candidate["footer_bbox"][0]/candidate["source_width"]
            top=candidate["footer_bbox"][1]/candidate["source_height"]
            support=[c for c in candidates if abs(c["footer_bbox"][0]/c["source_width"]-left)<=.005
                     and abs(c["footer_bbox"][1]/c["source_height"]-top)<=.005]
            position={"source_sha256":page["source_sha256"],"source_pages":sorted({c["page"] for c in support}),
                      "anchor_left_fraction":left,"anchor_top_fraction":top,"position_tolerance_fraction":.005,
                      "support_footer_bboxes":[{"page":c["page"],"bbox":c["footer_bbox"],
                                               "gap_points":c["vertical_gap_points"]} for c in support]}
            proof,reason=identify_footer(page,n,extracted.get(page["page"],{}),text,position_evidence=position)
            if proof is None:rejections[reason]+=1;continue
            proof.update(cached_extraction_path=str(extraction_path),cached_extraction_sha256=extraction_sha,
                         native_text_path=n["text_path"],native_text_file_sha256=n["text_sha256"])
            key=canonical_hash(proof);path=out/"native_footer_evidence"/(page["id"]+"_"+key[:16]+".json")
            atomic_json(path,proof)
            records.append({"page_id":page["id"],"identity":page["identity"],"source_sha256":page["source_sha256"],
                            "page":page["page"],"footer_text":proof["footer_text"],"footer_bbox":proof["footer_bbox"],
                            "analysis_path":path.relative_to(workspace).as_posix(),"analysis_sha256":file_sha256(path),
                            "human_verified":False})
    target=out/"native_footer_evidence.jsonl"
    atomic_bytes(target,("\n".join(json.dumps(row,ensure_ascii=False,sort_keys=True) for row in records)+"\n").encode("utf-8"))
    report={"schema":"bkquiz-native-footer-evidence-report-v1","revision":REVISION,"pages":len(pages),"proven_footers":len(records),
            "rejections":dict(rejections),"index_path":str(target),"index_sha256":file_sha256(target),"human_review_events_created":0}
    atomic_json(out/"native_footer_report.json",report);print(json.dumps(report,ensure_ascii=False,indent=2))
    return report


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--workspace",type=Path,required=True);parser.add_argument("--evidence-dir",type=Path)
    args=parser.parse_args();build(args.workspace,args.evidence_dir)
