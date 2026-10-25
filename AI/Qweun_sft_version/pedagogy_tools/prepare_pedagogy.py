"""Prepare two teacher tasks from the actual frozen CPT/exam releases."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
import zlib
import zipfile
from itertools import zip_longest

from pedagogy_core import SCHEMA, TEACHER, atomic_json, canonical, digest, file_sha, normalized, read_jsonl, shingles, write_jsonl

COURSE_MAP = {
    "Công nghệ phần mềm": ["IT3180", "IT3120"], "OS": ["IT3070"],
    "An ninh mạng": ["IT4263", "IT4025", "IT4812"],
    "An toàn thông tin": ["IT4263", "IT4025", "IT4812"],
    "Phân tích thiết kế hệ thống": ["IT3120"], "Thị giác máy tính": ["IT4653"],
    "Điện tử CNTT": ["IT4272"], "Tìm kiếm thông tin": ["IT4868"],
}
RELATED_ONLY = {"Thị giác máy tính", "Điện tử CNTT", "Tìm kiếm thông tin"}
STOP = set("a an the of to and or in on with from is are was which what how when why for not all select choose correct incorrect statement following one more can could should would be as at by into using được không trong những các một của và cho nào với khi theo sau từ để này trên là hãy đúng sai về có hoặc loại giá trị".split())
GLOSSARY = {"process": "tiến trình", "thread": "luồng", "file": "tệp", "memory": "bộ nhớ", "kernel": "nhân", "deadlock": "bế tắc",
            "scheduling": "lập lịch", "page": "trang", "requirement": "yêu cầu", "software": "phần mềm", "testing": "kiểm thử",
            "inheritance": "kế thừa", "encryption": "mã hóa", "authentication": "xác thực", "network": "mạng", "database": "cơ sở dữ liệu"}
QUESTION_BANK = re.compile(r"(?:^|\n)\s*(?:Câu\s*(?:hỏi)?\s*\d+|Question\s*\d+|ANSWER\s*:|Đáp\s*án\s*:)|select\s+one|the\s+correct\s+answer", re.I)


class Groups:
    def __init__(self): self.parent = {}
    def find(self, key):
        self.parent.setdefault(key, key)
        if self.parent[key] != key: self.parent[key] = self.find(self.parent[key])
        return self.parent[key]
    def join(self, a, b):
        a,b = self.find(a),self.find(b)
        if a != b: self.parent[max(a,b)] = min(a,b)


def quality_reason(text):
    if any(marker in text for marker in ("<|im_start|>","<|im_end|>","<think>","</think>")): return "reserved_markers"
    if re.search(r"[\ue000-\uf8ff\ufffd\x00-\x08]", text): return "unsupported_glyphs"
    if QUESTION_BANK.search(text): return "existing_question_or_answer_bank"
    repeated = re.findall(r"([A-Za-zÀ-ỹ]{3,})\1", text, re.I)
    if len(repeated) >= 3: return "repeated_text_corruption"
    if sum(c.isalpha() for c in text) / max(1,len(text)) < .2: return "too_little_readable_prose"
    return None


def split_paragraphs(text, maximum=3600):
    """Keep source text verbatim; reject overlong lines instead of truncating."""
    pieces=[]; current=[]; size=0
    for line in text.splitlines(keepends=True):
        if len(line) > maximum:
            if current: pieces.append("".join(current).strip());current=[];size=0
            pieces.append(None);continue
        if current and size+len(line)>maximum:
            pieces.append("".join(current).strip());current=[];size=0
        current.append(line);size+=len(line)
    if current:pieces.append("".join(current).strip())
    return pieces


def make_contexts(records, catalog, block_pages=8, max_chars=3600):
    by_block=defaultdict(list); excluded=Counter()
    for record in records:
        text=record.get("text", "").strip(); reason=quality_reason(text)
        if not text or reason: excluded[reason or "empty"]+=1;continue
        block=(record["page"]-1)//block_pages
        for piece in split_paragraphs(text,max_chars):
            if not piece: excluded["overlong_physical_line"]+=1;continue
            by_block[(record["document_id"],block)].append((record,piece))
    contexts=[]
    for (document,block),parts in sorted(by_block.items()):
        doc=catalog[document]; parts.sort(key=lambda item:(item[0]["page"],item[0]["record"].get("bbox",[0,0,0,0])[1],item[0]["id"]))
        seen=set();buffer=[];size=0
        def flush():
            nonlocal buffer,size
            if not buffer:return
            text="\n\n".join(piece for _,piece in buffer)
            if len(text)>=450 and len(normalized(text).split())>=65 and not quality_reason(text):
                row={"course":doc["course"],"title":doc["title"],"document_id":document,"source_sha256":doc["source_sha256"],
                     "source_pdf":doc["source_pdf"],"pages":sorted({r["page"] for r,_ in buffer}),"block":block,
                     "block_id":document+":block"+str(block),"text":text,"text_sha256":hashlib.sha256(text.encode()).hexdigest(),
                     "record_ids":[r["id"] for r,_ in buffer],"cpt_seen_in_training":True,
                     "source_acceptances":dict(Counter(r["acceptance"] for r,_ in buffer)),
                     "all_source_records_human_reviewed":all(r.get("human_verified") is True for r,_ in buffer)}
                row["id"]="ctx_"+digest(row)[:24];contexts.append(row)
            else:excluded["short_or_non_theory_context"]+=1
            buffer=[];size=0
        for record,piece in parts:
            key=(record["page"],normalized(piece))
            if key in seen:excluded["duplicate_region_on_page"]+=1;continue
            seen.add(key)
            if buffer and size+len(piece)+2>max_chars:flush()
            buffer.append((record,piece));size+=len(piece)+2
        flush()
    return contexts,dict(excluded)


def assign_splits(contexts, threshold=.85):
    """Keep whole page blocks and near-duplicate theory in a single split.

    Prefix filtering under a global token order generates Jaccard candidates;
    actual word shingles confirm matches (CRC is only a compact index key).
    """
    groups=Groups();sets=[];frequency=Counter()
    for c in contexts:
        groups.find(c["block_id"])
        values={zlib.crc32(s.encode()) for s in shingles(c["text"])}
        sets.append(values);frequency.update(values)
    index=defaultdict(list);comparisons=0;near_pairs=0;exact={}
    for i,(c,values) in enumerate(zip(contexts,sets)):
        exact_key=digest(normalized(c["text"]))
        if exact_key in exact:groups.join(c["block_id"],contexts[exact[exact_key]]["block_id"])
        else:exact[exact_key]=i
        ordered=sorted(values,key=lambda token:(frequency[token],token))
        prefix=ordered[:len(ordered)-math.ceil(threshold*len(ordered))+1]
        candidates={j for token in prefix for j in index[token]}
        for j in candidates:
            other=sets[j]
            if min(len(values),len(other))<threshold*max(len(values),len(other)):continue
            comparisons+=1
            if len(values & other)/max(1,len(values | other))>=threshold:
                x,y=shingles(c["text"]),shingles(contexts[j]["text"])
                if len(x & y)/max(1,len(x | y))>=threshold:
                    groups.join(c["block_id"],contexts[j]["block_id"]);near_pairs+=1
        for token in prefix:index[token].append(i)
    for c in contexts:
        group=groups.find(c["block_id"]);number=int(digest({"seed":20261025,"group":group})[:8],16)%100
        c.update(split="train" if number<80 else "validation" if number<90 else "test",split_group=group,
                 evaluation_scope="held-out theory page blocks; these PDFs were already used in CPT")
    return {"near_duplicate_pairs_grouped":near_pairs,"candidate_comparisons":comparisons,
            "split_policy":"whole_8_page_blocks_and_near_duplicate_components","independent_unseen_document_test":False}


def retrieval_terms(text):
    expanded=text+" "+" ".join(v for k,v in GLOSSARY.items() if re.search(r"\b"+k+r"\b",text,re.I))
    return {w for w in normalized(expanded).split() if len(w)>2 and w not in STOP and not w.isdecimal()}


def retrieve(connection, question, courses, split, contexts):
    terms=retrieval_terms(question["prompt"]+" "+" ".join(o["text"] for o in question["options"]))
    if not terms or not courses:return [],0.
    query=" OR ".join('"'+w+'"' for w in sorted(terms,key=lambda w:(-len(w),w))[:45])
    sql="SELECT id FROM lookup WHERE lookup MATCH ? AND course IN ("+",".join("?" for _ in courses)+") AND split=? ORDER BY bm25(lookup) LIMIT 15"
    ids=[r[0] for r in connection.execute(sql,[query,*courses,split])]
    chosen=[];chars=0;best=0.
    for identity in ids:
        c=contexts[identity];overlap=terms & retrieval_terms(c["text"]);coverage=len(overlap)/len(terms)
        if len(overlap)<3 or coverage<.08:continue
        if chosen and chars+len(c["text"])>5500:continue
        chosen.append(identity);chars+=len(c["text"]);best=max(best,coverage)
        if len(chosen)==2:break
    return chosen,best


def finish_job(job, teacher):
    job.update(schema=SCHEMA,teacher=teacher,human_verified=False,expert_semantically_verified=False)
    job["id"]="job_"+digest(job)[:24];job["job_sha256"]=digest(job)
    return job


def prepare(cpt_release, cpt_catalog, exam_release, workspace, per_course=50, verify_sources=True):
    cpt_release=Path(cpt_release).resolve();exam_release=Path(exam_release).resolve();workspace=Path(workspace).resolve()
    if not 1<=per_course<=500:raise ValueError("Questions/course must be between1and500")
    paths={"cpt_selection":cpt_release/"final_selection.jsonl","cpt_catalog":Path(cpt_catalog).resolve(),
           "cpt_training_manifest":cpt_release/"prepared_cpu_exact/manifest.json","cpt_packed_sources":cpt_release/"prepared_cpu_exact/train.sources.jsonl",
           "cpt_bundle_info":cpt_release/"bundle_info.json","cpt_bundle":cpt_release/"bkquiz_cpt_27courses_20261023.zip",
           "exam_manifest":exam_release/"release_manifest.json","student_provenance":exam_release/"MODEL_PROVENANCE.json",
           "exam_tokenization_report":exam_release/"tokenization_report.json"}
    fingerprints={k:file_sha(p) for k,p in paths.items()}
    config={"source_fingerprints":fingerprints,"teacher":TEACHER,"questions_per_course":per_course,"block_pages":8,"max_context_characters":3600}
    if (workspace/"manifest.json").exists():
        old=json.loads((workspace/"manifest.json").read_text(encoding="utf-8"))
        if old["preparation_config"]!=config:raise ValueError("Workspace already has different inputs/config; choose a new directory")
    workspace.mkdir(parents=True,exist_ok=True)
    catalog={r["document_id"]:r for r in json.loads(paths["cpt_catalog"].read_text(encoding="utf-8"))["documents"]}
    records=list(read_jsonl(paths["cpt_selection"]))
    bundle_info=json.loads(paths["cpt_bundle_info"].read_text(encoding="utf-8"))
    if fingerprints["cpt_bundle"]!=bundle_info["sha256"]:raise ValueError("Frozen CPT training ZIP changed")
    packed_manifest=json.loads(paths["cpt_training_manifest"].read_text(encoding="utf-8"))
    if fingerprints["cpt_packed_sources"]!=packed_manifest["files_sha256"]["train.sources.jsonl"]:raise ValueError("CPT source-span provenance changed")
    with zipfile.ZipFile(paths["cpt_bundle"]) as archive:
        entry=next(name for name in archive.namelist() if name.endswith("/data/train.jsonl"))
        with archive.open(entry) as stream:
            for selected,packed in zip_longest(records,(json.loads(line) for line in stream)):
                if selected is None or packed is None or selected["text"]!=packed["text"]:raise ValueError("Theory text differs from the exact CPT export")
    exam_files=json.loads(paths["exam_manifest"].read_text(encoding="utf-8"))["files_sha256"]
    for split in ("train","validation","test"):
        for suffix in ("messages.jsonl","metadata.jsonl"):
            name=split+"."+suffix
            if file_sha(exam_release/name)!=exam_files[name]:raise ValueError("Frozen exam split changed: "+name)
    packed_ids={span["sample_id"] for row in read_jsonl(paths["cpt_packed_sources"]) for span in row["spans"]}
    if {r["id"] for r in records}!=packed_ids:raise ValueError("Selection differs from the exact corpus actually packed for CPT")
    if any(r["record"].get("split")!="train" or r["acceptance"] not in {"owner_default_pass","review_approve"} for r in records):
        raise ValueError("Protected/unauthorized CPT records cannot become teacher input")
    source_checks=[]
    for document,doc in catalog.items():
        if verify_sources:
            current=file_sha(Path(doc["source_pdf"]))
            if current!=doc["source_sha256"]:raise ValueError("Original CPT PDF changed: "+document)
        source_checks.append({"document_id":document,"source_sha256":doc["source_sha256"],"verified":verify_sources})
    contexts,excluded=make_contexts(records,catalog);split_report=assign_splits(contexts)
    by_id={c["id"]:c for c in contexts};by_course=defaultdict(list)
    for c in contexts:by_course[c["course"]].append(c)
    lookup=workspace/"retrieval.sqlite3"
    with sqlite3.connect(lookup) as connection:
        connection.execute("CREATE VIRTUAL TABLE IF NOT EXISTS lookup USING fts5(id UNINDEXED,course UNINDEXED,split UNINDEXED,text)")
        connection.execute("DELETE FROM lookup")
        connection.executemany("INSERT INTO lookup VALUES(?,?,?,?)",[(c["id"],c["course"],c["split"],normalized(c["text"])) for c in contexts]);connection.commit()
        jobs=[];blocked=[];known=[];origins=Counter()
        for split in ("train","validation","test"):
            metas=list(read_jsonl(exam_release/(split+".metadata.jsonl")));messages=list(read_jsonl(exam_release/(split+".messages.jsonl")))
            if len(metas)!=len(messages):raise ValueError("Exam rows and provenance misaligned")
            for meta,chat in zip(metas,messages):
                q=json.loads(chat["messages"][-1]["content"])["questions"][0];known.append({"id":meta["id"],"prompt":q["prompt"],"split":split,"split_group":meta["split_group"]})
                origins[meta["rationale_origin"]]+=1
                if meta["rationale_origin"]!="source_answer_attribution":continue
                question={"type":q["type"],"prompt":q["prompt"],"options":[{"label":chr(65+i),"text":o["text"]} for i,o in enumerate(q["options"])]}
                sources,coverage=retrieve(connection,question,COURSE_MAP.get(meta["course"],[]),split,by_id)
                if not sources or (meta["course"] in RELATED_ONLY and coverage<.2):
                    blocked.append({"exam_id":meta["id"],"course":meta["course"],"split":split,"reason":"insufficient_retrievable_theory_in_this_split","candidate_courses":COURSE_MAP.get(meta["course"],[]),"retrieval_coverage":coverage});continue
                job={"task":"enrich_rationale","split":split,"split_group":meta["split_group"],"exam_id":meta["id"],"exam_course":meta["course"],
                     "course":by_id[sources[0]]["course"],"context_ids":sources,"context_groups":sorted({by_id[s]["split_group"] for s in sources}),
                     "reference_question":question,"expected_correct_labels":[chr(65+i) for i,o in enumerate(q["options"]) if o["correct"]],
                     "retrieval_coverage":coverage,"retrieval_semantics_verified":False,"original_metadata":meta}
                jobs.append(finish_job(job,TEACHER))
    theory_counts=Counter()
    for course,choices in sorted(by_course.items()):
        choices.sort(key=lambda c:digest({"seed":20261025,"id":c["id"]}))
        available={split:[c for c in choices if c["split"]==split] for split in ("train","validation","test")}
        split_counter=Counter()
        for i in range(per_course):
            desired="train" if i%10<8 else "validation" if i%10==8 else "test"
            pool=available[desired]
            if not pool:continue
            context=pool[(i//10*8+i%8 if desired=="train" else i//10)%len(pool)]
            local=split_counter[desired];split_counter[desired]+=1
            blueprint={"type":"MULTIPLE_SELECT" if local%4==3 else "SINGLE_CHOICE","bloom":["understand","apply","analyze","apply"][local%4],
                       "difficulty":["easy","medium","hard"][local%3],"variant":i+1,"language":"vi","question_count":1,
                       "instruction":"Tạo tình huống hoặc đối chiếu mới từ nguyên lý trong lý thuyết; nêu đủ giả định và giải thích tất cả phương án."}
            jobs.append(finish_job({"task":"theory_to_quiz","split":context["split"],"split_group":context["split_group"],"course":course,
                                   "context_ids":[context["id"]],"context_groups":[context["split_group"]],"blueprint":blueprint},TEACHER));theory_counts[course]+=1
    pilot=[];selected=Counter()
    for job in sorted(jobs,key=lambda j:(j["course"],j["task"],digest(j["id"]))):
        key=(job["course"],job["task"]);limit=2 if job["task"]=="theory_to_quiz" else 1
        if selected[key]<limit:pilot.append(job["id"]);selected[key]+=1
    write_jsonl(workspace/"contexts.jsonl",contexts);write_jsonl(workspace/"jobs.jsonl",jobs)
    write_jsonl(workspace/"blocked_context_jobs.jsonl",blocked);write_jsonl(workspace/"known_exam_questions.jsonl",known)
    atomic_json(workspace/"pilot_job_ids.json",pilot);atomic_json(workspace/"course_mapping.json",{"mapping":COURSE_MAP,"related_domain_only":sorted(RELATED_ONLY),"not_an_exact_curriculum_match":True})
    manifest={"schema":SCHEMA,"preparation_config":config,"teacher":TEACHER,"student":json.loads(paths["student_provenance"].read_text(encoding="utf-8")),
              "source_paths":{k:str(v) for k,v in paths.items()},
              "files_sha256":{name:file_sha(workspace/name) for name in ["contexts.jsonl","jobs.jsonl","blocked_context_jobs.jsonl","known_exam_questions.jsonl","pilot_job_ids.json","course_mapping.json"]},
              "sources_verified":verify_sources,"source_checks":source_checks,"human_reviews_created":0,"gpu_executed":False,
              "student_task_mix":{"theory_to_quiz":.8,"enrich_rationale":.2},"source_catalog":list(catalog.values())}
    atomic_json(workspace/"manifest.json",manifest)
    report={"courses":len(by_course),"cpt_training_records":len(records),"theory_contexts":len(contexts),"context_exclusions":excluded,
            "existing_exam_questions":len(known),"rationale_origins":dict(origins),"shallow_questions":origins["source_answer_attribution"],
            "enrichment_jobs_ready":sum(j["task"]=="enrich_rationale" for j in jobs),"enrichment_jobs_blocked":len(blocked),
            "blocked_by_course":dict(Counter(j["course"] for j in blocked)),"theory_generation_jobs":dict(theory_counts),
            "jobs":len(jobs),"pilot_jobs":len(pilot),"split_report":split_report,"jobs_by_task_split":dict(Counter(j["task"]+":"+j["split"] for j in jobs)),
            "training_examples_generated":0,"teacher_outputs_human_verified":0,"gpu_executed":False}
    atomic_json(workspace/"PREPARATION_REPORT.json",report);print(json.dumps(report,ensure_ascii=False,indent=2))
    return report


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--cpt-release",type=Path,required=True);p.add_argument("--cpt-catalog",type=Path,required=True)
    p.add_argument("--exam-release",type=Path,required=True);p.add_argument("--workspace",type=Path,required=True);p.add_argument("--per-course",type=int,default=50)
    a=p.parse_args();prepare(a.cpt_release,a.cpt_catalog,a.exam_release,a.workspace,a.per_course)
