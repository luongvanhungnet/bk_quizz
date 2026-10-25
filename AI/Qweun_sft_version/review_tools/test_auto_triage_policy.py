from __future__ import annotations

import copy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

from auto_triage_policy import build, canonical, classify, read_jsonl, sha
from ocr_probe import VERSION


SOURCE_TEXT = ("Câu 1: Hãy mô tả những trách nhiệm được nêu trong tài liệu về quản lý tài nguyên của hệ điều hành.\n"
               "Phần trình bày cần dựa vào các thông tin có sẵn và giữ nguyên các thuật ngữ được tài liệu sử dụng. "
               "Nội dung bao gồm quản lý tiến trình, quản lý bộ nhớ, quản lý thiết bị và tổ chức các tập tin trong hệ thống.")


def native(**changes):
    result={"native_chars":400,"native_words":80,"native_bad_glyphs":0,"native_long_word_ratio":0,
            "native_letters_ratio":.8,"native_math_font_ratio":0,"native_color_ratio":0,
            "visual_answer_markings":False,"drawing_count":0,"source_risk_flags":[],
            "image_coverage":0,"image_count":0}
    result.update(changes);return result


def probe(**changes):
    result={"status":"ok","config":{"version":VERSION},
            "ocr":{"text":SOURCE_TEXT,"word_count":65,"weighted_confidence":95,
                   "word_fraction_conf_ge60":1.,"word_fraction_conf_lt40":0.},
            "image_metrics":{"width":1200,"height":1600,"ink_fraction":.08,"gray_mean":240,"gray_std":50,
                             "glyph_like_components":200,"median_glyph_height":14,"small_glyph_fraction":.05,
                             "laplacian_variance":300,"ocr_ink_coverage":.99}}
    result.update(changes);return result


class RoutingBoundaryTests(unittest.TestCase):
    def test_clean_native_open_question_can_use_pdf_text(self):
        self.assertEqual(classify(native(),None,SOURCE_TEXT)[0],"native_text")

    def test_even_small_embedded_image_prevents_plain_text_route(self):
        result=classify(native(image_count=1,image_coverage=.0001),{"status":"native_skipped"},SOURCE_TEXT)
        self.assertEqual(result[0],"auto_vlm")

    def test_native_math_markings_and_color_stay_visual(self):
        for metrics,text in [(native(native_math_font_ratio=.1),SOURCE_TEXT),
                             (native(visual_answer_markings=True),SOURCE_TEXT),
                             (native(native_color_ratio=.2),SOURCE_TEXT),
                             (native(),SOURCE_TEXT+" ∫ f(x) dx"),
                             (native(),SOURCE_TEXT+" Xem sơ đồ dưới đây.")]:
            with self.subTest(metrics=metrics,text=text):
                self.assertEqual(classify(metrics,{"status":"native_skipped"},text)[0],"auto_vlm")

    def test_unknown_native_glyphs_are_not_plain_text(self):
        self.assertEqual(classify(native(native_bad_glyphs=1),{"status":"native_skipped"},SOURCE_TEXT)[0],"auto_vlm")

    def test_actual_probe_field_names_allow_strong_open_question_ocr(self):
        self.assertEqual(classify(native(native_chars=0,native_words=0,image_coverage=1,image_count=1),probe(),"")[0],"ocr_text")

    def test_ocr_uncovered_ink_prevents_plain_text(self):
        result=probe();result["image_metrics"]["ocr_ink_coverage"]=.6
        self.assertEqual(classify(native(native_chars=0),result,"")[0],"auto_vlm")

    def test_strong_ocr_mcq_keeps_image_to_preserve_small_answer_markings(self):
        result=probe();result["ocr"]["text"]=SOURCE_TEXT+"\nA. Phương án đầu\nB. Phương án sau\nĐáp án: A"
        self.assertEqual(classify(native(native_chars=0),result,"")[0],"auto_vlm")

    def test_native_quiz_interface_and_checkbox_or_equation_keep_image(self):
        for suffix in ["\nSelect one:","\nCorrected", "\n☑ Một lựa chọn", "\nx^2=4"]:
            with self.subTest(suffix=suffix):
                self.assertEqual(classify(native(),{"status":"native_skipped"},SOURCE_TEXT+suffix)[0],"auto_vlm")

    def test_low_ocr_confidence_alone_is_not_vlm_failure(self):
        result=probe();result["ocr"].update(weighted_confidence=8,word_count=55)
        self.assertEqual(classify(native(native_chars=0),result,"")[0],"auto_vlm")

    def test_clear_sparse_image_is_uncertain_without_failure_probability_claim(self):
        result=probe();result["ocr"].update(weighted_confidence=20,word_count=3)
        route,score,reasons=classify(native(native_chars=0),result,"")
        self.assertEqual(route,"manual")
        self.assertNotIn("%"," ".join(reasons))
        self.assertGreater(score,0)

    def test_weak_ocr_with_degraded_pixels_remains_manual(self):
        result=probe();result["ocr"].update(weighted_confidence=20,word_count=15)
        result["image_metrics"].update(laplacian_variance=2,median_glyph_height=3,small_glyph_fraction=.95)
        self.assertEqual(classify(native(native_chars=0),result,"")[0],"manual")

    def test_only_exact_empty_source_and_zero_ink_is_blank(self):
        result=probe();result["ocr"].update(weighted_confidence=None,word_count=0)
        result["image_metrics"].update(ink_fraction=0,gray_std=.5,gray_mean=255,glyph_like_components=0,median_glyph_height=None)
        self.assertEqual(classify(native(native_chars=0,native_words=0),result,"")[0],"blank")
        for changes in [{"ink_fraction":.000001},{"gray_std":1},{"glyph_like_components":1}]:
            altered=copy.deepcopy(result);altered["image_metrics"].update(changes)
            with self.subTest(changes=changes):self.assertNotEqual(classify(native(native_chars=0),altered,"")[0],"blank")
        for changes in [{"native_chars":1},{"annotation_count":1}]:
            with self.subTest(changes=changes):self.assertNotEqual(classify(native(native_chars=0,**changes) if "native_chars" not in changes else native(**changes),result,"")[0],"blank")
        altered=copy.deepcopy(result);altered["ocr"]["word_count"]=1
        self.assertNotEqual(classify(native(native_chars=0),altered,"")[0],"blank")

    def test_page_header_without_questions_is_not_blank(self):
        result=probe();result["ocr"].update(text="ĐỀ THI",word_count=2,weighted_confidence=95)
        result["image_metrics"].update(ink_fraction=.0001,gray_std=.2,glyph_like_components=1)
        self.assertNotEqual(classify(native(native_chars=0),result,"")[0],"blank")

    def test_points_grade_is_quiz_interface_not_plain_native_question(self):
        self.assertEqual(classify(native(),{"status":"native_skipped"},SOURCE_TEXT+"\n4 Points")[0],"auto_vlm")

    def test_strong_ocr_requires_explicit_essay_instruction_for_text_route(self):
        result=probe();result["ocr"]["text"]="Câu 1: Những đặc điểm của hệ điều hành được ghi trong tài liệu là gì?\n"+"Thông tin nguồn cần được giữ nguyên. "*8
        self.assertEqual(classify(native(native_chars=0),result,"")[0],"auto_vlm")

    def test_toc_and_unsegmented_text_do_not_enter_text_route(self):
        for value in ["Mục lục\n"+SOURCE_TEXT,"Nội dung 1\n"+SOURCE_TEXT,SOURCE_TEXT.replace("Câu 1: ","")]:
            with self.subTest(value=value):self.assertEqual(classify(native(),{"status":"native_skipped"},value)[0],"auto_vlm")

    def test_orphan_options_preamble_and_last_mcq_stem_require_vlm(self):
        for value in ["A. Nội dung từ câu trước\nB. Phương án còn lại\n"+SOURCE_TEXT,
                      SOURCE_TEXT+"\nA. Phương án đầu\nB. Phương án sau\nCâu 2: Câu cuối chưa có các lựa chọn."]:
            with self.subTest(value=value):self.assertEqual(classify(native(),{"status":"native_skipped"},value)[0],"auto_vlm")

    def test_unsupported_solution_and_bracketed_weight_layout_require_vlm(self):
        for suffix in ["\nSol: Nội dung giải đáp.","\n[100] Điểm của phương án", "\n[0] Điểm của phương án"]:
            with self.subTest(suffix=suffix):self.assertEqual(classify(native(),{"status":"native_skipped"},SOURCE_TEXT+suffix)[0],"auto_vlm")

    def test_no_glyph_components_does_not_crash_on_nonblank_page(self):
        result=probe();result["ocr"].update(weighted_confidence=None,word_count=0)
        result["image_metrics"].update(median_glyph_height=None,glyph_like_components=0,ink_fraction=.9,gray_mean=40,gray_std=1)
        self.assertEqual(classify(native(native_chars=0),result,"")[0],"manual")

    def test_missing_or_failed_probe_for_scan_needs_manual(self):
        for result in [None,{"status":"error"},{"status":"unknown"}]:
            self.assertEqual(classify(native(native_chars=0),result,"")[0],"manual")


class PolicySnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.evidence=self.root/"evidence";self.evidence.mkdir()
        (self.evidence/"ocr").mkdir();self.pages=[];self.native_rows=[]
        self.analysis=self.evidence/"shared-native-analysis.json";self.analysis.write_text("{}",encoding="utf8")
        self.text=self.evidence/"shared-native-text.txt";self.text.write_text("",encoding="utf8")

    def tearDown(self):self.temp.cleanup()

    def add_page(self,index=0,version=VERSION,status="error"):
        identity=f"{index+1:064x}";page_id="rp_"+identity[-24:]
        page={"id":page_id,"identity":identity,"source_sha256":"a"*64}
        self.pages.append(page)
        self.native_rows.append({**native(native_chars=0,native_words=0),"page_id":page_id,"identity":identity,
            "analysis_path":self.analysis.relative_to(self.root).as_posix(),"analysis_sha256":sha(self.analysis),
            "text_path":self.text.relative_to(self.root).as_posix(),"text_sha256":sha(self.text)})
        result={**probe(status=status),"id":page_id,"page_identity":identity,"source_sha256":"a"*64,
                "config":{"version":version},"evidence_identity":f"{index+1000:064x}"}
        path=self.evidence/"ocr"/(page_id+".json");path.write_text(canonical(result),encoding="utf8")
        return path

    def publish_inputs(self):
        for path,rows in [(self.root/"pages.jsonl",self.pages),(self.evidence/"native_features.jsonl",self.native_rows)]:
            path.write_text("\n".join(canonical(row) for row in rows)+"\n",encoding="utf8")

    def build(self,**kwargs):
        self.publish_inputs()
        with redirect_stdout(io.StringIO()):return build(self.root,self.evidence,**kwargs)

    def test_v2_probe_cannot_activate_current_policy(self):
        self.add_page(version="sft-ocr-probe-v2")
        with self.assertRaisesRegex(ValueError,"incomplete/stale"):
            self.build(activate=True)
        self.assertFalse((self.root/"auto_routing_current.json").exists())
        report=self.build(allow_incomplete=True)
        self.assertEqual(report["routes"],{"manual":1})
        self.assertEqual(len(report["incomplete_ocr"]),1)

    def test_changed_page_identity_is_stale_even_with_v3_probe(self):
        path=self.add_page();value=json.loads(path.read_text(encoding="utf8"));value["page_identity"]="b"*64
        path.write_text(canonical(value),encoding="utf8")
        with self.assertRaisesRegex(ValueError,"incomplete/stale"):self.build(activate=True)
        self.assertFalse((self.root/"auto_routing_current.json").exists())

    def test_changed_source_hash_is_stale_even_with_v3_probe(self):
        path=self.add_page();value=json.loads(path.read_text(encoding="utf8"));value["source_sha256"]="b"*64
        path.write_text(canonical(value),encoding="utf8")
        with self.assertRaisesRegex(ValueError,"incomplete/stale"):self.build(activate=True)
        self.assertFalse((self.root/"auto_routing_current.json").exists())

    def test_manual_queue_is_not_capped_at_user_target(self):
        for index in range(501):self.add_page(index)
        report=self.build()
        self.assertEqual(report["routes"],{"manual":501})
        self.assertFalse(report["manual_target_met_by_machine_routes"])
        policy=json.loads(Path(report["policy_path"]).read_text(encoding="utf8"))
        self.assertTrue(policy["manual_queue_is_not_capped"])
        self.assertFalse(policy["ocr_confidence_is_vlm_failure_probability"])
        self.assertTrue(policy["round2_human_review_required"])

    def test_changed_ocr_bytes_create_new_snapshot_without_overwriting_old_evidence(self):
        path=self.add_page();first=self.build()
        first_routes=Path(first["routing_path"]);first_bytes=first_routes.read_bytes()
        analyses=[self.root/r["analysis_path"] for r in read_jsonl(first_routes)]
        before={p:p.read_bytes() for p in analyses}
        value=json.loads(path.read_text(encoding="utf8"));value["image_metrics"]["gray_std"]=51
        path.write_text(canonical(value),encoding="utf8")
        second=self.build()
        self.assertNotEqual(first["run_id"],second["run_id"])
        self.assertEqual(first_routes.read_bytes(),first_bytes)
        self.assertTrue(all(p.read_bytes()==body for p,body in before.items()))


if __name__=="__main__":unittest.main()
