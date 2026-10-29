from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import copy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from sft_review_store import SFTReviewStore, canonical_hash, file_sha256, page_identity, question_identity


class ReviewStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "original.pdf"
        self.source.write_bytes(b"immutable source fixture")
        (self.root / "assets").mkdir()
        (self.root / "manifest.json").write_text(json.dumps({"schema": "bkquiz-sft-review-v1"}), encoding="utf-8")
        self.page = {"id": "rp_fixture", "source_id": "exam_fixture", "source_sha256": file_sha256(self.source),
                     "source_path": str(self.source), "relative_path": "original.pdf", "course": "OS", "page": 1,
                     "bbox": [0.0, 0.0, 600.0, 800.0], "tile_index": 0, "tile_count": 1,
                     "render_policy": "sft-page-v1", "reasons": ["ocr_required"], "question_ids": [],
                     "native_text_preview": "A\u2028B\u2029C"}
        self.page["identity"] = page_identity(self.page)
        self.write_page(self.page)
        self.asset = self.root / "assets/rp_fixture.png"
        self.asset.write_bytes(b"rendered image fixture")
        self.image_sha = file_sha256(self.asset)
        self.store = SFTReviewStore(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def write_page(self, page):
        with (self.root / "pages.jsonl").open("w", encoding="utf-8", newline="\n") as output:
            output.write(json.dumps(page, ensure_ascii=False) + "\n")

    def approve_page(self):
        return self.store.decide_page(self.page["id"], "approve", self.page["identity"], self.image_sha)

    def question(self, identity="qv_fixture", result="1" * 64):
        return {"id": identity, "page_id": self.page["id"], "image_sha256": self.image_sha,
                "result_sha256": result, "question": {"prompt": "Which statement is printed in the source?",
                "options": [{"label": "A", "text": "Printed answer", "source_marking": "checked"},
                            {"label": "B", "text": "Other answer", "source_marking": "unchecked"}],
                "answer": {"labels": ["A"], "text": "", "evidence": "checked", "origin": "source_marking"},
                "solution": "", "flags": []}}

    def import_question(self, row=None):
        row = row or self.question()
        self.approve_page()
        self.store.import_questions([row], "batch_fixture")
        return self.store.get_question(row["id"])

    def counts(self):
        with closing(sqlite3.connect(self.store.database)) as connection:
            return {table: connection.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]
                    for table in ["review_events", "machine_questions", "machine_batches", "page_result_versions"]}

    def install_route(self, route="native_text", **changes):
        folder = self.root / "triage"
        folder.mkdir(exist_ok=True)
        analysis = folder / "analysis.json"
        analysis.write_text(json.dumps({"page_id": self.page["id"], "identity": self.page["identity"],
                                       "source_sha256": self.page["source_sha256"]}), encoding="utf-8")
        text = folder / "text.txt"
        text.write_text("Câu 1. Nội dung nguồn được giữ nguyên.\nA. Phương án A\nB. Phương án B", encoding="utf-8")
        policy = folder / "policy.json"
        policy.write_text(json.dumps({"schema": "bkquiz-sft-auto-routing-policy-v1", "policy_id": "policy_fixture",
                                     "automatic_stage1_authorized": True, "authorization": "User requested automatic OCR triage"}), encoding="utf-8")
        row = {"page_id": self.page["id"], "identity": self.page["identity"], "policy_id": "policy_fixture",
               "route": route, "automatic": True, "human_verified": False,
               "analysis_path": "triage/analysis.json", "analysis_sha256": file_sha256(analysis)}
        if route in {"native_text", "ocr_text"}:
            row.update(text_path="triage/text.txt", text_sha256=file_sha256(text))
        row.update(changes)
        routing = folder / "routing.jsonl"
        routing.write_text(json.dumps(row) + "\n", encoding="utf-8")
        pointer = {"schema": "bkquiz-sft-auto-routing-pointer-v1", "policy_path": "triage/policy.json",
                   "policy_sha256": file_sha256(policy), "routing_path": "triage/routing.jsonl",
                   "routing_sha256": file_sha256(routing)}
        (self.root / "auto_routing_current.json").write_text(json.dumps(pointer), encoding="utf-8")
        return row

    def text_question(self, identity="qt_fixture"):
        page = self.store.get_page(self.page["id"])
        row = self.question(identity)
        row.pop("image_sha256")
        row.update(extraction_origin=page["automatic_routing"]["route"], text_sha256=page["automatic_routing"]["text_sha256"],
                   routing_policy_id=page["routing_policy_id"], routing_identity=page["routing_identity"],
                   routing_policy_sha256=page["routing_policy_sha256"], source_text_path=page["automatic_routing"]["source_text_path"])
        return row

    def write_render_meta(self):
        self.asset.with_suffix(".json").write_text(json.dumps({"identity": self.page["identity"],
                "source_sha256": self.page["source_sha256"], "sha256": self.image_sha}), encoding="utf-8")

    def test_gets_preserve_unicode_physical_lines_and_create_no_decisions(self):
        self.assertEqual(self.store.get_page(self.page["id"])["native_text_preview"], "A\u2028B\u2029C")
        self.assertEqual(self.store.list_pages()["total"], 1)
        self.assertEqual(self.store.page_progress()["pending"], 1)
        self.assertEqual(self.store.progress()["stage2"]["total"], 0)
        self.assertEqual(self.counts()["review_events"], 0)

    def test_page_batch_cache_does_not_survive_a_source_change(self):
        self.write_render_meta()
        self.install_route("auto_vlm")
        self.assertEqual(self.store.page_progress()["automatic_vlm"], 1)
        self.assertEqual(self.store.list_pages(status="auto_vlm")["total"], 1)
        self.source.write_bytes(b"changed source after the previous list request")
        self.assertEqual(self.store.page_progress()["manual_pending"], 1)
        self.assertEqual(self.store.list_pages(status="pending")["total"], 1)
        with self.assertRaises(ValueError):
            self.store.verify_vlm_page(self.page["id"], self.image_sha)
        self.assertEqual(self.counts()["review_events"], 0)

    def test_page_identity_exact_contract_ignores_mutable_preview_and_count(self):
        expected = canonical_hash({"source_sha256": self.page["source_sha256"], "page": 1,
                                   "bbox": self.page["bbox"], "tile_index": 0, "render_policy": "sft-page-v1"})
        self.assertEqual(self.page["identity"], expected)
        changed = dict(self.page, tile_count=9, native_text_preview="different", id="other")
        self.assertEqual(page_identity(changed), expected)

    def test_invalid_catalogue_fails_before_database_creation(self):
        root = self.root / "bad"
        root.mkdir()
        (root / "manifest.json").write_text('{"schema":"bkquiz-sft-review-v1"}', encoding="utf-8")
        changed = dict(self.page, identity="bad")
        (root / "pages.jsonl").write_text(json.dumps(changed) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "identity"):
            SFTReviewStore(root)
        self.assertFalse((root / "human_reviews.sqlite3").exists())

    def test_approve_requires_exact_rendered_image(self):
        with self.assertRaisesRegex(ValueError, "image_sha256"):
            self.store.decide_page(self.page["id"], "approve", self.page["identity"])
        with self.assertRaisesRegex(ValueError, "stale_image_hash"):
            self.store.decide_page(self.page["id"], "approve", self.page["identity"], "2" * 64)
        self.assertEqual(self.counts()["review_events"], 0)
        self.approve_page()
        selected = self.store.selected_pages()
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["image_sha256"], self.image_sha)
        self.assertEqual(Path(selected[0]["image_path"]), self.asset)

    def test_stale_expected_identity_rejected_without_event(self):
        with self.assertRaisesRegex(ValueError, "stale_identity"):
            self.store.decide_page(self.page["id"], "approve", "3" * 64, self.image_sha)
        self.assertEqual(self.counts()["review_events"], 0)

    def test_image_or_pdf_tamper_revokes_export_without_erasing_history(self):
        self.approve_page()
        self.asset.write_bytes(b"tampered image")
        self.assertEqual(self.store.selected_pages(), [])
        self.assertEqual(self.store.get_page(self.page["id"])["status"], "stale")
        self.asset.write_bytes(b"rendered image fixture")
        self.source.write_bytes(b"tampered original")
        self.assertEqual(self.store.selected_pages(), [])
        with self.assertRaisesRegex(ValueError, "stale_source_hash"):
            self.store.decide_page(self.page["id"], "approve", self.page["identity"], self.image_sha)
        self.assertEqual(len(self.store.history(1, self.page["id"])), 1)

    def test_defer_and_reject_remain_distinct_append_only_events(self):
        self.store.decide_page(self.page["id"], "defer", self.page["identity"], note="later")
        self.assertEqual(self.store.list_pages(status="pending")["total"], 1)
        self.assertEqual(self.store.page_progress()["deferred"], 1)
        self.store.decide_page(self.page["id"], "reject", self.page["identity"], note="not useful")
        self.assertEqual(self.store.selected_pages(), [])
        self.assertEqual(self.store.page_progress()["rejected"], 1)
        self.assertEqual(len(self.store.history(1, self.page["id"])), 2)
        with closing(sqlite3.connect(self.store.database)) as connection:
            with self.assertRaisesRegex(sqlite3.IntegrityError, "append-only"):
                connection.execute("DELETE FROM review_events")

    def test_machine_import_requires_current_stage1_approval(self):
        with self.assertRaisesRegex(ValueError, "not currently approved"):
            self.store.import_questions([self.question()], "batch")
        self.approve_page()
        bad = self.question(); bad["image_sha256"] = "9" * 64
        with self.assertRaisesRegex(ValueError, "does not match stage1"):
            self.store.import_questions([bad], "batch")
        bad = self.question(); bad["page_id"] = "unknown"
        with self.assertRaisesRegex(ValueError, "unknown imported page"):
            self.store.import_questions([bad], "batch")
        self.assertEqual(self.counts()["machine_questions"], 0)

    def test_machine_import_idempotency_does_not_approve_questions(self):
        self.approve_page()
        receipt = self.store.import_questions([self.question()], "batch")
        self.assertEqual(receipt["imported"], 1)
        repeated = self.store.import_questions([self.question()], "batch")
        self.assertTrue(repeated["idempotent"])
        self.assertEqual(repeated["imported"], 0)
        self.assertEqual(self.store.get_question("qv_fixture")["status"], "pending")
        self.assertEqual(self.store.export_approved_questions(), [])
        self.assertEqual(self.counts()["review_events"], 1)

    def test_conflicting_machine_id_and_provenance_are_rejected_atomically(self):
        self.approve_page()
        self.store.import_questions([self.question()], "batch")
        bad = self.question(); bad["question"]["prompt"] = "Different immutable output"
        with self.assertRaisesRegex(ValueError, "conflicts with immutable"):
            self.store.import_questions([bad, self.question("qv_new")], "batch2")
        self.assertEqual(self.counts()["machine_questions"], 1)
        bad = self.question("qv_new"); bad["source_sha256"] = "9" * 64
        with self.assertRaisesRegex(ValueError, "provenance mismatch"):
            self.store.import_questions([bad], "batch2")
        self.assertEqual(self.counts()["machine_batches"], 1)

    def test_stage2_approve_and_correct_preserve_machine_original(self):
        row = self.import_question()
        corrected = copy.deepcopy(row["question"])
        corrected["prompt"] = "A corrected transcription from the source image"
        with self.assertRaisesRegex(ValueError, "use correct"):
            self.store.decide_question(row["id"], "approve", row["identity"], corrected)
        self.store.decide_question(row["id"], "correct", row["identity"], corrected, note="fixed OCR")
        current = self.store.get_question(row["id"])
        self.assertEqual(current["question"], row["question"])
        self.assertEqual(current["accepted_question"], corrected)
        self.assertTrue(current["human_verified"])
        self.assertEqual(len(self.store.export_approved_questions()), 1)
        self.store.decide_question(row["id"], "reject", row["identity"], note="later found erroneous")
        self.assertEqual(self.store.export_approved_questions(), [])
        self.assertEqual(len(self.store.history(2, row["id"])), 2)
        with closing(sqlite3.connect(self.store.database)) as connection:
            with self.assertRaisesRegex(sqlite3.IntegrityError, "append-only"):
                connection.execute("UPDATE machine_questions SET identity='bad'")

    def test_page_rejection_blocks_previously_approved_questions(self):
        row = self.import_question()
        self.store.decide_question(row["id"], "approve", row["identity"])
        self.store.decide_page(self.page["id"], "reject", self.page["identity"], note="discard page")
        self.assertEqual(self.store.get_question(row["id"])["status"], "blocked")
        self.assertEqual(self.store.export_approved_questions(), [])
        with self.assertRaisesRegex(ValueError, "stale_dependency"):
            self.store.decide_question(row["id"], "approve", row["identity"])

    def test_new_vlm_revision_supersedes_old_reviews_without_overwrite(self):
        old = self.import_question()
        self.store.decide_question(old["id"], "approve", old["identity"])
        new = self.question("qv_new", "2" * 64)
        self.store.import_questions([new], "batch2")
        self.assertEqual(self.store.get_question(old["id"])["status"], "superseded")
        self.assertEqual(self.store.export_approved_questions(), [])
        self.assertEqual(len(self.store.history(2, old["id"])), 1)
        with self.assertRaisesRegex(ValueError, "stale_result_revision"):
            self.store.import_questions([self.question()], "batch_old_fresh_id")

    def test_changed_catalogue_identity_marks_old_page_review_stale(self):
        self.approve_page()
        changed = dict(self.page, bbox=[0.0, 0.0, 600.0, 700.0])
        changed["identity"] = page_identity(changed)
        self.write_page(changed)
        self.assertEqual(self.store.get_page(self.page["id"])["status"], "stale")
        self.assertEqual(self.store.selected_pages(), [])

    def test_concurrent_explicit_decisions_preserve_every_event(self):
        def save(index):
            return self.store.decide_page(self.page["id"], "defer", self.page["identity"], note=str(index))
        with ThreadPoolExecutor(max_workers=5) as executor:
            events = list(executor.map(save, range(15)))
        self.assertEqual(len({event["sequence"] for event in events}), 15)
        self.assertEqual(len(self.store.history(1, self.page["id"])), 15)

    def test_concurrent_idempotent_imports_insert_one_machine_snapshot(self):
        self.approve_page()
        with ThreadPoolExecutor(max_workers=4) as executor:
            receipts = list(executor.map(lambda _: self.store.import_questions([self.question()], "batch"), range(8)))
        self.assertEqual(sum(receipt["imported"] for receipt in receipts), 1)
        self.assertEqual(self.counts()["machine_questions"], 1)
        self.assertEqual(self.counts()["review_events"], 1)

    def test_invalid_question_corrections_and_identity_are_rejected(self):
        row = self.import_question()
        self.assertEqual(row["identity"], question_identity(row))
        with self.assertRaisesRegex(ValueError, "stale_identity"):
            self.store.decide_question(row["id"], "approve", "bad")
        with self.assertRaisesRegex(ValueError, "nonempty prompt"):
            self.store.decide_question(row["id"], "correct", row["identity"], {"prompt": ""})
        with self.assertRaises(ValueError):
            self.store.decide_question(row["id"], "correct", row["identity"], {"prompt": "text", "invalid": float("nan")})
        self.assertEqual(self.counts()["review_events"], 1)

    def test_progress_does_not_truncate_more_than_ten_thousand_questions(self):
        self.approve_page()
        rows = [self.question("qv_" + str(index)) for index in range(10005)]
        self.store.import_questions(rows, "large_fixture")
        self.assertEqual(self.store.list_questions(status="all", limit=10)["total"], 10005)
        progress = self.store.question_progress()
        self.assertEqual(progress["total"], 10005)
        self.assertEqual(progress["pending"], 10005)

    def test_automatic_text_routes_have_separate_progress_and_no_human_events(self):
        self.install_route()
        page = self.store.get_page(self.page["id"])
        self.assertEqual(page["status"], "auto_text")
        self.assertFalse(page["human_verified"])
        self.assertFalse(page["manual_review_required"])
        self.assertEqual(self.store.selected_pages(), [])
        self.assertEqual(self.store.vlm_eligible_pages(), [])
        progress = self.store.page_progress()
        self.assertEqual(progress["manual_pending"], 0)
        self.assertEqual(progress["automatic_text"], 1)
        self.assertEqual(progress["automatic_total"], 1)
        self.assertEqual(self.counts()["review_events"], 0)
        self.assertEqual(self.store.list_pages(status="auto_text")["total"], 1)

    def test_text_import_without_rendered_png_remains_stage2_pending_until_human_review(self):
        self.install_route("ocr_text")
        self.asset.unlink()
        row = self.text_question()
        verified = self.store.verify_text_page(row["page_id"], row["text_sha256"], row["routing_policy_id"],
                                              row["routing_identity"], row["routing_policy_sha256"])
        self.assertEqual(verified["status"], "auto_text")
        self.store.import_text_questions([row], "text_batch")
        current = self.store.get_question(row["id"])
        self.assertEqual(current["status"], "pending")
        self.assertEqual(self.store.export_approved_questions(), [])
        self.assertEqual(self.counts()["review_events"], 0)
        event = self.store.decide_question(row["id"], "approve", current["identity"])
        self.assertEqual(event["text_sha256"], row["text_sha256"])
        self.assertEqual(event["extraction_origin"], "ocr_text")
        self.assertNotIn("image_sha256", event)
        self.assertEqual(len(self.store.export_approved_questions()), 1)

    def test_every_human_page_decision_precedes_machine_routing(self):
        self.install_route()
        for decision in ["defer", "reject", "approve"]:
            with self.subTest(decision=decision):
                self.store.decide_page(self.page["id"], decision, self.page["identity"], self.image_sha)
                current = self.store.get_page(self.page["id"])
                self.assertEqual(current["status"], decision)
                self.assertEqual(current["human_verified"], decision == "approve")
        self.asset.write_bytes(b"changed")
        self.assertEqual(self.store.get_page(self.page["id"])["status"], "stale")
        self.assertEqual(len(self.store.history(1, self.page["id"])), 3)

    def test_machine_evidence_or_text_tamper_returns_to_manual_queue(self):
        for target in ["analysis.json", "text.txt", "policy.json", "routing.jsonl"]:
            with self.subTest(target=target):
                self.install_route()
                self.assertEqual(self.store.get_page(self.page["id"])["status"], "auto_text")
                (self.root / "triage" / target).write_text("changed", encoding="utf-8")
                current = self.store.get_page(self.page["id"])
                self.assertEqual(current["status"], "pending")
                self.assertTrue(current["manual_review_required"])
                self.assertIn("machine_routing_error", current)
        self.assertEqual(self.counts()["review_events"], 0)

    def test_changed_routing_snapshot_blocks_existing_automatic_questions(self):
        self.install_route()
        row = self.text_question()
        self.store.import_text_questions([row], "text_batch")
        self.install_route(reasons=["updated policy evidence"])
        self.assertEqual(self.store.get_question(row["id"])["status"], "blocked")
        with self.assertRaisesRegex(ValueError, "routing evidence"):
            self.store.import_text_questions([row], "different_batch")
        self.assertEqual(self.counts()["review_events"], 0)

    def test_auto_vlm_requires_current_render_and_policy_snapshot(self):
        self.asset.unlink()
        self.install_route("auto_vlm")
        page = self.store.get_page(self.page["id"])
        self.assertEqual(page["status"], "auto_vlm")
        self.assertEqual(len(self.store.vlm_eligible_pages()), 1)
        self.assertEqual(self.store.selected_pages(), [])
        with self.assertRaisesRegex(ValueError, "stale_image_hash"):
            self.store.verify_vlm_page(page["id"], self.image_sha, page["routing_policy_id"], page["routing_identity"])
        self.asset.write_bytes(b"rendered image fixture")
        self.write_render_meta()
        verified = self.store.verify_vlm_page(page["id"], self.image_sha, page["routing_policy_id"], page["routing_identity"])
        self.assertEqual(verified["status"], "auto_vlm")
        row = self.question()
        row.update(routing_policy_id=page["routing_policy_id"], routing_identity=page["routing_identity"],
                   routing_policy_sha256=page["routing_policy_sha256"])
        self.store.import_questions([row], "automatic_vlm")
        self.assertEqual(self.store.get_question(row["id"])["status"], "pending")
        self.assertEqual(self.counts()["review_events"], 0)
        self.store.decide_page(page["id"], "reject", page["identity"], self.image_sha)
        self.assertEqual(self.store.get_question(row["id"])["status"], "blocked")

    def test_automatic_routes_cannot_claim_human_verification_or_escape_workspace(self):
        for changes in [{"human_verified": True}, {"automatic": False}, {"analysis_path": "../outside.json"},
                        {"identity": "a" * 64}, {"risk_score": float("nan")}]:
            with self.subTest(changes=changes):
                self.install_route(**changes)
                current = self.store.get_page(self.page["id"])
                self.assertEqual(current["status"], "pending")
                self.assertIn("machine_routing_error", current)
        self.assertEqual(self.counts()["review_events"], 0)

    def test_invalid_pointer_and_nonobject_evidence_fail_to_manual(self):
        self.install_route()
        (self.root / "auto_routing_current.json").write_text("[]", encoding="utf-8")
        self.assertEqual(self.store.get_page(self.page["id"])["status"], "pending")
        self.install_route()
        evidence = self.root / "triage/analysis.json"
        # Publish a correctly hashed array to exercise JSON shape validation.
        evidence.write_text("[]", encoding="utf-8")
        routing = self.root / "triage/routing.jsonl"
        route = json.loads(routing.read_text(encoding="utf-8"))
        route["analysis_sha256"] = file_sha256(evidence)
        routing.write_text(json.dumps(route) + "\n", encoding="utf-8")
        pointer_path = self.root / "auto_routing_current.json"
        pointer = json.loads(pointer_path.read_text(encoding="utf-8")); pointer["routing_sha256"] = file_sha256(routing)
        pointer_path.write_text(json.dumps(pointer), encoding="utf-8")
        current = self.store.get_page(self.page["id"])
        self.assertEqual(current["status"], "pending")
        self.assertIn("analysis does not belong", current["machine_routing_error"])

    def test_automatic_blank_and_manual_are_distinct_without_user_rejection(self):
        self.install_route("blank")
        self.assertEqual(self.store.page_progress()["automatic_blank"], 1)
        self.assertEqual(self.store.page_progress()["rejected"], 0)
        self.install_route("manual", reasons=["unreadable source"])
        self.assertEqual(self.store.page_progress()["manual_pending"], 1)
        self.assertEqual(self.counts()["review_events"], 0)


if __name__ == "__main__":
    unittest.main()
