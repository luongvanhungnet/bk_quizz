"""Native PDF evidence for automatic page routing; no human decisions are written."""
from __future__ import annotations

import argparse
from collections import Counter,defaultdict
import hashlib
import json
from pathlib import Path
import re
import unicodedata


def read_jsonl(path):
    with Path(path).open(encoding="utf-8-sig") as stream:return [json.loads(line) for line in stream if line.strip()]


def sha(path):
    with Path(path).open("rb") as stream:return hashlib.file_digest(stream,"sha256").hexdigest()


def write_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")


def overlap(left,right):
    return max(0,min(left[2],right[2])-max(left[0],right[0]))*max(0,min(left[3],right[3])-max(left[1],right[1]))


def features(row,page):
    box=row["bbox"];area=max(1,(box[2]-box[0])*(box[3]-box[1]))
    lines=[line for line in page.get("lines",[]) if overlap(box,line["bbox"])>0]
    text=page.get("text","") if row.get("tile_count",1)==1 else "\n".join(line["text"] for line in lines)
    text=unicodedata.normalize("NFC",text)
    chars=len(re.sub(r"\s","",text));word=re.findall(r"\w+",text,flags=re.U)
    bad=len(re.findall(r"[\ue000-\uf8ff\ufffd]|[\x00-\x08\x0b\x0c\x0e-\x1f]",text))
    math_chars=sum(len(span.get("text","")) for line in lines for span in line.get("spans",[]) if re.search(r"math|symbol|cmsy|cmmi|cmex|msbm",span.get("font",""),re.I))
    color_chars=sum(len(span.get("text","")) for line in lines for span in line.get("spans",[]) if span.get("color",0) not in [0,16777215,2368548])
    images=[im for im in page.get("images",[]) if overlap(box,im["bbox"])>0]
    image_coverage=min(1,sum(overlap(box,im["bbox"]) for im in images)/area)
    native_coverage=min(1,sum(overlap(box,line["bbox"]) for line in lines)/area)
    visual_key=bool(re.search(r"\bCorrected\b|\bCorrect\s*\d+/\d+\s*Points|đạt\s+\d+/\d+",text,re.I))
    explicit_key=bool(re.search(r"the correct answer|ANSWER\s*:|đáp\s*án\s*:",text,re.I))
    return {"page_id":row["id"],"identity":row["identity"],"source_id":row["source_id"],"page":row["page"],
            "native_chars":chars,"native_words":len(word),"native_bad_glyphs":bad,"native_bad_ratio":bad/max(1,chars),
            "native_math_font_ratio":math_chars/max(1,chars),"native_color_ratio":color_chars/max(1,chars),
            "native_long_word_ratio":sum(len(w)>35 for w in word)/max(1,len(word)),
            "native_letters_ratio":sum(c.isalpha() for c in text)/max(1,chars),
            "image_coverage":image_coverage,"image_count":len(images),"native_text_area":native_coverage,
            "drawing_count":page.get("drawing_count",0),"visual_answer_markings":visual_key,"explicit_answer_key":explicit_key,
            "source_risk_flags":row.get("reasons",[]),"text":text}


def run(workspace,out):
    workspace=Path(workspace).resolve();out=Path(out).resolve();out.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((workspace/"manifest.json").read_text(encoding="utf-8"));dataset=Path(manifest["dataset_path"])
    by_source=defaultdict(list)
    for row in read_jsonl(workspace/"pages.jsonl"):by_source[row["source_id"]].append(row)
    results=[]
    for source_id,rows in by_source.items():
        document=json.loads((dataset/"extracted"/(source_id+".json")).read_text(encoding="utf-8"))
        pages={page["page"]:page for page in document["pages"]}
        for row in rows:
            value=features(row,pages.get(row["page"],{}))
            text=value.pop("text")
            path=out/"native_text"/(row["id"]+".txt");path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(text,encoding="utf-8",newline="\n")
            value.update(text_path=path.relative_to(workspace).as_posix(),text_sha256=sha(path),
                         source_extraction_status=document.get("status"))
            evidence=out/"native"/(row["id"]+".json")
            write_json(evidence,value)
            value.update(analysis_path=evidence.relative_to(workspace).as_posix(),analysis_sha256=sha(evidence))
            results.append(value)
    with (out/"native_features.jsonl").open("w",encoding="utf-8",newline="\n") as stream:
        for row in results:stream.write(json.dumps(row,ensure_ascii=False)+"\n")
    summary={"pages":len(results),"native_ge300":sum(r["native_chars"]>=300 for r in results),
             "native_lt80":sum(r["native_chars"]<80 for r in results),"bad_glyphs_ge5":sum(r["native_bad_glyphs"]>=5 for r in results),
             "math_font_gt5pct":sum(r["native_math_font_ratio"]>.05 for r in results),
             "raster_majority":sum(r["image_coverage"]>.5 for r in results),
             "source_extraction_status":dict(Counter(r["source_extraction_status"] for r in results)),"human_decisions_created":0}
    write_json(out/"native_summary.json",summary);print(json.dumps(summary,ensure_ascii=False,indent=2))
    return results


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--workspace",type=Path,required=True);parser.add_argument("--out",type=Path,required=True)
    args=parser.parse_args();run(args.workspace,args.out)
