from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from auto_extract_questions import extract_questions,import_auto_text_questions
from sft_review_store import SFTReviewStore,canonical_hash,file_sha256,page_identity


class TextQuestionParserTests(unittest.TestCase):
    def test_explicit_questions_and_printed_answers_preserved(self):
        text="""Câu 1: Chức năng nào được tài liệu ghi nhận?
A. Quản lý tài nguyên
B. Không quản lý tài nguyên
Đáp án: A
Lời giải: Hệ điều hành quản lý tài nguyên.
Câu 2. Một câu hỏi khác chưa có đáp án?
A. Phương án một
B. Phương án hai"""
        result=extract_questions(text)
        self.assertEqual(len(result["questions"]),2)
        first,second=result["questions"]
        self.assertEqual(first["answer"]["labels"],["A"])
        self.assertEqual(first["solution"],"Hệ điều hành quản lý tài nguyên.")
        self.assertEqual(second["answer"]["origin"],"missing")
        self.assertEqual(second["solution"],"")
        self.assertFalse(result["requires_vlm"])

    def test_attempt_score_is_not_promoted_to_answer(self):
        result=extract_questions("Câu hỏi #abcdef\n(đạt 1/1 điểm, không tích lũy)\nLựa chọn nào chính xác theo đề?\nA. Nội dung thứ nhất\nB. Nội dung thứ hai")
        self.assertEqual(result["questions"][0]["answer"],{"labels":[],"text":"","evidence":"","origin":"missing"})
        self.assertIn("attempt_grade_is_not_answer_evidence",result["questions"][0]["flags"])

    def test_answer_letter_bank_crosses_items_without_guessing(self):
        result=extract_questions("Một câu hỏi đầy đủ thứ nhất?\nA) Một\nB) Hai\nANSWER: B\nCâu hỏi đầy đủ thứ hai?\nA) Ba\nB) Bốn\nANSWER: A")
        self.assertEqual(len(result["questions"]),2)
        self.assertEqual(result["questions"][0]["answer"]["labels"],["B"])

    def test_nonsequential_options_report_vlm_reroute(self):
        result=extract_questions("Câu 1: Những lựa chọn nào còn đầy đủ?\nA. Lựa chọn đầu\nC. Lựa chọn bị thiếu ở giữa")
        self.assertTrue(result["requires_vlm"])
        self.assertEqual(result["questions"][0]["options"],[])

    def test_code_line_numbers_not_silently_split_into_questions(self):
        result=extract_questions("Đoạn chương trình sau có ý nghĩa gì?\n1. Public example code\n2. Return some value\nint main() { return 0; }")
        self.assertEqual(len(result["questions"]),1)
        self.assertIn("unsegmented_page_text",result["questions"][0]["flags"])

    def test_boolean_printed_key_without_colon(self):
        result=extract_questions("Question 1\nThis statement has a printed true/false answer.\nSelect one:\nTrue\nFalse\nThe correct answer is 'False'.")
        self.assertEqual(result["questions"][0]["answer"]["text"],"False")
        self.assertEqual([o["text"] for o in result["questions"][0]["options"]],["True","False"])

    def test_section_heading_is_not_a_question_boundary(self):
        result=extract_questions("Câu hỏi lý thuyết\nCâu 1: Nội dung câu hỏi có số ở đây?\nA. Đáp án đầu\nB. Đáp án sau")
        self.assertEqual(len(result["questions"]),1)
        self.assertEqual(result["questions"][0]["source_number"],"1")

    def test_shared_source_passage_is_preserved_in_each_question(self):
        passage="Dựa vào đoạn văn: Tiến trình A đang chờ một tài nguyên."
        result=extract_questions(passage+"\nCâu 1: Tiến trình nào đang chờ?\nA. A\nB. B\nCâu 2: Điều gì được nêu trong đoạn văn?\nA. Chờ tài nguyên\nB. Hoàn thành")
        self.assertEqual(len(result["questions"]),2)
        self.assertTrue(all(q["source_context"]==passage and q["prompt"].startswith(passage+"\n\n") for q in result["questions"]))

    def test_decimal_and_url_are_source_data_and_must_not_be_stripped_as_interface(self):
        result=extract_questions("Câu 1: Giá trị ở dòng dưới là bao nhiêu?\n1.5\nNguồn URL trong câu hỏi:\nhttps://example.org/a\nA. Một\nB. Hai")
        self.assertIn("1.5",result["questions"][0]["prompt"])
        self.assertIn("https://example.org/a",result["questions"][0]["prompt"])

    def test_numeric_question_boundaries_keep_shared_context(self):
        context="Dựa vào các thông số được cho trong tài liệu này."
        result=extract_questions(context+"\n1. Nội dung câu thứ nhất được ghi rõ?\nA. Một\nB. Hai\n2. Nội dung câu thứ hai được ghi rõ?\nA. Ba\nB. Bốn")
        self.assertEqual(len(result["questions"]),2)
        self.assertTrue(all(q["source_context"]==context for q in result["questions"]))

    def test_short_math_prompt_is_retained(self):
        result=extract_questions("Câu 1: 2+2=?\nA. 4\nB. 5")
        self.assertEqual(result["questions"][0]["prompt"],"2+2=?")
        self.assertIn("short_source_prompt",result["questions"][0]["flags"])

    def test_text_after_true_false_options_is_preserved_and_rerouted(self):
        result=extract_questions("Question 1\nThe source statement is visible here.\nSelect one:\nTrue\nFalse\nA further line remains in the source.")
        self.assertTrue(result["requires_vlm"])
        self.assertIn("A further line remains",result["questions"][0]["prompt"])

    def test_verified_footer_only_removes_exact_unique_final_physical_line(self):
        text="Câu 1: Lựa chọn nào ghi đúng số?\nA. 49\nB. 50\n       49\n\n"
        result=extract_questions(text,footer_text="49")
        self.assertEqual([q["text"] for q in result["questions"][0]["options"]],["49","50"])
        self.assertTrue(result["text_transforms"][0]["applied"])
        self.assertEqual(result["text_transforms"][0]["line_number"],4)
        self.assertIn("verified_native_footer_removed",result["questions"][0]["flags"])
        self.assertFalse(result["requires_vlm"])

    def test_no_footer_argument_keeps_numeric_data_and_trailing_number(self):
        text="Câu 1: Theo dữ liệu nguồn, lựa chọn nào?\nA. 49\nB. Giá trị khác\n49"
        result=extract_questions(text)
        self.assertEqual(result["text_transforms"],[])
        self.assertEqual(result["questions"][0]["options"][1]["text"],"Giá trị khác\n49")

    def test_footer_removal_keeps_decimals_urls_and_numeric_options(self):
        text="Câu 1: Giữ nguyên dữ kiện 1.5 và https://example.org/49?\nA. 0\nB. 49\n49"
        result=extract_questions(text,footer_text="49")
        question=result["questions"][0]
        self.assertIn("1.5",question["prompt"])
        self.assertIn("https://example.org/49",question["prompt"])
        self.assertEqual([o["text"] for o in question["options"]],["0","49"])

    def test_footer_mismatch_or_nonfinal_occurrence_does_not_erase_text(self):
        for text in ["Câu 1: Nội dung nguyên vẹn?\n49\nA. Một\nB. Hai",
                     "Câu 1: Nội dung nguyên vẹn?\nA. Một\nB. Hai\n149",
                     "Câu 1: Nội dung nguyên vẹn?\n49\nA. Một\nB. Hai\n49"]:
            with self.subTest(text=text):
                result=extract_questions(text,footer_text="49")
                self.assertFalse(result["text_transforms"][0]["applied"])
                self.assertTrue(result["requires_vlm"])
                self.assertEqual(result["questions"],extract_questions(text)["questions"])

    def test_footer_argument_cannot_be_decimal_url_partial_or_nontext(self):
        text="Câu 1: Nội dung nguyên vẹn?\nA. Một\nB. Hai\n49"
        for footer in [49,"4"," 49","49 ","049","4.9","https://example.org/49",""]:
            with self.subTest(footer=footer):
                result=extract_questions(text,footer_text=footer)
                self.assertFalse(result["text_transforms"][0]["applied"])
                self.assertTrue(result["requires_vlm"])

    def test_verified_footer_crlf_only_removes_one_line_and_preserves_other_data(self):
        result=extract_questions("Câu 1: Dữ kiện nào giữ lại?\r\nA. 1.5\r\nB. 2.5\r\n49\r\n",footer_text="49")
        self.assertEqual([o["text"] for o in result["questions"][0]["options"]],["1.5","2.5"])
        self.assertTrue(result["text_transforms"][0]["applied"])


class AutomaticTextImportTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        (self.root/"manifest.json").write_text(json.dumps({"schema":"bkquiz-sft-review-v1"}),encoding="utf8")
        source=self.root/"source.pdf";source.write_bytes(b"isolated original source fixture")
        self.page={"id":"rp_text_fixture","source_id":"exam_fixture","source_path":str(source),"source_sha256":file_sha256(source),
                   "page":1,"bbox":[0.,0.,600.,800.],"tile_index":0,"tile_count":1,"course":"TEST ONLY","reasons":[],"native_text_preview":""}
        self.page["identity"]=page_identity(self.page)
        (self.root/"pages.jsonl").write_text(json.dumps(self.page)+"\n",encoding="utf8")
        folder=self.root/"auto";folder.mkdir()
        text=folder/"text.txt";text.write_text("Câu 1: Câu hỏi native đã trích xuất đúng?\nA. Một lựa chọn\nB. Lựa chọn còn lại\nĐáp án: A",encoding="utf8")
        evidence=folder/"evidence.json";evidence.write_text(json.dumps({"page_id":self.page["id"],"identity":self.page["identity"],"source_sha256":self.page["source_sha256"]}),encoding="utf8")
        policy=folder/"policy.json";policy.write_text(json.dumps({"schema":"bkquiz-sft-auto-routing-policy-v1","policy_id":"test-policy","automatic_stage1_authorized":True,"authorization":"User authorized automatic OCR triage 2026-10-25"}),encoding="utf8")
        self.route={"page_id":self.page["id"],"identity":self.page["identity"],"policy_id":"test-policy","route":"native_text","automatic":True,"human_verified":False,
                    "analysis_path":"auto/evidence.json","analysis_sha256":file_sha256(evidence),"risk_score":.1,"reasons":[],"text_path":"auto/text.txt","text_sha256":file_sha256(text)}
        routing=folder/"routing.jsonl";routing.write_text(json.dumps(self.route)+"\n",encoding="utf8")
        self.pointer={"schema":"bkquiz-sft-auto-routing-pointer-v1","policy_path":"auto/policy.json","policy_sha256":file_sha256(policy),"routing_path":"auto/routing.jsonl","routing_sha256":file_sha256(routing)}
        (self.root/"auto_routing_current.json").write_text(json.dumps(self.pointer),encoding="utf8")

    def tearDown(self):self.temp.cleanup()

    def test_text_import_needs_no_image_and_questions_stay_pending(self):
        report=import_auto_text_questions(self.root)
        self.assertEqual(report["errors"],[])
        self.assertEqual(report["new_questions_imported"],1)
        store=SFTReviewStore(self.root)
        question=store.list_questions()["items"][0]
        self.assertEqual(question["status"],"pending")
        self.assertEqual(question["extraction_origin"],"native_text")
        self.assertNotIn("image_sha256",question)
        with closing(sqlite3.connect(store.database)) as connection:self.assertEqual(connection.execute("SELECT COUNT(*) FROM review_events").fetchone()[0],0)
        self.assertFalse((self.root/"assets").exists())
        again=import_auto_text_questions(self.root)
        self.assertEqual(again["new_questions_imported"],0)

    def test_missing_or_changed_policy_does_not_import(self):
        (self.root/"auto/policy.json").write_text("{}",encoding="utf8")
        with self.assertRaises(ValueError):import_auto_text_questions(self.root)

    def test_text_tampering_is_reported_and_not_imported(self):
        (self.root/"auto/text.txt").write_text("tampered",encoding="utf8")
        report=import_auto_text_questions(self.root)
        self.assertEqual(report["new_questions_imported"],0)
        self.assertEqual(len(report["errors"]),1)

    def publish_footer_fixture(self,box=None,footer="1",route="native_text"):
        self.page.update(source_width=600.,source_height=800.)
        (self.root/"pages.jsonl").write_text(json.dumps(self.page)+"\n",encoding="utf8")
        text=self.root/"auto/text.txt"
        text.write_text("Câu 1: Lựa chọn nào được ghi trong nguồn?\nA. 1\nB. Nội dung khác\n1\n",encoding="utf8")
        self.route.update(route=route,text_sha256=file_sha256(text),footer_text=footer,footer_bbox=box or [550.,745.,560.,759.])
        routing=self.root/"auto/routing.jsonl";routing.write_text(json.dumps(self.route)+"\n",encoding="utf8")
        self.pointer["routing_sha256"]=file_sha256(routing)
        (self.root/"auto_routing_current.json").write_text(json.dumps(self.pointer),encoding="utf8")
        return text.read_text(encoding="utf8")

    def test_bound_footer_import_retains_raw_source_and_records_transform(self):
        original=self.publish_footer_fixture()
        report=import_auto_text_questions(self.root)
        self.assertEqual(report["errors"],[])
        self.assertEqual(report["new_questions_imported"],1)
        store=SFTReviewStore(self.root);question=store.list_questions()["items"][0]
        self.assertEqual(question["question"]["options"][0]["text"],"1")
        self.assertEqual(question["question"]["options"][1]["text"],"Nội dung khác")
        result=json.loads(Path(question["raw_result_path"]).read_text(encoding="utf8"))
        self.assertEqual(result["raw_text"],original)
        self.assertEqual(result["footer_source_evidence"]["footer_bbox"],self.route["footer_bbox"])
        self.assertTrue(result["text_transforms"][0]["applied"])
        self.assertEqual(question["status"],"pending")
        with closing(sqlite3.connect(store.database)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM review_events").fetchone()[0],0)

    def test_footer_import_rejects_nonbottom_bbox_wrong_number_and_ocr_route(self):
        for kwargs in [{"box":[20.,100.,30.,120.]},{"footer":"2"},{"route":"ocr_text"}]:
            with self.subTest(kwargs=kwargs):
                self.publish_footer_fixture(**kwargs)
                report=import_auto_text_questions(self.root)
                self.assertEqual(report["new_questions_imported"],0)
                self.assertEqual(len(report["errors"]),1)


if __name__=="__main__":unittest.main()
