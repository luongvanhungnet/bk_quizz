"""Reproducible release-validation fixtures; all artifacts live in temporary folders."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from prepare_sft import encode_example, prepare, read_jsonl, sha256, write_jsonl
from validate_release import validate_output, validate_release


AI_ROOT = Path(__file__).resolve().parents[2]
TOKENIZER = AI_ROOT / "data_preprocessing/training_releases/cpt_27courses_20261023/tokenizer_pinned"


def grounded_question(prompt: str = "Chọn đáp án nào?") -> dict:
    citation = {"sourceId": "ctx_1", "evidenceQuote": "A là lựa chọn đúng."}
    return {
        "type": "SINGLE_CHOICE", "prompt": prompt,
        "options": [{"text": "A", "correct": True}, {"text": "B", "correct": False}],
        "explanation": "Tài liệu xác nhận A.", "acceptedAnswers": [],
        "questionCitations": [citation], "answerCitations": [citation],
        "explanationCitations": [citation],
    }


def manifest(root: Path) -> None:
    paths = list(root.glob("*.messages.jsonl")) + list(root.glob("*.metadata.jsonl"))
    paths += list((root / "tokenized").glob("*.jsonl"))
    paths += [root / "build_report.json", root / "tokenization_report.json"]
    value = {"files_sha256": {path.relative_to(root).as_posix(): sha256(path) for path in paths}}
    (root / "release_manifest.json").write_text(json.dumps(value), encoding="utf-8")


def release_fixture(root: Path, *, family_policy: bool = False) -> None:
    source = root / "source.txt"
    source.write_text("Nguồn đã xác nhận A là lựa chọn đúng.", encoding="utf-8")
    policy = "question_family" if family_policy else "source_document"
    (root / "build_report.json").write_text(json.dumps({"split_policy": policy}), encoding="utf-8")
    for split in ("train", "validation", "test"):
        question = grounded_question(f"Chọn đáp án nào cho ví dụ {split}?")
        assistant = json.dumps({"questions": [question]}, ensure_ascii=False)
        chat = {"messages": [
            {"role": "system", "content": "Tạo câu hỏi theo nguồn."},
            {"role": "user", "content": "ctx_1\nA là lựa chọn đúng.\u2028Đây là ngữ cảnh."},
            {"role": "assistant", "content": assistant},
        ]}
        metadata = {
            "id": f"{split}_q1", "split": split, "source_ids": ["source_1"],
            "sources": [{"source_id": "source_1", "path": str(source), "sha256": sha256(source)}],
            "split_group": f"{split}_family",
            "content_sha256": hashlib.sha256(assistant.encode()).hexdigest(),
        }
        present = family_policy or split == "train"
        write_jsonl(root / f"{split}.messages.jsonl", [chat] if present else [])
        write_jsonl(root / f"{split}.metadata.jsonl", [metadata] if present else [])
    prepare(root, TOKENIZER, allow_shared_source_documents=family_policy)
    manifest(root)


@unittest.skipUnless(TOKENIZER.is_dir(), "Pinned local Qwen3 tokenizer unavailable")
class ReleaseValidationTests(unittest.TestCase):
    def test_valid_release_checks_real_tokenizer_unicode_and_sources(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            release_fixture(root)
            report = validate_release(root, TOKENIZER, True, write_report=False)
            self.assertTrue(report["passed"], report["errors"])
            self.assertEqual(report["counts"]["token_masks_reconstructed"], 1)
            self.assertEqual(report["counts"]["source_files_hashed"], 1)

    def test_prompt_loss_is_rejected_even_after_updating_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            release_fixture(root)
            path = root / "tokenized/train.jsonl"
            rows = [row for _, row in read_jsonl(path)]
            rows[0]["labels"][0] = rows[0]["input_ids"][0]
            write_jsonl(path, rows)
            manifest(root)
            report = validate_release(root, TOKENIZER, True, write_report=False)
            self.assertFalse(report["passed"])
            self.assertTrue(any("mask differ" in error for error in report["errors"]))

    def test_missing_quote_is_rejected(self) -> None:
        question = grounded_question()
        question["answerCitations"] = [{"sourceId": "ctx_1", "evidenceQuote": "Absent evidence"}]
        errors = validate_output({"questions": [question]}, "ctx_1\nA là lựa chọn đúng.")
        self.assertTrue(any("evidenceQuote" in error for error in errors))

    def test_all_options_correct_is_rejected(self) -> None:
        question = grounded_question()
        question["type"] = "MULTIPLE_SELECT"
        question["options"][1]["correct"] = True
        errors = validate_output({"questions": [question]}, "ctx_1\nA là lựa chọn đúng.")
        self.assertTrue(any("incorrect option" in error for error in errors))

    def test_manifest_tampering_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            release_fixture(root)
            (root / "build_report.json").write_text('{"changed":true}', encoding="utf-8")
            report = validate_release(root, write_report=False)
            self.assertFalse(report["passed"])
            self.assertTrue(any("hash mismatch" in error for error in report["errors"]))

    def test_source_hash_tampering_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            release_fixture(root)
            (root / "source.txt").write_text("Changed source", encoding="utf-8")
            report = validate_release(root, TOKENIZER, True, write_report=False)
            self.assertFalse(report["passed"])
            self.assertTrue(any("source hash mismatch" in error for error in report["errors"]))

    def test_cross_split_source_leak_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            release_fixture(root)
            chat = next(read_jsonl(root / "train.messages.jsonl"))[1]
            metadata = next(read_jsonl(root / "train.metadata.jsonl"))[1]
            metadata.update(id="test_q2", split="test", split_group="test_family",
                            content_sha256=hashlib.sha256(b"another-content").hexdigest())
            write_jsonl(root / "test.messages.jsonl", [chat])
            write_jsonl(root / "test.metadata.jsonl", [metadata])
            from transformers import AutoTokenizer
            tokenizer = AutoTokenizer.from_pretrained(str(TOKENIZER), local_files_only=True)
            write_jsonl(root / "tokenized/test.jsonl", [encode_example(tokenizer, chat, "test_q2")])
            manifest(root)
            report = validate_release(root, write_report=False)
            self.assertFalse(report["passed"])
            self.assertTrue(any("occurs in both" in error and "source_1" in error for error in report["errors"]))


@unittest.skipUnless(TOKENIZER.is_dir(), "Pinned local Qwen3 tokenizer unavailable")
class QuestionFamilyPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        release_fixture(self.root, family_policy=True)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def result(self, *, allow: bool = True) -> dict:
        return validate_release(self.root, TOKENIZER, allow_shared_source_documents=allow, write_report=False)

    def test_question_family_policy_explicitly_allows_shared_source(self) -> None:
        report = self.result()
        self.assertTrue(report["passed"], report["errors"])
        self.assertEqual(report["shared_source_documents"], 1)
        self.assertIn("source PDFs shared; not unseen-document evaluation", report["warnings"])

    def test_strict_default_rejects_shared_source(self) -> None:
        report = self.result(allow=False)
        self.assertFalse(report["passed"])
        self.assertTrue(any("source source_1 occurs in both" in error for error in report["errors"]))

    def test_shared_source_allowance_requires_family_policy(self) -> None:
        (self.root / "build_report.json").write_text('{"split_policy":"source_document"}', encoding="utf-8")
        manifest(self.root)
        report = self.result()
        self.assertFalse(report["passed"])
        self.assertTrue(any("split_policy=question_family" in error for error in report["errors"]))

    def test_shared_family_is_rejected_despite_shared_source_allowance(self) -> None:
        path = self.root / "test.metadata.jsonl"
        rows = [row for _, row in read_jsonl(path)]
        rows[0]["split_group"] = "train_family"
        write_jsonl(path, rows)
        manifest(self.root)
        report = self.result()
        self.assertFalse(report["passed"])
        self.assertTrue(any("question family train_family occurs in both" in error for error in report["errors"]))

    def test_duplicate_content_hash_is_rejected_despite_shared_source_allowance(self) -> None:
        train = next(read_jsonl(self.root / "train.metadata.jsonl"))[1]
        path = self.root / "test.metadata.jsonl"
        rows = [row for _, row in read_jsonl(path)]
        rows[0]["content_sha256"] = train["content_sha256"]
        write_jsonl(path, rows)
        manifest(self.root)
        report = self.result()
        self.assertFalse(report["passed"])
        self.assertTrue(any("duplicate content_sha256" in error for error in report["errors"]))


if __name__ == "__main__":
    unittest.main()
