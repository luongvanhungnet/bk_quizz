"""Portable, CPU-only integrity and assistant-loss contracts for completed SFT."""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path,PurePosixPath
import re
import uuid
import zipfile

SCHEMA="bkquiz-completed-sft-v1"
MODEL_ID="Qwen/Qwen3-1.7B"
MODEL_REVISION="70d244cc86ccca08cf5af4e1e306ecf908b1ad5e"
SPLITS=("train","validation","test")
EOS_ID=151645
CPT_HASHES={"adapter_config.json":"332b12c48d0421ed269f01bb9110224f005d8b50cac571c6f0ba0a5d0d470499",
            "adapter_model.safetensors":"b46d53c4807be3fdb4e246dc1066ea3dc4895128abbce5902cf65ee1e9c6a120"}
RESERVED=("<|im_start|>","<|im_end|>","<|endoftext|>","<think>","</think>")


def canonical(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode("utf-8")
def digest(value):return hashlib.sha256(canonical(value)).hexdigest()
def sha(path):
    with Path(path).open("rb") as stream:return hashlib.file_digest(stream,"sha256").hexdigest()
def load(path):return json.loads(Path(path).read_text(encoding="utf-8-sig"))
def save(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+"."+uuid.uuid4().hex+".partial")
    try:
        temporary.write_bytes(canonical(value)+b"\n");os.replace(temporary,path)
    finally:temporary.unlink(missing_ok=True)
def read_jsonl(path):
    with Path(path).open(encoding="utf-8-sig") as stream:
        for number,line in enumerate(stream,1):
            if not line.strip():raise ValueError(f"Blank JSONL line: {path}:{number}")
            value=json.loads(line)
            if not isinstance(value,dict):raise ValueError("JSONL object required")
            yield value


def inside(root,name):
    root=Path(root).resolve();rel=PurePosixPath(name)
    if not isinstance(name,str) or not name or "\\" in name or ":" in name or rel.is_absolute() or any(p in {"..","."} for p in rel.parts):
        raise ValueError("Unsafe bundled path")
    target=(root/name).resolve()
    if not target.is_relative_to(root):raise ValueError("Bundled path escapes dataset")
    return target


def validate_messages(row):
    messages=row.get("messages")
    if not isinstance(messages,list) or len(messages)!=3 or [m.get("role") for m in messages]!=["system","user","assistant"]:
        raise ValueError("Exactly system/user/assistant required")
    for message in messages:
        if set(message)!={"role","content"} or not isinstance(message["content"],str) or not message["content"].strip():raise ValueError("Invalid message fields")
        if any(marker in message["content"] for marker in RESERVED):raise ValueError("Reserved chat/think delimiter in sample content")
    return messages


def encode_chat(tokenizer,row,identity):
    messages=validate_messages(row)
    if tokenizer.eos_token!="<|im_end|>" or tokenizer.eos_token_id!=EOS_ID:raise ValueError("Pinned Qwen3 EOS required")
    prefix=tokenizer.apply_chat_template(messages[:-1],tokenize=False,add_generation_prompt=True,enable_thinking=False)
    full=tokenizer.apply_chat_template(messages,tokenize=False,add_generation_prompt=False,enable_thinking=False)
    if not full.startswith(prefix):raise ValueError("Chat generation prefix mismatch")
    ids=tokenizer(full,add_special_tokens=False,truncation=False)["input_ids"]
    prompt=tokenizer(prefix,add_special_tokens=False,truncation=False)["input_ids"]
    if ids[:len(prompt)]!=prompt:raise ValueError("Assistant token boundary changed")
    ends=[i for i in range(len(prompt),len(ids)) if ids[i]==EOS_ID]
    if len(ends)!=1 or ends[0]<=len(prompt):raise ValueError("Exactly one supervised EOS required")
    end=ends[0]+1
    if tokenizer.decode(ids[len(prompt):end],skip_special_tokens=False)!=messages[-1]["content"]+tokenizer.eos_token:raise ValueError("Assistant target differs from content plus EOS")
    labels=[-100]*len(ids);labels[len(prompt):end]=ids[len(prompt):end]
    return {"id":identity,"input_ids":ids,"attention_mask":[1]*len(ids),"labels":labels}


def validate_tokens(row,max_length=4096):
    if not isinstance(row.get("id"),str) or not row["id"]:raise ValueError("Tokenized sample ID required")
    ids=row.get("input_ids");labels=row.get("labels");attention=row.get("attention_mask")
    if not isinstance(ids,list) or not 2<=len(ids)<=max_length or any(type(v)is not int or v<0 for v in ids):raise ValueError("Invalid or overlength token sequence; truncation disabled")
    if not isinstance(labels,list) or len(labels)!=len(ids) or any(type(v)is not int for v in labels):raise ValueError("Invalid labels")
    if attention!=[1]*len(ids) or any(type(v)is not int for v in attention):raise ValueError("Unpadded samples require attention=1")
    positions=[i for i,v in enumerate(labels) if v!=-100]
    if not positions or positions[0]<1 or positions!=list(range(positions[0],positions[-1]+1)):raise ValueError("Assistant supervision must be nonempty and contiguous")
    if any(label!=-100 and label!=ids[i] for i,label in enumerate(labels)):raise ValueError("Supervised label must equal its input token")
    if labels[positions[-1]]!=EOS_ID or sum(labels[i]==EOS_ID for i in positions)!=1:raise ValueError("Exactly one supervised im_end required")
    return len(positions)


def verify_adapter(root):
    adapter=Path(root)/"assets/cpt_adapter"
    for name,wanted in CPT_HASHES.items():
        if sha(adapter/name)!=wanted:raise ValueError("Wrong CPT27 adapter: "+name)
    cfg=load(adapter/"adapter_config.json")
    if cfg.get("base_model_name_or_path")!=MODEL_ID or cfg.get("peft_type")!="LORA":raise ValueError("CPT adapter base/type mismatch")
    return adapter


def source_pages(entries):
    if not isinstance(entries,list) or not entries:raise ValueError("All source-page provenance is required")
    result=set()
    for entry in entries:
        if not isinstance(entry,dict) or not isinstance(entry.get("source_id"),str) or not entry["source_id"] or not isinstance(entry.get("pages"),list) or not entry["pages"]:
            raise ValueError("Incomplete source-page provenance")
        for page in entry["pages"]:
            if type(page)is not int or page<1:raise ValueError("Invalid physical source page")
            result.add((entry["source_id"],page))
    return result


def verify_completion_metadata(metadata,original,excluded_pages):
    if metadata.get("completion_origin")!="frozen_native_release" or metadata.get("source_pages_complete")is not True:
        raise ValueError("Sample is not from completed frozen native pages")
    for key in ("requires_additional_llm","requires_vlm","requires_manual_completion"):
        if metadata.get(key)is not False:raise ValueError("Sample still requires completion: "+key)
    pages=source_pages(metadata.get("sources"))
    if pages!=source_pages(original.get("origins")):raise ValueError("Original/all-origin page provenance differs from metadata")
    if pages & excluded_pages:raise ValueError("Sample touches excluded LLM/VLM/manual-review source page")
    return pages


def verify_dataset(root,tokenizer=None,verify_cpt=True):
    root=Path(root).resolve();manifest=load(root/"manifest.json")
    if manifest.get("schema")!=SCHEMA or manifest.get("source_policy")!="completed_native_pages_only":raise ValueError("Only completed-native SFT bundle accepted")
    if manifest.get("tokenizer_eos_token_id")!=EOS_ID or manifest.get("max_length")!=4096:raise ValueError("Pinned tokenizer/max-length contract changed")
    files=manifest.get("files_sha256")
    required={"MODEL_PROVENANCE.json","selection_policy.json","excluded_pages.jsonl","source_questions.jsonl",
              "tokenizer/tokenizer.json","tokenizer/tokenizer_config.json","tokenizer/chat_template.jinja",
              *(f"{split}.{kind}.jsonl" for split in SPLITS for kind in ("messages","metadata")),*(f"tokenized/{split}.jsonl" for split in SPLITS)}
    if not isinstance(files,dict) or not required.issubset(files):raise ValueError("Incomplete bundle file registry")
    for name,wanted in files.items():
        if not isinstance(wanted,str) or not re.fullmatch(r"[0-9a-f]{64}",wanted) or sha(inside(root,name))!=wanted:raise ValueError("Dataset file hash mismatch: "+name)
    provenance=load(root/"MODEL_PROVENANCE.json")
    if provenance.get("base_model")!=MODEL_ID or provenance.get("base_revision")!=MODEL_REVISION or provenance.get("current_cpt_adapter_sha256")!=CPT_HASHES:
        raise ValueError("Student/CPT provenance differs from pinned current model")
    if verify_cpt:verify_adapter(root)
    policy=load(root/"selection_policy.json")
    if manifest.get("source_policy_sha256")!=files["selection_policy.json"] or policy.get("source_policy")!="completed_native_pages_only":raise ValueError("Selection policy identity mismatch")
    if any(policy.get(key)is not True for key in ("all_origin_pages_must_be_complete","no_teacher_outputs_used","no_pending_stage2_questions_used")):
        raise ValueError("Selection policy must exclude incomplete/teacher/pending pages")
    excluded=list(read_jsonl(root/"excluded_pages.jsonl"));excluded_pages=set()
    for row in excluded:
        if not isinstance(row.get("source_id"),str) or not row["source_id"] or type(row.get("page"))is not int or row["page"]<1:raise ValueError("Invalid excluded page provenance")
        excluded_pages.add((row["source_id"],row["page"]))
    if policy.get("excluded_review_items")!=len(excluded) or policy.get("excluded_physical_pages")!=len(excluded_pages):raise ValueError("Excluded page policy count mismatch")
    originals=list(read_jsonl(root/"source_questions.jsonl"));by_original={row.get("id"):row for row in originals}
    if len(by_original)!=len(originals):raise ValueError("Duplicate original source-question ID")
    counts=manifest.get("counts",{});datasets={};ids=set();families={};chats={};supervised={}
    for split in SPLITS:
        tokens=list(read_jsonl(root/f"tokenized/{split}.jsonl"));messages=list(read_jsonl(root/f"{split}.messages.jsonl"));metas=list(read_jsonl(root/f"{split}.metadata.jsonl"))
        if len(tokens)!=len(messages) or len(tokens)!=len(metas) or counts.get(split)!=len(tokens):raise ValueError("Split rows/count mismatch: "+split)
        n_supervised=0
        for encoded,chat,meta in zip(tokens,messages,metas):
            identity=meta.get("id")
            if identity!=encoded.get("id") or meta.get("split")!=split or identity in ids:raise ValueError("Missing/duplicate sample or split mismatch")
            if identity not in by_original:raise ValueError("Original source question is missing")
            verify_completion_metadata(meta,by_original[identity],excluded_pages)
            ids.add(identity);family=meta.get("split_group")
            if not isinstance(family,str) or not family:raise ValueError("Question family provenance required")
            if family in families and families[family]!=split:raise ValueError("Question family crosses held-out splits")
            families[family]=split;validate_messages(chat)
            signature=digest(chat)
            if signature in chats:raise ValueError("Duplicate chat across dataset")
            chats[signature]=split;n_supervised+=validate_tokens(encoded,manifest["max_length"])
            if tokenizer is not None and encode_chat(tokenizer,chat,identity)!=encoded:raise ValueError("Stored assistant-only token mask differs from pinned tokenizer")
        datasets[split]=tokens;supervised[split]=n_supervised
    if not datasets["train"]:raise ValueError("Empty training split")
    if set(by_original)!=ids:raise ValueError("Original source-question count differs from selected samples")
    report={"schema":SCHEMA,"dataset_manifest_sha256":sha(root/"manifest.json"),"counts":{k:len(v) for k,v in datasets.items()},
            "supervised_tokens":supervised,"chat_mask_retokenized":tokenizer is not None,"cpt_hashes_verified":verify_cpt,
            "model_weights_loaded":False,"truncation":False,"source_policy":manifest["source_policy"],
            "max_length":manifest["max_length"],"test_used_for_training_or_selection":False}
    report.update(completed_page_dependencies_checked=True,excluded_physical_pages=len(excluded_pages))
    return manifest,provenance,datasets,report


def padded_batch(rows,pad_id):
    if not rows:raise ValueError("Nonempty batch required")
    width=math.ceil(max(len(r["input_ids"]) for r in rows)/8)*8
    result={key:[] for key in ("input_ids","attention_mask","labels")}
    for row in rows:
        n=len(row["input_ids"]);pad=width-n
        if len(row["labels"])!=n or len(row["attention_mask"])!=n:raise ValueError("Batch mask lengths differ")
        result["input_ids"].append(row["input_ids"]+[pad_id]*pad)
        result["attention_mask"].append(row["attention_mask"]+[0]*pad)
        result["labels"].append(row["labels"]+[-100]*pad)
    return result


def native_bf16(torch):
    if torch.cuda.get_device_properties(0).major<8:return False
    try:return bool(torch.cuda.is_bf16_supported(including_emulation=False))
    except TypeError:return True  # Older API: major>=8 supplies the native capability gate.


def complete_checkpoint(path,require_scaler=False):
    path=Path(path)
    required=["trainer_state.json","adapter_config.json","adapter_model.safetensors","optimizer.pt","scheduler.pt","rng_state.pth"]
    if require_scaler:required.append("scaler.pt")
    if not all((path/name).is_file() and (path/name).stat().st_size>0 for name in required):return False
    try:return load(path/"trainer_state.json").get("global_step")==int(path.name.removeprefix("checkpoint-"))
    except (ValueError,TypeError,AttributeError):return False


def latest_checkpoint(output,require_scaler=False):
    choices=[p for p in Path(output).glob("checkpoint-*") if p.name.removeprefix("checkpoint-").isdigit() and complete_checkpoint(p,require_scaler)]
    if not choices:raise ValueError("No complete checkpoint with optimizer/scheduler/RNG state; use a new output directory")
    return max(choices,key=lambda p:int(p.name.removeprefix("checkpoint-")))


def export_zip(path,files):
    path=Path(path);temporary=path.with_suffix(".partial.zip")
    with zipfile.ZipFile(temporary,"w",zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for name,target in sorted(files.items()):archive.write(target,name)
    temporary.replace(path);return path
