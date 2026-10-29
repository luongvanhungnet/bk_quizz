"""Isolated CPU tests; not a GPU throughput benchmark."""
import ast
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from contextlib import nullcontext

from pedagogy_core import FAST_POLICY,TEACHER,audit_reasons,canonical,digest,validate_result_checks
from prepare_pedagogy import finish_job
from package_pedagogy import build_packet
from package_fast_pedagogy import fast_notebook
from teacher_fast_runtime import RUNTIME_FILES,run_session,BatchTeacher,cache_key,valid_state,seal,fast_draft_messages
from teacher_runtime import export_results
from export_pedagogy import select_examples
from test_pedagogy import fixture_job,fixture_source,fixture_draft,fixture_workspace,FakeTeacher


def job_for(draft=None,sample=False):
    draft=draft or fixture_draft()
    for nonce in range(1000):
        body=fixture_job();body={k:v for k,v in body.items() if k not in {"id","job_sha256","teacher","schema","human_verified","expert_semantically_verified"}}
        body["blueprint"]["nonce"]=nonce
        job=finish_job(body,TEACHER)
        if ("random_sample" in audit_reasons(job,draft))==sample:return job
    raise AssertionError("No fixture hash found")


class Clock:
    def __init__(self):self.now=0
    def __call__(self):return self.now


class FakeBatch:
    def __init__(self,draft=None,clock=None):
        self.batch_size=2;self.environment={"test_fixture":True};self.teacher=FakeTeacher(draft);self.calls=[];self.clock=clock
    def generate_many(self,requests,deadline):
        self.calls.append([r["phase"] for r in requests])
        if self.clock:self.clock.now+=10
        return [self.teacher.generate(r["messages"],r["phase"],r["seed"]) for r in requests]


class FastTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.source=fixture_source();self.draft=fixture_draft()
    def tearDown(self):self.temp.cleanup()
    def execute(self,job,teacher=None,deadline=100,clock=None):
        store=fixture_workspace(self.root,job)
        packet=build_packet(store,[job["id"]],"fast_fixture",RUNTIME_FILES,FAST_POLICY)
        manifest=json.loads((self.root/"packets/manifests"/(packet["packet_id"]+".json")).read_text())
        teacher=teacher or FakeBatch();clock=clock or Clock()
        report=run_session(manifest,store.contexts,[job],[],teacher,self.root/"run",deadline,clock=clock)
        return store,manifest,report,teacher
    def test_low_risk_only_draft_and_cpu_checks(self):
        store,manifest,report,teacher=self.execute(job_for())
        self.assertEqual(teacher.calls,[["draft"]]);self.assertEqual(report["completed"],1)
        store.import_archive(report["result_zip"]);row=store.rows()[0]
        self.assertFalse(row["human_verified"]);self.assertTrue(row["quality_pass"])
        self.assertEqual(row["teacher_result"]["verification_level"],"cpu_only_pending_human")
    def test_fast_prompt_reinforces_schema_without_revealing_key(self):
        messages=fast_draft_messages(fixture_job('enrich_rationale'),[self.source])
        self.assertIn('ĐÚNG MỘT',messages[0]['content'])
        self.assertIn('Không dịch quote',messages[0]['content'])
        user=json.loads(messages[-1]['content'])
        self.assertNotIn('expected_correct_labels',user)
        self.assertTrue(all('correct' not in option for option in user['question']['options']))
    def test_cpu_checked_still_needs_human_approval(self):
        store,manifest,report,teacher=self.execute(job_for())
        store.import_archive(report["result_zip"]);self.assertEqual(select_examples(store)[0],[])
        row=store.rows()[0];store.decide(row["id"],"approve",row["identity"])
        main,aux,excluded=select_examples(store)
        self.assertEqual(len(main),1);self.assertEqual(main[0]["metadata"]["verification_level"],"cpu_only_pending_human")
    def test_random_sample_runs_full_audit(self):
        store,manifest,report,teacher=self.execute(job_for(sample=True))
        self.assertEqual(teacher.calls,[["draft"],["blind_original"],["blind_reversed"],["critic"]])
        store.import_archive(report["result_zip"]);self.assertTrue(store.rows()[0]["quality_pass"])
    def test_risky_numeric_question_runs_full_audit(self):
        draft=fixture_draft("Khi 2 luồng cùng thuộc một tiến trình, tài nguyên nào được chia sẻ trong vùng nhớ?")
        job=job_for(draft=draft);teacher=FakeBatch(draft)
        store,manifest,report,_=self.execute(job,teacher)
        self.assertEqual(len(teacher.calls),4);store.import_archive(report["result_zip"])
        self.assertIn("numeric_reasoning",store.rows()[0]["teacher_result"]["audit_reasons"])
    def test_risk_rules(self):
        job=job_for();draft=fixture_draft();draft["question"]["type"]="MULTIPLE_SELECT"
        self.assertIn("multiple_select",audit_reasons(job,draft))
        job["exam_course"]="Điện tử CNTT";self.assertIn("related_curriculum",audit_reasons(job,draft))
        job["task"]="enrich_rationale";job["retrieval_coverage"]=.1;self.assertIn("weak_retrieval",audit_reasons(job,draft))
    def test_sampling_stable(self):
        job=job_for(sample=True)
        self.assertEqual(audit_reasons(job,self.draft),audit_reasons(copy.deepcopy(job),copy.deepcopy(self.draft)))
        self.assertIn("random_sample",audit_reasons(job,self.draft))
    def test_hard_cpu_failure_never_bypassed(self):
        draft=fixture_draft();draft["pedagogy"]["concept"]["citations"][0]["evidenceQuote"]="a fabricated statement missing from the theory"
        store,manifest,report,teacher=self.execute(job_for(),FakeBatch(draft))
        self.assertEqual(len(teacher.calls),1);store.import_archive(report["result_zip"])
        self.assertFalse(store.rows()[0]["quality_pass"])
    def test_finished_cache_avoids_new_model_calls(self):
        job=job_for();store,manifest,report,teacher=self.execute(job)
        other=FakeBatch();run_session(manifest,store.contexts,[job],[],other,self.root/"run",100,clock=Clock())
        self.assertFalse(other.calls)
    def test_deadline_keeps_audit_draft_and_resumes_without_redraft(self):
        job=job_for(sample=True);clock=Clock();teacher=FakeBatch(clock=clock)
        store,manifest,report,_=self.execute(job,teacher,deadline=5,clock=clock)
        self.assertEqual(report["stop_reason"],"time_budget");self.assertEqual(report["completed"],0)
        saved=json.loads((self.root/"run/cache"/(job["id"]+".json")).read_text())
        self.assertEqual(saved["status"],"pending_audit")
        resumed=FakeBatch();report=run_session(manifest,store.contexts,[job],[],resumed,self.root/"run",100,clock=Clock())
        self.assertEqual(resumed.calls,[["blind_original"],["blind_reversed"],["critic"]]);self.assertEqual(report["completed"],1)
    def test_expired_budget_starts_no_generation(self):
        store,manifest,report,teacher=self.execute(job_for(),deadline=0)
        self.assertFalse(teacher.calls);self.assertEqual(report["completed"],0)
    def test_policy_spoof_cannot_skip_required_audit(self):
        store,manifest,report,teacher=self.execute(job_for(sample=True))
        value=json.loads((self.root/"run/cache"/(next(iter(store.jobs))+".json")).read_text())
        value.update(audit_reasons=[],blind_checks=[],verification_level="cpu_only_pending_human");value.pop("critic",None);seal(value)
        archive=export_results(self.root,manifest,[value],{"test_fixture":True});store.import_archive(archive)
        self.assertFalse(store.rows()[0]["quality_pass"])
    def test_unregistered_fast_policy_on_strict_packet_blocked(self):
        job=job_for();store,manifest,report,teacher=self.execute(job)
        value=json.loads((self.root/"run/cache"/(job["id"]+".json")).read_text())
        with self.assertRaisesRegex(ValueError,"does not authorize"):validate_result_checks(job,value)
    def test_tampered_cache_not_reused(self):
        job=job_for();store,manifest,report,teacher=self.execute(job)
        path=self.root/"run/cache"/(job["id"]+".json");value=json.loads(path.read_text());value["draft"]["question"]["prompt"]+=" tampered";path.write_bytes(canonical(value))
        resumed=FakeBatch();run_session(manifest,store.contexts,[job],[],resumed,self.root/"run",100,clock=Clock())
        self.assertEqual(resumed.calls,[["draft"]])
    def test_real_batch_scheduling(self):
        job=job_for();job2=copy.deepcopy(job);job2["id"]+="other";job2["job_sha256"]="a"*64
        # Distinct test IDs only; no production packet loader is bypassed.
        teacher=FakeBatch();contexts={self.source["id"]:self.source};manifest={"packet_id":"fixture","verification_policy":FAST_POLICY}
        run_session(manifest,contexts,[job,job2],[],teacher,self.root/"run",100,clock=Clock())
        self.assertEqual(teacher.calls[0],["draft","draft"])
    def test_batch_oom_splits_and_reduces_future_size(self):
        class OOM(Exception):pass
        class Cuda:
            @staticmethod
            def empty_cache():pass
        class Torch:OutOfMemoryError=OOM;cuda=Cuda()
        backend=BatchTeacher.__new__(BatchTeacher);backend.torch=Torch();backend.batch_size=2
        def batch(requests,deadline):
            if len(requests)>1:raise OOM()
            return [requests[0]]
        backend._batch=batch
        self.assertEqual(backend.generate_many(["a","b"],float("inf")),["a","b"]);self.assertEqual(backend.batch_size,1)
    def test_fast_notebook_has_watchdog_and_valid_child_commands(self):
        nb=fast_notebook({"runtime_sha256":"x","pilot_sha256":"y","full_sha256":"z"})
        joined="\n".join("".join(c["source"]) for c in nb["cells"])
        self.assertIn("SESSION_MINUTES=55",joined);self.assertIn("timeout=remaining()",joined)
        self.assertNotIn("torch==2.6.0",joined)
        for cell in nb["cells"]:
            if cell["cell_type"]!="code":continue
            tree=ast.parse("".join(cell["source"]))
            for node in ast.walk(tree):
                if isinstance(node,ast.List):
                    for i,entry in enumerate(node.elts[:-1]):
                        if isinstance(entry,ast.Constant) and entry.value=="-c":
                            child=node.elts[i+1]
                            if isinstance(child,ast.Constant):compile(child.value,"child-command","exec")

    def test_batched_decoding_separates_rows_and_removes_eos_padding(self):
        class Vector(list):
            def tolist(self):return list(self)
        class Matrix:
            def __init__(self,values):self.values=values;self.shape=(len(values),len(values[0]))
            def __getitem__(self,index):
                row,columns=index;return Vector(self.values[row][columns])
        class Inputs(dict):
            def to(self,device):return self
        class Tokenizer:
            pad_token_id=0;eos_token_id=99
            def apply_chat_template(self,messages,**kwargs):return messages[0]["content"]
            def __call__(self,text,**kwargs):
                if isinstance(text,str):return {"input_ids":list(range(len(text)))}
                width=max(map(len,text));self.inputs=text
                return Inputs(input_ids=Matrix([[0]*(width-len(t))+[1]*len(t) for t in text]))
            def decode(self,tokens,**kwargs):return ','.join(map(str,(t for t in tokens if t!=99)))
        class Model:
            device="test_only";generation_config=SimpleNamespace(eos_token_id=[99,100])
            def generate(self,**kwargs):
                width=kwargs["input_ids"].shape[1]
                return Matrix([[8]*width+[41,99,0,0],[9]*width+[42,43,100,0]])
        backend=BatchTeacher.__new__(BatchTeacher);backend.tokenizer=Tokenizer();backend.model=Model()
        backend.torch=SimpleNamespace(manual_seed=lambda seed:None,cuda=SimpleNamespace(manual_seed_all=lambda seed:None),inference_mode=nullcontext)
        module=SimpleNamespace(StoppingCriteria=object,StoppingCriteriaList=list)
        requests=[{"phase":"draft","seed":i,"messages":[{"role":"user","content":text}]} for i,text in enumerate(["x","longer"])]
        with patch.dict('sys.modules',{'transformers':module}):results=backend._batch(requests,float('inf'))
        self.assertEqual([r['output_tokens'] for r in results],[2,3])
        self.assertEqual(results[0]['raw'],'41');self.assertEqual(results[1]['raw'],'42,43,100')
        self.assertEqual([r['input_tokens'] for r in results],[1,6])


if __name__=="__main__":unittest.main()
