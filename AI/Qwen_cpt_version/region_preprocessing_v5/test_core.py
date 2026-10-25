from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from cross_validation import cross_validate
from metrics import (bbox_iou, cer, composite_quality, coverage, evaluate_metrics,
                     formula_exact_match, image_label_alignment, wer)
from models import RegionRecord
from review_store import ReviewStore


def record(**updates):
    value = {"id": "p0001_text", "page": 1, "kind": "text", "bbox": [0, 0, 1000, 1000],
             "render_path": "assets/slide.png", "crop_path": "assets/crop.png", "context_path": "assets/context.png",
             "source_sha256": "a" * 64, "render_sha256": hashlib.sha256(b"slide").hexdigest(),
             "crop_sha256": hashlib.sha256(b"crop").hexdigest(), "context_sha256": hashlib.sha256(b"context").hexdigest(),
             "group_id": "g1", "split": "train", "native_text": "Thuật toán là một dãy hữu hạn các bước.",
             "candidates": [{"engine": "native", "text": "Thuật toán là một dãy hữu hạn các bước.", "status": "ok",
                             "evidence": {"lineage": "pymupdf", "backend_family": "pymupdf", "region_id": "p0001_text", "source_sha256": "a" * 64}},
                            {"engine": "paddleocr", "text": "Thuật toán là một dãy hữu hạn các bước.", "status": "ok",
                             "evidence": {"lineage": "paddle", "backend_family": "paddle", "region_id": "p0001_text", "source_sha256": "a" * 64}}]}
    value.update(updates)
    return value


class CrossValidationTests(unittest.TestCase):
    def test_independent_native_ocr_exact_trusted(self):
        result = cross_validate(record())
        self.assertEqual(result["machine_bucket"], "trusted")
        self.assertEqual(result["cross_validation"]["selected_engine"], "native")
        self.assertFalse(result["cross_validation"]["semantic_verified"])

    def test_same_backend_does_not_confirm_itself(self):
        source = record()
        source["candidates"][1]["evidence"]["backend_family"] = "pymupdf"
        self.assertEqual(cross_validate(source)["machine_bucket"], "uncertain")

    def test_unbound_ocr_is_not_same_region_confirmation(self):
        source = record()
        source["candidates"][1]["evidence"] = {"backend_family": "paddle"}
        result = cross_validate(source)
        self.assertEqual(result["machine_bucket"], "uncertain")
        self.assertEqual(result["proposed_text"], source["native_text"])
        self.assertFalse(result["cross_validation"]["comparisons"][1]["region_evidence_bound"])

    def test_source_hash_alone_does_not_bind_region(self):
        source = record()
        source["candidates"][1]["evidence"] = {"backend_family": "paddle", "source_sha256": source["source_sha256"]}
        self.assertEqual(cross_validate(source)["machine_bucket"], "uncertain")

    def test_render_hash_binds_full_slide_native(self):
        source = record()
        source["candidates"][0]["evidence"] = {"backend_family": "pymupdf", "source_sha256": source["source_sha256"],
                                                 "render_sha256": source["render_sha256"]}
        self.assertEqual(cross_validate(source)["machine_bucket"], "trusted")

    def test_input_crop_hash_mismatch_is_critical(self):
        source = record()
        source["candidates"][1]["evidence"]["input_file_sha256"] = "f" * 64
        self.assertEqual(cross_validate(source)["machine_bucket"], "critical")

    def test_docling_native_is_not_independent_ocr(self):
        source = record()
        source["candidates"][1] = {"engine": "docling", "text": source["native_text"], "status": "ok",
                                    "evidence": {"backend_family": "docling_native_layout"}}
        self.assertEqual(cross_validate(source)["machine_bucket"], "uncertain")

    def test_paddle_mineru_shared_backend_is_not_independent(self):
        source = record(native_text="", candidates=[
            {"engine": "paddle_ocr", "text": "Thuật toán", "status": "ok", "evidence": {"backend_family": "paddle_ocr"}},
            {"engine": "mineru", "text": "Thuật toán", "status": "ok", "evidence": {"backend_family": "mineru_pipeline_paddle"}}])
        self.assertEqual(cross_validate(source)["machine_bucket"], "uncertain")

    def test_unknown_geometry_cannot_confirm_native(self):
        source = record()
        source["candidates"][1]["evidence"]["geometry_status"] = "unknown_or_invalid"
        self.assertEqual(cross_validate(source)["machine_bucket"], "uncertain")

    def test_no_majority_vote_can_override_native_disagreement(self):
        source = record(native_text="n − 1", candidates=[
            {"engine": "native", "text": "n − 1", "status": "ok"},
            {"engine": "paddleocr", "text": "n + 1", "status": "ok"},
            {"engine": "paddleocr_second", "text": "n + 1", "status": "ok"}])
        result = cross_validate(source)
        self.assertEqual(result["proposed_text"], "n − 1")
        self.assertEqual(result["machine_bucket"], "uncertain")
        self.assertIn("numeric_or_sign_disagreement", result["reasons"])

    def test_corrupted_native_does_not_win(self):
        source = record(native_text="Thuật \ufffd", candidates=[{"engine": "native", "text": "Thuật \ufffd", "status": "ok"},
                                                               {"engine": "paddleocr", "text": "Thuật toán", "status": "ok"}])
        result = cross_validate(source)
        self.assertEqual(result["proposed_text"], "Thuật toán")
        self.assertEqual(result["machine_bucket"], "uncertain")

    def test_pending_scanned_page_is_not_critical(self):
        result = cross_validate(record(native_text="", candidates=[], pending_engines=["paddleocr"], document_class="scanned"))
        self.assertEqual(result["machine_bucket"], "uncertain")
        self.assertIn("extraction_pending", result["reasons"])

    def test_completed_empty_failure_is_critical(self):
        result = cross_validate(record(native_text="", candidates=[{"engine": "paddleocr", "text": "", "status": "error"}]))
        self.assertEqual(result["machine_bucket"], "critical")

    def test_formula_structure_error_stays_critical_with_native_fallback(self):
        source = record(kind="formula", native_text="O(n)", candidates=[
            {"engine": "native", "text": "O(n)", "status": "ok"},
            {"engine": "PP-FormulaNet", "text": "O(n", "status": "error", "evidence": {"structural_errors": ["unbalanced"]}}])
        result = cross_validate(source)
        self.assertEqual(result["machine_bucket"], "critical")
        self.assertIn("extractor_formula_structure_error", result["reasons"])

    def test_new_formula_marked_ok_still_checked_for_corruption(self):
        source = record(kind="formula", native_text="x = 1", candidates=[
            {"engine": "native", "text": "x = 1", "status": "ok"},
            {"engine": "PP-FormulaNet", "text": r"\\frac{x}{y", "status": "ok"}])
        result = cross_validate(source)
        self.assertEqual(result["machine_bucket"], "critical")
        self.assertEqual(result["proposed_text"], "x = 1")

    def test_runaway_formula_repetition_is_critical(self):
        source = record(kind="formula", native_text="x = 1", candidates=[
            {"engine": "PP-FormulaNet", "text": r"\frac\frac\frac\frac\frac\frac", "status": "ok"}])
        self.assertEqual(cross_validate(source)["machine_bucket"], "critical")

    def test_reported_seed_errors_cannot_be_overridden_by_ok_status(self):
        source = record(kind="formula", native_text="x = 1", candidates=[
            {"engine": "PP-FormulaNet", "text": "x = 1", "status": "ok",
             "evidence": {"structural_errors": ["known_invalid_structure"]}}])
        result = cross_validate(source)
        self.assertEqual(result["machine_bucket"], "critical")
        self.assertEqual(result["proposed_text"], "x = 1")

    def test_valid_latex_indices_and_escaped_braces_preserved(self):
        text = r"x_{i+1}^{2} \in \{1, 2, 3\}"
        result = cross_validate(record(kind="formula", native_text="", candidates=[
            {"engine": "PP-FormulaNet", "text": text, "status": "ok"}]))
        self.assertEqual(result["machine_bucket"], "uncertain")
        self.assertEqual(result["proposed_text"], text)

    def test_high_risk_consensus_still_needs_human(self):
        result = cross_validate(record(kind="table"))
        self.assertEqual(result["risk"], "high")
        self.assertEqual(result["machine_bucket"], "uncertain")

    def test_inline_math_inside_text_still_high_risk(self):
        source = record(native_text="Độ phức tạp O(n log n).", candidates=[
            {"engine": "native", "text": "Độ phức tạp O(n log n).", "status": "ok"},
            {"engine": "paddle_ocr", "text": "Độ phức tạp O(n log n).", "status": "ok"}])
        result = cross_validate(source)
        self.assertEqual(result["machine_bucket"], "uncertain")
        self.assertEqual(result["risk"], "high")

    def test_vlm_partial_is_not_schema_failure(self):
        result = cross_validate(record(kind="diagram", native_text="", candidates=[
            {"engine": "qwen_vlm", "text": "Sơ đồ cây phân nhánh. Nhãn nhỏ không đọc rõ.", "status": "ok"}]))
        self.assertEqual(result["machine_bucket"], "uncertain")
        self.assertIn("Sơ đồ cây", result["proposed_text"])

    def test_vlm_prose_is_not_a_literal_ocr_vote(self):
        source = record()
        source["candidates"].append({"engine": "qwen_vlm", "text": "Ảnh trình bày một thuật toán.", "status": "ok"})
        result = cross_validate(source)
        self.assertEqual(result["machine_bucket"], "trusted")
        self.assertNotIn("independent_extractors_disagree", result["reasons"])

    def test_source_mismatch_critical(self):
        source = record()
        source["candidates"][1]["evidence"]["crop_sha256"] = "f" * 64
        self.assertEqual(cross_validate(source)["machine_bucket"], "critical")

    def test_revision_stable_and_bound_to_candidate_changes(self):
        result = cross_validate(record())
        self.assertEqual(result["machine_revision"], cross_validate(result)["machine_revision"])
        source = record()
        source["candidates"][1]["text"] += " khác"
        self.assertNotEqual(result["machine_revision"], cross_validate(source)["machine_revision"])

    def test_normalization_retains_vietnamese_and_math(self):
        source = record(native_text="a ≤ b ∧ n − 1", candidates=[{"engine": "native", "text": "a ≤ b ∧ n − 1", "status": "ok"}])
        self.assertEqual(cross_validate(source)["proposed_text"], "a ≤ b ∧ n − 1")

    def test_metadata_contract(self):
        result = RegionRecord.model_validate(cross_validate(record()))
        self.assertEqual(result.page, 1)
        with self.assertRaises(ValueError):
            RegionRecord.model_validate(record(bbox=[0, 0, 1001, 1000]))
        with self.assertRaises(ValueError):
            RegionRecord.model_validate(record(bbox=[False, 0, 1000, 1000]))


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.run = Path(self.temporary.name)
        (self.run / "assets").mkdir()
        for prefix, payload in (("slide", b"slide"), ("crop", b"crop"), ("context", b"context")):
            (self.run / "assets" / (prefix + ".png")).write_bytes(payload)
        self.current = cross_validate(record())
        (self.run / "manifest.json").write_text(json.dumps({"document": {"sha256": "a" * 64}}), encoding="utf-8")
        self.write_record()
        self.store = ReviewStore(self.run)

    def tearDown(self):
        self.temporary.cleanup()

    def write_record(self):
        (self.run / "records.jsonl").write_text(json.dumps(self.current, ensure_ascii=False) + "\n", encoding="utf-8")

    def submit(self, **updates):
        args = {"record_id": self.current["id"], "reviewer": "Reviewer A", "decision": "approve",
                "text": self.current["proposed_text"], "evidence": "Đã đối chiếu slide và crop.",
                "expected_revision": self.current["machine_revision"]}
        args.update(updates)
        return self.store.submit(**args)

    def test_human_approval_audited_separate_from_machine(self):
        review = self.submit()
        self.assertEqual(review["accepted_text"], self.current["proposed_text"])
        row = self.store.get_record(self.current["id"])
        self.assertEqual(row["review_decision"], "approve")
        self.assertEqual(row["proposed_text"], self.current["proposed_text"])
        self.assertEqual(self.store.stats()["eligible_for_training"], 1)

    def test_edit_cannot_masquerade_as_approve(self):
        with self.assertRaisesRegex(ValueError, "use correct"):
            self.submit(text="Nội dung mới")
        review = self.submit(decision="correct", text="Nội dung đã sửa ≤ 1")
        self.assertEqual(review["accepted_text"], "Nội dung đã sửa ≤ 1")
        self.assertNotEqual(self.store.get_record(self.current["id"])["proposed_text"], "Nội dung đã sửa ≤ 1")

    def test_stale_revision_rejected(self):
        with self.assertRaisesRegex(ValueError, "stale_revision"):
            self.submit(expected_revision="old")

    def test_changed_source_bytes_rejected(self):
        (self.run / "assets/context.png").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "stale_source_hash"):
            self.submit()

    def test_changed_manifest_source_rejected(self):
        (self.run / "manifest.json").write_text(json.dumps({"document": {"sha256": "b" * 64}}), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "stale_source_hash"):
            self.submit()

    def test_high_risk_requires_acknowledgment(self):
        self.current = cross_validate(record(kind="table"))
        self.write_record()
        with self.assertRaisesRegex(ValueError, "high-risk"):
            self.submit()
        self.assertTrue(self.submit(acknowledgement_high_risk=True)["human_verified"])

    def test_holdout_cannot_be_training_eligible(self):
        self.current["split"] = "holdout"
        self.write_record()
        self.assertFalse(self.submit()["eligible_for_training"])

    def test_revision_changed_invalidates_old_decision(self):
        self.submit()
        self.current["machine_revision"] = "new"
        self.write_record()
        row = self.store.get_record(self.current["id"])
        self.assertEqual(row["review_decision"], "pending")
        self.assertTrue(row["review_stale"])
        self.assertEqual(self.store.stats()["eligible_for_training"], 0)

    def test_proposal_changed_even_without_revision_invalidates_old_decision(self):
        self.submit()
        self.current["proposed_text"] += " changed"
        self.write_record()
        self.assertTrue(self.store.get_record(self.current["id"])["review_stale"])

    def test_history_append_only_and_latest_rejection_wins(self):
        self.submit()
        self.submit(decision="reject", text="")
        self.assertEqual(len(self.store.history(self.current["id"])), 2)
        self.assertEqual(self.store.stats()["eligible_for_training"], 0)
        with closing(sqlite3.connect(self.store.database)) as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("DELETE FROM reviews")

    def test_blank_reviewer_or_evidence_rejected(self):
        with self.assertRaisesRegex(ValueError, "reviewer"):
            self.submit(reviewer="")
        with self.assertRaisesRegex(ValueError, "evidence"):
            self.submit(evidence="")


class MetricTests(unittest.TestCase):
    def test_cer_wer_edit_distance(self):
        self.assertEqual(cer("abc", "adc"), 1 / 3)
        self.assertEqual(wer("a b c", "a x c"), 1 / 3)
        self.assertIsNone(cer("", "abc"))

    def test_math_is_not_normalized_away(self):
        self.assertFalse(formula_exact_match("n−1", "n+1"))
        self.assertFalse(formula_exact_match("x^{2}", "x^2"))
        self.assertTrue(formula_exact_match("a ≤ b", " a  ≤ b "))
        self.assertFalse(formula_exact_match("x₁", "x1"))
        self.assertFalse(formula_exact_match("x²", "x2"))
        self.assertFalse(formula_exact_match(r"x_{1", r"x_{1"))
        self.assertFalse(formula_exact_match("", ""))

    def test_iou_and_invalid_box(self):
        self.assertEqual(bbox_iou([0, 0, 10, 10], [0, 0, 10, 10]), 1)
        self.assertEqual(bbox_iou([0, 0, 10, 10], [10, 10, 20, 20]), 0)
        with self.assertRaises(ValueError):
            bbox_iou([0, 0, 0, 10], [0, 0, 10, 10])

    def test_q_missing_dimension_is_not_zero(self):
        self.assertIsNone(composite_quality({"A": 1, "G": None, "C": 1, "L": 1, "D": 1}))
        self.assertAlmostEqual(composite_quality(dict.fromkeys("AGCLD", 1)), 1)
        with self.assertRaises(ValueError):
            composite_quality(dict.fromkeys("AGCLD", 1.1))

    def test_human_refs_required_and_no_fake_gold(self):
        result = evaluate_metrics([{"id": "a", "reference": {"text": "abc"}, "prediction": {"text": "abc"}}])
        self.assertEqual(result["evaluated"], 0)
        self.assertIsNone(result["Q"])

    def test_reference_metrics_and_composite(self):
        refs = [{"id": "a", "reviewer": "A", "reference_verified": True,
                 "reference": {"text": "n ≤ 2", "latex": "n \\leq 2", "bbox": [0, 0, 10, 10],
                               "label": "formula", "component_ids": ["one", "two"]},
                 "assessment": {"groundedness": 1, "image_label_aligned": True}}]
        predictions = [{"id": "a", "text": "n ≤ 2", "latex": "n \\leq 2", "bbox": [0, 0, 10, 10],
                        "label": "formula", "covered_component_ids": ["one"], "structural_valid": True}]
        result = evaluate_metrics(refs, predictions)
        self.assertEqual(result["CER"], 0)
        self.assertEqual(result["Coverage"], .5)
        self.assertAlmostEqual(result["Q"], .9)

    def test_missing_prediction_counts_as_missing_content(self):
        result = evaluate_metrics([{"id": "a", "reviewer": "A", "reference_verified": True,
                                    "reference": {"text": "abc", "label": "text", "bbox": [0, 0, 1, 1]}}], [])
        self.assertEqual(result["missing_predictions"], 1)
        self.assertEqual(result["CER"], 1)
        self.assertEqual(result["Label_Accuracy"], 0)

    def test_no_coverage_without_human_inventory(self):
        self.assertIsNone(coverage(0, 0))
        self.assertIsNone(image_label_alignment([]))

    def test_missing_component_matching_is_not_zero_coverage(self):
        result = evaluate_metrics([{"id": "a", "reviewer": "A", "reference_verified": True,
                                    "reference": {"component_ids": ["one", "two"]}}], [{"id": "a", "text": "some text"}])
        self.assertIsNone(result["Coverage"])
        self.assertEqual(result["denominators"]["components"], 0)
        self.assertIsNone(result["Q"])

    def test_truthy_machine_flag_is_not_human_verification(self):
        result = evaluate_metrics([{"id": "a", "reviewer": "A", "reference_verified": "true",
                                    "reference": {"label": "text"}}], [{"id": "a", "label": "text"}])
        self.assertEqual(result["evaluated"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
