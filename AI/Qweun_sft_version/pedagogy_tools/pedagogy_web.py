"""Pedagogy review mounted on the established local review server."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import secrets
from urllib.parse import parse_qs

from pedagogy_store import PedagogyStore


class PedagogyWeb:
    def __init__(self,owner,workspace):
        self.owner=owner;self.store=PedagogyStore(workspace);self.workspace=self.store.workspace

    def send(self,handler,status,data,content_type="application/json; charset=utf-8",headers=None):
        return self.owner.send(handler,status,data,content_type,headers)

    def get(self,handler,parts):
        query=parse_qs(parts.query);arg=lambda n,d="":query.get(n,[d])[0]
        path=parts.path.rstrip("/");root="/sft/pedagogy"
        if path==root:
            body=(Path(__file__).with_name("pedagogy_review.html")).read_text(encoding="utf-8").replace("__CSRF_TOKEN__",self.owner.csrf)
            return self.send(handler,200,body.encode(),"text/html; charset=utf-8")
        if path==root+"/api/progress":
            progress=self.store.progress()
            progress["preparation"]=json.loads((self.workspace/"PREPARATION_REPORT.json").read_text(encoding="utf-8"))
            progress["assets"]=json.loads((self.workspace/"COLAB_ASSETS.json").read_text(encoding="utf-8"))
            for key in ("runtime","notebook"):
                progress["assets"][key]=Path(progress["assets"][key]).relative_to(self.workspace).as_posix()
            for key in ("pilot","full"):
                progress["assets"][key]["path"]=Path(progress["assets"][key]["path"]).relative_to(self.workspace).as_posix()
            cloud=self.workspace/"DRIVE_UPLOAD.json"
            if cloud.is_file():
                saved=json.loads(cloud.read_text(encoding="utf-8"))
                progress["cloud"]={"notebook":saved.get("notebook_url"),"folder":saved.get("folder_url")}
            fast=self.workspace/"FAST_COLAB_ASSETS.json"
            if fast.is_file():
                progress["fast_assets"]=json.loads(fast.read_text(encoding="utf-8"))
                for key in ("runtime","notebook"):
                    progress["fast_assets"][key]=Path(progress["fast_assets"][key]).relative_to(self.workspace).as_posix()
                for key in ("pilot","full"):
                    progress["fast_assets"][key]["path"]=Path(progress["fast_assets"][key]["path"]).relative_to(self.workspace).as_posix()
                cloud_fast=self.workspace/"FAST_DRIVE_UPLOAD.json"
                if cloud_fast.is_file():progress["fast_cloud"]=json.loads(cloud_fast.read_text(encoding="utf-8"))
            latest=self.workspace/"LATEST_APPROVED_SFT.json"
            if latest.is_file():
                result=json.loads(latest.read_text(encoding="utf-8"))
                progress["export"]={"report":result["report"],"directory":Path(result["directory"]).relative_to(self.workspace).as_posix(),
                                    "bundle":Path(result["bundle"]).relative_to(self.workspace).as_posix() if result["bundle"] else None}
            return self.send(handler,200,progress)
        if path==root+"/api/candidates":
            return self.send(handler,200,self.store.list(status=arg("status","pending"),course=arg("course"),task=arg("task"),
                             offset=max(0,int(arg("offset","0"))),limit=min(20,max(1,int(arg("limit","1"))))))
        if path==root+"/download":
            target=(self.workspace/arg("path")).resolve()
            if (not target.is_relative_to(self.workspace) or not target.is_file()
                or target.suffix.lower() not in {".zip",".ipynb",".json",".jsonl",".md"}):
                return self.send(handler,404,{"error":"Không tìm thấy tệp xuất."})
            return self.send(handler,200,target.read_bytes(),"application/octet-stream",
                             {"Content-Disposition":'attachment; filename="'+target.name.encode("ascii","ignore").decode()+'"'})
        return self.send(handler,404,{"error":"Không có đường dẫn này."})

    def post(self,handler,parts):
        # The parent checks CSRF and Origin before delegating here.
        path=parts.path.rstrip("/");length=int(handler.headers.get("Content-Length","0"))
        if path=="/sft/pedagogy/api/import":
            if not 0<length<=256*1024*1024:raise ValueError("ZIP kết quả phải từ 1 byte đến 256 MiB.")
            incoming=self.workspace/"incoming";incoming.mkdir(exist_ok=True)
            partial=incoming/(secrets.token_hex(16)+".uploading");sha=hashlib.sha256();remaining=length
            try:
                with partial.open("xb") as stream:
                    while remaining:
                        body=handler.rfile.read(min(1024*1024,remaining))
                        if not body:raise ValueError("Tệp tải lên bị ngắt.")
                        stream.write(body);sha.update(body);remaining-=len(body)
                archive=incoming/(sha.hexdigest()+".zip")
                if archive.exists():partial.unlink()
                else:partial.replace(archive)
            finally:partial.unlink(missing_ok=True)
            job=self.owner.start_job("pedagogy-import",lambda:self.store.import_archive(archive),dedupe_key=archive.name)
            return self.send(handler,202,{"job_id":job})
        if not 0<=length<=1024*1024:raise ValueError("Yêu cầu quá lớn.")
        payload=json.loads(handler.rfile.read(length) or b"{}")
        if not isinstance(payload,dict):raise ValueError("Cần một JSON object.")
        if path=="/sft/pedagogy/api/decision":
            result=self.store.decide(payload["id"],payload["decision"],payload["expected_identity"],
                                     note=payload.get("note",""),corrected_draft=payload.get("corrected_draft"))
            return self.send(handler,200,{"saved":True,"review":result})
        if path=="/sft/pedagogy/api/export":
            from export_pedagogy import export_approved
            job=self.owner.start_job("pedagogy-export",lambda:export_approved(self.workspace))
            return self.send(handler,202,{"job_id":job})
        return self.send(handler,404,{"error":"Không có thao tác này."})
