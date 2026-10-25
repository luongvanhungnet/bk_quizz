"""Turn authorized native/OCR text into source-faithful stage-two candidates.

No answer is solved or guessed and no human review event is generated. Pages
whose option layout cannot be recovered from text are reported for VLM routing.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
import time
import unicodedata

from colab_runtime.runtime import atomic_json
from sft_review_store import SFTReviewStore, canonical_hash, file_sha256, question_identity


PARSER_REVISION="source-text-questions-v2-verified-footer"
HEAD=re.compile(r"^\s*(?:Câu\s*(?:hỏi\s*)?|Question\s*|Q\.\s*)(#[A-Za-z0-9_-]+|\d+[a-z]?)\s*[:.)-]?\s*(.*)$",re.I)
NUMERIC_HEAD=re.compile(r"^\s*(\d+)\s*[.)]\s+([A-ZÀ-Ỹ][^\n]{8,})$")
OPTION=re.compile(r"^\s*([A-Ha-h])(?:[.)]\s*|\s+)(.*)$")
KEY=re.compile(r"^\s*(?:the\s+correct\s+answers?\s+(?:is|are)\s*:?[ \t]*|(?:đáp\s*án|ANSWER)\s*:[ \t]*)(.*)$",re.I)
SOLUTION=re.compile(r"^\s*(?:Lời\s*giải|Hướng\s*dẫn\s*giải|Solution|Explanation)\s*:\s*(.*)$",re.I)
UI=re.compile(r"^(?:Correct|Incorrect|Partially correct|Not answered|Unanswered|Hide sidebars|Hide|sidebars|Gửi|Auto-graded|Mark(?:ed)?\s+(?:out|\d).*|\d+(?:\.\d+)?\s*/\s*\d+(?:\.\d+)?\s*(?:Points|pts?)|(?:Trang|Page)\s*\d+\s*/\s*\d+)$",re.I)


def normalized(value):
    return re.sub(r"[^\w]","",unicodedata.normalize("NFC",value).casefold())


def lines_from_text(text):
    # str.splitlines is suitable for a text document, unlike a JSONL container.
    output=[]
    for value in unicodedata.normalize("NFC",text).replace("\r\n","\n").splitlines():
        value=value.strip()
        if not value or UI.fullmatch(value):continue
        if re.fullmatch(r"[\ue000-\uf8ff\s]{1,6}",value):continue
        if re.fullmatch(r"(?:Attempt review|Dashboard|Jump to\.\.\.)",value,re.I):continue
        output.append(value)
    return output


def split_question_chunks(lines):
    heads=[(i,HEAD.match(line)) for i,line in enumerate(lines) if HEAD.match(line)]
    if heads:
        return [(match.group(1),[match.group(2)]+lines[i+1:heads[j+1][0] if j+1<len(heads) else len(lines)])
                for j,(i,match) in enumerate(heads)],[]
    # Some banks terminate each item with a strict ANSWER letter line.
    answer_ends=[i for i,line in enumerate(lines) if re.fullmatch(r"ANSWER\s*:\s*[A-H](?:\s*[,;]\s*[A-H])*\s*[.]?",line)]
    if answer_ends:
        chunks=[];start=0
        for i in answer_ends:
            chunks.append(("",lines[start:i+1]));start=i+1
        if start<len(lines):chunks.append(("",lines[start:]))
        return chunks,[]
    numeric=[(i,NUMERIC_HEAD.match(line)) for i,line in enumerate(lines) if NUMERIC_HEAD.match(line)]
    code=re.search(r"\b(?:public\s+(?:class|void)|int\s+main|printf|pthread_|#include|return\s+\w)","\n".join(lines))
    if len(numeric)>=2 and not code:
        return [(match.group(1),[match.group(2)]+lines[i+1:numeric[j+1][0] if j+1<len(numeric) else len(lines)])
                for j,(i,match) in enumerate(numeric)],[]
    return [("",lines)],["unsegmented_page_text"]


def parse_chunk(number,chunk,base_flags):
    chunk=[line for line in chunk if line]
    if not chunk:return None
    flags=list(base_flags)
    key_at=next((i for i,line in enumerate(chunk) if KEY.match(line)),None)
    key_match=KEY.match(chunk[key_at]) if key_at is not None else None
    solution_at=next((i for i,line in enumerate(chunk) if SOLUTION.match(line)),None)
    body_end=min([i for i in [key_at,solution_at] if i is not None],default=len(chunk))
    body=chunk[:body_end]
    answer={"labels":[],"text":"","evidence":"","origin":"missing"}
    if key_match:
        key_end=solution_at if solution_at is not None and solution_at>key_at else len(chunk)
        answer_text="\n".join([key_match.group(1)]+chunk[key_at+1:key_end]).strip().strip("'\" .")
        answer={"labels":[],"text":answer_text,"evidence":"\n".join(chunk[key_at:key_end]),"origin":"printed_key"}
    solution=""
    if solution_at is not None:
        solution="\n".join([SOLUTION.match(chunk[solution_at]).group(1)]+chunk[solution_at+1:]).strip()
    starts=[(i,OPTION.match(line)) for i,line in enumerate(body) if OPTION.match(line)]
    labels=[match.group(1).upper() for _,match in starts]
    sequential=bool(starts and labels==[chr(65+i) for i in range(len(labels))] and 2<=len(labels)<=8)
    options=[]
    if sequential:
        first=starts[0][0]
        for index,(start,match) in enumerate(starts):
            end=starts[index+1][0] if index+1<len(starts) else len(body)
            options.append({"label":match.group(1).upper(),"text":"\n".join([match.group(2)]+body[start+1:end]).strip(),"source_marking":""})
        prompt="\n".join(body[:first]).strip()
        prompt=re.sub(r"\n?Select one(?: or more)?:\s*$","",prompt,flags=re.I).strip()
    else:
        selector=next((i for i,line in enumerate(body) if re.fullmatch(r"Select one:",line,re.I)),None)
        if selector is not None and body[selector+1:selector+3] in [["True","False"],["False","True"]]:
            prompt="\n".join(body[:selector]).strip()
            options=[{"label":"","text":value,"source_marking":""} for value in body[selector+1:selector+3]]
            if body[selector+3:]:
                prompt+="\n\n"+"\n".join(body[selector+3:])
                flags.append("option_layout_requires_vlm")
        else:
            prompt="\n".join(body).strip()
            if starts or selector is not None:flags.append("option_layout_requires_vlm")
    if answer["origin"]=="missing":flags.append("no_printed_answer")
    else:
        bare=re.fullmatch(r"([A-H](?:\s*[,;]\s*[A-H])*)",answer["text"],re.I)
        if bare:
            answer["labels"]=[v.upper() for v in re.split(r"\s*[,;]\s*",bare.group(1))]
            if not set(answer["labels"]).issubset({o["label"] for o in options}):flags.append("printed_key_label_missing_option")
        else:
            answer["labels"]=[o["label"] for o in options if o["label"] and normalized(o["text"])==normalized(answer["text"])]
    if any(not option["text"] for option in options):flags.append("empty_option_text")
    if re.search(r"(?:hình|sơ đồ|biểu đồ|bảng).{0,35}(?:sau|dưới|trên)|shown\s+(?:below|above)",prompt,re.I):flags.append("visual_reference_in_text")
    if re.search(r"\(đạt\s+\d+\s*/\s*\d+",prompt,re.I):flags.append("attempt_grade_is_not_answer_evidence")
    if re.search(r"[\ue000-\uf8ff\ufffd]",prompt+" ".join(o["text"] for o in options)):flags.append("unresolved_text_glyphs")
    if not prompt:return None
    if len(prompt)<10:flags.append("short_source_prompt")
    if len(prompt)>100000:raise ValueError("Page text too large for a single candidate; preserve and reroute to VLM")
    return {"source_number":number,"prompt":prompt,"options":options,"answer":answer,"solution":solution,
            "flags":list(dict.fromkeys(flags+["automatic_text_extraction_requires_round2_review"]))}


def remove_verified_footer(text, footer_text=None):
    """Remove only a caller-proven exact, unique, final physical line.

    Geometry/source checks belong to native_footer_evidence and the bound route.
    No footer is inferred from its appearance or from the final digit alone.
    """
    if footer_text is None:return text,[]
    transform={"kind":"verified_native_footer_removal","footer_text":footer_text,"applied":False}
    if not isinstance(footer_text,str) or not re.fullmatch(r"[1-9][0-9]{0,5}",footer_text):
        transform["reason"]="invalid_exact_decimal_footer"
        return text,[transform]
    physical=text.splitlines(keepends=True)
    nonempty=[index for index,line in enumerate(physical) if line.strip()]
    matches=[index for index,line in enumerate(physical) if line.strip()==footer_text]
    if not nonempty or matches!=[nonempty[-1]]:
        transform["reason"]="footer_is_not_unique_exact_last_nonempty_line"
        return text,[transform]
    index=nonempty[-1]
    clean="".join(physical[:index]+physical[index+1:])
    transform.update(applied=True,line_number=index+1,removed_line=physical[index].rstrip("\r\n"),
                     raw_text_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                     transformed_text_sha256=hashlib.sha256(clean.encode("utf-8")).hexdigest())
    return clean,[transform]


def extract_questions(text,footer_text=None):
    prepared,transforms=remove_verified_footer(text,footer_text)
    footer_failed=bool(transforms and not transforms[0]["applied"])
    lines=lines_from_text(prepared)
    if not lines:return {"questions":[],"flags":["no_readable_text"],"requires_vlm":footer_failed,"text_transforms":transforms}
    chunks,base_flags=split_question_chunks(lines)
    questions=[question for number,chunk in chunks if (question:=parse_chunk(number,chunk,base_flags)) is not None]
    # A passage or shared instruction before the first numbered item belongs
    # to the source. Keep it visible in every candidate rather than silently
    # losing the context while splitting the numbered questions.
    first_head=next((i for i,line in enumerate(lines) if HEAD.match(line)),None)
    if first_head is None and chunks and chunks[0][0]:
        first_head=next((i for i,line in enumerate(lines) if NUMERIC_HEAD.match(line)),None)
    if first_head is not None and first_head>0:
        preamble="\n".join(lines[:first_head]).strip()
        for question in questions:
            question["source_context"]=preamble
            question["prompt"]=preamble+"\n\n"+question["prompt"]
            question["flags"].append("page_preamble_preserved_as_context")
            if re.search(r"[\ue000-\uf8ff\ufffd]",preamble):question["flags"].append("unresolved_text_glyphs")
    requires_vlm=footer_failed or any("option_layout_requires_vlm" in q["flags"] or "unresolved_text_glyphs" in q["flags"] for q in questions)
    if transforms and transforms[0]["applied"]:
        for question in questions:question["flags"].append("verified_native_footer_removed")
    return {"questions":questions,"flags":base_flags,"requires_vlm":requires_vlm,"text_transforms":transforms}


def route_footer_text(route,page):
    """Validate a policy-bound native footer before applying its text change."""
    value=route.get("footer_text")
    if value is None:return None
    if route.get("route")!="native_text":raise ValueError("Verified footer removal only supports native PDF text")
    if value!=str(page["page"]):raise ValueError("Footer does not equal the exact source page number")
    if page.get("tile_count",1)!=1 or page.get("tile_index",0)!=0:raise ValueError("Footer removal cannot be applied to clipped tiles")
    width,height=page.get("source_width"),page.get("source_height")
    if not isinstance(width,(float,int)) or not isinstance(height,(float,int)):
        raise ValueError("Footer removal requires verified full-page dimensions")
    full=[0.,0.,float(width),float(height)]
    if any(abs(float(left)-right)>.01 for left,right in zip(page["bbox"],full)):
        raise ValueError("Footer removal requires the full source page")
    box=route.get("footer_bbox")
    if (not isinstance(box,list) or len(box)!=4 or any(type(v) not in {int,float} or not math.isfinite(v) for v in box)
            or not 0<=box[0]<box[2]<=width or not .9*height<=box[1]<box[3]<=height):
        raise ValueError("Footer removal requires a verified bottom-page bounding box")
    return value


def read_source_text(path):
    path=Path(path)
    if path.suffix.lower()==".json":
        value=json.loads(path.read_text(encoding="utf-8-sig"))
        text=value.get("text",value.get("native_text",value.get("ocr_text")))
        if not isinstance(text,str):raise ValueError("Text evidence JSON has no text field")
        return text
    return path.read_text(encoding="utf-8-sig")


def import_auto_text_questions(workspace,routes_path=None,dry_run=False):
    workspace=Path(workspace).resolve();store=SFTReviewStore(workspace)
    pointer=json.loads((workspace/"auto_routing_current.json").read_text(encoding="utf-8"))
    def resolve(value):
        path=Path(value)
        path=(workspace/path).resolve() if not path.is_absolute() else path.resolve()
        if not path.is_relative_to(workspace):raise ValueError("Text routing path escapes workspace")
        return path
    policy_path=resolve(pointer["policy_path"]);routing_path=resolve(routes_path or pointer["routing_path"])
    if file_sha256(policy_path)!=pointer["policy_sha256"] or file_sha256(routing_path)!=pointer["routing_sha256"]:raise ValueError("Routing snapshot hash mismatch")
    policy=json.loads(policy_path.read_text(encoding="utf-8"))
    if policy.get("automatic_stage1_authorized") is not True:raise ValueError("Automatic text extraction is not authorized")
    with routing_path.open(encoding="utf-8") as stream:routes=[json.loads(line) for line in stream if line.strip()]
    selected=[row for row in routes if row.get("route") in {"native_text","ocr_text"}]
    report={"schema":"bkquiz-auto-text-import-v1","policy_id":policy["policy_id"],"policy_sha256":pointer["policy_sha256"],
            "pages_considered":len(selected),"pages_imported":0,"questions_in_text":0,"new_questions_imported":0,
            "requires_vlm":[],"no_questions":[],"errors":[],"dry_run":dry_run,"human_review_events_created":0,
            "round2_approval_required":True,"parser_revision":PARSER_REVISION}
    output=workspace/"auto_text_results"/policy["policy_id"];output.mkdir(parents=True,exist_ok=True)
    for number,route in enumerate(selected,1):
        page_id=route["page_id"]
        try:
            text_path=resolve(route["text_path"]);text_sha=file_sha256(text_path)
            if text_sha!=route["text_sha256"]:raise ValueError("Native/OCR text hash changed")
            current=store.verify_text_page(page_id,text_sha,policy["policy_id"],routing_identity=canonical_hash(route),
                                           routing_policy_sha256=pointer["policy_sha256"])
            text=read_source_text(text_path);footer=route_footer_text(route,current)
            parsed=extract_questions(text,footer_text=footer)
            result={"schema":"bkquiz-automatic-text-result-v1","parser_revision":PARSER_REVISION,"page_id":page_id,
                    "page_identity":route["identity"],"extraction_origin":route["route"],"source_text_path":str(text_path),
                    "text_sha256":text_sha,"raw_text":text,"parsed":parsed,"text_transforms":parsed["text_transforms"],
                    "footer_source_evidence":{key:route[key] for key in ("footer_text","footer_bbox","footer_evidence_path","footer_evidence_sha256") if key in route},
                    "routing_identity":canonical_hash(route),
                    "routing_policy_id":policy["policy_id"],"routing_policy_sha256":pointer["policy_sha256"],"human_verified":False}
            result_sha=canonical_hash(result);result_path=output/(page_id+"_"+result_sha[:16]+".json")
            if result_path.exists():
                if json.loads(result_path.read_text(encoding="utf-8"))!=result:raise ValueError("Immutable text result conflict")
            else:atomic_json(result_path,result)
            if parsed["requires_vlm"]:
                report["requires_vlm"].append({"page_id":page_id,"result_path":str(result_path),"reason":"text_option_or_glyph_layout_incomplete"});continue
            if not parsed["questions"]:
                report["no_questions"].append({"page_id":page_id,"result_path":str(result_path)});continue
            rows=[]
            for index,question in enumerate(parsed["questions"]):
                row={"id":"qt_"+canonical_hash({"page_id":page_id,"result_sha256":result_sha,"index":index})[:24],
                     "page_id":page_id,"text_sha256":text_sha,"source_text_path":str(text_path),
                     "result_sha256":result_sha,"extraction_origin":route["route"],"question":question,
                     "routing_policy_id":policy["policy_id"],"routing_policy_sha256":pointer["policy_sha256"],
                     "routing_identity":canonical_hash(route),"raw_result_path":str(result_path),"human_verified":False}
                row["identity"]=question_identity(row);rows.append(row)
            report["questions_in_text"]+=len(rows)
            if not dry_run:
                receipt=store.import_text_questions(rows,"text:"+result_sha)
                report["new_questions_imported"]+=receipt.get("imported",0)
                report["pages_imported"]+=1
        except Exception as error:
            report["errors"].append({"page_id":page_id,"error":f"{type(error).__name__}: {error}"})
        if number%100==0:print(json.dumps({"text_pages":number,"total":len(selected),"new_questions":report["new_questions_imported"],"requires_vlm":len(report["requires_vlm"]),"errors":len(report["errors"])}),flush=True)
    stamp=str(time.time_ns());report_path=output/("import_report_"+stamp+".json")
    atomic_json(report_path,report);report["report_path"]=str(report_path)
    atomic_json(workspace/"LATEST_AUTO_TEXT_IMPORT.json",report)
    return report


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--workspace",type=Path,required=True)
    parser.add_argument("--routes-path",type=Path);parser.add_argument("--dry-run",action="store_true")
    args=parser.parse_args();result=import_auto_text_questions(args.workspace,args.routes_path,args.dry_run)
    print(json.dumps(result,ensure_ascii=False,indent=2))
