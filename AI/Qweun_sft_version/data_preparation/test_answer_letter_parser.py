"""Regression tests for key association, cross-page joining, and unsafe banks."""
import json
from pathlib import Path
import unittest

from answer_letter_parser import parse_answer_letters, SEMANTIC_CONTRADICTIONS, UNDERDETERMINED_QUESTIONS


def document(pages):
    return {"source_id":"fixture", "sha256":"abc", "path":"fixture.pdf", "relative_path":"fixture.pdf", "course":"fixture",
            "pages":[{"page":i+1,"height":792,"width":612,"images":[],
                      "lines":[{"text":text,"bbox":[72,74+j*20,530,86+j*20],"spans":[]}
                               for j,text in enumerate(lines)]} for i,lines in enumerate(pages)]}


class AnswerLetterTests(unittest.TestCase):
    def test_cross_page_prompt_and_wrapped_option_remain_one_question(self):
        rows=parse_answer_letters(document([
            ["Thiết bị nào được sử dụng trong tình huống được mô tả?", "A) Lựa chọn có mô tả", "tiếp tục trên dòng thứ hai"],
            ["B) Lựa chọn còn lại", "ANSWER: A"]]))
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["pages"],[1,2])
        self.assertEqual(rows[0]["options"][0]["text"],"Lựa chọn có mô tả tiếp tục trên dòng thứ hai")
        self.assertEqual(rows[0]["status"],"candidate")

    def test_missing_label_never_guesses_correct_choice(self):
        row=parse_answer_letters(document([["Câu hỏi có đầy đủ hai lựa chọn?", "A) Một", "B) Hai", "ANSWER: C"]]))[0]
        self.assertEqual(row["status"],"quarantine")
        self.assertIn("answer_key_label_missing",row["reasons"])

    def test_code_like_labels_without_a_to_b_sequence_are_rejected(self):
        row=parse_answer_letters(document([["Đoạn chương trình sau tạo ra kết quả gì?", "B) x++", "D) return x", "ANSWER: B"]]))[0]
        self.assertEqual(row["status"],"quarantine")
        self.assertIn("nonsequential_or_missing_option_labels",row["reasons"])

    def test_unsupported_answer_input_resets_boundary_without_contaminating_next_question(self):
        rows=parse_answer_letters(document([["This is an unkeyed edX answer input", "Answer:",
                                             "Đây là câu hỏi tiếp theo có nhãn rõ ràng?", "A) Một", "B) Hai", "ANSWER: B"]]))
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0]["status"],"quarantine")
        self.assertEqual(rows[1]["prompt"],"Đây là câu hỏi tiếp theo có nhãn rõ ràng?")
        self.assertTrue(rows[1]["options"][1]["correct"])

    def test_explicit_multiple_labels_preserve_all_correct_options(self):
        row=parse_answer_letters(document([["Chọn các lựa chọn phù hợp với dữ kiện?", "A) Một", "B) Hai", "C) Ba", "ANSWER: A,C"]]))[0]
        self.assertEqual(row["status"],"candidate")
        self.assertEqual(row["type"],"MULTIPLE_SELECT")
        self.assertEqual([o["label"] for o in row["options"] if o["correct"]],["A","C"])

    def test_trailing_question_without_key_cannot_become_candidate(self):
        self.assertEqual(parse_answer_letters(document([["Đây là câu hỏi chưa có đáp án?", "A) Một", "B) Hai"]])),[])

    def test_real_bank_regression_excludes_visually_confirmed_source_errors(self):
        root=Path(__file__).resolve().parents[1]/"datasets/sft_exams_20261024/extracted"
        bank=None
        for path in root.glob("*.json"):
            with path.open(encoding="utf-8") as stream:
                item=json.load(stream)
            if Path(item["path"]).name=="OS - ôn tập trắc nghiệm.pdf":
                bank=item
                break
        if bank is None:
            self.skipTest("local source bank not available")
        records={r["id"]:r for r in parse_answer_letters(bank)}
        self.assertEqual(len(records),269)
        for identity in SEMANTIC_CONTRADICTIONS:
            self.assertEqual(records[identity]["status"],"quarantine")
            self.assertIn("source_key_semantic_contradiction",records[identity]["reasons"])
        for identity in UNDERDETERMINED_QUESTIONS:
            self.assertEqual(records[identity]["status"],"quarantine")
        self.assertTrue(any(len(r["pages"])>1 and r["status"]=="candidate" for r in records.values()))


if __name__=="__main__":
    unittest.main()
