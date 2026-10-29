"""Explicit owner exclusions revoke exports without fabricating review events."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from owner_exclusion import install_owner_exclusion,OwnerExclusionPolicy,sha
from sft_review_store import SFTReviewStore,page_identity
import test_review_store as fixtures


class OwnerExclusionTests(unittest.TestCase):
    setUp=fixtures.ReviewStoreTests.setUp
    tearDown=fixtures.ReviewStoreTests.tearDown
    write_page=fixtures.ReviewStoreTests.write_page
    approve_page=fixtures.ReviewStoreTests.approve_page
    question=fixtures.ReviewStoreTests.question
    counts=fixtures.ReviewStoreTests.counts
    install_route=fixtures.ReviewStoreTests.install_route
    text_question=fixtures.ReviewStoreTests.text_question
    write_render_meta=fixtures.ReviewStoreTests.write_render_meta

    def exclude(self,**kwargs):
        return install_owner_exclusion(self.root,authorization="Owner explicitly excludes pending LLM/VLM/manual pages",note="isolated test",**kwargs)

    def test_requires_owner_authorization(self):
        with self.assertRaisesRegex(ValueError,"authorization"):install_owner_exclusion(self.root)
        self.assertFalse((self.root/"owner_exclusion_current.json").exists())

    def test_install_writes_versioned_receipt_but_no_human_event(self):
        receipt=self.exclude();self.assertEqual(receipt["excluded_items"],1)
        self.assertEqual(receipt["excluded_source_pages"],1)
        self.assertEqual(receipt["human_review_events_created"],0)
        self.assertEqual(self.counts()["review_events"],0)
        self.assertEqual(sha(receipt["policy_path"]),receipt["policy_sha256"])
        self.assertEqual(sha(receipt["ledger_path"]),receipt["ledger_sha256"])
        page=self.store.get_page(self.page["id"])
        self.assertEqual(page["status"],"excluded");self.assertTrue(page["export_excluded"])
        self.assertFalse(page["human_verified"]);self.assertFalse(page["manual_review_required"])

    def test_idempotent_install_and_append_only_versions(self):
        first=self.exclude();second=self.exclude()
        self.assertEqual(first["policy_id"],second["policy_id"]);self.assertTrue(second["already_current"])
        later=install_owner_exclusion(self.root,authorization="Owner excludes pending pages",note="new version")
        self.assertNotEqual(first["policy_id"],later["policy_id"])
        self.assertTrue(Path(first["policy_path"]).is_file());self.assertTrue(Path(first["ledger_path"]).is_file())
        self.assertEqual(len(list((self.root/"owner_exclusions/pointer_history").glob("*.json"))),1)
        self.assertEqual(self.counts()["review_events"],0)

    def test_unknown_page_rejected_without_pointer(self):
        with self.assertRaisesRegex(ValueError,"Unknown"):self.exclude(page_ids=["not_a_page"])
        self.assertFalse((self.root/"owner_exclusion_current.json").exists())

    def test_historical_image_approval_is_preserved_but_no_longer_eligible(self):
        self.approve_page();self.assertEqual(len(self.store.selected_pages()),1)
        self.exclude();page=self.store.get_page(self.page["id"])
        self.assertEqual(page["status"],"excluded");self.assertEqual(page["historical_review_decision"],"approve")
        self.assertEqual(page["latest_review"]["decision"],"approve");self.assertIsNone(page["effective_review"])
        self.assertEqual(self.store.selected_pages(),[]);self.assertEqual(self.store.vlm_eligible_pages(),[])
        self.assertEqual(len(self.store.history(1,self.page["id"])),1);self.assertEqual(self.counts()["review_events"],1)

    def test_exclusion_skips_expensive_legacy_verification(self):
        self.approve_page();self.exclude();self.source.unlink();self.asset.unlink()
        with patch.object(self.store,"_verify_source",side_effect=AssertionError("must not check excluded PDF")),patch.object(self.store,"_verify_image",side_effect=AssertionError("must not render/check excluded image")):
            self.assertEqual(self.store.get_page(self.page["id"])["status"],"excluded")
            self.assertEqual(self.store.page_progress()["excluded"],1)

    def test_excluded_progress_and_filter(self):
        self.write_render_meta();self.install_route("auto_vlm");self.exclude()
        progress=self.store.page_progress()
        self.assertEqual(progress["excluded"],1);self.assertEqual(progress["pending"],0)
        self.assertEqual(progress["vlm_eligible"],0);self.assertEqual(progress["automatic_vlm"],0)
        self.assertEqual(self.store.list_pages(status="excluded")["total"],1)
        self.assertEqual(self.store.list_pages(status="pending")["total"],0)

    def test_approve_cannot_override_exclusion(self):
        self.exclude()
        for decision in ("approve","reject","defer"):
            with self.assertRaisesRegex(ValueError,"owner_excluded"):
                self.store.decide_page(self.page["id"],decision,self.page["identity"],self.image_sha)
        self.assertEqual(self.counts()["review_events"],0)

    def test_vlm_permission_and_import_are_revoked(self):
        self.approve_page();self.exclude()
        with self.assertRaisesRegex(ValueError,"owner_excluded"):self.store.verify_vlm_page(self.page["id"],self.image_sha)
        with self.assertRaisesRegex(ValueError,"owner_excluded"):self.store.import_questions([self.question()],"excluded_batch")
        self.assertEqual(self.counts()["machine_questions"],0)

    def test_all_pending_text_questions_block_without_reviews(self):
        self.install_route("native_text")
        rows=[self.text_question("qt_pending_"+str(i)) for i in range(18)]
        self.store.import_text_questions(rows,"native_pending_batch")
        self.assertEqual(self.store.question_progress()["pending"],18)
        self.exclude();progress=self.store.question_progress()
        self.assertEqual(progress["pending"],0);self.assertEqual(progress["blocked"],18)
        self.assertEqual(self.store.export_approved_questions(),[]);self.assertEqual(self.counts()["review_events"],0)
        self.assertEqual(self.counts()["machine_questions"],18)
        self.assertTrue(self.store.get_question(rows[0]["id"])["export_excluded"])
        with self.assertRaisesRegex(ValueError,"owner_excluded"):
            self.store.verify_text_page(rows[0]["page_id"],rows[0]["text_sha256"],rows[0]["routing_policy_id"])
        with self.assertRaisesRegex(ValueError,"owner_excluded"):self.store.import_text_questions([self.text_question_for_existing(rows[0])],"new_excluded_batch")

    def text_question_for_existing(self,row):return dict(row,id="qt_new_pending")

    def test_old_approved_question_is_no_longer_exported(self):
        self.approve_page();row=self.question();self.store.import_questions([row],"old_batch")
        question=self.store.get_question(row["id"]);self.store.decide_question(row["id"],"approve",question["identity"])
        self.assertEqual(len(self.store.export_approved_questions()),1)
        self.exclude();self.assertEqual(self.store.export_approved_questions(),[])
        self.assertEqual(self.store.get_question(row["id"])["status"],"blocked")
        with self.assertRaisesRegex(ValueError,"stale_dependency"):self.store.decide_question(row["id"],"approve",question["identity"])
        self.assertEqual(self.counts()["review_events"],2)

    def test_partial_ledger_excludes_only_named_page(self):
        other=dict(self.page,id="rp_other",page=2);other["identity"]=page_identity(other)
        (self.root/"pages.jsonl").write_text(json.dumps(self.page)+"\n"+json.dumps(other)+"\n",encoding="utf-8")
        self.exclude(page_ids=[self.page["id"]])
        self.assertEqual(self.store.get_page(self.page["id"])["status"],"excluded")
        self.assertEqual(self.store.get_page(other["id"])["status"],"pending")

    def test_ledger_tamper_fails_closed(self):
        receipt=self.exclude();self.assertEqual(self.store.get_page(self.page["id"])["status"],"excluded")
        Path(receipt["ledger_path"]).write_text('{}\n',encoding="utf-8")
        page=self.store.get_page(self.page["id"])
        self.assertIn("mismatch",page["owner_exclusion_error"]);self.assertEqual(page["status"],"excluded")
        self.assertEqual(self.store.vlm_eligible_pages(),[])

    def test_policy_tamper_fails_closed(self):
        receipt=self.exclude();Path(receipt["policy_path"]).write_text('{}',encoding="utf-8")
        page=self.store.get_page(self.page["id"])
        self.assertIn("mismatch",page["owner_exclusion_error"]);self.assertFalse(page["human_verified"])

    def test_malformed_or_path_traversal_pointer_fails_closed(self):
        self.exclude();pointer=self.root/"owner_exclusion_current.json"
        for value in ([],{"schema":"bkquiz-sft-owner-exclusion-pointer-v1","policy_path":"../outside.json","ledger_path":"other.json"}):
            pointer.write_text(json.dumps(value),encoding="utf-8")
            page=self.store.get_page(self.page["id"])
            self.assertTrue(page["export_excluded"]);self.assertIn("owner_exclusion_error",page)

    def test_catalogue_identity_change_fails_closed(self):
        self.exclude();changed=dict(self.page,bbox=[0.0,0.0,600.0,700.0]);changed["identity"]=page_identity(changed);self.write_page(changed)
        page=self.store.get_page(changed["id"])
        self.assertEqual(page["status"],"excluded");self.assertIn("stale",page["owner_exclusion_error"])

    def test_missing_pointer_after_installation_fails_closed_for_new_store(self):
        self.exclude();(self.root/"owner_exclusion_current.json").unlink()
        store=SFTReviewStore(self.root);page=store.get_page(self.page["id"])
        self.assertEqual(page["status"],"excluded");self.assertIn("missing",page["owner_exclusion_error"])


if __name__=="__main__":unittest.main()
