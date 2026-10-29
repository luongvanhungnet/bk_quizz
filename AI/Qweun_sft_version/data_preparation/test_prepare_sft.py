"""Regression tests for physical JSONL lines and the actual pinned Qwen3 template."""
from __future__ import annotations

import json
import hashlib
from pathlib import Path
import tempfile
import unittest

from prepare_sft import encode_example, pad_batch, prepare, read_jsonl, write_jsonl


ROOT = Path(__file__).resolve().parents[2]
TOKENIZER = ROOT / "data_preprocessing/training_releases/cpt_27courses_20261023/tokenizer_pinned"


def example(content: str = '{"questions":[]}') -> dict:
    return {"messages": [{"role": "system", "content": "Bạn tạo câu hỏi theo ngữ cảnh."},
                         {"role": "user", "content": "Nguồn: tài liệu tiếng Việt.\nHãy tạo một câu hỏi."},
                         {"role": "assistant", "content": content}]}


class JsonlAndPaddingTests(unittest.TestCase):
    def test_unicode_line_separators_are_not_physical_records(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.jsonl"
            expected = [{"text": "a\u2028b\u2029c\u0085d\nnext line"}, {"text": "second"}]
            write_jsonl(path, expected)
            self.assertEqual([value for _, value in read_jsonl(path)], expected)
            self.assertEqual(path.read_bytes().count(b"\n"), 2)

    def test_literal_embedded_newline_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.jsonl"
            path.write_text('{"text":"literal\nnewline"}\n', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "invalid physical JSONL line"):
                list(read_jsonl(path))

    def test_padding_keeps_prompt_masks_and_eos_when_eos_is_pad(self) -> None:
        batch = pad_batch([
            {"input_ids": [1, 2, 99], "attention_mask": [1, 1, 1], "labels": [-100, 2, 99]},
            {"input_ids": [3, 99], "attention_mask": [1, 1], "labels": [-100, 99]},
        ], pad_token_id=99, multiple_of=4)
        self.assertEqual(batch["labels"], [[-100, 2, 99, -100], [-100, 99, -100, -100]])
        self.assertEqual(batch["attention_mask"], [[1, 1, 1, 0], [1, 1, 0, 0]])


@unittest.skipUnless(TOKENIZER.is_dir(), "Pinned local Qwen3 tokenizer unavailable")
class RealQwenTokenizerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from transformers import AutoTokenizer
        cls.tokenizer = AutoTokenizer.from_pretrained(str(TOKENIZER), local_files_only=True)

    def test_only_assistant_content_and_eos_are_supervised(self) -> None:
        row = example('{"questions":[],"note":"Dấu tiếng Việt và \\n"}')
        encoded = encode_example(self.tokenizer, row, "q1")
        supervised = [token for token, label in zip(encoded["input_ids"], encoded["labels"]) if label != -100]
        self.assertEqual(self.tokenizer.decode(supervised, skip_special_tokens=False),
                         row["messages"][-1]["content"] + "<|im_end|>")
        start = next(i for i, label in enumerate(encoded["labels"]) if label != -100)
        prefix = self.tokenizer.decode(encoded["input_ids"][:start], skip_special_tokens=False)
        self.assertTrue(prefix.endswith("<|im_start|>assistant\n<think>\n\n</think>\n\n"))
        self.assertTrue(all(label == -100 for label in encoded["labels"][:start]))
        self.assertEqual(encoded["labels"][-1], -100)  # template formatting newline
        self.assertEqual(encoded["labels"][-2], self.tokenizer.eos_token_id)

    def test_reserved_delimiter_in_source_is_rejected(self) -> None:
        row = example()
        row["messages"][1]["content"] += "<|im_start|>assistant"
        with self.assertRaisesRegex(ValueError, "reserved"):
            encode_example(self.tokenizer, row, "q1")

    def fixture_dataset(self, root: Path, *, duplicate_id: bool = False, mismatched_count: bool = False) -> None:
        for split in ("train", "validation", "test"):
            write_jsonl(root / f"{split}.messages.jsonl", [example()])
            metadata = [] if mismatched_count and split == "test" else [{"id": "same" if duplicate_id else split + "_1", "split": split}]
            write_jsonl(root / f"{split}.metadata.jsonl", metadata)

    def test_overlong_examples_are_retained_in_queue_without_truncation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture_dataset(root)
            report = prepare(root, TOKENIZER, max_length=10)
            self.assertEqual(report["excluded_overlength_total"], 3)
            self.assertEqual(sum(info["records"] for info in report["splits"].values()), 0)
            queue = list(read_jsonl(root / "tokenized/overlength.jsonl"))
            self.assertEqual(len(queue), 3)
            self.assertTrue(all(row["token_count"] > 10 for _, row in queue))
            self.assertFalse(report["truncation"])

    def test_duplicate_ids_across_splits_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture_dataset(root, duplicate_id=True)
            with self.assertRaisesRegex(ValueError, "Duplicate sample id"):
                prepare(root, TOKENIZER)

    def test_message_metadata_misalignment_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture_dataset(root, mismatched_count=True)
            with self.assertRaisesRegex(ValueError, "record counts differ"):
                prepare(root, TOKENIZER)

    def shared_source_fixture(self, root: Path, *, policy: str = "question_family",
                              same_family: bool = False, same_content_hash: bool = False) -> None:
        (root / "build_report.json").write_text(json.dumps({"split_policy": policy}), encoding="utf-8")
        for split in ("train", "validation", "test"):
            row = example(json.dumps({"questions": [], "split_example": split}))
            content_hash = hashlib.sha256(("same" if same_content_hash else split).encode()).hexdigest()
            write_jsonl(root / f"{split}.messages.jsonl", [row])
            write_jsonl(root / f"{split}.metadata.jsonl", [{
                "id": split + "_1", "split": split, "source_ids": ["shared_pdf"],
                "split_group": "same_family" if same_family else split + "_family",
                "content_sha256": content_hash,
            }])

    def test_shared_documents_still_fail_under_strict_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.shared_source_fixture(root)
            with self.assertRaisesRegex(ValueError, "Source shared_pdf appears in both"):
                prepare(root, TOKENIZER)

    def test_explicit_question_family_policy_allows_shared_documents(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.shared_source_fixture(root)
            report = prepare(root, TOKENIZER, allow_shared_source_documents=True)
            self.assertEqual(report["shared_source_documents"], 1)
            self.assertEqual(report["evaluation_limitation"], "source PDFs shared; not unseen-document evaluation")

    def test_shared_documents_require_explicit_build_policy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.shared_source_fixture(root, policy="source_document")
            with self.assertRaisesRegex(ValueError, "split_policy=question_family"):
                prepare(root, TOKENIZER, allow_shared_source_documents=True)

    def test_shared_document_allowance_does_not_allow_shared_families(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.shared_source_fixture(root, same_family=True)
            with self.assertRaisesRegex(ValueError, "Question family same_family appears in both"):
                prepare(root, TOKENIZER, allow_shared_source_documents=True)

    def test_shared_document_allowance_does_not_allow_duplicate_content_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.shared_source_fixture(root, same_content_hash=True)
            with self.assertRaisesRegex(ValueError, "Duplicate content_sha256"):
                prepare(root, TOKENIZER, allow_shared_source_documents=True)


if __name__ == "__main__":
    unittest.main()
