"""Build source-faithful grounded quiz SFT with document-grouped holdouts."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import random
import re

from extract_questions import key, write_jsonl
from scan_sources import dump

SYSTEM = """Bạn biên soạn câu hỏi ôn tập dựa trên tài liệu được cung cấp. Chỉ dùng kiến thức và đáp án có trong ngữ cảnh. Trả về duy nhất JSON có khóa questions. Mỗi câu gồm type (SINGLE_CHOICE hoặc MULTIPLE_SELECT), prompt, explanation, options (mỗi lựa chọn có text và correct), acceptedAnswers (mảng rỗng đối với câu trắc nghiệm), questionCitations, answerCitations, explanationCitations (mỗi trích dẫn gồm sourceId và evidenceQuote nguyên văn từ ngữ cảnh). SINGLE_CHOICE có đúng một lựa chọn đúng; MULTIPLE_SELECT có từ hai lựa chọn đúng. Giữ đúng ý nghĩa của câu hỏi và đáp án nguồn. Giải thích ngắn gọn, không tự bổ sung lời giải khi nguồn chỉ nêu đáp án."""


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonical(record: dict) -> str:
    return key(record["prompt"]) + "|" + "|".join(sorted(key(o["text"]) for o in record["options"]))


def correct_signature(record: dict) -> tuple:
    return tuple(sorted(key(o["text"]) for o in record["options"] if o["correct"]))


class UnionFind:
    def __init__(self, values):
        self.parent = {v:v for v in values}

    def find(self,value):
        if self.parent[value]!=value:
            self.parent[value]=self.find(self.parent[value])
        return self.parent[value]

    def union(self,left,right):
        a,b=self.find(left),self.find(right)
        self.parent[max(a,b)]=min(a,b)


def shingles(value: str) -> set[str]:
    value=re.sub(r"\d+","#",key(value))
    return {value[i:i+5] for i in range(max(0,len(value)-4))}


def jaccard(left: set, right: set) -> float:
    return len(left&right)/max(1,len(left|right))


def quality(record: dict) -> tuple:
    priority={"moodle_explicit_key":4,"native_answer_letter":4,"inline_explicit_key":3,
              "corrected_filled_circle":2,"forms_full_credit_radio":1}
    return (bool(record.get("explanation_source")),priority.get(record["parser"],0),-len(record["raw_text"]),record["id"])


def choose_holdout(groups: list[tuple[str,list[dict]]],target: int,seed: int) -> set[str]:
    # Deterministic subset-sum over whole connected source components.
    ordered=groups.copy();random.Random(seed).shuffle(ordered)
    possibilities={0:()}
    for identity,rows in ordered:
        for count,selection in list(possibilities.items()):
            total=count+len(rows)
            if total<=max(target*2,target+50) and total not in possibilities:
                possibilities[total]=selection+(identity,)
    nonzero=[n for n in possibilities if n]
    if not nonzero:
        return {min(ordered,key=lambda item:len(item[1]))[0]} if ordered else set()
    best=min(nonzero,key=lambda n:(abs(n-target),n>target,n))
    return set(possibilities[best])


def prepare_records(candidates: list[dict], semantic_exclusions: list[dict]) -> tuple[list[dict],list[dict],dict]:
    exclusions=[];valid=[]
    for record in candidates:
        reasons=[]
        for exclusion in semantic_exclusions:
            if record["id"]==exclusion.get("id") or (record["source_id"]==exclusion.get("source_id") and key(record["prompt"])==key(exclusion.get("prompt",""))):
                reasons.append(exclusion.get("reason","source_key_semantic_contradiction"))
        if all(o["correct"] for o in record["options"]):
            reasons.append("no_incorrect_distractor")
        answer="; ".join(o["text"] for o in record["options"] if o["correct"])
        if re.search(r"tất cả|tất các|không (?:có )?(?:đáp án|lựa chọn)|không lựa chọn|all (?:of|the)|none of|cả [abcd]|^[a-h](?:\s*[,;và]+\s*[a-h])*$",answer,re.I):
            reasons.append("correct_answer_depends_on_unprovided_alternatives")
        if re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}",record["prompt"]+answer):
            reasons.append("personal_contact_in_training_content")
        if len(record["prompt"])>1000 or any(len(o["text"])>1000 for o in record["options"] if o["correct"]):
            reasons.append("citation_quote_exceeds_schema_limit")
        if reasons:
            exclusions.append({**record,"status":"excluded_from_release","reasons":reasons})
        else:
            valid.append(record)
    by_content=defaultdict(list)
    for record in valid:
        by_content[canonical(record)].append(record)
    union=UnionFind({r["source_id"] for r in valid})
    unique=[];duplicates=[];conflicts=[]
    for identity,rows in sorted(by_content.items()):
        for row in rows[1:]:
            union.union(rows[0]["source_id"],row["source_id"])
        if len({correct_signature(r) for r in rows})>1:
            conflicts.extend({**r,"status":"excluded_from_release","reasons":["conflicting_source_answer_keys"]} for r in rows)
            continue
        chosen=max(rows,key=quality).copy()
        chosen["origins"]=[{"id":r["id"],"source_id":r["source_id"],"path":r["source_path"],
                            "sha256":r["source_sha256"],"relative_path":r["source_relative_path"],
                            "pages":r["pages"],"regions":r["regions"]} for r in sorted(rows,key=lambda r:r["id"])]
        chosen["content_sha256"]=digest(identity)
        unique.append(chosen)
        duplicates.extend({"id":r["id"],"kept_id":chosen["id"],"source_id":r["source_id"],"reason":"exact_normalized_question_and_unordered_options"} for r in rows if r["id"]!=chosen["id"])
    near_pairs=[]
    shapes=[(shingles(r["prompt"]),shingles(" ".join(sorted(o["text"] for o in r["options"])))) for r in unique]
    for i,left in enumerate(unique):
        if len(key(left["prompt"]))<35:
            continue
        for j in range(i):
            right=unique[j]
            if left["source_id"]==right["source_id"] or len(key(right["prompt"]))<35:
                continue
            if jaccard(shapes[i][0],shapes[j][0])>=.88 and jaccard(shapes[i][1],shapes[j][1])>=.75:
                union.union(left["source_id"],right["source_id"])
                near_pairs.append({"left":left["id"],"right":right["id"],"prompt_shingle_jaccard":round(jaccard(shapes[i][0],shapes[j][0]),4)})
    components=defaultdict(list)
    for row in unique:
        components[union.find(row["source_id"])].append(row)
    ordered=sorted(components.items(),key=lambda pair:(-len(pair[1]),pair[0]))
    if len(ordered)<3:
        raise ValueError("Fewer than three source components: cannot create three disjoint splits")
    target=max(1,round(len(unique)*.1))
    test=choose_holdout(ordered[1:],target,20261024)
    validation=choose_holdout([g for g in ordered[1:] if g[0] not in test],target,20261025)
    if not test or not validation:
        raise ValueError("Unable to make nonempty document-disjoint holdouts")
    for row in unique:
        component=union.find(row["source_id"])
        row["split_group"]=component
        row["split"]="test" if component in test else "validation" if component in validation else "train"
    report={"input_candidates":len(candidates),"pre_dedup_excluded":len(exclusions),
            "conflicting_records_excluded":len(conflicts),"exact_duplicates_removed":len(duplicates),
            "unique_examples":len(unique),"source_components":len(ordered),"near_duplicate_pairs_grouped":len(near_pairs),
            "components":[{"id":identity,"examples":len(rows),"split":rows[0]["split"],
                           "source_ids":sorted({o["source_id"] for r in rows for o in r["origins"]})} for identity,rows in ordered],
            "split_method":"whole source documents; exact duplicates and near question families connect source documents; deterministic subset-sum holdouts",
            "near_duplicate_policy":{"prompt_char5_jaccard":.88,"options_char5_jaccard":.75,"numeric_runs_normalized_for_grouping_only":True},
            "seed":20261024}
    return unique,exclusions+conflicts,{"summary":report,"duplicates":duplicates,"near_pairs":near_pairs}


def example(record: dict, rationales: list[dict]) -> tuple[dict,dict]:
    correct=[o["text"] for o in record["options"] if o["correct"]]
    context_id=record["source_id"]+":"+record["id"]
    rationale=record.get("explanation_source","")
    rationale_origin="source_rationale" if rationale else "source_answer_attribution"
    authored=next((r for r in rationales if r["source_id"]==record["source_id"] and key(r["prompt"])==key(record["prompt"])),None)
    if authored:
        rationale=authored["rationale"]
        rationale_origin=authored["rationale_origin"]
    context=(f"[{context_id}]\nHọc phần: {record['course']}\nCâu hỏi tham chiếu: {record['prompt']}\n"
             +"Đáp án được tài liệu xác nhận:\n"+"\n".join("- "+value for value in correct))
    # Authored explanations become explicit derived reference context, tagged in provenance.
    if rationale:
        context+="\nGiải thích kèm tham chiếu: "+rationale
    else:
        rationale="Theo đáp án đi kèm tài liệu, "+("các lựa chọn đúng là " if len(correct)>1 else "lựa chọn đúng là ")+"; ".join("“"+v+"”" for v in correct)+"."
    citation=lambda quote:{"sourceId":context_id,"evidenceQuote":quote}
    question={"type":record["type"],"prompt":record["prompt"],"explanation":rationale,
              "options":[{"text":o["text"],"correct":o["correct"]} for o in record["options"]],
              "acceptedAnswers":[],"questionCitations":[citation(record["prompt"])],
              "answerCitations":[citation(value) for value in correct],
              "explanationCitations":[citation(value) for value in correct]}
    if rationale_origin!="source_answer_attribution" and len(rationale)<=1000:
        question["explanationCitations"].append(citation(rationale))
    messages=[{"role":"system","content":SYSTEM},
              {"role":"user","content":"Từ nội dung tham chiếu dưới đây, biên soạn 1 câu hỏi ôn tập trắc nghiệm tương đương, có đáp án, giải thích ngắn và trích dẫn nguồn. Trả JSON theo cấu trúc đã yêu cầu.\n\n"+context},
              {"role":"assistant","content":json.dumps({"questions":[question]},ensure_ascii=False,separators=(",",":"))}]
    metadata={"id":record["id"],"split":record["split"],"split_group":record["split_group"],
              "content_sha256":record["content_sha256"],"source_id":record["source_id"],
              "source_ids":sorted({o["source_id"] for o in record["origins"]}),
              "sources":record["origins"],"source_path":record["source_path"],"source_sha256":record["source_sha256"],
              "pages":record["pages"],"course":record["course"],"parser":record["parser"],
              "context_id":context_id,"context_kind":"derived_reference_qa_without_original_distractors",
              "training_task":"reference_qa_to_grounded_quiz_json", "type":record["type"],
              "answer_origin":record["answer_origin"],"rationale_origin":rationale_origin,
              "human_verified":False,"expert_semantically_verified":False,
              "chat_sha256":digest(json.dumps({"messages":messages},ensure_ascii=False,separators=(",",":")))}
    return {"messages":messages},metadata


def assign_question_families(records: list[dict]) -> dict:
    union=UnionFind(r["id"] for r in records)
    by_template=defaultdict(list)
    for row in records:
        by_template[re.sub(r"\d+","#",key(row["prompt"]))].append(row)
    for rows in by_template.values():
        for row in rows[1:]:
            union.union(rows[0]["id"],row["id"])
    shapes=[(shingles(r["prompt"]),shingles(" ".join(sorted(o["text"] for o in r["options"])))) for r in records]
    near_pairs=[]
    for i,left in enumerate(records):
        if len(key(left["prompt"]))<35:continue
        for j in range(i):
            right=records[j]
            if len(key(right["prompt"]))<35:continue
            if jaccard(shapes[i][0],shapes[j][0])>=.88 and jaccard(shapes[i][1],shapes[j][1])>=.75:
                union.union(left["id"],right["id"])
                near_pairs.append({"left":left["id"],"right":right["id"]})
    components=defaultdict(list)
    for record in records:components[union.find(record["id"])].append(record)
    strata=defaultdict(list)
    for identity,rows in components.items():
        course=Counter(r["course"] for r in rows).most_common(1)[0][0]
        strata[course].append((identity,rows))
    for course,groups in sorted(strata.items()):
        groups.sort(key=lambda g:(-len(g[1]),g[0]))
        seed=20261024+int(digest(course)[:6],16)
        target=max(1,round(sum(len(g[1]) for g in groups)*.1))
        test=choose_holdout(groups[1:],target,seed) if len(groups)>=3 else set()
        validation=choose_holdout([g for g in groups[1:] if g[0] not in test],target,seed+1) if len(groups)>=3 else set()
        for identity,rows in groups:
            for row in rows:
                row["split_group"]="family_"+identity
                row["split"]="test" if identity in test else "validation" if identity in validation else "train"
    return {"split_policy":"question_family","question_families":len(components),
            "family_near_pairs":len(near_pairs),
            "split_method":"course-stratified deterministic whole-question-family holdouts; identical stems and numeric/template variants grouped",
            "source_document_policy":"source PDFs can occur across splits; question families and exact questions cannot; not an unseen-document evaluation",
            "family_groups":[{"id":"family_"+identity,"examples":len(rows),"split":rows[0]["split"]} for identity,rows in sorted(components.items())]}


def export_splits(root: Path, records: list[dict], rationales: list[dict], report: dict) -> None:
    root.mkdir(parents=True,exist_ok=True)
    report["splits"]={};origins=Counter();courses=Counter()
    for split in ["train","validation","test"]:
        selected=sorted((r for r in records if r["split"]==split),key=lambda r:digest(str(report["seed"])+r["id"]))
        pairs=[example(record,rationales) for record in selected]
        write_jsonl(root/(split+".messages.jsonl"),[p[0] for p in pairs])
        write_jsonl(root/(split+".metadata.jsonl"),[p[1] for p in pairs])
        report["splits"][split]={"examples":len(pairs),"courses":dict(Counter(r["course"] for r in selected)),
                                 "source_documents":len({o["source_id"] for r in selected for o in r["origins"]})}
        origins.update(p[1]["rationale_origin"] for p in pairs);courses.update(r["course"] for r in selected)
    report["rationale_origins"]=dict(origins);report["courses"]=dict(courses)
    dump(root/"build_report.json",report)


def main() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument("--dataset",type=Path,required=True)
    args=parser.parse_args();root=args.dataset
    candidates=read_jsonl(root/"questions_candidates.jsonl")
    exclusions=[]
    for pattern in ["source_semantic_exclusions*.json","source_visual_exclusions*.json"]:
        for path in sorted((root/"audit").glob(pattern)):
            exclusions.extend(json.loads(path.read_text(encoding="utf-8")))
    rationales=[]
    for path in sorted((root/"audit").glob("curated_rationales*.json")):
        rationales.extend(json.loads(path.read_text(encoding="utf-8")))
    additional=root/"audit/answer_letter_semantic_findings_additional.json"
    if additional.exists():exclusions.extend(json.loads(additional.read_text(encoding="utf-8")))
    records,excluded,details=prepare_records(candidates,exclusions)
    write_jsonl(root/"release_excluded.jsonl",excluded)
    write_jsonl(root/"deduplication.jsonl",details["duplicates"])
    write_jsonl(root/"near_duplicate_groups.jsonl",details["near_pairs"])
    report=details["summary"]
    report["release_exclusion_reasons"]=dict(Counter(reason for r in excluded for reason in r["reasons"]))
    report["semantic_status"]="source-keyed, automatically checked plus risk-enriched Codex sample audit; not expert gold"
    report["task_limit"]="Reference Q&A is converted to grounded quiz JSON; this is not a theory-to-novel-question benchmark. Attribution-only explanations are not detailed pedagogical solutions."
    report["split_policy"]="document_component"
    export_splits(root/"document_holdout",records,rationales,dict(report))
    report.update(assign_question_families(records))
    write_jsonl(root/"questions_selected.jsonl",records)
    export_splits(root,records,rationales,report)
    core=[r for r in records if r.get("explanation_source") or any(a["source_id"]==r["source_id"] and key(a["prompt"])==key(r["prompt"]) for a in rationales)]
    core_report={"split_policy":"question_family","seed":report["seed"],"unique_examples":len(core),
                 "quality_tier":"rationale_enriched_pilot","selection":"subset of the main split; explanations copied from source or explicitly authored and grounded by Codex",
                 "human_verified":False,"expert_semantically_verified":False,
                 "source_document_policy":report["source_document_policy"]}
    export_splits(root/"rationale_core",core,rationales,core_report)
    print(json.dumps({k:v for k,v in report.items() if k not in ["components","family_groups"]},ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
