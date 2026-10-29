"""Small portable contracts shared by preparation, GPU runtime and local review."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import unicodedata
import uuid
import zipfile

MODEL_ID = "Qwen/Qwen3-1.7B"
REVISION = "70d244cc86ccca08cf5af4e1e306ecf908b1ad5e"
EOS = 151645
SEED = 20261025


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value): return hashlib.sha256(canonical(value)).hexdigest()
def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()
def load(path): return json.loads(Path(path).read_text(encoding="utf-8-sig"))
def read_rows(path):
    with Path(path).open(encoding="utf-8-sig") as f:
        return [json.loads(line) for line in f if line.strip()]
def save(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name+"."+uuid.uuid4().hex+".partial")
    tmp.write_bytes(canonical(value)+b"\n"); os.replace(tmp, path)
def write_rows(path, rows):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name+"."+uuid.uuid4().hex+".partial")
    with tmp.open("wb") as f:
        for row in rows: f.write(canonical(row)+b"\n")
    os.replace(tmp, path)
def norm(text): return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip().casefold()


def strict_json(text):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result: raise ValueError("Duplicate key")
            result[key] = value
        return result
    return json.loads(text.strip(), object_pairs_hook=unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def verify_files(root, manifest_name="manifest.json"):
    root = Path(root).resolve(); manifest = load(root/manifest_name)
    for name, wanted in manifest["files_sha256"].items():
        rel = PurePosixPath(name); path = (root/name).resolve()
        if rel.is_absolute() or ".." in rel.parts or "\\" in name or ":" in name or not path.is_relative_to(root):
            raise ValueError("Unsafe registered path")
        if sha(path) != wanted: raise ValueError("Input bytes changed: "+name)
    return manifest


def native_bf16(torch):
    if torch.cuda.get_device_properties(0).major < 8: return False
    return bool(torch.cuda.is_bf16_supported(including_emulation=False))


def encode(tokenizer, messages, identity):
    if [m["role"] for m in messages] != ["system", "user", "assistant"]:
        raise ValueError("Chat role order")
    if tokenizer.eos_token_id != EOS: raise ValueError("Wrong tokenizer EOS")
    for m in messages:
        if any(x in m["content"] for x in ("<|im_start|>", "<|im_end|>", "<think>", "</think>")):
            raise ValueError("Reserved delimiter in source")
    prefix = tokenizer.apply_chat_template(messages[:-1], tokenize=False, add_generation_prompt=True, enable_thinking=False)
    full = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=False, enable_thinking=False)
    if not full.startswith(prefix): raise ValueError("Assistant prefix changed")
    ids = tokenizer(full, add_special_tokens=False)["input_ids"]
    prompt = tokenizer(prefix, add_special_tokens=False)["input_ids"]
    if ids[:len(prompt)] != prompt: raise ValueError("Token boundary changed")
    ends = [i for i in range(len(prompt), len(ids)) if ids[i] == EOS]
    if len(ends) != 1 or ends[0] <= len(prompt) or len(ids) > 4096:
        raise ValueError("Invalid assistant span or overlength; no truncation")
    labels = [-100]*len(ids)
    labels[len(prompt):ends[0]+1] = ids[len(prompt):ends[0]+1]
    return {"id": identity, "input_ids": ids, "labels": labels, "attention_mask": [1]*len(ids)}


def padded(rows, pad):
    width = (max(len(r["input_ids"]) for r in rows)+7)//8*8
    return {k: [r[k]+[(-100 if k == "labels" else 0 if k == "attention_mask" else pad)]*(width-len(r[k])) for r in rows]
            for k in ("input_ids", "attention_mask", "labels")}


def make_zip(path, files):
    path = Path(path); tmp = path.with_suffix(".partial.zip")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for name, source in sorted(files.items()): z.write(source, name)
    os.replace(tmp, path)
