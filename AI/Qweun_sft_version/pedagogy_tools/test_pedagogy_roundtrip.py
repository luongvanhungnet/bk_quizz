"""Transport, append-only review and HTTP checks with isolated CPU fixtures."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from urllib.parse import urlsplit
from types import SimpleNamespace
from unittest.mock import patch

from pedagogy_core import canonical,digest,write_jsonl
from pedagogy_store import PedagogyStore
from pedagogy_web import PedagogyWeb
from teacher_runtime import RUNTIME_FILES,run_job,export_results
from package_pedagogy import build_packet
from export_pedagogy import select_examples
from test_pedagogy import fixture_workspace,fixture_source,FakeTeacher
import test_pedagogy as fixtures


class ResultRegressionTests(unittest.TestCase):
    setUp=fixtures.RuntimeAndStoreTests.setUp
    tearDown=fixtures.RuntimeAndStoreTests.tearDown
    result=fixtures.RuntimeAndStoreTests.result
    archive=fixtures.RuntimeAndStoreTests.archive
    def test_superseded_approval_excluded(self):
        self.store.import_archive(self.archive());row=self.store.rows()[0];self.store.decide(row["id"],"approve",row["identity"])
        result=self.result();result["status"]="blocked";result["error"]="new generation is ambiguous"
        result.pop("result_sha256");result["result_sha256"]=digest(result)
        self.store.import_archive(self.archive(result));self.assertEqual(self.store.progress()["approved"],0)
        self.assertEqual(select_examples(self.store)[0],[])
    def test_unknown_packet_rejected(self):
        manifest=dict(self.packet_manifest,packet_id="packet_"+"0"*24)
        archive=export_results(self.root,manifest,[self.result()],{"test_fixture":True})
        with self.assertRaisesRegex(ValueError,"unregistered"):self.store.import_archive(archive)
    def test_different_transport_same_result_is_idempotent(self):
        self.store.import_archive(self.archive())
        archive=self.archive(environment={"test_fixture":True,"different_transport":"yes"})
        self.assertEqual(self.store.import_archive(archive)["imported"],0)
    def test_runtime_pin_mismatch_rejected(self):
        result=self.result();result["runtime_files_sha256"]={};result.pop("result_sha256");result["result_sha256"]=digest(result)
        with self.assertRaisesRegex(ValueError,"runtime differs"):self.store.import_archive(self.archive(result))
    def test_wrong_corrected_key_cannot_enter_sft(self):
        self.store.import_archive(self.archive());row=self.store.rows()[0];draft=copy.deepcopy(row["accepted_draft"])
        draft["question"]["options"][0]["correct"]=False;draft["question"]["options"][1]["correct"]=True
        draft["pedagogy"]["options"][0]["verdict"]="incorrect";draft["pedagogy"]["options"][1]["verdict"]="correct"
        with self.assertRaisesRegex(ValueError,"blind_answer_disagreement"):self.store.decide(row["id"],"correct",row["identity"],corrected_draft=draft)
        self.assertEqual(self.store.progress()["approved"],0)


class WebRoundtripTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.store=fixture_workspace(self.root)
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"review_tools"))
        sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"data_preprocessing/local_review_tools"))
        from sft_review_web import SFTReviewWeb
        from serve import HubHandler
        owner=SFTReviewWeb.__new__(SFTReviewWeb);owner.workspace=self.root;owner.csrf="isolated_csrf";owner.jobs={};owner.job_lock=threading.RLock()
        owner._pedagogy=PedagogyWeb(owner,self.root);self.owner=owner
        class Hub:
            def sft_app(inner):return owner
        self.server=ThreadingHTTPServer(("127.0.0.1",0),HubHandler);self.server.hub=Hub()
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.base=f"http://127.0.0.1:{self.server.server_port}"
        job=next(iter(self.store.jobs.values()));self.packet=build_packet(self.store,[job["id"]],"fixture",RUNTIME_FILES)
        manifest=json.loads((self.root/"packets/manifests"/(self.packet["packet_id"]+".json")).read_text())
        self.archive=export_results(self.root,manifest,[run_job(job,self.store.sources(job),[],FakeTeacher())],{"test_fixture":True})
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.tmp.cleanup()
    def request(self,path,body=None,token=True,origin=None,raw=None):
        headers={"X-CSRF-Token":self.owner.csrf} if token else {}
        if origin:headers["Origin"]=origin
        data=raw if raw is not None else canonical(body) if body is not None else None
        try:
            with urlopen(Request(self.base+path,data=data,headers=headers),timeout=15) as response:return response.status,response.read()
        except HTTPError as error:return error.code,error.read()
    def test_parent_csrf_covers_teacher_decisions(self):
        # Exercise the parent gate directly: Windows may reset a TCP connection
        # when an early 403 deliberately leaves a rejected POST body unread.
        parts=urlsplit("/sft/pedagogy/api/decision")
        with patch.object(self.owner,"send",side_effect=lambda handler,status,*args:status):
            self.assertEqual(self.owner.post(SimpleNamespace(headers={},server=self.server),parts),403)
            headers={"X-CSRF-Token":self.owner.csrf,"Origin":"https://evil.invalid"}
            self.assertEqual(self.owner.post(SimpleNamespace(headers=headers,server=self.server),parts),403)
        self.assertEqual(self.store.progress()["approved"],0)
    def test_html_route_uses_parent_csrf(self):
        status,body=self.request("/sft/pedagogy/")
        self.assertEqual(status,200);self.assertIn(self.owner.csrf,body.decode())
    def test_upload_to_pending_then_manual_approval(self):
        status,body=self.request("/sft/pedagogy/api/import",raw=self.archive.read_bytes());self.assertEqual(status,202)
        job_id=json.loads(body)["job_id"]
        for _ in range(100):
            state=self.owner.jobs[job_id]
            if state["status"]!="running":break
            time.sleep(.02)
        self.assertEqual(state["status"],"complete",state)
        status,body=self.request("/sft/pedagogy/api/candidates")
        row=json.loads(body)["items"][0];self.assertFalse(row["human_verified"])
        status,body=self.request("/sft/pedagogy/api/decision",{"id":row["id"],"decision":"approve","expected_identity":row["identity"]})
        self.assertEqual(status,200);self.assertEqual(self.store.progress()["approved"],1)
    def test_download_matches_frozen_bytes(self):
        status,body=self.request("/sft/pedagogy/download?path=packets/teacher_fixture.zip")
        self.assertEqual(status,200);self.assertEqual(hashlib.sha256(body).hexdigest(),self.packet["sha256"])
    def test_frozen_source_mutation_fails_closed(self):
        write_jsonl(self.root/"contexts.jsonl",[dict(fixture_source(),text="Changed theory")])
        with self.assertRaisesRegex(ValueError,"input changed"):PedagogyStore(self.root)


if __name__=="__main__":unittest.main()
