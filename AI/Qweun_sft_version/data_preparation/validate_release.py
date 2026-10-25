"""Independent structural, provenance and token-mask audit of an SFT release.

This verifies the recorded evidence and training representation. It does not
establish expert correctness of the source answer keys or generated questions.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import unicodedata
from typing import Any

from prepare_sft import SPLITS, encode_example, read_jsonl, sha256, validate_messages


def normalized_option(value: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", value)).strip().casefold()


def validate_output(value: Any, context: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(value, dict) or not isinstance(value.get("questions"), list):
        return ["assistant JSON must be an object with a questions list"]
    for index, question in enumerate(value["questions"]):
        tag = f"question[{index}]"
        if not isinstance(question, dict):
            errors.append(f"{tag}: expected an object")
            continue
        kind = question.get("type")
        if kind not in {"SINGLE_CHOICE", "MULTIPLE_SELECT", "FILL_BLANK"}:
            errors.append(f"{tag}: unsupported question type")
        for field in ("prompt", "explanation"):
            text = question.get(field)
            if not isinstance(text, str) or not 1 <= len(text.strip()) <= 10000:
                errors.append(f"{tag}: {field} must be a nonempty string up to 10000 characters")
        options = question.get("options", [])
        if not isinstance(options, list):
            errors.append(f"{tag}: options must be a list")
            options = []
        texts, correct = [], 0
        for option in options:
            if not isinstance(option, dict) or set(option) != {"text", "correct"}:
                errors.append(f"{tag}: each option must contain text and correct only")
                continue
            text = option.get("text")
            if not isinstance(text, str) or not 1 <= len(text.strip()) <= 2000:
                errors.append(f"{tag}: option text is empty or longer than 2000 characters")
            else:
                texts.append(normalized_option(text))
            if not isinstance(option.get("correct"), bool):
                errors.append(f"{tag}: correct must be a JSON boolean")
            correct += option.get("correct") is True
        if len(texts) != len(set(texts)):
            errors.append(f"{tag}: duplicate option text")
        if kind in {"SINGLE_CHOICE", "MULTIPLE_SELECT"}:
            if not 2 <= len(options) <= 8:
                errors.append(f"{tag}: choice questions require 2 to 8 options")
            if kind == "SINGLE_CHOICE" and correct != 1:
                errors.append(f"{tag}: SINGLE_CHOICE must have exactly one correct option")
            if kind == "MULTIPLE_SELECT" and correct < 2:
                errors.append(f"{tag}: MULTIPLE_SELECT must have at least two correct options")
            if correct >= len(options):
                errors.append(f"{tag}: at least one incorrect option is required")
        accepted = question.get("acceptedAnswers", [])
        if not isinstance(accepted, list) or any(not isinstance(v, str) or not v.strip() for v in accepted):
            errors.append(f"{tag}: acceptedAnswers must be a list of nonempty strings")
        if kind == "FILL_BLANK" and (options or not accepted):
            errors.append(f"{tag}: FILL_BLANK requires acceptedAnswers and no options")
        if question.get("difficulty") not in {None, "EASY", "MEDIUM", "HARD"}:
            errors.append(f"{tag}: unsupported difficulty")
        if question.get("cognitiveLevel") not in {None, "L1", "L2", "L3", "L4", "L5"}:
            errors.append(f"{tag}: unsupported cognitive level")
        for field in ("questionCitations", "answerCitations", "explanationCitations"):
            citations = question.get(field)
            if not isinstance(citations, list) or not citations:
                errors.append(f"{tag}: {field} must contain at least one citation")
                continue
            for citation in citations:
                if not isinstance(citation, dict):
                    errors.append(f"{tag}: malformed {field} entry")
                    continue
                source_id, quote = citation.get("sourceId"), citation.get("evidenceQuote")
                if not isinstance(source_id, str) or not source_id.strip() or source_id not in context:
                    errors.append(f"{tag}: citation sourceId is absent from user context")
                if not isinstance(quote, str) or not 1 <= len(quote.strip()) <= 1000 or quote not in context:
                    errors.append(f"{tag}: citation evidenceQuote is absent from user context or invalid")
    return errors


def source_entries(metadata: dict[str, Any]) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for field in ("sources", "provenance", "originals"):
        value = metadata.get(field)
        if not isinstance(value, list):
            continue
        for raw in value:
            if isinstance(raw, dict):
                path = raw.get("path", raw.get("source_path"))
                digest = raw.get("sha256", raw.get("source_sha256"))
                if path and digest:
                    entries.append({"path": path, "sha256": digest, "source_id": raw.get("source_id", "")})
    if metadata.get("source_path") and metadata.get("source_sha256"):
        entries.append({"path": metadata["source_path"], "sha256": metadata["source_sha256"],
                        "source_id": metadata.get("source_id", "")})
    return entries


def validate_release(dataset: Path, tokenizer_path: Path | None = None,
                     verify_sources: bool = False, *, allow_shared_source_documents: bool = False,
                     write_report: bool = True) -> dict[str, Any]:
    dataset = dataset.resolve()
    errors: list[str] = []
    warnings: list[str] = []
    counts: Counter[str] = Counter()
    manifest_path = dataset / "release_manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        hashes = manifest["files_sha256"]
        if not isinstance(hashes, dict) or not hashes:
            raise ValueError("files_sha256 must be a nonempty mapping")
    except (OSError, ValueError, KeyError, TypeError) as error:
        errors.append(f"release_manifest.json: {error}")
        hashes = {}
    for name, expected in hashes.items():
        if not isinstance(name, str) or not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
            errors.append(f"Manifest contains an invalid hash entry: {name!r}")
            continue
        path = (dataset / name).resolve()
        if not path.is_relative_to(dataset):
            errors.append(f"Manifest path leaves the release directory: {name}")
            continue
        try:
            actual = sha256(path)
            counts["release_files_hashed"] += 1
            if actual != expected:
                errors.append(f"Release hash mismatch: {name}")
        except OSError as error:
            errors.append(f"Cannot hash release file {name}: {error}")
    required = [f"{split}.{kind}.jsonl" for split in SPLITS for kind in ("messages", "metadata")]
    required += [f"tokenized/{split}.jsonl" for split in SPLITS]
    required += ["build_report.json", "tokenization_report.json", "tokenized/overlength.jsonl"]
    for name in required:
        if name not in hashes:
            errors.append(f"Required release file is absent from files_sha256: {name}")
    build_report: dict[str, Any] = {}
    try:
        build_report = json.loads((dataset / "build_report.json").read_text(encoding="utf-8-sig"))
        if not isinstance(build_report, dict):
            errors.append("build_report.json must contain an object")
            build_report = {}
    except (OSError, ValueError) as error:
        errors.append(f"build_report.json: {error}")
    allow_shared = allow_shared_source_documents and build_report.get("split_policy") == "question_family"
    if allow_shared_source_documents and not allow_shared:
        errors.append("Shared source documents require build_report.json split_policy=question_family")
    if allow_shared:
        warnings.append("source PDFs shared; not unseen-document evaluation")
    tokenizer = None
    if tokenizer_path is not None:
        try:
            from transformers import AutoTokenizer
            if not tokenizer_path.is_dir():
                raise ValueError("Expected a local tokenizer directory")
            tokenizer = AutoTokenizer.from_pretrained(str(tokenizer_path.resolve()), local_files_only=True)
        except (OSError, ValueError) as error:
            errors.append(f"Tokenizer could not be loaded offline: {error}")
    else:
        warnings.append("Exact assistant-only token-mask reconstruction was skipped because --tokenizer was omitted.")
    try:
        token_report = json.loads((dataset / "tokenization_report.json").read_text(encoding="utf-8-sig"))
        max_length = token_report["max_length"]
        if token_report.get("truncation") is not False or token_report.get("enable_thinking") is not False:
            errors.append("Tokenization report must explicitly disable truncation and thinking")
    except (OSError, ValueError, KeyError, TypeError) as error:
        errors.append(f"tokenization_report.json: {error}")
        max_length = None
    excluded_ids: dict[str, str] = {}
    queue_path = dataset / "tokenized/overlength.jsonl"
    if queue_path.is_file():
        try:
            for _, row in read_jsonl(queue_path):
                sample_id, split = row.get("id"), row.get("split")
                if not isinstance(sample_id, str) or split not in SPLITS or sample_id in excluded_ids:
                    errors.append("Overlength queue contains an invalid or duplicate id/split")
                    continue
                excluded_ids[sample_id] = split
                if row.get("reason") != "sequence_exceeds_max_length" or not isinstance(row.get("token_count"), int):
                    errors.append(f"{sample_id}: invalid overlength exclusion reason or length")
                elif max_length is not None and row["token_count"] <= max_length:
                    errors.append(f"{sample_id}: excluded record does not exceed maximum length")
        except (OSError, ValueError) as error:
            errors.append(f"overlength.jsonl: {error}")
    seen_ids: dict[str, str] = {}
    source_splits: dict[str, str] = {}
    source_membership: dict[str, set[str]] = {}
    family_splits: dict[str, str] = {}
    content_ids: dict[str, str] = {}
    checked_sources: dict[str, str] = {}
    seen_excluded: set[str] = set()
    split_counts: dict[str, dict[str, int]] = {}
    for split in SPLITS:
        try:
            chats = [row for _, row in read_jsonl(dataset / f"{split}.messages.jsonl")]
            metadata_rows = [row for _, row in read_jsonl(dataset / f"{split}.metadata.jsonl")]
            tokens = [row for _, row in read_jsonl(dataset / "tokenized" / f"{split}.jsonl")]
        except (OSError, ValueError) as error:
            errors.append(f"{split}: {error}")
            continue
        split_counts[split] = {"chats": len(chats), "metadata": len(metadata_rows), "tokenized": len(tokens)}
        if len(chats) != len(metadata_rows):
            errors.append(f"{split}: chat and metadata record counts differ")
            continue
        expected_token_ids = []
        reconstructed: dict[str, dict[str, Any]] = {}
        for line, (chat, metadata) in enumerate(zip(chats, metadata_rows), 1):
            sample_id = metadata.get("id")
            tag = f"{split}:{line}:{sample_id}"
            if not isinstance(sample_id, str) or not sample_id.strip() or metadata.get("split") != split:
                errors.append(f"{tag}: invalid metadata id/split")
                continue
            if sample_id in seen_ids:
                errors.append(f"{tag}: duplicate id also present in {seen_ids[sample_id]}")
            seen_ids[sample_id] = split
            family = metadata.get("split_group")
            if family is not None or allow_shared:
                if not isinstance(family, str) or not family.strip():
                    errors.append(f"{tag}: nonempty split_group is required")
                else:
                    if family in family_splits and family_splits[family] != split:
                        errors.append(f"{tag}: question family {family} occurs in both {family_splits[family]} and {split}")
                    family_splits[family] = split
            content_hash = metadata.get("content_sha256")
            if content_hash is not None or allow_shared:
                if not isinstance(content_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", content_hash):
                    errors.append(f"{tag}: valid content_sha256 is required")
                elif content_hash in content_ids:
                    errors.append(f"{tag}: duplicate content_sha256 also used by {content_ids[content_hash]}")
                else:
                    content_ids[content_hash] = sample_id
            ids = metadata.get("source_ids", [])
            if metadata.get("source_id"):
                ids = [*(ids if isinstance(ids, list) else []), metadata["source_id"]]
            if not isinstance(ids, list) or not ids or any(not isinstance(i, str) or not i for i in ids):
                errors.append(f"{tag}: nonempty source_ids provenance is required")
                ids = []
            for source_id in ids:
                if source_id in source_splits and source_splits[source_id] != split and not allow_shared:
                    errors.append(f"{tag}: source {source_id} occurs in both {source_splits[source_id]} and {split}")
                source_splits[source_id] = split
                source_membership.setdefault(source_id, set()).add(split)
            try:
                messages = validate_messages(chat)
                parsed = json.loads(messages[-1]["content"])
                errors.extend(f"{tag}: {error}" for error in validate_output(parsed, messages[1]["content"]))
                counts["chat_records_checked"] += 1
                if tokenizer is not None:
                    reconstructed[sample_id] = encode_example(tokenizer, chat, sample_id)
            except (ValueError, TypeError) as error:
                errors.append(f"{tag}: malformed chat or assistant JSON: {error}")
            if sample_id in excluded_ids:
                seen_excluded.add(sample_id)
                if excluded_ids[sample_id] != split:
                    errors.append(f"{tag}: overlength queue refers to the wrong split")
                if sample_id in reconstructed and max_length is not None and len(reconstructed[sample_id]["input_ids"]) <= max_length:
                    errors.append(f"{tag}: reconstructed record should not have been excluded as overlength")
            else:
                expected_token_ids.append(sample_id)
            if verify_sources:
                entries = source_entries(metadata)
                if not entries:
                    errors.append(f"{tag}: no source path/SHA-256 entries available for --verify-sources")
                for entry in entries:
                    path, expected = entry["path"], entry["sha256"]
                    if not isinstance(path, str) or not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
                        errors.append(f"{tag}: malformed source path/SHA-256")
                        continue
                    if path in checked_sources:
                        if checked_sources[path] != expected:
                            errors.append(f"{tag}: conflicting expected hashes for source {path}")
                        continue
                    checked_sources[path] = expected
                    try:
                        if sha256(Path(path)) != expected:
                            errors.append(f"{tag}: source hash mismatch: {path}")
                        counts["source_files_hashed"] += 1
                    except OSError as error:
                        errors.append(f"{tag}: source unavailable: {path}: {error}")
        actual_token_ids = [row.get("id") for row in tokens]
        if actual_token_ids != expected_token_ids:
            errors.append(f"{split}: tokenized ids/order do not match non-excluded metadata ids")
        for token_row in tokens:
            sample_id = token_row.get("id")
            tag = f"{split}:{sample_id}:tokens"
            if not isinstance(sample_id, str) or not sample_id:
                errors.append(f"{tag}: invalid token record id")
                continue
            input_ids, attention, labels = (token_row.get(field) for field in ("input_ids", "attention_mask", "labels"))
            if not all(isinstance(value, list) for value in (input_ids, attention, labels)):
                errors.append(f"{tag}: input_ids/attention_mask/labels must be lists")
                continue
            if not input_ids or not len(input_ids) == len(attention) == len(labels):
                errors.append(f"{tag}: sequence field lengths differ or are empty")
                continue
            if any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in input_ids):
                errors.append(f"{tag}: token ids must be nonnegative integers")
            if any(type(value) is not int or value != 1 for value in attention):
                errors.append(f"{tag}: persisted examples must be unpadded with attention=1")
            if any(type(value) is not int or value < 0 and value != -100 for value in labels):
                errors.append(f"{tag}: labels must contain integer token ids or -100")
            active = [i for i, value in enumerate(labels) if value != -100]
            if not active or active[0] == 0 or active != list(range(active[0], active[-1] + 1)):
                errors.append(f"{tag}: assistant supervision must be one nonempty suffix region after a masked prompt")
            if any(value != -100 and value != input_ids[i] for i, value in enumerate(labels)):
                errors.append(f"{tag}: active labels differ from corresponding input token ids")
            if max_length is not None and len(input_ids) > max_length:
                errors.append(f"{tag}: persisted sequence exceeds maximum length")
            if tokenizer is not None and sample_id in reconstructed:
                expected = reconstructed[sample_id]
                if any(token_row.get(field) != expected[field] for field in ("input_ids", "attention_mask", "labels")):
                    errors.append(f"{tag}: token ids or assistant-only mask differ from exact offline reconstruction")
                else:
                    counts["token_masks_reconstructed"] += 1
            counts["token_records_checked"] += 1
    for sample_id in excluded_ids.keys() - seen_excluded:
        errors.append(f"Orphan overlength queue id: {sample_id}")
    if not split_counts.get("train", {}).get("tokenized", 0):
        errors.append("Training split has no usable tokenized records")
    warnings.append("Structural checks do not establish expert correctness of source answer keys or pedagogical quality of explanations.")
    report = {
        "schema": "bkquiz-sft-release-validation-v1", "dataset": str(dataset),
        "release_manifest_sha256": sha256(dataset / "release_manifest.json") if (dataset / "release_manifest.json").is_file() else None,
        "passed": not errors, "errors": errors, "warnings": warnings,
        "counts": dict(counts), "splits": split_counts,
        "distinct_record_ids": len(seen_ids), "distinct_source_ids": len(source_splits),
        "overlength_records": len(excluded_ids), "max_length": max_length,
        "verify_sources_requested": verify_sources,
        "allow_shared_source_documents": allow_shared,
        "split_policy": build_report.get("split_policy"),
        "shared_source_documents": sum(len(splits) > 1 for splits in source_membership.values()),
        "distinct_question_families": len(family_splits),
        "distinct_content_hashes": len(content_ids),
        "exact_tokenizer_reconstruction": tokenizer is not None,
        "tokenizer": str(tokenizer_path.resolve()) if tokenizer_path else None,
        "training_or_inference_run": False,
    }
    if write_report:
        (dataset / "validation_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--tokenizer", type=Path)
    parser.add_argument("--verify-sources", action="store_true")
    parser.add_argument("--allow-shared-source-documents", action="store_true")
    args = parser.parse_args()
    report = validate_release(args.dataset, args.tokenizer, args.verify_sources,
                              allow_shared_source_documents=args.allow_shared_source_documents)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
