"""Behavioral review API and Label Studio boundary tests (stdlib only)."""
from __future__ import annotations

import copy
import hashlib
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest

from review_app import ReviewHTTPServer, allowed_roots, image_file, review_target
from label_studio import export_tasks, import_annotations

PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000b49444154789c636000020000050001a5f645400000000049454e44ae426082")


class FakeStore:
    def __init__(self, record):
        self.record = record
        self.reviews = []

    def get_record(self, identifier):
        if identifier != self.record["id"]:
            raise KeyError(identifier)
        return self.record

    def list_records(self, bucket=None, decision=None, limit=100, offset=0):
        records = [self.record] if not bucket or bucket == self.record["machine_bucket"] else []
        return records[offset:offset + limit]

    def history(self, identifier):
        self.get_record(identifier)
        return self.reviews

    def stats(self):
        return {"total": 1, "reviews": len(self.reviews)}

    def submit(self, **kwargs):
        if kwargs["expected_revision"] != self.record["machine_revision"]:
            raise ValueError("stale_revision")
        if self.record["risk"] == "high" and kwargs["decision"] in {"approve", "correct"} and not kwargs.get("acknowledgement_high_risk"):
            raise ValueError("Manual high-risk acknowledgement required")
        self.reviews.append(copy.deepcopy(kwargs))
        return kwargs


class ReviewBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.run = self.root / "run"
        self.run.mkdir()
        (self.run / "slide.png").write_bytes(PNG)
        (self.run / "manifest.json").write_text(json.dumps({"document": {"sha256": "a" * 64, "pages": 1}}), encoding="utf-8")
        sha = hashlib.sha256(PNG).hexdigest()
        self.record = {"id": "p0001_diagram", "page": 1, "kind": "diagram", "bbox": [0, 0, 1000, 1000],
            "source_sha256": "a" * 64, "render_path": "slide.png", "crop_path": "slide.png",
            "render_sha256": sha, "crop_sha256": sha, "machine_revision": "b" * 64,
            "machine_bucket": "uncertain", "risk": "high", "split": "train", "group_id": "g1",
            "native_text": "<script>alert('native')</script>", "proposed_text": "Đồ thị có hai đỉnh.",
            "candidates": [{"engine": "vlm", "text": "<img src=x onerror=alert(1)>", "status": "ok"}]}
        self.store = FakeStore(self.record)
        self.server = ReviewHTTPServer(("127.0.0.1", 0), self.run, self.store, scope=getattr(self,"SCOPE","all"))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temporary.cleanup()

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        result = (response.status, dict(response.getheaders()), response.read())
        connection.close()
        return result

    def payload(self, **changes):
        return {"record_id": self.record["id"], "reviewer": "Human", "decision": "correct", "text": "Hai đỉnh nối bằng một cạnh.",
                "evidence": "Đã đối chiếu vùng giữa slide gốc.", "expected_revision": self.record["machine_revision"],
                "acknowledgement_high_risk": True, **changes}

    def post(self, payload, **headers):
        return self.request("POST", "/api/review", json.dumps(payload),
            {"Content-Type": "application/json", "X-Review-Token": self.server.csrf_token, **headers})

    def test_record_api_exposes_candidates_without_approval(self):
        status, headers, body = self.request("GET", "/api/record/p0001_diagram")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["record"]["candidates"], self.record["candidates"])
        self.assertEqual(self.store.reviews, [])
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")

    def test_valid_human_submission_is_delegated_once(self):
        self.assertEqual(self.post(self.payload())[0], 201)
        self.assertEqual(len(self.store.reviews), 1)
        self.assertEqual(self.store.reviews[0]["expected_revision"], "b" * 64)

    def test_no_token_cannot_mutate(self):
        status, _, _ = self.request("POST", "/api/review", "{}", {"Content-Type": "application/json"})
        self.assertEqual(status, 403)
        self.assertEqual(self.store.reviews, [])

    def test_cross_origin_blocked_even_with_token(self):
        self.assertEqual(self.post(self.payload(), Origin="http://evil.example")[0], 403)
        self.assertEqual(self.store.reviews, [])

    def test_dns_rebinding_host_blocked(self):
        status, _, _ = self.request("GET", "/api/bootstrap", headers={"Host": "evil.example"})
        self.assertEqual(status, 403)

    def test_empty_reviewer_and_evidence_are_rejected(self):
        self.assertEqual(self.post(self.payload(reviewer=" "))[0], 400)
        self.assertEqual(self.post(self.payload(evidence=" "))[0], 400)

    def test_non_boolean_ack_and_unknown_fields_rejected(self):
        self.assertEqual(self.post(self.payload(acknowledgement_high_risk="true"))[0], 400)
        self.assertEqual(self.post(self.payload(semantic_verified=True))[0], 400)

    def test_stale_revision_cannot_be_reviewed(self):
        self.assertEqual(self.post(self.payload(expected_revision="outdated"))[0], 400)
        self.assertEqual(self.store.reviews, [])

    def test_store_high_risk_guard_survives_http(self):
        self.assertEqual(self.post(self.payload(acknowledgement_high_risk=False))[0], 400)
        self.assertEqual(self.store.reviews, [])

    def test_filter_validation_and_pagination(self):
        self.assertEqual(self.request("GET", "/api/records?bucket=uncertain")[0], 200)
        self.assertEqual(self.request("GET", "/api/records?bucket=anything")[0], 400)
        self.assertEqual(self.request("GET", "/api/records?limit=100000")[0], 400)

    def test_static_inventory_blocks_filesystem_reads(self):
        self.assertEqual(self.request("GET", "/../manifest.json")[0], 404)
        self.assertEqual(self.request("GET", "/api/record/p0001_diagram/image/../manifest.json")[0], 404)
        self.assertEqual(self.request("GET", "/api/record/%2e%2e%2fmanifest.json")[0], 400)

    def test_image_only_from_bound_record(self):
        status, headers, data = self.request("GET", "/api/record/p0001_diagram/image/render")
        self.assertEqual((status, data), (200, PNG))
        self.assertEqual(headers["Content-Type"], "image/png")

    def test_contextual_crop_is_source_bound(self):
        self.record["context_path"] = "slide.png"
        self.record["context_sha256"] = self.record["render_sha256"]
        self.assertEqual(self.request("GET", "/api/record/p0001_diagram/image/context")[0], 200)
        self.record["context_sha256"] = "d" * 64
        self.assertEqual(self.request("GET", "/api/record/p0001_diagram/image/context")[0], 409)

    def test_image_path_escape_rejected(self):
        outside = self.root / "private.png"
        outside.write_bytes(PNG)
        self.record["render_path"] = str(outside)
        self.assertEqual(self.request("GET", "/api/record/p0001_diagram/image/render")[0], 403)

    def test_image_hash_mismatch_rejected(self):
        self.record["render_sha256"] = "c" * 64
        self.assertEqual(self.request("GET", "/api/record/p0001_diagram/image/render")[0], 409)

    def test_html_disguised_as_png_is_not_served(self):
        (self.run / "slide.png").write_bytes(b"<script>alert(1)</script>")
        self.assertEqual(self.request("GET", "/api/record/p0001_diagram/image/render")[0], 400)

    def test_declared_external_asset_root_is_explicit(self):
        roots = allowed_roots(self.run, {"asset_root": str(self.root)})
        outside = self.root / "external.png"
        outside.write_bytes(PNG)
        self.record["render_path"] = str(outside)
        self.assertEqual(image_file(self.run, roots, self.record, "render")[0], PNG)

    def test_ui_inserts_untrusted_text_as_text_only(self):
        status, headers, body = self.request("GET", "/app.js")
        self.assertEqual(status, 200)
        self.assertNotIn(b"innerHTML", body)
        self.assertIn(b"textContent", body)
        self.assertIn("default-src 'self'", headers["Content-Security-Policy"])

    def real_store(self):
        from review_store import ReviewStore
        (self.run / "records.jsonl").write_text(json.dumps(self.record, ensure_ascii=False) + "\n", encoding="utf-8")
        self.server.store = ReviewStore(self.run)
        return self.server.store

    def test_real_store_http_preserves_machine_and_appends_human_history(self):
        store = self.real_store()
        initial = (self.run / "records.jsonl").read_bytes()
        status, _, body = self.post(self.payload(decision="approve", text=self.record["proposed_text"]))
        self.assertEqual(status, 201)
        self.assertTrue(json.loads(body)["review"]["human_verified"])
        self.assertEqual(self.post(self.payload(decision="reject", text=""))[0], 201)
        self.assertEqual(len(store.history(self.record["id"])), 2)
        self.assertFalse(store.get_record(self.record["id"])["human_verified"])
        self.assertEqual((self.run / "records.jsonl").read_bytes(), initial)

    def test_real_store_pending_filter_matches_review_ui(self):
        self.real_store()
        status, _, body = self.request("GET", "/api/records?decision=pending")
        self.assertEqual(status, 200)
        self.assertEqual(len(json.loads(body)["records"]), 1)

    def test_real_store_rejects_modified_evidence_on_submit(self):
        store = self.real_store()
        (self.run / "slide.png").write_bytes(PNG + b"changed")
        self.assertEqual(self.post(self.payload())[0], 400)
        self.assertEqual(store.history(self.record["id"]), [])

    def tasks(self):
        output = self.root / "label_studio"
        export_tasks(self.run, output, self.store)
        return output, json.loads((output / "tasks.json").read_text(encoding="utf-8"))

    def write_annotations(self, tasks):
        source = self.root / "annotations.json"
        source.write_text(json.dumps(tasks, ensure_ascii=False), encoding="utf-8")
        return source

    def annotation(self, **overrides):
        values = {"final_text": self.record["proposed_text"], "evidence": "Đã đối chiếu bản gốc.", "decision": "approve", **overrides}
        results = [{"from_name": key, "value": {"text" if key in {"final_text", "evidence"} else "choices": [value]}} for key, value in values.items()]
        results.append({"from_name": "high_risk_ack", "value": {"choices": ["manually_checked_high_risk"]}})
        return {"id": 5, "completed_by": 8, "result": results}

    def test_label_studio_export_copies_only_allowlisted_raster_evidence(self):
        output, tasks = self.tasks()
        self.assertEqual(tasks[0]["data"]["machine_revision"], self.record["machine_revision"])
        self.assertEqual(len(list((output / "assets").glob("*.png"))), 1)
        self.assertTrue((output / "label_config.xml").exists())
        self.assertEqual(self.store.reviews, [])

    def test_label_studio_ignores_machine_predictions(self):
        _, tasks = self.tasks()
        tasks[0]["predictions"] = [{"result": self.annotation()["result"]}]
        result = import_annotations(self.run, self.write_annotations(tasks), "Human", self.store)
        self.assertEqual(len(result["skipped"]), 1)
        self.assertEqual(self.store.reviews, [])

    def test_label_studio_human_import_and_idempotency(self):
        _, tasks = self.tasks()
        tasks[0]["annotations"] = [self.annotation()]
        path = self.write_annotations(tasks)
        result = import_annotations(self.run, path, "Human", self.store)
        self.assertEqual(len(result["accepted"]), 1)
        result = import_annotations(self.run, path, "Human", self.store)
        self.assertEqual(len(result["skipped"]), 1)
        self.assertEqual(len(self.store.reviews), 1)

    def test_label_studio_tampered_source_binding_rejected(self):
        _, tasks = self.tasks()
        tasks[0]["data"]["render_sha256"] = "c" * 64
        tasks[0]["annotations"] = [self.annotation()]
        result = import_annotations(self.run, self.write_annotations(tasks), "Human", self.store)
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(self.store.reviews, [])

    def test_label_studio_changed_approved_text_requires_correction_decision(self):
        _, tasks = self.tasks()
        tasks[0]["annotations"] = [self.annotation(final_text="Nội dung đã sửa")]
        result = import_annotations(self.run, self.write_annotations(tasks), "Human", self.store)
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(self.store.reviews, [])

    def test_label_studio_missing_human_evidence_rejected(self):
        _, tasks = self.tasks()
        tasks[0]["annotations"] = [self.annotation(evidence=" ")]
        result = import_annotations(self.run, self.write_annotations(tasks), "Human", self.store)
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(self.store.reviews, [])


class VLMScopeTests(unittest.TestCase):
    SCOPE = "vlm"
    tearDown = ReviewBoundaryTests.tearDown
    request = ReviewBoundaryTests.request
    post = ReviewBoundaryTests.post

    def setUp(self):
        ReviewBoundaryTests.setUp(self)
        self.record["proposed_text"] = self.record["candidates"][0]["text"]

    def quick(self, action="approve", **changes):
        return {"record_id":self.record["id"],"reviewer":"Named human","decision":action,
            "text":self.record["proposed_text"] if action=="approve" else "",
            "expected_revision":self.record["machine_revision"],
            "expected_candidate_sha256":review_target(self.record)["candidate_sha256"],
            "input_method":"keyboard_up" if action=="approve" else "keyboard_down",
            "action_id":"unique-human-gesture-12345",**changes}

    def test_vlm_scope_hides_native_only_record_and_image(self):
        self.record["candidates"]=[{"engine":"native","status":"ok","text":"Native text"}]
        status,_,body=self.request("GET","/api/records")
        self.assertEqual(status,200);self.assertEqual(json.loads(body)["records"],[])
        self.assertEqual(self.request("GET","/api/record/p0001_diagram")[0],403)
        self.assertEqual(self.request("GET","/api/record/p0001_diagram/image/render")[0],403)

    def test_hidden_native_id_cannot_receive_review(self):
        payload=self.quick();self.record["candidates"]=[]
        self.assertEqual(self.post(payload)[0],403);self.assertFalse(self.store.reviews)

    def test_failed_or_empty_vlm_not_in_factual_queue(self):
        for status,text in [("error","Failed"),("ok","   "),("not_run",""),("pending","queued")]:
            self.record["candidates"]=[{"engine":"vlm","status":status,"text":text}]
            self.assertEqual(json.loads(self.request("GET","/api/records")[2])["total"],0)
        data=json.loads(self.request("GET","/api/stats")[2])
        self.assertEqual(data["diagnostics"]["vlm_failed_or_empty_records"],1)

    def test_scoped_counts_are_distinct_from_inventory_and_pdf_pages(self):
        self.server.manifest["document"]["pages"]=1060
        data=json.loads(self.request("GET","/api/stats")[2])
        self.assertEqual(data["total"],1);self.assertEqual(data["vlm_pages"],1)
        self.assertEqual(data["source_pdf_pages"],1060);self.assertEqual(data["inventory"]["total"],1)

    def test_quick_human_key_generates_factual_audit_and_high_risk_ack(self):
        self.assertEqual(self.post(self.quick())[0],201)
        review=self.store.reviews[0]
        self.assertTrue(review["acknowledgement_high_risk"])
        self.assertIn("input_method=keyboard_up",review["evidence"])
        self.assertIn("Explicit UI action",review["evidence"])
        self.assertNotIn("Source checked",review["evidence"])

    def test_wrong_selected_native_proposal_cannot_be_approved(self):
        payload=self.quick();self.record["proposed_text"]="Native fallback"
        self.assertEqual(self.post(payload)[0],409);self.assertFalse(self.store.reviews)

    def test_changed_vlm_component_rejected_even_with_same_record_revision(self):
        payload=self.quick();self.record["candidates"][0]["text"]="Different VLM text"
        self.record["proposed_text"]="Different VLM text"
        self.assertEqual(self.post(payload)[0],409);self.assertFalse(self.store.reviews)

    def test_explicit_input_method_required_no_automatic_approval(self):
        payload=self.quick();payload.pop("input_method")
        self.assertEqual(self.post(payload)[0],400);self.assertFalse(self.store.reviews)

    def test_direction_and_action_must_match(self):
        self.assertEqual(self.post(self.quick(input_method="keyboard_down"))[0],400)
        self.assertFalse(self.store.reviews)

    def test_repeated_http_gesture_is_idempotent(self):
        payload=self.quick();self.assertEqual(self.post(payload)[0],201)
        self.assertEqual(self.post(payload)[0],200);self.assertEqual(len(self.store.reviews),1)

    def test_reused_action_id_cannot_change_decision(self):
        self.post(self.quick())
        self.assertEqual(self.post(self.quick("reject"))[0],409)
        self.assertEqual(len(self.store.reviews),1)

    def test_native_fallback_text_cannot_be_smuggled_into_approval(self):
        self.assertEqual(self.post(self.quick(text="Hidden native text"))[0],400)
        self.assertFalse(self.store.reviews)

    def test_explicit_correction_requires_save_action(self):
        payload=self.quick("reject",decision="correct",text="Human correction",input_method="click_save_correction")
        self.assertEqual(self.post(payload)[0],201)
        self.assertEqual(self.store.reviews[0]["text"],"Human correction")


if __name__ == "__main__":
    unittest.main()
