"""Bounded batch generation with CPU gates and deterministic risk/sample audit.

No CUDA fallback to CPU, no automatic human approval, no truncated candidate export.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import time

from pedagogy_core import (SCHEMA,TEACHER,FAST_POLICY,atomic_json,canonical,digest,file_sha,make_zip,
                           draft_messages,blind_messages,parse_json_response,validate_draft,
                           validate_result_checks,audit_reasons)
from teacher_runtime import HFTeacher,critic_messages,load_packet,export_results

RUNTIME_FILES={name:file_sha(Path(__file__).with_name(name)) for name in
               ("pedagogy_core.py","teacher_runtime.py","teacher_fast_runtime.py")}


def fast_draft_messages(job,sources):
    messages=draft_messages(job,sources)
    messages[0]["content"]+="""
Quy tắc JSON bắt buộc: type chỉ là SINGLE_CHOICE hoặc MULTIPLE_SELECT.
Nhãn options.label lần lượt A, B, C, D (rồi E... nếu đề gốc có thêm); không dùng a, A., số hoặc bỏ nhãn.
correct là boolean true/false. SINGLE_CHOICE có ĐÚNG MỘT lựa chọn correct:true.
MULTIPLE_SELECT có ít nhất HAI lựa chọn đúng và ít nhất MỘT lựa chọn sai.
Câu mới có đúng4 lựa chọn. Câu bổ sung lời giải giữ nguyên tất cả lựa chọn đề gốc.
pedagogy.options dùng đúng cùng nhãn và verdict khớp correct của từng lựa chọn.
evidenceQuote phải copy20–600 ký tự LIÊN TIẾP từ text nguồn, giữ nguyên ngôn ngữ, dấu câu,
chữ hoa/thường và xuống dòng. Không dịch quote sang tiếng Việt, không sửa lỗi chữ của nguồn,
không thêm dấu ba chấm để nối hai đoạn. Phần giải thích ngoài quote viết tiếng Việt.
Nếu không thể trích đúng nguyên văn hoặc xác định đáp án, dùng abstain:true thay vì đoán.
"""
    return messages


class BatchTeacher(HFTeacher):
    def __init__(self,batch_size=2):
        print('Loading pinned Qwen7B on CUDA...',flush=True)
        super().__init__();self.batch_size=batch_size;self.tokenizer.padding_side="left"
        if self.tokenizer.pad_token_id is None:self.tokenizer.pad_token=self.tokenizer.eos_token
        print(json.dumps(self.environment),flush=True)

    def generate_many(self,requests,deadline):
        if not requests:return []
        if time.monotonic()>=deadline:return [None]*len(requests)
        try:return self._batch(requests,deadline)
        except self.torch.OutOfMemoryError:
            pass
        # Outside the exception handler: release the failed frame/tensor refs.
        self.torch.cuda.empty_cache()
        if len(requests)==1:return [RuntimeError("CUDA OutOfMemory on a single request")]
        self.batch_size=max(1,len(requests)//2)
        print('CUDA OOM: reducing batch to',self.batch_size,flush=True)
        mid=len(requests)//2
        return self.generate_many(requests[:mid],deadline)+self.generate_many(requests[mid:],deadline)

    def _batch(self,requests,deadline):
        from transformers import StoppingCriteria,StoppingCriteriaList
        torch=self.torch;tokenizer=self.tokenizer
        class DeadlineStop(StoppingCriteria):
            last_log=time.monotonic()
            def __call__(self,input_ids,scores,**kwargs):
                now=time.monotonic()
                if now-self.last_log>=30:
                    print(json.dumps({"event":"generating","phase":phase,"batch_size":len(requests),"generated_steps":input_ids.shape[1]-width,"remaining_seconds":round(max(0,deadline-now))}),flush=True)
                    self.last_log=now
                return now>=deadline
        phase=requests[0]["phase"]
        if any(r["phase"]!=phase for r in requests):raise ValueError("Batch phases must match")
        texts=[tokenizer.apply_chat_template(r["messages"],tokenize=False,add_generation_prompt=True) for r in requests]
        lengths=[len(tokenizer(t,add_special_tokens=False)["input_ids"]) for t in texts]
        maximum=TEACHER["max_new_tokens"] if phase=="draft" else 256 if phase.startswith("blind") else 512
        eligible=[i for i,n in enumerate(lengths) if n<=TEACHER["max_input_tokens"] and n+maximum<=TEACHER["max_total_tokens"]]
        responses=[ValueError("Token budget exceeded; no truncation") for _ in requests]
        if not eligible:return responses
        inputs=tokenizer([texts[i] for i in eligible],padding=True,truncation=False,add_special_tokens=False,return_tensors="pt").to(self.model.device)
        width=inputs["input_ids"].shape[1];seed=int(digest([requests[i]["seed"] for i in eligible])[:8],16)%2147483647
        torch.manual_seed(seed);torch.cuda.manual_seed_all(seed)
        params={"max_new_tokens":maximum,"do_sample":phase=="draft","pad_token_id":tokenizer.pad_token_id,
                "stopping_criteria":StoppingCriteriaList([DeadlineStop()]),"use_cache":True}
        if phase=="draft":params.update(temperature=.6,top_p=.9)
        started=time.monotonic()
        with torch.inference_mode():outputs=self.model.generate(**inputs,**params)
        elapsed=time.monotonic()-started;eos=self.model.generation_config.eos_token_id
        eos=set(eos if isinstance(eos,list) else [eos if eos is not None else tokenizer.eos_token_id])
        for row,index in enumerate(eligible):
            tokens=outputs[row,width:].tolist();end=next((i for i,t in enumerate(tokens) if t in eos),None)
            if end is None:
                responses[index]=None if time.monotonic()>=deadline else ValueError("generation_stopped_for_length; not exported")
                continue
            tokens=tokens[:end+1]
            responses[index]={"raw":tokenizer.decode(tokens,skip_special_tokens=True),"input_tokens":lengths[index],
                              "output_tokens":len(tokens),"batch_seconds":round(elapsed,3),"batch_size":len(eligible),
                              "phase":phase,"batch_seed":seed,"input_sha256":digest(requests[index]["messages"]),"ended_with_eos":True}
        return responses


def request(messages,phase,job):
    return {"messages":messages,"phase":phase,"seed":int(job["job_sha256"][:8],16)%2147483647}


def cache_key(job,sources):
    return digest({"job":job["job_sha256"],"sources":[s["text_sha256"] for s in sources],"runtime":RUNTIME_FILES,"policy":FAST_POLICY})


def valid_state(value,key):
    if not isinstance(value,dict) or value.get("cache_key")!=key:return False
    body=dict(value);expected=body.pop("result_sha256",None)
    return digest(body)==expected and value.get("runtime_files_sha256")==RUNTIME_FILES and value.get("verification_policy")==FAST_POLICY


def seal(value):
    value.pop("result_sha256",None);value["result_sha256"]=digest(value);return value


def fresh(job,sources):
    return {"schema":SCHEMA,"teacher":TEACHER,"job_id":job["id"],"job_sha256":job["job_sha256"],
            "cache_key":cache_key(job,sources),"runtime_files_sha256":RUNTIME_FILES,"verification_policy":FAST_POLICY,
            "human_verified":False,"expert_semantically_verified":False,"status":"pending_audit","phases":[],"blind_checks":[]}


def checkpoint(out,manifest,results,environment):
    import hashlib
    body=b"".join(canonical(r)+b"\n" for r in results)
    run={"schema":SCHEMA,"teacher":TEACHER,"packet_id":manifest["packet_id"],"packet_manifest_sha256":digest(manifest),
         "results_sha256":hashlib.sha256(body).hexdigest(),"jobs":len(results),"environment":environment,"human_reviews_created":0}
    target=Path(out)/"pedagogy_checkpoint.zip"
    make_zip(target,{"run_manifest.json":canonical(run)+b"\n","results.jsonl":body});return target


def run_session(manifest,contexts,jobs,known,teacher,out,deadline,clock=time.monotonic,retry_failed=False):
    """Save each job; interrupted drafts/audits remain resumable but unexported."""
    if manifest.get("verification_policy")!=FAST_POLICY:raise ValueError("Fast packet policy required")
    out=Path(out);out.mkdir(parents=True,exist_ok=True);cache=out/"cache";cache.mkdir(exist_ok=True)
    states={};todo=[];started=clock();new_done=0
    def sources(job):return [contexts[c] for c in job["context_ids"]]
    def path(job):return cache/(job["id"]+".json")
    def save(job,state):
        states[job["id"]]=seal(state);atomic_json(path(job),state)
    def results():return [states[j["id"]] for j in jobs if j["id"] in states and states[j["id"]]["status"] in {"generated","blocked","failed"}]
    def finish(job,state,error=None):
        nonlocal new_done
        if error is not None:
            state.update(status="blocked" if isinstance(error,(ValueError,KeyError,TypeError)) else "failed",error=type(error).__name__+": "+str(error))
        else:
            validate_result_checks(job,state,FAST_POLICY);state["status"]="generated"
        save(job,state);new_done+=1
        print(json.dumps({"event":"job_saved","job_id":job["id"],"status":state["status"],"verification_level":state.get("verification_level"),"completed":len(results()),"total":len(jobs)}),flush=True)
    for job in jobs:
        try:old=json.loads(path(job).read_text(encoding="utf-8"))
        except (OSError,ValueError):old=None
        if valid_state(old,cache_key(job,sources(job))):
            if old["status"] in {"generated","blocked"} or (old["status"]=="failed" and not retry_failed):
                states[job["id"]]=old;continue
            if old["status"]=="pending_audit":states[job["id"]]=old
        todo.append(job)
    # Similar input lengths reduce padding cost. This does not change split IDs.
    todo.sort(key=lambda j:(0 if j["id"] in states else 1,sum(len(s["text"]) for s in sources(j)),j["id"]))
    remaining=list(todo);stop="complete"
    while remaining:
        if clock()>=deadline:stop="time_budget";break
        count=max(1,teacher.batch_size);batch=remaining[:count];remaining=remaining[count:]
        new=[j for j in batch if j["id"] not in states]
        if new:
            print(json.dumps({"event":"phase_start","phase":"draft","jobs":[j["id"] for j in new],"remaining_seconds":round(max(0,deadline-clock()))}),flush=True)
            try:responses=teacher.generate_many([request(fast_draft_messages(j,sources(j)),"draft",j) for j in new],deadline)
            except Exception as error:responses=[error]*len(new)
            if len(responses)!=len(new):raise ValueError("Batch response cardinality mismatch")
            for job,response in zip(new,responses):
                if response is None:continue
                state=fresh(job,sources(job))
                try:
                    if isinstance(response,Exception):raise response
                    state["phases"].append(response);state["draft"]=parse_json_response(response["raw"])
                    validate_draft(job,state["draft"],sources(job),known)
                    state["audit_reasons"]=audit_reasons(job,state["draft"])
                    state["verification_level"]="model_audited_pending_human" if state["audit_reasons"] else "cpu_only_pending_human"
                    save(job,state)
                    if not state["audit_reasons"]:finish(job,state)
                except Exception as error:finish(job,state,error)
        audits=[j for j in batch if j["id"] in states and states[j["id"]]["status"]=="pending_audit"]
        for phase in ("blind_original","blind_reversed","critic"):
            pending=[j for j in audits if not any(p["phase"]==phase for p in states[j["id"]]["phases"]) and states[j["id"]]["status"]=="pending_audit"]
            if not pending:continue
            if clock()>=deadline:stop="time_budget";break
            requests=[];orders={}
            for job in pending:
                state=states[job["id"]]
                validate_draft(job,state["draft"],sources(job),known)
                if phase=="critic":messages=critic_messages(state["draft"],sources(job))
                else:
                    messages,orders[job["id"]]=blind_messages(state["draft"],sources(job),phase=="blind_reversed")
                requests.append(request(messages,phase,job))
            print(json.dumps({"event":"phase_start","phase":phase,"batch_size":len(pending)}),flush=True)
            try:responses=teacher.generate_many(requests,deadline)
            except Exception as error:responses=[error]*len(pending)
            if len(responses)!=len(pending):raise ValueError("Batch response cardinality mismatch")
            for job,response in zip(pending,responses):
                if response is None:continue
                state=states[job["id"]]
                try:
                    if isinstance(response,Exception):raise response
                    state["phases"].append(response);value=parse_json_response(response["raw"])
                    if phase=="critic":state["critic"]=value;finish(job,state)
                    else:state["blind_checks"].append([value,orders[job["id"]]]);save(job,state)
                except Exception as error:finish(job,state,error)
            # A reversed/critic stage must never run when the previous stage was
            # interrupted for one member of the batch.
            audits=[j for j in audits if any(p["phase"]==phase for p in states[j["id"]]["phases"])]
        current=results();checkpoint(out,manifest,current,teacher.environment)
        elapsed=max(.001,clock()-started)
        atomic_json(out/"progress.json",{"completed":len(current),"total":len(jobs),"new_completed":new_done,
                    "counts_by_status":dict(Counter(r["status"] for r in current)),
                    "elapsed_seconds":round(elapsed,2),"remaining_seconds":round(max(0,deadline-clock()),2),
                    "estimated_remaining_seconds":(len(jobs)-len(current))*elapsed/new_done if new_done else None,
                    "pending_audit_cached":sum(s["status"]=="pending_audit" for s in states.values()),"human_reviews_created":0})
        if any(r["status"]=="failed" and ("CUDA" in r.get("error","") or "OutOfMemory" in r.get("error","")) for r in current):stop="gpu_failure";break
    current=results()
    if stop=="complete" and len(current)<len(jobs):stop="time_budget" if clock()>=deadline else "interrupted_generation"
    archive=export_results(out,manifest,current,teacher.environment)
    summary={"stop_reason":stop,"completed":len(current),"counts_by_status":dict(Counter(r["status"] for r in current)),
             "total":len(jobs),"pending":len(jobs)-len(current),"result_zip":str(archive),"human_reviews_created":0}
    atomic_json(out/"SESSION_REPORT.json",summary);print("RESULT_ZIP",archive,flush=True);print(json.dumps(summary),flush=True)
    return summary


def main():
    start=time.monotonic();p=argparse.ArgumentParser();p.add_argument("--input",type=Path,required=True);p.add_argument("--out",type=Path,required=True)
    p.add_argument("--batch-size",type=int,default=2);p.add_argument("--minutes",type=float,default=50);p.add_argument("--max-jobs",type=int);p.add_argument("--retry-failed",action="store_true")
    args=p.parse_args()
    if not 1<=args.batch_size<=8 or not 0<args.minutes<=55:raise ValueError("Batch must be1..8, runtime budget0..55 minutes")
    manifest,contexts,jobs,known=load_packet(args.input,RUNTIME_FILES)
    if args.max_jobs is not None:
        if args.max_jobs<1:raise ValueError("max-jobs must be positive")
        jobs=jobs[:args.max_jobs]
    teacher=BatchTeacher(args.batch_size);args.out.mkdir(parents=True,exist_ok=True);atomic_json(args.out/"environment.json",teacher.environment)
    run_session(manifest,contexts,jobs,known,teacher,args.out,start+args.minutes*60-20,retry_failed=args.retry_failed)


if __name__=="__main__":main()
