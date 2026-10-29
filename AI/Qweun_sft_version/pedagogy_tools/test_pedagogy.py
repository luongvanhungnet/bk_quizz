"""CPU fixtures are isolated in TemporaryDirectory; never actual teacher evidence."""
from __future__ import annotations

import copy
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit
import zipfile

from pedagogy_core import *
from prepare_pedagogy import assign_splits, finish_job, quality_reason, retrieve, normalized
from teacher_runtime import run_job, RUNTIME_FILES, export_results, load_packet
from pedagogy_store import PedagogyStore
from package_pedagogy import build_packet, notebook
from export_pedagogy import select_examples, export_approved
from pedagogy_web import PedagogyWeb

THEORY=("A process is a program in execution. Each process has a separate address space. "
        "Threads within one process share its address space but each thread has its own stack and registers. "
        "Mutual exclusion protects critical sections; a lock allows at most one owner at a time. ")*3
PROMPT="Trong cùng một tiến trình, hai luồng cần trao đổi dữ liệu. Tài nguyên nào được chia sẻ theo mô hình bộ nhớ đã nêu?"


def fixture_draft(prompt=PROMPT):
    cite=[{"sourceId":"ctx_fixture","evidenceQuote":"Threads within one process share its address space"}]
    long="Các luồng thuộc cùng tiến trình chia sẻ không gian địa chỉ nhưng có ngăn xếp và thanh ghi riêng. Sự khác biệt này cho phép trao đổi dữ liệu qua vùng nhớ chung và giữ trạng thái thực thi độc lập."
    return {"abstain":False,"question":{"type":"SINGLE_CHOICE","prompt":prompt,"options":[
        {"label":"A","text":"Không gian địa chỉ của tiến trình","correct":True},
        {"label":"B","text":"Ngăn xếp riêng của từng luồng","correct":False},
        {"label":"C","text":"Tập thanh ghi riêng của từng luồng","correct":False},
        {"label":"D","text":"Một không gian địa chỉ tách biệt cho mỗi luồng","correct":False}]},
        "pedagogy":{"concept":{"text":long,"citations":cite},"application":{"text":long,"citations":cite},
        "options":[{"label":chr(65+i),"verdict":"correct" if i==0 else "incorrect","text":long,"citations":cite} for i in range(4)]}}


def fixture_job(task="theory_to_quiz",split="train",draft=None):
    job={"task":task,"split":split,"split_group":"block_fixture","course":"IT3070","context_ids":["ctx_fixture"],"context_groups":["block_fixture"]}
    if task=="theory_to_quiz":job["blueprint"]={"type":"SINGLE_CHOICE"}
    else:
        job["reference_question"]=public_question((draft or fixture_draft())["question"])
        job["expected_correct_labels"]=["A"]
    return finish_job(job,TEACHER)


def fixture_source(split="train"):
    return {"id":"ctx_fixture","text":THEORY,"text_sha256":hashlib.sha256(THEORY.encode()).hexdigest(),"course":"IT3070",
            "title":"CPU TEST FIXTURE","pages":[1],"split":split,"split_group":"block_fixture","source_sha256":"f"*64}


class FakeTeacher:
    """Test double; no GPU, no real model generation."""
    def __init__(self,draft=None):self.draft=draft or fixture_draft();self.calls=[]
    def generate(self,messages,phase,seed):
        self.calls.append((messages,phase))
        if phase=="draft":value=self.draft
        elif phase.startswith("blind"):value={"answerable":True,"correct_labels":["D" if phase=="blind_reversed" else "A"]}
        else:value={key:True for key in ("grounded","unambiguous","all_options_explained","pedagogical")}
        return {"raw":canonical(value).decode(),"phase":phase,"test_fixture":True}


def fixture_workspace(path,job=None):
    source=fixture_source();job=job or fixture_job()
    write_jsonl(path/"contexts.jsonl",[source]);write_jsonl(path/"jobs.jsonl",[job]);write_jsonl(path/"known_exam_questions.jsonl",[])
    atomic_json(path/"pilot_job_ids.json",[job["id"]])
    atomic_json(path/"manifest.json",{"schema":SCHEMA,"teacher":TEACHER,"student":{"base_model":"Qwen/Qwen3-1.7B"},
            "test_fixture":True,"files_sha256":{n:file_sha(path/n) for n in ("contexts.jsonl","jobs.jsonl","known_exam_questions.jsonl")}})
    return PedagogyStore(path)


class ContractTests(unittest.TestCase):
    def setUp(self):self.job=fixture_job();self.source=fixture_source();self.draft=fixture_draft()
    def rejects(self,mutate,job=None):
        mutate(self.draft)
        with self.assertRaises((ValueError,TypeError,KeyError)):validate_draft(job or self.job,self.draft,[self.source])
    def test_valid_pedagogy(self):self.assertEqual(validate_draft(self.job,self.draft,[self.source]),["A"])
    def test_missing_option_reason(self):self.rejects(lambda d:d["pedagogy"]["options"].pop())
    def test_shallow_section(self):self.rejects(lambda d:d["pedagogy"]["concept"].update(text="Theo đáp án nguồn"))
    def test_fabricated_quote(self):self.rejects(lambda d:d["pedagogy"]["application"]["citations"][0].update(evidenceQuote="a quotation absent from the source"))
    def test_duplicate_option(self):self.rejects(lambda d:d["question"]["options"][1].update(text=d["question"]["options"][0]["text"]))
    def test_false_key_conflict(self):
        job=fixture_job("enrich_rationale");job["expected_correct_labels"]=["B"]
        with self.assertRaisesRegex(ValueError,"source_key_conflict"):validate_draft(job,self.draft,[self.source])
    def test_edit_source_question(self):self.rejects(lambda d:d["question"].update(prompt="Giáo viên đã thay câu hỏi ban đầu và đổi yêu cầu?"),fixture_job("enrich_rationale"))
    def test_novel_question_rejects_old_numeric_variant(self):
        self.draft["question"]["prompt"]="Một hệ thống gồm 12 tiến trình thì cần bao nhiêu hàng đợi?"
        with self.assertRaisesRegex(ValueError,"near-duplicate"):validate_draft(self.job,self.draft,[self.source],["Một hệ thống gồm 24 tiến trình thì cần bao nhiêu hàng đợi?"])
    def test_theory_cannot_be_question(self):self.rejects(lambda d:d["question"].update(prompt="A process is a program in execution."))
    def test_reserved_tokens(self):self.rejects(lambda d:d["pedagogy"]["concept"].update(text="<think>"+d["pedagogy"]["concept"]["text"]))
    def test_boolean_not_integer(self):self.rejects(lambda d:d["question"]["options"][0].update(correct=1))
    def test_teacher_prompt_hides_private_key(self):
        job=fixture_job("enrich_rationale");payload=json.loads(draft_messages(job,[self.source])[-1]["content"])
        self.assertNotIn("expected_correct_labels",payload)
        self.assertTrue(all("correct" not in o for o in payload["question"]["options"]))
    def test_theory_task_input_has_no_old_exam(self):
        payload=json.loads(draft_messages(self.job,[self.source])[-1]["content"])
        self.assertNotIn("question",payload);self.assertNotIn("pedagogy",payload)
        student=student_messages(self.job,self.draft,[self.source])
        self.assertNotIn(PROMPT,student["messages"][1]["content"])
    def test_blind_reverse_and_private_fields(self):
        messages,order=blind_messages(self.draft,[self.source],True);question=json.loads(messages[-1]["content"])["question"]
        self.assertEqual(order,[3,2,1,0]);self.assertNotIn("pedagogy",question)
        self.assertNotIn("correct",question["options"][0])
        validate_checks(self.draft,[({"answerable":True,"correct_labels":["A"]},[0,1,2,3]),({"answerable":True,"correct_labels":["D"]},[3,2,1,0])])
    def test_blind_same_order_twice_rejected(self):
        with self.assertRaises(ValueError):validate_checks(self.draft,[({"answerable":True,"correct_labels":["A"]},[0,1,2,3])]*2)
    def test_blind_answer_disagreement(self):
        with self.assertRaisesRegex(ValueError,"blind_answer_disagreement"):validate_checks(self.draft,[({"answerable":True,"correct_labels":["A"]},[0,1,2,3]),({"answerable":True,"correct_labels":["A"]},[3,2,1,0])])
    def test_three_public_explanation_sections(self):
        result=quiz_output(self.draft)["questions"][0]
        self.assertIn("3. Phân tích",result["explanation"]);self.assertEqual(len(result["options"]),4)
    def test_corrupt_theory_rejected(self):self.assertEqual(quality_reason("\ue000"+THEORY),"unsupported_glyphs")
    def test_question_bank_not_theory(self):self.assertEqual(quality_reason("Question 12: Which answer is correct?"),"existing_question_or_answer_bank")
    def test_near_duplicate_block_splits(self):
        contexts=[{"block_id":"a","text":THEORY},{"block_id":"b","text":THEORY+" Additional note."},{"block_id":"a","text":"Other text from same eight page block."}]
        assign_splits(contexts)
        self.assertEqual(len({c["split"] for c in contexts}),1);self.assertEqual(len({c["split_group"] for c in contexts}),1)
    def test_retrieval_never_uses_other_split(self):
        with sqlite3.connect(":memory:") as connection:
            connection.execute("CREATE VIRTUAL TABLE lookup USING fts5(id UNINDEXED,course UNINDEXED,split UNINDEXED,text)")
            connection.execute("INSERT INTO lookup VALUES(?,?,?,?)",("ctx_fixture","IT3070","test",normalized(THEORY)))
            question={"prompt":"process threads memory share address space","options":[]}
            self.assertEqual(retrieve(connection,question,["IT3070"],"train",{"ctx_fixture":self.source})[0],[])


class RuntimeAndStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.store=fixture_workspace(self.root)
        self.job=next(iter(self.store.jobs.values()));self.source=self.store.sources(self.job)[0]
        self.packet=build_packet(self.store,[self.job["id"]],"fixture",RUNTIME_FILES)
        self.packet_manifest=json.loads((self.root/"packets/manifests"/(self.packet["packet_id"]+".json")).read_text())
    def tearDown(self):self.tmp.cleanup()
    def result(self):return run_job(self.job,[self.source],[],FakeTeacher())
    def archive(self,result=None,environment=None):return export_results(self.root,self.packet_manifest,[result or self.result()],environment or {"test_fixture":True})
    def test_packet_load_and_split(self):
        manifest,contexts,jobs,known=load_packet(self.packet["path"]);self.assertEqual(len(jobs),1)
    def test_four_phases_and_unverified_result(self):
        teacher=FakeTeacher();result=run_job(self.job,[self.source],[],teacher)
        self.assertEqual(result["status"],"generated");self.assertEqual(len(teacher.calls),4);self.assertFalse(result["human_verified"])
    def test_cache_integrity_requires_regeneration(self):
        old=self.result();old["draft"]["question"]["prompt"]+=" tampered"
        teacher=FakeTeacher();run_job(self.job,[self.source],[],teacher,old);self.assertEqual(len(teacher.calls),4)
    def test_valid_cache_no_extra_calls(self):
        old=self.result();teacher=FakeTeacher();self.assertEqual(run_job(self.job,[self.source],[],teacher,old),old);self.assertFalse(teacher.calls)
    def test_truncation_is_blocked(self):
        with patch.object(FakeTeacher,"generate",side_effect=ValueError("generation_stopped_for_length")):
            result=self.result();self.assertEqual(result["status"],"blocked")
    def test_import_idempotent_no_approval(self):
        archive=self.archive();self.assertEqual(self.store.import_archive(archive)["imported"],1)
        self.assertEqual(self.store.import_archive(archive)["imported"],0);self.assertEqual(self.store.progress()["approved"],0)
    def test_test_fixture_cannot_enter_production(self):
        self.store.manifest["test_fixture"]=False
        with self.assertRaisesRegex(ValueError,"test fixtures"):self.store.import_archive(self.archive())
    def test_result_tampering_rejected(self):
        result=self.result();result["draft"]["question"]["prompt"]+=" changed"
        with self.assertRaisesRegex(ValueError,"hash changed"):self.store.import_archive(self.archive(result))
    def test_model_cannot_assert_human_approval(self):
        result=self.result();result["human_verified"]=True;result.pop("result_sha256");result["result_sha256"]=digest(result)
        with self.assertRaisesRegex(ValueError,"human/expert approval"):self.store.import_archive(self.archive(result))
    def test_human_review_identity_and_history(self):
        self.store.import_archive(self.archive());row=self.store.rows()[0]
        with self.assertRaises(ValueError):self.store.decide(row["id"],"approve","wrong")
        self.store.decide(row["id"],"approve",row["identity"]);self.assertEqual(self.store.progress()["approved"],1)
        self.store.decide(row["id"],"reject",row["identity"]);self.assertEqual(self.store.progress()["approved"],0)
        with self.store.connect() as c:
            self.assertEqual(c.execute("SELECT count(*) FROM reviews").fetchone()[0],2)
            with self.assertRaises(sqlite3.IntegrityError):c.execute("DELETE FROM reviews")
    def test_blocked_cannot_be_approved(self):
        result=self.result();result.update(status="blocked",error="source_key_conflict");result.pop("result_sha256");result["result_sha256"]=digest(result)
        self.store.import_archive(self.archive(result));row=self.store.rows()[0]
        with self.assertRaisesRegex(ValueError,"Blocked"):self.store.decide(row["id"],"approve",row["identity"])
    def test_human_correction_persists_on_reapproval(self):
        self.store.import_archive(self.archive());row=self.store.rows()[0];draft=copy.deepcopy(row["accepted_draft"])
        draft["pedagogy"]["concept"]["text"]+=" Bổ sung cách diễn đạt rõ ràng cho người học."
        self.store.decide(row["id"],"correct",row["identity"],corrected_draft=draft)
        self.store.decide(row["id"],"approve",row["identity"])
        self.assertEqual(self.store.rows()[0]["accepted_draft"],draft)
    def test_no_approvals_no_training_bundle(self):
        result=export_approved(self.root)
        self.assertIsNone(result["bundle"]);self.assertFalse(result["report"]["main_counts"])
    def test_sft_excludes_unreviewed(self):
        self.store.import_archive(self.archive());self.assertEqual(select_examples(self.store)[0],[])
    def test_unsafe_zip_rejected(self):
        path=self.root/"bad.zip"
        with zipfile.ZipFile(path,"w") as archive:archive.writestr("../escape.txt","evil")
        with self.assertRaises(ValueError):safe_zip(path)
    def test_notebook_cells_are_valid_python(self):
        nb=notebook({"runtime_sha256":"x","pilot_sha256":"y","full_sha256":"z"})
        for cell in nb["cells"]:
            if cell["cell_type"]=="code":compile("".join(cell["source"]),"cell","exec")
    def test_web_download_cannot_traverse_workspace(self):
        class Owner:
            def send(self,*args):return args[1]
        web=PedagogyWeb(Owner(),self.root)
        self.assertEqual(web.get(None,urlsplit("/sft/pedagogy/download?path=../outside.json")),404)


class MixtureTests(unittest.TestCase):
    def test_actual_main_train_ratio_and_auxiliary(self):
        class Store:
            known=[]
            def __init__(self):self.jobs={};self.values=[]
            def sources(self,job):return [fixture_source()]
            def rows(self):return self.values
        store=Store()
        # Deliberately unrelated prompts so novelty filtering cannot mask the cap.
        prompts=["Nguyên lý quản lý bộ nhớ phân trang trong một tiến trình đang thực thi là gì?",
                 "Nếu luồng chia sẻ vùng dữ liệu, cơ chế đồng bộ ảnh hưởng trạng thái thanh ghi ra sao?",
                 "Kỹ sư kiểm thử khóa bảo vệ tài nguyên, lựa chọn nào mô tả miền găng chính xác?",
                 "Từ tình huống ứng dụng phản hồi sự kiện, hãy xác định vai trò của không gian địa chỉ?",
                 "Câu hỏi sửa lời giải về một vấn đề đặc thù của hệ thống phân tán có nội dung nào?",
                 "Bài tập quan sát hàng đợi xử lý yêu cầu đĩa cứng và cấu hình nhập xuất chọn nhận định nào?",
                 "Một mô hình đồ thị phụ thuộc biểu diễn tranh chấp, điều kiện chu trình nào đáng xét?"]
        for index,prompt in enumerate(prompts):
            draft=fixture_draft(prompt);task="theory_to_quiz" if index<4 else "enrich_rationale";job=fixture_job(task,draft=draft);store.jobs[job["id"]]=job
            checks=[({"answerable":True,"correct_labels":["A"]},[0,1,2,3]),({"answerable":True,"correct_labels":["D"]},[3,2,1,0])]
            store.values.append({"id":"candidate_"+str(index),"job_id":job["id"],"split":"train","task":task,"human_verified":True,
                                 "accepted_draft":draft,"latest_review":{"review_id":"fixture"},"teacher_result":{"teacher":TEACHER,"draft":draft,"result_sha256":"fixture","blind_checks":checks}})
            # Theory jobs otherwise share the same blueprint and get the same ID.
            if task=="theory_to_quiz":
                job["id"]="theory_fixture_"+str(index);store.jobs[job["id"]]=job;store.values[-1]["job_id"]=job["id"]
        main,aux,excluded=select_examples(store)
        self.assertFalse(excluded);self.assertEqual(len(main),5);self.assertEqual(len(aux),2)
        self.assertEqual(sum(r["metadata"]["task"]=="theory_to_quiz" for r in main)/len(main),.8)


class RealTokenizerTest(unittest.TestCase):
    def test_current_qwen3_assistant_mask(self):
        from transformers import AutoTokenizer
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"data_preparation"))
        from prepare_sft import encode_example
        root=Path(__file__).resolve().parents[2]/"data_preprocessing/training_releases/cpt_27courses_20261023/tokenizer_pinned"
        tokenizer=AutoTokenizer.from_pretrained(str(root),local_files_only=True)
        row=student_messages(fixture_job(),fixture_draft(),[fixture_source()]);encoded=encode_example(tokenizer,row,"isolated_fixture")
        target=[v for v in encoded["labels"] if v!=-100]
        self.assertEqual(tokenizer.decode(target,skip_special_tokens=False),row["messages"][-1]["content"]+tokenizer.eos_token)
        self.assertEqual(encoded["labels"][0],-100)


if __name__=="__main__":unittest.main()
