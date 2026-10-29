"""Export only current human approvals, with a real >=80% theory task mixture."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

from pedagogy_core import (SCHEMA, SPLITS, atomic_bytes, atomic_json, canonical, digest, file_sha, make_zip,
                           similarity, student_messages, validate_checks, validate_draft, write_jsonl)
from pedagogy_store import PedagogyStore
from pedagogy_core import validate_reviewed_checks


def select_examples(store, tokenizer=None, max_length=4096, reviewed_rows=None):
    # Held-out candidates win duplicate conflicts; nothing is reassigned into train.
    rows=sorted((r for r in (store.rows() if reviewed_rows is None else reviewed_rows) if r["human_verified"]),
                key=lambda r:({"test":0,"validation":1,"train":2}[r["split"]],r["task"]!="theory_to_quiz",r["id"]))
    seen=[];groups={};families={};selected=[];excluded=[]
    if tokenizer is not None:
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"data_preparation"))
        from prepare_sft import encode_example
    for row in rows:
        job=store.jobs[row["job_id"]];sources=store.sources(job);draft=row["accepted_draft"]
        validate_draft(job,draft,sources,store.known)
        validate_reviewed_checks(job,row["teacher_result"],draft)
        if any(s["split"]!=job["split"] for s in sources):raise ValueError("Theory source crosses held-out split")
        for group in job["context_groups"]:
            if group in groups and groups[group]!=job["split"]:raise ValueError("Theory block leakage")
            groups[group]=job["split"]
        if job["task"]=="enrich_rationale":
            if job["split_group"] in families and families[job["split_group"]]!=job["split"]:raise ValueError("Exam family leakage")
            families[job["split_group"]]=job["split"]
        prompt=draft["question"]["prompt"]
        match=next((r for p,r in seen if similarity(prompt,p)>=.86),None)
        if match:
            excluded.append({"id":row["id"],"reason":"duplicate_question_family","matches":match});continue
        chat=student_messages(job,draft,sources)
        encoded=encode_example(tokenizer,chat,row["id"]) if tokenizer is not None else None
        if encoded and len(encoded["input_ids"])>max_length:
            excluded.append({"id":row["id"],"reason":"overlength_not_truncated","tokens":len(encoded["input_ids"])});continue
        metadata={"id":row["id"],"job_id":job["id"],"split":job["split"],"task":job["task"],"course":job["course"],
                  "split_group":job["split_group"],"theory_groups":job["context_groups"],"context_ids":job["context_ids"],
                  "source_sha256":sorted({s["source_sha256"] for s in sources}),"source_pages":{s["id"]:s["pages"] for s in sources},
                  "teacher":row["teacher_result"]["teacher"],"teacher_result_sha256":row["teacher_result"]["result_sha256"],
                  "verification_level":row["teacher_result"].get("verification_level","legacy_full_model_audit"),
                  "review_id":row["latest_review"]["review_id"],"human_verified":True,"expert_semantically_verified":False,
                  "cpt_seen_in_training":True,"rationale_origin":"qwen7b_pedagogy_human_approved"}
        selected.append({"chat":chat,"metadata":metadata,"encoded":encoded});seen.append((prompt,row["id"]))
    train_theory=[r for r in selected if r["metadata"]["split"]=="train" and r["metadata"]["task"]=="theory_to_quiz"]
    train_enrich=[r for r in selected if r["metadata"]["split"]=="train" and r["metadata"]["task"]=="enrich_rationale"]
    cap=len(train_theory)//4
    auxiliary=train_enrich[cap:];extra={r["metadata"]["id"] for r in auxiliary}
    main=[r for r in selected if r["metadata"]["id"] not in extra]
    return main,auxiliary,excluded


def load_student_tokenizer(store, supplied=None):
    path=Path(store.manifest["source_paths"]["exam_tokenization_report"])
    wanted=store.manifest["preparation_config"]["source_fingerprints"]["exam_tokenization_report"]
    if file_sha(path)!=wanted:raise ValueError("Frozen student tokenization provenance changed")
    report=json.loads(path.read_text(encoding="utf-8"));tokenizer=Path(supplied or report["tokenizer"])
    hashes=report["tokenizer_sha256"]
    if any(file_sha(tokenizer/name)!=expected for name,expected in hashes.items()):raise ValueError("Student tokenizer differs from the pinned CPT27 tokenizer")
    from transformers import AutoTokenizer
    return AutoTokenizer.from_pretrained(str(tokenizer),local_files_only=True,trust_remote_code=False),hashes


def export_approved(workspace, tokenizer_path=None, tokenizer_for_test=None):
    store=PedagogyStore(workspace)
    reviewed_rows=store.rows()
    approvals=[(r["id"],r["latest_review"]["review_id"]) for r in reviewed_rows if r["human_verified"]]
    snapshot=digest({"approvals":approvals,"inputs":file_sha(store.workspace/"manifest.json"),"exporter":file_sha(__file__)})
    folder=store.workspace/"approved_sft"/snapshot[:24];folder.mkdir(parents=True,exist_ok=True)
    if tokenizer_for_test is not None:
        if store.manifest.get("test_fixture") is not True:raise ValueError("Test tokenizer cannot produce a production release")
        tokenizer,tokenizer_hashes=tokenizer_for_test,{}
    elif approvals:tokenizer,tokenizer_hashes=load_student_tokenizer(store,tokenizer_path)
    else:tokenizer,tokenizer_hashes=None,{}
    main,auxiliary,excluded=select_examples(store,tokenizer,reviewed_rows=reviewed_rows)
    counts=Counter(r["metadata"]["split"] for r in main)
    task_counts=Counter(r["metadata"]["split"]+":"+r["metadata"]["task"] for r in main)
    for split in SPLITS:
        values=[r for r in main if r["metadata"]["split"]==split]
        write_jsonl(folder/(split+".messages.jsonl"),[r["chat"] for r in values])
        write_jsonl(folder/(split+".metadata.jsonl"),[r["metadata"] for r in values])
        write_jsonl(folder/"tokenized"/(split+".jsonl"),[r["encoded"] for r in values if r["encoded"]])
    write_jsonl(folder/"auxiliary_enrichment.messages.jsonl",[r["chat"] for r in auxiliary])
    write_jsonl(folder/"auxiliary_enrichment.metadata.jsonl",[r["metadata"] for r in auxiliary])
    write_jsonl(folder/"excluded.jsonl",excluded)
    ready=all(counts[s]>0 for s in SPLITS) and task_counts["train:theory_to_quiz"]>=.8*counts["train"]
    report={"schema":SCHEMA,"status":"ready_for_training" if ready else "awaiting_approved_theory_and_heldout_examples",
            "human_approved_candidates":len(approvals),"main_counts":dict(counts),"main_task_counts":dict(task_counts),
            "main_train_theory_fraction":task_counts["train:theory_to_quiz"]/counts["train"] if counts["train"] else None,
            "verification_levels":dict(Counter(r["metadata"]["verification_level"] for r in main)),
            "auxiliary_enrichment_not_in_main_train":len(auxiliary),"excluded":len(excluded),"maximum_tokens":4096,"truncation":False,
            "train_courses":sorted({r["metadata"]["course"] for r in main if r["metadata"]["split"]=="train"}),
            "split_policy":"theory_page_blocks_plus_near_duplicates_and_original_exam_families",
            "evaluation_scope":"held-out SFT theory blocks; these PDFs were previously used in CPT; not unseen-document generalization",
            "semantic_expert_gold":False,"student_improvement_measured":False,"model_weights_loaded_or_training_started":False,
            "snapshot_sha256":snapshot,"tokenizer_sha256":tokenizer_hashes,"loss_policy":"assistant content and im_end only; prompt and padding masked -100"}
    atomic_json(folder/"build_report.json",report);atomic_json(folder/"MODEL_PROVENANCE.json",store.manifest["student"])
    card="""# BKQuiz: theory → novel quiz and pedagogical explanations

Only the latest human-approved candidate for each teacher job is exported.
Theory-to-quiz inputs contain theory and a blueprint, without a pre-existing question or answer.
Enrichment inputs contain the original question and all options, without the private answer key.
The public explanation covers the concept, application to the correct answer, and every option.
All examples pass CPU structure, verbatim citation and known-question novelty gates before human review.
Strict outputs additionally use two blind option orders and a same-model critic for every candidate.
FAST outputs use those model checks only for deterministic risk cases and a 10% hash-selected sample.
Other FAST outputs are explicitly labelled cpu_only_pending_human in provenance; no model audit is implied.
These automated checks are not independent semantic proof. Human approval is not an expert-gold claim.

Main train contains at least 80% unique theory-to-quiz examples; excess enrichment is auxiliary only.
Do not concatenate the old 742-question release or the auxiliary pool into main train unchecked.
Contexts from the same 8-page block and near-duplicate components stay in a single split.
Original exam families keep their existing split. Duplicates prefer the held-out record.
The source PDFs were already seen in CPT: this is not a test on unseen textbooks.

The student remains Qwen3-1.7B and the verified 27-course CPT adapter. No training occurs here.
Reuse the pinned Qwen3 tokenizer with enable_thinking=False. Loss is on assistant content and EOS only.
Overlong records are excluded intact, never truncated. Inspect build_report.json before training.
Compare the pre-SFT and post-SFT student on the same held-out theory prompts with human scoring of
answer correctness, grounding, novelty, explanation and distractor quality. This gain is not yet measured.
"""
    atomic_bytes(folder/"DATASET_CARD.md",card.encode())
    files={p.relative_to(folder).as_posix():file_sha(p) for p in folder.rglob("*") if p.is_file() and p.name not in {"release_manifest.json","sft_pedagogy.zip"}}
    atomic_json(folder/"release_manifest.json",{"schema":SCHEMA,"build_report":report,"files_sha256":files})
    bundle=None
    if ready:
        bundle=folder/"sft_pedagogy.zip"
        make_zip(bundle,{p.relative_to(folder).as_posix():p.read_bytes() for p in folder.rglob("*") if p.is_file() and p!=bundle})
    receipt={"directory":str(folder),"report":report,"bundle":str(bundle) if bundle else None}
    atomic_json(store.workspace/"LATEST_APPROVED_SFT.json",receipt);return receipt


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--workspace",type=Path,required=True);p.add_argument("--tokenizer",type=Path)
    a=p.parse_args();print(json.dumps(export_approved(a.workspace,a.tokenizer),ensure_ascii=False,indent=2))
