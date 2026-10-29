"""Versioned owner export exclusions; separate from human review events.

No source PDF, question payload or review database is modified by this module.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import threading
import time
import uuid

POLICY_SCHEMA="bkquiz-sft-owner-exclusion-policy-v1"
POINTER_SCHEMA="bkquiz-sft-owner-exclusion-pointer-v1"
HASH_RE=re.compile(r"^[0-9a-f]{64}$")


def canonical(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode("utf-8")
def sha(path):
    with Path(path).open("rb") as stream:return hashlib.file_digest(stream,"sha256").hexdigest()


def _stamp(path):
    info=Path(path).stat();return info.st_size,info.st_mtime_ns,info.st_ctime_ns


def _inside(workspace,value):
    if not isinstance(value,str) or not value or Path(value).is_absolute() or "\\" in value or ":" in value:raise ValueError("Owner exclusion path must be relative")
    target=(workspace/value).resolve()
    if not target.is_relative_to(workspace):raise ValueError("Owner exclusion path escapes workspace")
    return target


def _write(path,body,immutable=False):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    if path.is_file() and path.read_bytes()==body:return
    temporary=path.with_name(path.name+"."+uuid.uuid4().hex+".partial")
    try:
        temporary.write_bytes(body)
        if immutable:
            try:os.link(temporary,path)
            except FileExistsError:
                if path.read_bytes()!=body:raise ValueError("Immutable owner exclusion artifact differs")
        else:
            for attempt in range(6):
                try:os.replace(temporary,path);break
                except PermissionError:
                    if attempt==5:raise
                    time.sleep(.05*(attempt+1))
    finally:temporary.unlink(missing_ok=True)


def install_owner_exclusion(workspace,page_ids=None,authorization="",note=""):
    """Install an explicitly authorized, content-addressed exclusion snapshot.

    page_ids=None means every current review item, including tiles. An explicit
    empty list creates a new authorized empty policy; removal is not implicit.
    """
    workspace=Path(workspace).resolve()
    if not isinstance(authorization,str) or not authorization.strip():raise ValueError("Explicit owner authorization is required")
    if not isinstance(note,str) or len(note)>20000:raise ValueError("Invalid owner exclusion note")
    catalogue=workspace/"pages.jsonl";manifest_path=workspace/"manifest.json"
    body=catalogue.read_bytes();catalog_sha=hashlib.sha256(body).hexdigest();manifest_sha=sha(manifest_path)
    manifest=json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    if manifest.get("schema")!="bkquiz-sft-review-v1":raise ValueError("Wrong review workspace")
    pages={}
    for line in body.decode("utf-8-sig").split("\n"):
        if not line.strip():continue
        page=json.loads(line);identity=page.get("id")
        if not isinstance(identity,str) or identity in pages:raise ValueError("Invalid/duplicate page catalogue ID")
        if not HASH_RE.fullmatch(page.get("identity","")) or not HASH_RE.fullmatch(page.get("source_sha256","")):raise ValueError("Invalid catalogue source identity")
        pages[identity]=page
    selected=sorted(pages) if page_ids is None else list(page_ids)
    if len(set(selected))!=len(selected) or any(p not in pages for p in selected):raise ValueError("Unknown/duplicate owner-excluded page ID")
    records=[]
    for identity in sorted(selected):
        page=pages[identity]
        records.append({"page_id":identity,"identity":page["identity"],"source_id":page["source_id"],"page":page["page"],
                        "source_sha256":page["source_sha256"],"export_excluded":True,"human_verified":False,
                        "reason":"owner_excluded_pending_model_or_manual_processing"})
    ledger=b"".join(canonical(r)+b"\n" for r in records);ledger_sha=hashlib.sha256(ledger).hexdigest()
    policy={"schema":POLICY_SCHEMA,"authorization":authorization.strip(),"note":note,"authorization_origin":"explicit_user_instruction",
            "catalogue_sha256":catalog_sha,"workspace_manifest_sha256":manifest_sha,"ledger_sha256":ledger_sha,
            "excluded_items":len(records),"excluded_source_pages":len({(r["source_id"],r["page"]) for r in records}),
            "precedence":"owner_export_exclusion_overrides_prior_processing_permissions","human_review_events_created":0,
            "source_files_modified":False,"review_database_modified":False}
    policy["policy_id"]="owner_exclude_"+hashlib.sha256(canonical(policy)).hexdigest()[:24]
    folder=workspace/"owner_exclusions"/policy["policy_id"]
    policy_path=folder/"policy.json";ledger_path=folder/"excluded_pages.jsonl"
    _write(ledger_path,ledger,immutable=True);_write(policy_path,canonical(policy)+b"\n",immutable=True)
    pointer={"schema":POINTER_SCHEMA,"policy_id":policy["policy_id"],"policy_path":policy_path.relative_to(workspace).as_posix(),
             "policy_sha256":sha(policy_path),"ledger_path":ledger_path.relative_to(workspace).as_posix(),"ledger_sha256":ledger_sha}
    pointer_path=workspace/"owner_exclusion_current.json";pointer_body=canonical(pointer)+b"\n"
    already=pointer_path.is_file() and pointer_path.read_bytes()==pointer_body
    if pointer_path.is_file() and not already:
        previous=pointer_path.read_bytes();key=hashlib.sha256(previous).hexdigest()
        _write(workspace/"owner_exclusions/pointer_history"/(key+".json"),previous,immutable=True)
    if sha(catalogue)!=catalog_sha or sha(manifest_path)!=manifest_sha:raise ValueError("Review catalogue changed while installing owner exclusion")
    _write(pointer_path,pointer_body)
    return {"policy_id":policy["policy_id"],"policy_path":str(policy_path),"policy_sha256":sha(policy_path),
            "ledger_path":str(ledger_path),"ledger_sha256":ledger_sha,"pointer_path":str(pointer_path),"pointer_sha256":sha(pointer_path),
            "catalogue_sha256":catalog_sha,"excluded_items":len(records),"excluded_source_pages":policy["excluded_source_pages"],
            "human_review_events_created":0,"source_files_modified":False,"review_database_modified":False,"already_current":already}


class OwnerExclusionPolicy:
    """Read-only validated snapshots with stat-keyed caching and fail-closed errors."""
    def __init__(self,workspace):
        self.workspace=Path(workspace).resolve();self.lock=threading.RLock();self.stamp=None;self.records={};self.metadata={};self.error=None;self.seen=False

    def load(self):
        workspace=self.workspace;pointer_path=workspace/"owner_exclusion_current.json"
        with self.lock:
            try:
                if not pointer_path.is_file():
                    if self.seen or any((workspace/"owner_exclusions").glob("owner_exclude_*/policy.json")):
                        raise ValueError("Owner exclusion pointer missing after installation")
                    return {},{"active":False},None
                self.seen=True
                start=(_stamp(pointer_path),_stamp(workspace/"pages.jsonl"),_stamp(workspace/"manifest.json"))
                if self.stamp and start==self.stamp[:3]:
                    paths=(Path(self.metadata["policy_path"]),Path(self.metadata["ledger_path"]))
                    if start+tuple(_stamp(p) for p in paths)==self.stamp:return self.records,self.metadata,None
                pointer=json.loads(pointer_path.read_text(encoding="utf-8-sig"))
                if not isinstance(pointer,dict) or pointer.get("schema")!=POINTER_SCHEMA:raise ValueError("Unsupported owner exclusion pointer")
                policy_path=_inside(workspace,pointer["policy_path"]);ledger_path=_inside(workspace,pointer["ledger_path"])
                stamp=start+(_stamp(policy_path),_stamp(ledger_path))
                for path,key in ((policy_path,"policy_sha256"),(ledger_path,"ledger_sha256")):
                    if not HASH_RE.fullmatch(pointer.get(key,"")) or sha(path)!=pointer[key]:raise ValueError("Owner exclusion "+key+" mismatch")
                policy=json.loads(policy_path.read_text(encoding="utf-8-sig"))
                if (not isinstance(policy,dict) or policy.get("schema")!=POLICY_SCHEMA or not policy.get("authorization") or policy.get("authorization_origin")!="explicit_user_instruction"
                    or policy.get("policy_id")!=pointer.get("policy_id") or policy.get("human_review_events_created")!=0
                    or policy.get("ledger_sha256")!=pointer.get("ledger_sha256")):
                    raise ValueError("Invalid owner exclusion policy authorization/identity")
                value=dict(policy);wanted=value.pop("policy_id")
                if wanted!="owner_exclude_"+hashlib.sha256(canonical(value)).hexdigest()[:24]:raise ValueError("Owner exclusion policy ID changed")
                if sha(workspace/"pages.jsonl")!=policy.get("catalogue_sha256") or sha(workspace/"manifest.json")!=policy.get("workspace_manifest_sha256"):
                    raise ValueError("Owner exclusion catalogue snapshot is stale")
                pages={}
                with (workspace/"pages.jsonl").open(encoding="utf-8-sig") as stream:
                    for line in stream:
                        if line.strip():
                            page=json.loads(line);pages[page["id"]]=page
                records={}
                with ledger_path.open(encoding="utf-8-sig") as stream:
                    for line in stream:
                        if not line.strip():continue
                        row=json.loads(line)
                        if not isinstance(row,dict):raise ValueError("Excluded page ledger row is not an object")
                        identity=row.get("page_id");page=pages.get(identity)
                        if page is None or identity in records:raise ValueError("Unknown/duplicate excluded page")
                        if any(row.get(key)!=page.get(key) for key in ("identity","source_id","page","source_sha256")):
                            raise ValueError("Excluded page identity/source snapshot changed")
                        if row.get("export_excluded") is not True or row.get("human_verified") is not False:raise ValueError("Owner exclusion cannot impersonate review")
                        records[identity]=row
                if len(records)!=policy.get("excluded_items") or len({(r["source_id"],r["page"]) for r in records.values()})!=policy.get("excluded_source_pages"):
                    raise ValueError("Owner exclusion ledger count changed")
                metadata={"active":True,"policy_id":policy["policy_id"],"policy_path":str(policy_path),"policy_sha256":pointer["policy_sha256"],
                          "ledger_path":str(ledger_path),"ledger_sha256":pointer["ledger_sha256"],"pointer_sha256":sha(pointer_path),
                          "catalogue_sha256":policy["catalogue_sha256"],"excluded_items":len(records),"excluded_source_pages":policy["excluded_source_pages"],
                          "authorization":policy["authorization"],"note":policy.get("note","")}
                # Refuse a mixed snapshot if any file changed during validation.
                if stamp!=(_stamp(pointer_path),_stamp(workspace/"pages.jsonl"),_stamp(workspace/"manifest.json"),_stamp(policy_path),_stamp(ledger_path)):
                    raise ValueError("Owner exclusion changed while reading")
                self.records,self.metadata,self.stamp,self.error=records,metadata,stamp,None
                return records,metadata,None
            except (OSError,ValueError,KeyError,TypeError) as error:
                self.stamp=None;self.records={};self.metadata={"active":True};self.error=str(error)
                return {},self.metadata,self.error

    def lookup(self,page,snapshot=None):
        records,metadata,error=self.load() if snapshot is None else snapshot
        if error:return None,metadata,error
        record=records.get(page["id"])
        if record and any(record.get(k)!=page.get(k) for k in ("identity","source_id","page","source_sha256")):
            return None,metadata,"Owner exclusion no longer matches current page identity"
        return record,metadata,None


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--workspace",type=Path,required=True);p.add_argument("--authorization",required=True);p.add_argument("--note",default="");p.add_argument("--page-ids",type=Path)
    a=p.parse_args();ids=json.loads(a.page_ids.read_text(encoding="utf-8-sig")) if a.page_ids else None
    print(json.dumps(install_owner_exclusion(a.workspace,ids,a.authorization,a.note),ensure_ascii=False,indent=2))
