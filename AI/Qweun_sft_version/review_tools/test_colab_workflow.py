from __future__ import annotations

import copy
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from colab_workflow import export_approved, import_results, prepare_colab_assets
from colab_runtime.runtime import atomic_bytes, parse_response, run_batch, verified_zip, validate_input
from sft_review_store import SFTReviewStore, page_identity, file_sha256


class FakeObserver:
    def __init__(self, failure=False):
        self.calls=0;self.failure=failure;self.telemetry={"possibly_truncated":False};self.versions={"engine":"CPU test double"}
    def infer(self,path):
        self.calls+=1
        if self.failure:raise ValueError("fixture unreadable")
        return json.dumps({"page_text":"Câu 1\u2028AB", "questions":[{"source_number":"1", "prompt":"Which label is visibly printed?", "options":[
            {"label":"A","text":"Printed label","source_marking":""},{"label":"B","text":"Other label","source_marking":""}],
            "answer":{"labels":[],"text":"","evidence":"","origin":"missing"},"solution":"","flags":["missing_answer"]}],"flags":[]},ensure_ascii=False)


class ColabWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.source=self.root/"original.pdf";self.source.write_bytes(b"source fixture")
        (self.root/"assets").mkdir()
        (self.root/"manifest.json").write_text('{"schema":"bkquiz-sft-review-v1"}',encoding="utf8")
        self.pages=[]
        for i in range(2):
            row={"id":"rp_fixture"+str(i),"source_id":"exam_fixture","source_sha256":file_sha256(self.source),"source_path":str(self.source),
                 "relative_path":"original.pdf","course":"OS","page":i+1,"bbox":[0.,0.,600.,800.],"tile_index":0,"tile_count":1,
                 "reasons":["ocr_required"],"question_ids":[],"native_text_preview":"A\u2028B"}
            row["identity"]=page_identity(row);self.pages.append(row)
            (self.root/"assets"/(row["id"]+".png")).write_bytes(b"PNG fixture "+str(i).encode())
        with (self.root/"pages.jsonl").open("w",encoding="utf8",newline="\n") as out:
            for row in self.pages:out.write(json.dumps(row,ensure_ascii=False)+"\n")
        self.store=SFTReviewStore(self.root)

    def tearDown(self):self.temp.cleanup()
    def approve(self,index=0):
        row=self.pages[index];self.store.decide_page(row["id"],"approve",row["identity"],file_sha256(self.root/"assets"/(row["id"]+".png")))
    def event_count(self):
        with closing(sqlite3.connect(self.store.database)) as c:return c.execute("select count(*) from review_events").fetchone()[0]
    def exported(self):
        self.approve();return export_approved(self.root)["batches"][0]["archive"]
    def result(self,observer=None):return run_batch(self.exported(),self.root/"cpu_results",observer or FakeObserver())["archive"]

    def route_automatically(self,index=0,route="auto_vlm"):
        folder=self.root/"auto";folder.mkdir(exist_ok=True)
        page=self.pages[index]
        evidence=folder/(page["id"]+".json")
        evidence.write_text(json.dumps({"page_id":page["id"],"identity":page["identity"]}),encoding="utf8")
        policy=folder/"policy.json"
        policy.write_text(json.dumps({"schema":"bkquiz-sft-auto-routing-policy-v1","policy_id":"test-automatic-policy",
            "automatic_stage1_authorized":True,"authorization":"User requested automatic OCR routing"}),encoding="utf8")
        row={"page_id":page["id"],"identity":page["identity"],"route":route,"policy_id":"test-automatic-policy",
             "automatic":True,"human_verified":False,"analysis_path":"auto/"+evidence.name,"analysis_sha256":file_sha256(evidence)}
        if route in {"native_text","ocr_text"}:
            text=folder/"text.txt";text.write_text("This page already has complete text.",encoding="utf8")
            row.update(text_path="auto/text.txt",text_sha256=file_sha256(text))
        routing=folder/"routing.jsonl";routing.write_text(json.dumps(row)+"\n",encoding="utf8")
        pointer={"schema":"bkquiz-sft-auto-routing-pointer-v1","policy_path":"auto/policy.json","policy_sha256":file_sha256(policy),
                 "routing_path":"auto/routing.jsonl","routing_sha256":file_sha256(routing)}
        (self.root/"auto_routing_current.json").write_text(json.dumps(pointer),encoding="utf8")
        image=self.root/"assets"/(page["id"]+".png")
        image.with_suffix(".json").write_text(json.dumps({"identity":page["identity"],"source_sha256":page["source_sha256"],
                                                       "sha256":file_sha256(image)}),encoding="utf8")
        return row

    def test_empty_selection_prepares_notebook_but_exports_no_images(self):
        report=export_approved(self.root)
        self.assertEqual(report["status"],"awaiting_stage1");self.assertEqual(report["batches"],[])
        self.assertEqual(self.event_count(),0)
        notebook=json.loads(Path(report["colab_assets"]["notebook"]).read_text(encoding="utf8"))
        source="\n".join("".join(cell["source"]) for cell in notebook["cells"])
        self.assertIn("assert list(INPUTS.glob",source)
        for cell in notebook["cells"]:
            if cell["cell_type"]=="code":compile("".join(cell["source"]),"notebook","exec")

    def test_only_current_approved_images_exported_and_repeated_export_identical(self):
        archive=self.exported();first=Path(archive).read_bytes()
        report=export_approved(self.root)
        self.assertEqual(report["approved_images"],1);self.assertEqual(Path(report["batches"][0]["archive"]).read_bytes(),first)
        members=verified_zip(archive);m=json.loads(members["manifest.json"])
        self.assertEqual([j["page_id"] for j in m["jobs"]],[self.pages[0]["id"]])
        self.assertEqual(self.event_count(),1)

    def test_reject_defer_and_unreviewed_images_never_export(self):
        self.store.decide_page(self.pages[0]["id"],"reject",self.pages[0]["identity"])
        self.store.decide_page(self.pages[1]["id"],"defer",self.pages[1]["identity"])
        self.assertEqual(export_approved(self.root)["approved_images"],0)

    def test_automatic_vlm_export_and_roundtrip_keep_separate_provenance_and_pending_review(self):
        self.route_automatically()
        with patch("review_render.ReviewRenderer.ensure_image") as renderer:
            exported=export_approved(self.root)
        renderer.assert_called_once()
        self.assertEqual(exported["human_approved_images"],0)
        self.assertEqual(exported["automatically_routed_images"],1)
        manifest,_=validate_input(exported["batches"][0]["archive"])
        job=manifest["jobs"][0]
        self.assertEqual(job["stage1_decision"],"auto_vlm")
        self.assertFalse(job["human_verified"])
        archive=run_batch(exported["batches"][0]["archive"],self.root/"cpu_results",FakeObserver())["archive"]
        report=import_results(self.root,archive)
        self.assertEqual(report["imported_questions"],1)
        question=self.store.list_questions()["items"][0]
        self.assertEqual(question["status"],"pending")
        self.assertEqual(question["routing_policy_id"],job["routing_policy_id"])
        self.assertEqual(self.event_count(),0)

    def test_native_text_route_does_not_enter_vlm_export(self):
        self.route_automatically(route="native_text")
        self.assertEqual(export_approved(self.root)["approved_images"],0)
        self.assertEqual(self.event_count(),0)

    def test_automatic_result_is_blocked_after_human_reject(self):
        self.route_automatically()
        with patch("review_render.ReviewRenderer.ensure_image"):
            exported=export_approved(self.root)
        archive=run_batch(exported["batches"][0]["archive"],self.root/"cpu_results",FakeObserver())["archive"]
        page=self.pages[0];self.store.decide_page(page["id"],"reject",page["identity"])
        with self.assertRaisesRegex(ValueError,"no longer"):
            import_results(self.root,archive)
        self.assertEqual(self.store.list_questions()["total"],0)
        self.assertEqual(self.event_count(),1)

    def test_automatic_input_requires_matching_policy_snapshot(self):
        self.route_automatically()
        with patch("review_render.ReviewRenderer.ensure_image"):
            exported=export_approved(self.root)
        archive=exported["batches"][0]["archive"]
        members=verified_zip(archive);manifest=json.loads(members["manifest.json"])
        manifest["automatic_stage1_policies"]={}
        target=self.root/"bad-automatic.zip"
        with zipfile.ZipFile(target,"w") as output:
            for name,body in members.items():
                output.writestr(name,json.dumps(manifest).encode() if name=="manifest.json" else body)
        with self.assertRaisesRegex(ValueError,"policy provenance"):
            validate_input(target)

    def test_batch_limit_is_enforced(self):
        self.approve(0);self.approve(1)
        report=export_approved(self.root,max_images=1)
        self.assertEqual(len(report["batches"]),2)
        self.assertTrue(all(batch["images"]==1 for batch in report["batches"]))

    def test_fake_vlm_roundtrip_creates_pending_questions_without_human_approval(self):
        report=import_results(self.root,self.result())
        self.assertEqual(report["imported_questions"],1);self.assertEqual(report["human_decisions_created"],0)
        q=self.store.list_questions()["items"][0]
        self.assertEqual(q["status"],"pending");self.assertEqual(q["question"]["answer"]["origin"],"missing")
        self.assertEqual(self.store.export_approved_questions(),[]);self.assertEqual(self.event_count(),1)
        again=import_results(self.root,report["retained_directory"]+"/original_result.zip")
        self.assertEqual(again["store_receipt"]["imported"],0)
        self.assertEqual(again["imported_questions"],0);self.assertEqual(again["questions_in_archive"],1)

    def test_export_streams_assets_without_read_bytes_or_all_image_buffer(self):
        self.approve(0);self.approve(1)
        real_read_bytes=Path.read_bytes
        def no_asset_read_bytes(path):
            if path.parent==self.root/"assets":raise AssertionError("eager image read is forbidden")
            return real_read_bytes(path)
        with patch.object(Path,"read_bytes",no_asset_read_bytes):
            report=export_approved(self.root,max_images=1)
        self.assertEqual(len(report["batches"]),2)
        self.assertTrue(all(batch["images"]==1 for batch in report["batches"]))

    def test_concurrent_prepare_and_distinct_imports_are_atomic(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            prepared=list(pool.map(lambda _:prepare_colab_assets(self.root),range(8)))
        self.assertEqual(len({entry["runtime_sha256"] for entry in prepared}),1)
        self.approve(0);self.approve(1)
        batches=export_approved(self.root,max_images=1)["batches"]
        returns=[run_batch(batch["archive"],self.root/"cpu_results",FakeObserver())["archive"] for batch in batches]
        with ThreadPoolExecutor(max_workers=2) as pool:
            reports=list(pool.map(lambda archive:import_results(self.root,archive),returns))
        self.assertEqual(sum(report["imported_questions"] for report in reports),2)
        self.assertEqual(self.store.list_questions(status="pending")["total"],2)
        latest=json.loads((self.root/"colab/LATEST_IMPORT.json").read_text(encoding="utf8"))
        self.assertIn(latest["archive_sha256"],{report["archive_sha256"] for report in reports})
        self.assertEqual(self.event_count(),2)

    def test_atomic_write_retries_sharing_denial_without_truncating_target(self):
        target=self.root/"shared_metadata.json";target.write_bytes(b"original")
        original_replace=Path.replace;attempts=[]
        def sharing_denied_then_replace(source,destination):
            attempts.append(1)
            if len(attempts)<=2:
                self.assertEqual(target.read_bytes(),b"original")
                raise PermissionError("fixture Windows sharing denial")
            return original_replace(source,destination)
        with patch.object(Path,"replace",sharing_denied_then_replace):
            atomic_bytes(target,b"replacement")
        self.assertEqual(len(attempts),3);self.assertEqual(target.read_bytes(),b"replacement")
        self.assertEqual(list(self.root.glob("shared_metadata.json.*.partial")),[])

    def test_cached_result_can_be_rebatched_without_resetting_existing_review(self):
        first_result=self.result();first=import_results(self.root,first_result)
        question=self.store.list_questions()["items"][0]
        self.store.decide_question(question["id"],"approve",question["identity"])
        observer=FakeObserver();self.approve(1)
        rebatch=export_approved(self.root,max_images=2)["batches"][0]["archive"]
        new_result=run_batch(rebatch,self.root/"cpu_results",observer)
        report=import_results(self.root,new_result["archive"])
        self.assertEqual(observer.calls,1);self.assertEqual(report["questions_in_archive"],2)
        self.assertEqual(report["imported_questions"],1)
        self.assertEqual(self.store.get_question(question["id"])["status"],"approve")
        self.assertEqual(self.store.get_question(question["id"])["identity"],question["identity"])
        self.assertEqual(self.store.list_questions(status="pending")["total"],1)

    def test_cache_resume_does_not_call_model_again(self):
        observer=FakeObserver();archive=self.exported()
        a=run_batch(archive,self.root/"cpu_results",observer)
        b=run_batch(archive,self.root/"cpu_results",observer)
        self.assertEqual(observer.calls,1);self.assertEqual(a["archive"],b["archive"])

    def test_vlm_failure_retained_and_not_imported_as_question(self):
        report=import_results(self.root,self.result(FakeObserver(True)))
        self.assertEqual(report["imported_questions"],0);self.assertEqual(len(report["failed_pages"]),1)
        self.assertEqual(self.store.list_questions()["total"],0);self.assertEqual(self.event_count(),1)

    def test_revoked_stage1_approval_blocks_old_result_import(self):
        archive=self.result();row=self.pages[0]
        self.store.decide_page(row["id"],"reject",row["identity"])
        with self.assertRaisesRegex(ValueError,"no longer"):
            import_results(self.root,archive)
        self.assertEqual(self.store.list_questions()["total"],0)

    def test_unknown_export_input_is_rejected(self):
        archive=self.result()
        registry=self.root/"colab/exports/manifests"
        for p in registry.glob("*.json"):p.unlink()
        with self.assertRaisesRegex(ValueError,"known approved export"):
            import_results(self.root,archive)

    def test_zip_traversal_duplicate_members_and_size_budgets_rejected(self):
        for members in [[("../escape.txt",b"x")],[("same",b"a"),("same",b"b")]]:
            archive=self.root/("bad"+str(len(members))+".zip")
            with zipfile.ZipFile(archive,"w") as z:
                for n,b in members:z.writestr(n,b)
            with self.assertRaises(ValueError):verified_zip(archive)
        archive=self.root/"large.zip"
        with zipfile.ZipFile(archive,"w",zipfile.ZIP_DEFLATED) as z:z.writestr("payload",b"x"*10000)
        with self.assertRaisesRegex(ValueError,"budget"):
            verified_zip(archive,max_bytes=1000)

    def test_answer_invention_and_malformed_output_not_silently_accepted(self):
        raw=json.loads(FakeObserver().infer("unused"))
        raw["questions"][0]["answer"]["labels"]=["A"]
        with self.assertRaisesRegex(ValueError,"Missing answer"):
            parse_response(json.dumps(raw))
        with self.assertRaises(json.JSONDecodeError):parse_response("not JSON")

    def test_missing_option_text_and_nonstring_flags_are_rejected_as_parse_errors(self):
        for change in ["missing_text","page_flag","question_flag"]:
            raw=json.loads(FakeObserver().infer("unused"))
            if change=="missing_text":raw["questions"][0]["options"][0].pop("text")
            if change=="page_flag":raw["flags"]=[42]
            if change=="question_flag":raw["questions"][0]["flags"]=[{}]
            with self.assertRaises(ValueError):parse_response(json.dumps(raw))

    def test_archive_member_tamper_detected_before_import(self):
        archive=self.result();target=self.root/"tampered.zip"
        with zipfile.ZipFile(archive) as source,zipfile.ZipFile(target,"w") as dest:
            for name in source.namelist():dest.writestr(name,source.read(name)+b" " if name.startswith("results/") else source.read(name))
        with self.assertRaisesRegex(ValueError,"hash mismatch"):
            import_results(self.root,target)
        self.assertEqual(self.store.list_questions()["total"],0)


if __name__=="__main__":unittest.main()
