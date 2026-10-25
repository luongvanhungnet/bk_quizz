"""Offline Qwen3 chat tokenization with loss on assistant content and EOS only.

Input: {train,validation,test}.messages.jsonl and matching .metadata.jsonl.
No weights are loaded, no network request is made, and long records are never cut.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
from itertools import zip_longest
import json
import math
from pathlib import Path
from statistics import median
from typing import Any, Iterable


SPLITS = ("train", "validation", "test")
RESERVED_MARKERS = ("<|im_start|>", "<|im_end|>", "<|endoftext|>", "<think>", "</think>")
TOKENIZER_FILES = (
    "tokenizer.json", "tokenizer_config.json", "chat_template.jinja", "vocab.json",
    "merges.txt", "special_tokens_map.json", "added_tokens.json",
)


def sha256(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def read_jsonl(path: Path) -> Iterable[tuple[int, dict[str, Any]]]:
    """Iterate physical LF/CRLF lines. str.splitlines splits valid U+2028 strings."""
    with path.open("r", encoding="utf-8-sig", newline=None) as source:
        for line_number, line in enumerate(source, 1):
            if not line.strip():
                raise ValueError(f"{path}:{line_number}: blank JSONL record")
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"{path}:{line_number}: invalid physical JSONL line: {error.msg}") from error
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{line_number}: expected JSON object")
            yield line_number, row


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as output:
        for row in rows:
            output.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def validate_messages(row: dict[str, Any]) -> list[dict[str, str]]:
    messages = row.get("messages")
    if not isinstance(messages, list) or len(messages) != 3:
        raise ValueError("Expected exactly three messages: system, user, assistant")
    if [m.get("role") if isinstance(m, dict) else None for m in messages] != ["system", "user", "assistant"]:
        raise ValueError("Expected message roles system, user, assistant in that order")
    for message in messages:
        if not isinstance(message.get("content"), str) or not message["content"].strip():
            raise ValueError("Every message must contain nonempty string content")
        if set(message) != {"role", "content"}:
            raise ValueError("Only role/content fields are supported; reasoning/tool fields need a separate pipeline")
        if any(marker in message["content"] for marker in RESERVED_MARKERS):
            raise ValueError("Message content contains a reserved chat or reasoning delimiter")
    return messages


def encode_example(tokenizer: Any, row: dict[str, Any], sample_id: str) -> dict[str, Any]:
    messages = validate_messages(row)
    if tokenizer.eos_token != "<|im_end|>":
        raise ValueError("This preparation requires a Qwen chat tokenizer with <|im_end|> EOS")
    prompt = tokenizer.apply_chat_template(
        messages[:-1], tokenize=False, add_generation_prompt=True, enable_thinking=False,
    )
    full = tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=False, enable_thinking=False,
    )
    if not full.startswith(prompt):
        raise ValueError(f"{sample_id}: full chat does not preserve its generation prefix")
    input_ids = tokenizer(full, add_special_tokens=False, truncation=False)["input_ids"]
    prompt_ids = tokenizer(prompt, add_special_tokens=False, truncation=False)["input_ids"]
    if input_ids[:len(prompt_ids)] != prompt_ids:
        raise ValueError(f"{sample_id}: token boundary merges across the assistant generation prefix")
    assistant_start = len(prompt_ids)
    eos_positions = [i for i in range(assistant_start, len(input_ids)) if input_ids[i] == tokenizer.eos_token_id]
    if len(eos_positions) != 1 or eos_positions[0] <= assistant_start:
        raise ValueError(f"{sample_id}: expected exactly one EOS after nonempty assistant content")
    assistant_end = eos_positions[0] + 1
    decoded_target = tokenizer.decode(input_ids[assistant_start:assistant_end], skip_special_tokens=False)
    if decoded_target != messages[-1]["content"] + tokenizer.eos_token:
        raise ValueError(f"{sample_id}: supervised tokens do not exactly equal assistant content plus EOS")
    labels = [-100] * len(input_ids)
    labels[assistant_start:assistant_end] = input_ids[assistant_start:assistant_end]
    # The Qwen template's empty think block belongs to the prompt. Its final
    # formatting newline after <|im_end|> is also excluded from supervision.
    return {
        "id": sample_id, "input_ids": input_ids, "attention_mask": [1] * len(input_ids),
        "labels": labels,
    }


def pad_batch(rows: list[dict[str, Any]], pad_token_id: int, multiple_of: int = 8) -> dict[str, list[list[int]]]:
    """Preserve each loss mask and mask added padding by position, including EOS=PAD."""
    if not rows or multiple_of < 1:
        raise ValueError("A nonempty batch and positive padding multiple are required")
    width = math.ceil(max(len(row["input_ids"]) for row in rows) / multiple_of) * multiple_of
    batch: dict[str, list[list[int]]] = {"input_ids": [], "attention_mask": [], "labels": []}
    for row in rows:
        length = len(row["input_ids"])
        if len(row["attention_mask"]) != length or len(row["labels"]) != length:
            raise ValueError("Input, attention, and label lengths differ")
        padding = width - length
        batch["input_ids"].append(row["input_ids"] + [pad_token_id] * padding)
        batch["attention_mask"].append(row["attention_mask"] + [0] * padding)
        batch["labels"].append(row["labels"] + [-100] * padding)
    return batch


def length_statistics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    lengths = sorted(len(row["input_ids"]) for row in rows)
    return {
        "records": len(rows),
        "total_tokens": sum(lengths),
        "supervised_tokens": sum(sum(label != -100 for label in row["labels"]) for row in rows),
        "masked_tokens": sum(sum(label == -100 for label in row["labels"]) for row in rows),
        "length_min": lengths[0] if lengths else None,
        "length_median": median(lengths) if lengths else None,
        "length_p95": lengths[max(0, math.ceil(len(lengths) * .95) - 1)] if lengths else None,
        "length_max": lengths[-1] if lengths else None,
    }


def prepare(dataset: Path, tokenizer_path: Path, max_length: int = 4096, *,
            allow_shared_source_documents: bool = False) -> dict[str, Any]:
    if not tokenizer_path.is_dir():
        raise ValueError(f"A local tokenizer directory is required: {tokenizer_path}")
    if max_length < 2:
        raise ValueError("max_length must be at least 2")
    if allow_shared_source_documents:
        try:
            policy = json.loads((dataset / "build_report.json").read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as error:
            raise ValueError("Shared source documents require build_report.json split_policy=question_family") from error
        if not isinstance(policy, dict) or policy.get("split_policy") != "question_family":
            raise ValueError("Shared source documents require build_report.json split_policy=question_family")
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(str(tokenizer_path.resolve()), local_files_only=True)
    included: dict[str, list[dict[str, Any]]] = {split: [] for split in SPLITS}
    excluded = []
    counts: Counter[str] = Counter()
    input_hashes: dict[str, str] = {}
    seen_ids: dict[str, str] = {}
    source_splits: dict[str, str] = {}
    source_membership: dict[str, set[str]] = {}
    family_splits: dict[str, str] = {}
    content_ids: dict[str, str] = {}
    for split in SPLITS:
        message_path = dataset / f"{split}.messages.jsonl"
        metadata_path = dataset / f"{split}.metadata.jsonl"
        input_hashes[message_path.name] = sha256(message_path)
        input_hashes[metadata_path.name] = sha256(metadata_path)
        pairs = zip_longest(read_jsonl(message_path), read_jsonl(metadata_path))
        for message_entry, metadata_entry in pairs:
            if message_entry is None or metadata_entry is None:
                raise ValueError(f"{split}: message and metadata record counts differ")
            line_number, message = message_entry
            _, metadata = metadata_entry
            sample_id = metadata.get("id")
            if not isinstance(sample_id, str) or not sample_id.strip() or metadata.get("split") != split:
                raise ValueError(f"{metadata_path}:{line_number}: expected nonempty id and split={split}")
            if sample_id in seen_ids:
                raise ValueError(f"Duplicate sample id {sample_id} in {seen_ids[sample_id]} and {split}")
            seen_ids[sample_id] = split
            family = metadata.get("split_group")
            if family is not None or allow_shared_source_documents:
                if not isinstance(family, str) or not family.strip():
                    raise ValueError(f"{sample_id}: nonempty split_group is required")
                if family in family_splits and family_splits[family] != split:
                    raise ValueError(f"Question family {family} appears in both {family_splits[family]} and {split}")
                family_splits[family] = split
            content_hash = metadata.get("content_sha256")
            if content_hash is not None or allow_shared_source_documents:
                if not isinstance(content_hash, str) or len(content_hash) != 64 or any(c not in "0123456789abcdef" for c in content_hash):
                    raise ValueError(f"{sample_id}: valid content_sha256 is required")
                if content_hash in content_ids:
                    raise ValueError(f"Duplicate content_sha256 for {content_ids[content_hash]} and {sample_id}")
                content_ids[content_hash] = sample_id
            source_ids = metadata.get("source_ids", [])
            if metadata.get("source_id"):
                source_ids = [*source_ids, metadata["source_id"]]
            for source_id in source_ids:
                if source_id in source_splits and source_splits[source_id] != split and not allow_shared_source_documents:
                    raise ValueError(f"Source {source_id} appears in both {source_splits[source_id]} and {split}")
                source_splits[source_id] = split
                source_membership.setdefault(source_id, set()).add(split)
            counts[split] += 1
            try:
                encoded = encode_example(tokenizer, message, sample_id)
            except ValueError as error:
                raise ValueError(f"{message_path}:{line_number}: {error}") from error
            if len(encoded["input_ids"]) > max_length:
                excluded.append({
                    "id": sample_id, "split": split, "reason": "sequence_exceeds_max_length",
                    "token_count": len(encoded["input_ids"]), "max_length": max_length,
                    "input_line": line_number, "messages_file": message_path.name,
                    "metadata_file": metadata_path.name, "metadata": metadata,
                })
            else:
                included[split].append(encoded)
    output = dataset / "tokenized"
    output.mkdir(parents=True, exist_ok=True)
    for split in SPLITS:
        write_jsonl(output / f"{split}.jsonl", included[split])
    write_jsonl(output / "overlength.jsonl", excluded)
    report = {
        "schema": "bkquiz-qwen3-assistant-loss-v1",
        "dataset": str(dataset.resolve()), "tokenizer": str(tokenizer_path.resolve()),
        "tokenizer_sha256": {name: sha256(tokenizer_path / name) for name in TOKENIZER_FILES if (tokenizer_path / name).is_file()},
        "inputs_sha256": input_hashes,
        "max_length": max_length, "truncation": False, "enable_thinking": False,
        "allow_shared_source_documents": allow_shared_source_documents,
        "split_policy": "question_family" if allow_shared_source_documents else "source_document",
        "shared_source_documents": sum(len(splits) > 1 for splits in source_membership.values()),
        "evaluation_limitation": "source PDFs shared; not unseen-document evaluation" if allow_shared_source_documents else None,
        "loss_policy": {
            "system_user_and_assistant_prefix": "masked_-100",
            "empty_think_prefix": "masked_-100",
            "assistant_content_and_im_end": "supervised",
            "post_eos_formatting_newline": "masked_-100",
            "padding": "mask_by_position_-100; preserve_existing_prompt_mask",
            "packing": False,
        },
        "splits": {split: {"input_records": counts[split],
                           "excluded_overlength": sum(row["split"] == split for row in excluded),
                           **length_statistics(included[split])} for split in SPLITS},
        "excluded_overlength_total": len(excluded),
        "outputs_sha256": {path.relative_to(dataset).as_posix(): sha256(path) for path in sorted(output.glob("*.jsonl"))},
        "model_weights_loaded": False, "network_used": False,
    }
    (dataset / "tokenization_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--tokenizer", type=Path, required=True)
    parser.add_argument("--max-length", type=int, default=4096)
    parser.add_argument("--allow-shared-source-documents", action="store_true",
                        help="Require question_family build policy, disjoint families and unique content hashes")
    args = parser.parse_args()
    report = prepare(args.dataset, args.tokenizer, args.max_length,
                     allow_shared_source_documents=args.allow_shared_source_documents)
    print(json.dumps({"splits": report["splits"], "excluded_overlength_total": report["excluded_overlength_total"],
                      "report": str((args.dataset / "tokenization_report.json").resolve())}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
