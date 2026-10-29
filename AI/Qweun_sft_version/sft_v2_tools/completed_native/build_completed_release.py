"""Freeze a page-filtered subset of the existing completed native exam release.

No model inference, OCR, VLM, new rationale generation or review approval.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import shutil
import sys

SFT_ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(SFT_ROOT/"pedagogy_tools"))
sys.path.insert(0,str(SFT_ROOT/"data_preparation"))
from pedagogy_core import atomic_bytes,atomic_json,canonical,digest,file_sha,make_zip,read_jsonl,write_jsonl
from prepare_sft import SPLITS,TOKENIZER_FILES,encode_example,length_statistics
from validate_release import validate_output

SCHEMA="bkquiz-completed-sft-v1"
COMPLETED_PARSERS={"native_answer_letter","moodle_explicit_key","forms_full_credit_radio","corrected_filled_circle","inline_explicit_key"}
AUTHORIZATION="Loại bỏ toàn bộ những trang cần LLM, VLM và duyệt thủ công; đóng gói những trang đã hoàn tất để SFT trên Colab."


def dependencies(metadata):
    entries=metadata.get("sources",[])
    if not entries:raise ValueError("No source-page provenance")
    output=set()
    for entry in entries:
        if not entry.get("source_id") or not entry.get("pages"):raise ValueError("Incomplete source-page provenance")
        for page in entry["pages"]:
            if type(page) is not int or page<1:raise ValueError("Invalid physical PDF page")
            output.add((entry["source_id"],page))
    return output


def verify_frozen_source(source):
    manifest=json.loads((source/"release_manifest.json").read_text(encoding="utf-8"))
    names=[split+suffix for split in SPLITS for suffix in (".messages.jsonl",".metadata.jsonl")]
    names += ["questions_selected.jsonl","MODEL_PROVENANCE.json","tokenization_report.json"]
    hashes={}
    for name in names:
        actual=file_sha(source/name)
        if manifest["files_sha256"].get(name)!=actual:raise ValueError("Frozen release changed: "+name)
        hashes[name]=actual
    tokens=json.loads((source/"tokenization_report.json").read_text(encoding="utf-8"))
    for split in SPLITS:
        name="tokenized/"+split+".jsonl";actual=file_sha(source/name)
        if tokens["outputs_sha256"].get(name)!=actual:raise ValueError("Frozen token data changed")
        hashes[name]=actual
    return hashes,tokens


def select_records(source,review):
    source=Path(source);review=Path(review)
    input_hashes,token_report=verify_frozen_source(source)
    pages=list(read_jsonl(review/"pages.jsonl"));excluded_pages={(p["source_id"],p["page"]) for p in pages}
    review_manifest=json.loads((review/"manifest.json").read_text(encoding="utf-8"))
    if file_sha(review/"pages.jsonl")!=review_manifest["catalog_sha256"]:raise ValueError("Review page catalog changed")
    originals={q["id"]:q for q in read_jsonl(source/"questions_selected.jsonl")}
    selected={s:[] for s in SPLITS};excluded=[];families={};contents=set();ids=set()
    for split in SPLITS:
        chats=list(read_jsonl(source/(split+".messages.jsonl")))
        metas=list(read_jsonl(source/(split+".metadata.jsonl")))
        encoded=list(read_jsonl(source/"tokenized"/(split+".jsonl")))
        if len(chats)!=len(metas) or len(encoded)!=len(metas):raise ValueError("Frozen messages/provenance/tokens misaligned")
        for chat,meta,tokens in zip(chats,metas,encoded):
            identity=meta["id"]
            if identity in ids or identity not in originals or tokens["id"]!=identity:raise ValueError("Duplicate or unknown native example")
            ids.add(identity)
            pages_for_question=dependencies(meta)
            original_pages={(o["source_id"],p) for o in originals[identity]["origins"] for p in o["pages"]}
            if original_pages!=pages_for_question:raise ValueError("Original and release source pages disagree")
            blocked=sorted(pages_for_question & excluded_pages)
            if blocked:
                excluded.append({"id":identity,"split":split,"reason":"source_page_requires_llm_vlm_or_manual_completion",
                                 "dependencies":[{"source_id":s,"page":p} for s,p in blocked]});continue
            if meta.get("split")!=split or meta.get("parser") not in COMPLETED_PARSERS:
                raise ValueError("Incomplete or nonnative example passed selection")
            import hashlib
            legacy=hashlib.sha256(json.dumps(chat,ensure_ascii=False,separators=(",", ":")).encode()).hexdigest()
            if legacy!=meta.get("chat_sha256"):raise ValueError("Source chat identity mismatch")
            if meta["split_group"] in families and families[meta["split_group"]]!=split:raise ValueError("Question family crosses split")
            families[meta["split_group"]]=split
            if meta["content_sha256"] in contents:raise ValueError("Duplicate native question content")
            contents.add(meta["content_sha256"])
            output=json.loads(chat["messages"][-1]["content"])
            if len(output.get("questions",[]))!=1 or validate_output(output,chat["messages"][1]["content"]):
                raise ValueError("Completed source output no longer validates")
            new_meta=dict(meta,completion_origin="frozen_native_release",requires_additional_llm=False,requires_vlm=False,
                          requires_manual_completion=False,source_pages_complete=True,
                          completion_authorization="owner_requested_completed_subset_20261025")
            # Preserve human_verified/expert flags and original rationale origin.
            selected[split].append((chat,new_meta,tokens,originals[identity]))
    return selected,excluded,pages,input_hashes,token_report


def build_data(source,review,out,owner_receipt=None):
    source=Path(source).resolve();review=Path(review).resolve();out=Path(out).resolve();payload=out/"payload"
    if (payload/"manifest.json").exists():raise ValueError("Release is already frozen; use a new output directory")
    selected,excluded,pages,hashes,old_tokens=select_records(source,review)
    tokenizer_path=Path(old_tokens["tokenizer"])
    for name,wanted in old_tokens["tokenizer_sha256"].items():
        if file_sha(tokenizer_path/name)!=wanted:raise ValueError("Pinned tokenizer changed: "+name)
    from transformers import AutoTokenizer
    tokenizer=AutoTokenizer.from_pretrained(str(tokenizer_path),local_files_only=True,trust_remote_code=False)
    provenance=json.loads((source/"MODEL_PROVENANCE.json").read_text(encoding="utf-8"))
    adapter=Path(provenance["current_cpt_adapter_path"])
    for name,wanted in provenance["current_cpt_adapter_sha256"].items():
        if file_sha(adapter/name)!=wanted:raise ValueError("Wrong CPT27 adapter: "+name)
    checked_sources={};source_pages=set();courses=Counter();rationales=Counter();stats={}
    for split,values in selected.items():
        for chat,meta,tokens,original in values:
            if encode_example(tokenizer,chat,meta["id"])!=tokens:raise ValueError("Assistant-only token mask differs from frozen source")
            if len(tokens["input_ids"])>4096:raise ValueError("Overlong example must not be truncated")
            courses[meta["course"]]+=1;rationales[meta["rationale_origin"]]+=1;source_pages.update(dependencies(meta))
            for entry in meta["sources"]:
                path=Path(entry["path"])
                if str(path) not in checked_sources:
                    if file_sha(path)!=entry["sha256"]:raise ValueError("Native PDF changed: "+str(path))
                    checked_sources[str(path)]=entry["sha256"]
        write_jsonl(payload/(split+".messages.jsonl"),[v[0] for v in values])
        write_jsonl(payload/(split+".metadata.jsonl"),[v[1] for v in values])
        write_jsonl(payload/"tokenized"/(split+".jsonl"),[v[2] for v in values])
        stats[split]=length_statistics([v[2] for v in values])
    write_jsonl(payload/"source_questions.jsonl",[v[3] for values in selected.values() for v in values])
    write_jsonl(payload/"excluded_questions.jsonl",excluded)
    write_jsonl(payload/"excluded_pages.jsonl",[{k:p[k] for k in ("id","identity","source_id","page","source_sha256")} for p in pages])
    atomic_json(payload/"MODEL_PROVENANCE.json",dict(provenance,continuation_method="continue_same_verified_CPT27_adapter_with_is_trainable_true",
                 continuation_note="Complete output adapter contains CPT+SFT; load it onto the pinned Qwen3 base, without stacking the original CPT adapter."))
    for name in TOKENIZER_FILES:
        if (tokenizer_path/name).is_file():
            target=payload/"tokenizer"/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(tokenizer_path/name,target)
    for name in provenance["current_cpt_adapter_sha256"]:
        target=payload/"assets/cpt_adapter"/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(adapter/name,target)
    policy={"authorization":AUTHORIZATION,"source_policy":"completed_native_pages_only","review_catalog_sha256":file_sha(review/"pages.jsonl"),
            "excluded_review_items":len(pages),"excluded_physical_pages":len({(p["source_id"],p["page"]) for p in pages}),
            "all_origin_pages_must_be_complete":True,"no_teacher_outputs_used":True,"no_pending_stage2_questions_used":True}
    if owner_receipt:
        receipt=Path(owner_receipt);policy["owner_exclusion_receipt_sha256"]=file_sha(receipt)
        atomic_json(payload/"owner_exclusion_receipt.json",json.loads(receipt.read_text(encoding="utf-8")))
    atomic_json(payload/"selection_policy.json",policy)
    report={"schema":SCHEMA,"counts":{s:len(v) for s,v in selected.items()},"total":sum(map(len,selected.values())),
            "completed_source_pages":len(source_pages),"source_pdfs_verified":len(checked_sources),"courses":dict(courses),
            "rationale_origins":dict(rationales),"excluded_old_examples":len(excluded),"excluded_review_pages":policy["excluded_physical_pages"],
            "source_fingerprints":hashes,"review_catalog_sha256":policy["review_catalog_sha256"],"tokenizer_sha256":old_tokens["tokenizer_sha256"],
            "split_policy":"question_family","existing_splits_preserved":True,"question_families":len({v[1]["split_group"] for vals in selected.values() for v in vals}),
            "evaluation_limitation":"Source PDFs can be shared across splits; not unseen-document generalization.",
            "training_task":"reference_qa_to_grounded_quiz_json","not_theory_to_novel_quiz":True,
            "no_new_data_generation":True,"model_weights_loaded_or_training_executed_locally":False,"human_reviews_created":0,
            "tokenization":stats,"passed":True}
    atomic_json(payload/"build_report.json",report)
    atomic_json(out/"DATA_BUILD_RECEIPT.json",report)
    card="""# BKQuiz: bộ SFT chỉ gồm trang native đã hoàn tất

Lấy một tập con nguyên vẹn từ release đề thi 742 câu, loại toàn bộ câu chạm bất kỳ trang nào
còn trong luồng LLM/VLM/duyệt thủ công, xét mọi nguồn của câu. Không dùng các câu TXT đang
chờ duyệt, đầu ra teacher, ảnh cần xử lý thêm hoặc dữ liệu CPT dạng văn bản thô làm nhãn SFT.
Quyết định loại là chính sách của chủ dữ liệu, không tạo phê duyệt giả và không xóa nguồn gốc.

Giữ nguyên messages, đáp án, giải thích đã hoàn tất, nhóm câu hỏi và train/validation/test cũ.
Tập này huấn luyện chuyển Q&A có đáp án thành quiz JSON có căn cứ; chưa dạy đầy đủ khả năng
đọc giáo trình rồi tự sáng tạo câu hỏi mới. Lời giải dẫn đáp án nguồn còn ngắn. Các lời giải
Codex có căn cứ đã hoàn tất trước đây được giữ nguyên và đánh dấu đúng nguồn gốc; không gọi LLM mới.
human_verified/expert_semantically_verified được giữ nguyên; đáp án nguồn chưa phải expert gold.

Chỉ token assistant content và EOS im_end chịu loss; prompt, think-prefix và padding là -100.
Không truncate, không packing các mẫu chat; tokenizer Qwen3 chính xác theo SHA256 release gốc.
Tệp PDF có thể dùng chung giữa split, nhưng nhóm câu hỏi không chồng split. Đây không phải
phép đo tổng quát hóa trên tài liệu chưa thấy. Không dùng test để chọn checkpoint/hyperparameter.

Student: Qwen3-1.7B đúng revision cùng adapter CPT27 đã kiểm tra hash. Notebook train tiếp
chính adapter đó với QLoRA. Kết quả adapter cuối chứa CPT+SFT; nạp cùng base, không chồng lại
adapter CPT ban đầu. Không có teacher7B/VLM hoặc bước sinh dữ liệu trong notebook này.
Huấn luyện GPU chưa được chạy tại máy chuẩn bị; người dùng tự chạy Colab.
"""
    atomic_bytes(payload/"DATASET_CARD.md",card.encode())
    return report


def freeze_bundle(out):
    out=Path(out).resolve();payload=out/"payload";runtime=Path(__file__).with_name("runtime")
    if (payload/"manifest.json").exists():raise ValueError("Bundle is already frozen; use a new release directory")
    for name in ("train_sft.py","sft_contract.py","config.json","requirements.txt"):
        target=payload/"runtime"/name;target.parent.mkdir(exist_ok=True);shutil.copyfile(runtime/name,target)
    report=json.loads((payload/"build_report.json").read_text(encoding="utf-8"))
    hashes={p.relative_to(payload).as_posix():file_sha(p) for p in sorted(payload.rglob("*")) if p.is_file() and p.name!="manifest.json"}
    manifest={"schema":SCHEMA,"source_policy":"completed_native_pages_only","counts":report["counts"],"max_length":4096,
              "tokenizer_eos_token_id":151645,"files_sha256":hashes,"no_pending_llm_vlm_manual_pages":True,
              "no_training_executed_locally":True,"split_policy":"question_family","source_policy_sha256":hashes["selection_policy.json"]}
    atomic_json(payload/"manifest.json",manifest)
    archive=out/"bkquiz_completed_sft_20261025.zip"
    make_zip(archive,{p.relative_to(payload).as_posix():p.read_bytes() for p in sorted(payload.rglob("*")) if p.is_file()})
    receipt={"archive":str(archive),"sha256":file_sha(archive),"bytes":archive.stat().st_size,"manifest_sha256":file_sha(payload/"manifest.json"),"counts":report["counts"]}
    atomic_json(out/"BUNDLE_INFO.json",receipt);return receipt


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--source",type=Path,required=True);p.add_argument("--review",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True);p.add_argument("--owner-receipt",type=Path);p.add_argument("--data-only",action="store_true")
    args=p.parse_args();report=build_data(args.source,args.review,args.out,args.owner_receipt)
    if not args.data_only:report["bundle"]=freeze_bundle(args.out)
    print(json.dumps(report,ensure_ascii=False,indent=2))
