"""Append-only teacher candidates/reviews, isolated from exam/CPT decisions."""
from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3
import time
import uuid

from pedagogy_core import (SCHEMA,TEACHER,atomic_json,canonical,digest,file_sha,read_jsonl,safe_zip,validate_draft,validate_checks)
from pedagogy_core import validate_result_checks,validate_reviewed_checks


class PedagogyStore:
    def __init__(self,workspace):
        self.workspace=Path(workspace).resolve()
        self.manifest=json.loads((self.workspace/"manifest.json").read_text(encoding="utf-8"))
        if self.manifest.get("schema")!=SCHEMA:raise ValueError("Wrong pedagogy workspace")
        for name,wanted in self.manifest["files_sha256"].items():
            path=(self.workspace/name).resolve()
            if not path.is_relative_to(self.workspace) or file_sha(path)!=wanted:raise ValueError("Frozen teacher input changed")
        self.contexts={r["id"]:r for r in read_jsonl(self.workspace/"contexts.jsonl")}
        self.jobs={r["id"]:r for r in read_jsonl(self.workspace/"jobs.jsonl")}
        self.known=[r["prompt"] for r in read_jsonl(self.workspace/"known_exam_questions.jsonl")]
        self.database=self.workspace/"pedagogy_reviews.sqlite3"
        with self.connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.executescript("""
            CREATE TABLE IF NOT EXISTS candidates(sequence INTEGER PRIMARY KEY AUTOINCREMENT,id TEXT UNIQUE NOT NULL,job_id TEXT NOT NULL,identity TEXT NOT NULL,payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS reviews(sequence INTEGER PRIMARY KEY AUTOINCREMENT,candidate_id TEXT NOT NULL,payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS imports(archive_sha256 TEXT PRIMARY KEY,payload TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS candidate_job ON candidates(job_id,sequence);
            CREATE INDEX IF NOT EXISTS review_candidate ON reviews(candidate_id,sequence);
            """)
            for table in ("candidates","reviews","imports"):
                for operation in ("UPDATE","DELETE"):
                    connection.execute(f"CREATE TRIGGER IF NOT EXISTS {table}_no_{operation.lower()} BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT,'append-only'); END")

    @contextmanager
    def connect(self):
        connection=sqlite3.connect(self.database,timeout=30)
        try:
            with connection:yield connection
        finally:connection.close()

    def sources(self,job):return [self.contexts[cid] for cid in job["context_ids"]]

    def validate_result(self,result,packet):
        if result.get("job_id") not in packet["job_ids"] or result["job_id"] not in self.jobs:raise ValueError("Unknown teacher job")
        job=self.jobs[result["job_id"]]
        if result.get("schema")!=SCHEMA or result.get("teacher")!=TEACHER or result.get("job_sha256")!=job["job_sha256"]:raise ValueError("Teacher/job snapshot mismatch")
        if result.get("human_verified") is not False or result.get("expert_semantically_verified") is not False:raise ValueError("Model result cannot declare human/expert approval")
        body=dict(result);expected=body.pop("result_sha256",None)
        if digest(body)!=expected:raise ValueError("Teacher result hash changed")
        if result.get("runtime_files_sha256")!=packet["runtime_files_sha256"]:raise ValueError("Teacher runtime differs from exported snapshot")
        if result.get("status") not in {"generated","blocked","failed"}:raise ValueError("Invalid teacher result status")
        reasons=[]
        if result["status"]=="generated":
            try:
                validate_draft(job,result["draft"],self.sources(job),self.known)
                validate_result_checks(job,result,packet.get("verification_policy"))
            except (ValueError,KeyError,TypeError) as error:reasons.append(str(error))
        else:reasons.append(result.get("error","teacher did not produce an eligible candidate"))
        return job,reasons

    def import_archive(self,archive):
        archive=Path(archive);members=safe_zip(archive)
        if set(members)!={"run_manifest.json","results.jsonl"}:raise ValueError("Unexpected teacher result archive")
        run=json.loads(members["run_manifest.json"])
        if run.get("schema")!=SCHEMA or run.get("teacher")!=TEACHER:raise ValueError("Wrong teacher result schema/model")
        identity=run.get("packet_id","")
        if not isinstance(identity,str) or not __import__('re').fullmatch(r"packet_[0-9a-f]{24}",identity):raise ValueError("Invalid packet ID")
        registered=self.workspace/"packets/manifests"/(identity+".json")
        if not registered.is_file():raise ValueError("Results from an unregistered input packet")
        packet=json.loads(registered.read_text(encoding="utf-8"))
        if digest(packet)!=run.get("packet_manifest_sha256") or hashlib.sha256(members["results.jsonl"]).hexdigest()!=run.get("results_sha256"):raise ValueError("Teacher archive hash mismatch")
        if run.get("environment",{}).get("test_fixture") is True and self.manifest.get("test_fixture") is not True:raise ValueError("CPU test fixtures cannot enter a production workspace")
        results=[json.loads(line) for line in members["results.jsonl"].decode("utf-8").split("\n") if line.strip()]
        if len(results)!=run.get("jobs") or len({r.get("job_id") for r in results})!=len(results):raise ValueError("Duplicate/incomplete teacher results")
        validated=[(result,*self.validate_result(result,packet)) for result in results]
        archive_sha=file_sha(archive);retained=self.workspace/"returns"/archive_sha;retained.mkdir(parents=True,exist_ok=True)
        from pedagogy_core import atomic_bytes
        atomic_bytes(retained/"original.zip",archive.read_bytes())
        for name,body in members.items():atomic_bytes(retained/name,body)
        count=0;blocked=0
        with self.connect() as connection:
            for result,job,reasons in validated:
                cid="ped_"+digest({"job":job["id"],"result":result["result_sha256"]})[:24]
                payload={"id":cid,"job_id":job["id"],"course":job["course"],"task":job["task"],"split":job["split"],
                         "verification_level":result.get("verification_level","legacy_full_model_audit"),
                         "quality_pass":not reasons,"quality_reasons":reasons,"teacher_result":result,"raw_archive_sha256":archive_sha,
                         "teacher_generated":True,"human_verified":False,"expert_semantically_verified":False}
                payload["identity"]=digest(payload)
                old=connection.execute("SELECT identity FROM candidates WHERE id=?",(cid,)).fetchone()
                if old and old[0]!=payload["identity"]:
                    # Different transport ZIPs may carry an identical model result.
                    previous=json.loads(connection.execute("SELECT payload FROM candidates WHERE id=?",(cid,)).fetchone()[0])
                    if previous["teacher_result"]!=result:raise ValueError("Immutable candidate conflict")
                if not old:
                    connection.execute("INSERT INTO candidates(id,job_id,identity,payload) VALUES(?,?,?,?)",(cid,job["id"],payload["identity"],canonical(payload).decode()));count+=1
                blocked+=bool(reasons)
            connection.execute("INSERT OR IGNORE INTO imports VALUES(?,?)",(archive_sha,canonical(run).decode()))
        receipt={"imported":count,"blocked_in_archive":blocked,"questions_in_archive":len(results),"human_reviews_created":0,"retained_directory":str(retained)}
        atomic_json(retained/"IMPORT_REPORT.json",receipt);return receipt

    def rows(self):
        with self.connect() as c:
            c.execute("BEGIN")
            candidates=[json.loads(r[0]) for r in c.execute("SELECT x.payload FROM candidates x JOIN (SELECT job_id,MAX(sequence) s FROM candidates GROUP BY job_id) latest ON x.sequence=latest.s ORDER BY x.sequence")]
            reviews={r[0]:json.loads(r[1]) for r in c.execute("SELECT x.candidate_id,x.payload FROM reviews x JOIN (SELECT candidate_id,MAX(sequence) s FROM reviews GROUP BY candidate_id) latest ON x.sequence=latest.s")}
        for row in candidates:
            review=reviews.get(row["id"]);row["latest_review"]=review
            row["status"]=review["decision"] if review else "ready" if row["quality_pass"] else "blocked"
            row["human_verified"]=bool(review and review["decision"] in {"approve","correct"})
            row["accepted_draft"]=review.get("accepted_draft",review.get("corrected_draft")) if review and review["decision"] in {"approve","correct"} else row["teacher_result"].get("draft")
        return candidates

    def get(self,identity):
        row=next((r for r in self.rows() if r["id"]==identity),None)
        if row is None:raise ValueError("Candidate is missing or superseded")
        job=self.jobs[row["job_id"]];return dict(row,job=job,sources=self.sources(job))

    def list(self,status="pending",course="",task="",offset=0,limit=1):
        rows=self.rows()
        if status=="pending":rows=[r for r in rows if r["status"] in {"ready","defer"}]
        elif status!="all":rows=[r for r in rows if r["status"]==status]
        rows=[r for r in rows if (not course or r["course"]==course) and (not task or r["task"]==task)]
        return {"total":len(rows),"items":[self.get(r["id"]) for r in rows[offset:offset+limit]]}

    def progress(self):
        rows=self.rows();counts=Counter(r["status"] for r in rows)
        return {"jobs_prepared":len(self.jobs),"theory_jobs":sum(j["task"]=="theory_to_quiz" for j in self.jobs.values()),
                "rationale_jobs":sum(j["task"]=="enrich_rationale" for j in self.jobs.values()),"courses":sorted({j["course"] for j in self.jobs.values()}),
                "candidates":len(rows),"counts":dict(counts),"ready_for_review":counts["ready"]+counts["defer"],
                "approved":counts["approve"]+counts["correct"],"blocked":counts["blocked"],"rejected":counts["reject"]}

    def decide(self,identity,decision,expected_identity,note="",corrected_draft=None):
        if decision not in {"approve","correct","reject","defer"}:raise ValueError("Unknown review decision")
        row=self.get(identity)
        if row["identity"]!=expected_identity:raise ValueError("Candidate identity changed")
        if decision in {"approve","correct"}:
            if not row["quality_pass"]:raise ValueError("Blocked teacher outputs must be regenerated before approval")
            draft=corrected_draft if decision=="correct" else row["accepted_draft"]
            validate_draft(row["job"],draft,row["sources"],self.known)
            validate_reviewed_checks(row["job"],row["teacher_result"],draft)
        event={"candidate_id":identity,"identity":row["identity"],"review_id":str(uuid.uuid4()),"created_ns":time.time_ns(),
               "decision":decision,"note":str(note),"human_verified":decision in {"approve","correct"},"reviewer":"local_user"}
        if decision=="correct":event["corrected_draft"]=corrected_draft
        if decision in {"approve","correct"}:event["accepted_draft"]=draft
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            latest=c.execute("SELECT id FROM candidates WHERE job_id=? ORDER BY sequence DESC LIMIT 1",(row["job_id"],)).fetchone()
            if latest[0]!=identity:raise ValueError("Candidate superseded during review")
            c.execute("INSERT INTO reviews(candidate_id,payload) VALUES(?,?)",(identity,canonical(event).decode()))
        return event
