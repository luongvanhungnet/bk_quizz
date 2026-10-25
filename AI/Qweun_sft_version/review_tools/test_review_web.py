from __future__ import annotations

from contextlib import closing
from http.server import ThreadingHTTPServer
import http.client
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request,urlopen

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"data_preprocessing/local_review_tools"))
from serve import HubHandler
from sft_review_store import file_sha256,page_identity
from sft_review_web import SFTReviewWeb


class FakeRenderer:
    def __init__(self,path):self.path=path
    def ensure_image(self,page):return {"path":str(self.path),"sha256":file_sha256(self.path),"width":1,"height":1}


class ReviewWebTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        source=self.root/"source.pdf";source.write_bytes(b"isolated fixture, not a production exam")
        (self.root/"manifest.json").write_text(json.dumps({"schema":"bkquiz-sft-review-v1"}),encoding="utf-8")
        self.page={"id":"rp_webfixture","source_id":"exam_webfixture","source_sha256":file_sha256(source),
                   "source_path":str(source),"relative_path":"isolated-test.pdf","course":"TEST ONLY","page":1,
                   "bbox":[0.,0.,600.,800.],"tile_index":0,"tile_count":1,"reasons":["ocr_required"],
                   "question_ids":[],"native_text_preview":"fixture"}
        self.page["identity"]=page_identity(self.page)
        (self.root/"pages.jsonl").write_text(json.dumps(self.page)+"\n",encoding="utf-8")
        assets=self.root/"assets";assets.mkdir();self.asset=assets/(self.page["id"]+".png")
        self.asset.write_bytes(b"isolated rendered-image fixture")
        self.app=SFTReviewWeb(self.root);self.app.renderer=FakeRenderer(self.asset)
        class Hub:
            def __init__(self,app):self.app=app
            def sft_app(self):return self.app
        self.server=ThreadingHTTPServer(("127.0.0.1",0),HubHandler);self.server.hub=Hub(self.app)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.base=f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.temp.cleanup()

    def request(self,path,payload=None,token=True,origin=None,raw=None):
        headers={}
        if token:headers["X-CSRF-Token"]=self.app.csrf
        if origin:headers["Origin"]=origin
        data=raw if raw is not None else json.dumps(payload).encode() if payload is not None else None
        request=Request(self.base+path,data=data,headers=headers)
        try:
            with urlopen(request,timeout=10) as response:return response.status,response.read(),dict(response.headers)
        except HTTPError as error:return error.code,error.read(),dict(error.headers)

    def decision(self):
        return {"id":self.page["id"],"decision":"approve","expected_identity":self.page["identity"],"image_sha256":file_sha256(self.asset)}

    def events(self):
        with closing(sqlite3.connect(self.app.store.database)) as connection:
            return connection.execute("SELECT COUNT(*) FROM review_events").fetchone()[0]

    def automatic_text(self):
        text=self.root/"source.txt"
        text.write_text("Question 1: Which source fact is printed here?\nA. First option\nB. Second option\nANSWER: A\n",encoding="utf-8")
        analysis=self.root/"analysis.json"
        analysis.write_text(json.dumps({"page_id":self.page["id"],"identity":self.page["identity"]}),encoding="utf-8")
        policy=self.root/"policy.json"
        policy.write_text(json.dumps({"schema":"bkquiz-sft-auto-routing-policy-v1","policy_id":"fixture_policy",
                                      "automatic_stage1_authorized":True,"authorization":"isolated test"}),encoding="utf-8")
        route={"page_id":self.page["id"],"identity":self.page["identity"],"policy_id":"fixture_policy",
               "route":"native_text","automatic":True,"human_verified":False,
               "analysis_path":"analysis.json","analysis_sha256":file_sha256(analysis),
               "text_path":"source.txt","text_sha256":file_sha256(text)}
        routing=self.root/"routing.jsonl";routing.write_text(json.dumps(route)+"\n",encoding="utf-8")
        (self.root/"auto_routing_current.json").write_text(json.dumps({"schema":"bkquiz-sft-auto-routing-pointer-v1",
            "policy_path":"policy.json","policy_sha256":file_sha256(policy),"routing_path":"routing.jsonl",
            "routing_sha256":file_sha256(routing)}),encoding="utf-8")
        return text

    def test_automatic_text_preview_has_checked_provenance_and_no_review_event(self):
        text=self.automatic_text()
        status,data,_=self.request("/sft/api/text?id="+self.page["id"])
        self.assertEqual(status,200);self.assertEqual(json.loads(data)["text"],text.read_text(encoding="utf-8"))
        self.assertFalse(json.loads(data)["human_verified"]);self.assertEqual(self.events(),0)
        text.write_text("tampered source",encoding="utf-8")
        self.assertEqual(self.request("/sft/api/text?id="+self.page["id"])[0],400)
        self.assertEqual(self.app.store.page_progress()["manual_pending"],1)

    def test_text_extraction_endpoint_creates_pending_questions_only(self):
        self.automatic_text()
        status,data,_=self.request("/sft/api/extract-text",{})
        self.assertEqual(status,202);job_id=json.loads(data)["job_id"]
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            with self.app.job_lock:job=dict(self.app.jobs[job_id])
            if job["status"]!="running":break
            time.sleep(.02)
        self.assertEqual(job["status"],"complete",job)
        self.assertEqual(job["result"]["new_questions_imported"],1)
        self.assertEqual(self.app.store.question_progress()["pending"],1)
        self.assertEqual(self.events(),0)

    def test_ocr_progress_cannot_read_outside_workspace(self):
        (self.root/"auto_triage_progress.json").write_text(json.dumps({"progress_path":"../outside.json","status":"running"}),encoding="utf-8")
        status,data,_=self.request("/sft/api/progress")
        self.assertEqual(status,200);self.assertNotIn("triage",json.loads(data))

    def test_review_page_and_catalogue_get_create_no_human_event(self):
        status,data,_=self.request("/sft/?stage=1")
        self.assertEqual(status,200);self.assertIn("Duyệt hai đợt",data.decode())
        status,data,_=self.request("/sft/api/catalog")
        self.assertEqual(json.loads(data)["courses"],["TEST ONLY"])
        status,data,_=self.request("/sft/api/page?id="+self.page["id"])
        self.assertEqual(json.loads(data)["identity"],self.page["identity"])
        self.assertEqual(self.events(),0)

    def test_csrf_and_cross_origin_save_are_rejected(self):
        self.assertEqual(self.request("/sft/api/page-decision",self.decision(),token=False)[0],403)
        self.assertEqual(self.request("/sft/api/page-decision",self.decision(),origin="https://outside.invalid")[0],403)
        self.assertEqual(self.events(),0)

    def test_host_gate_and_download_traversal(self):
        connection=http.client.HTTPConnection("127.0.0.1",self.server.server_port,timeout=10)
        connection.request("GET","/sft/",headers={"Host":"outside.invalid"})
        response=connection.getresponse();self.assertEqual(response.status,403);response.read();connection.close()
        self.assertEqual(self.request("/sft/download?path=../../private.json")[0],404)

    def test_image_is_bound_to_current_page_identity(self):
        status,_,headers=self.request("/sft/api/image?id="+self.page["id"]+"&identity="+self.page["identity"])
        self.assertEqual(status,200);self.assertEqual(headers["X-Image-SHA256"],file_sha256(self.asset))
        self.assertEqual(self.request("/sft/api/image?id="+self.page["id"]+"&identity=old")[0],409)

    def test_round1_does_not_approve_round2_and_export_only_round2_approved(self):
        self.assertEqual(self.request("/sft/api/page-decision",self.decision())[0],200)
        row={"id":"qv_webfixture","page_id":self.page["id"],"image_sha256":file_sha256(self.asset),
             "result_sha256":"1"*64,"question":{"prompt":"Question printed in isolated test?","options":[{"text":"first"},{"text":"second"}],"answer":{"text":"first"},"solution":"","flags":[]}}
        self.app.store.import_questions([row],"batch_webfixture")
        question=self.app.store.get_question(row["id"])
        self.assertEqual(question["status"],"pending")
        status,data,_=self.request("/sft/api/export-questions",{})
        self.assertEqual(json.loads(data)["questions"],0)
        save={"id":question["id"],"decision":"reject","expected_identity":question["identity"]}
        self.assertEqual(self.request("/sft/api/question-decision",save)[0],200)
        self.assertEqual(self.app.store.question_progress()["rejected"],1)
        self.assertEqual(self.events(),2)

    def test_bad_uploaded_zip_is_retained_as_failed_job_without_machine_approval(self):
        status,data,_=self.request("/sft/api/import",raw=b"not a zip")
        self.assertEqual(status,202);job_id=json.loads(data)["job_id"]
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            with self.app.job_lock:job=dict(self.app.jobs[job_id])
            if job["status"]!="running":break
            time.sleep(.02)
        self.assertEqual(job["status"],"failed")
        self.assertEqual(self.app.store.question_progress()["total"],0)
        self.assertEqual(self.events(),0)

    def test_distinct_upload_jobs_are_not_silently_dropped(self):
        release=threading.Event();started=[]
        def operation(label):
            started.append(label);release.wait(3);return {"label":label}
        one=self.app.start_job("import",lambda:operation("one"),dedupe_key="first.zip")
        same=self.app.start_job("import",lambda:operation("duplicate"),dedupe_key="first.zip")
        two=self.app.start_job("import",lambda:operation("two"),dedupe_key="second.zip")
        self.assertEqual(one,same);self.assertNotEqual(one,two)
        release.set()
        deadline=time.monotonic()+3
        while time.monotonic()<deadline and any(self.app.jobs[j]["status"]=="running" for j in [one,two]):time.sleep(.02)
        self.assertEqual(sorted(started),["one","two"])


if __name__=="__main__":unittest.main()
