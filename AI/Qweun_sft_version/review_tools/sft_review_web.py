"""Two-stage exam review mounted under /sft on the established CPT review hub."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import secrets
import sys
import threading
import time
from urllib.parse import parse_qs

from sft_review_store import SFTReviewStore
from review_render import ReviewRenderer


class SFTReviewWeb:
    def __init__(self, workspace: Path):
        self.workspace=Path(workspace).resolve()
        self.store=SFTReviewStore(self.workspace)
        self.renderer=ReviewRenderer(self.workspace)
        self.csrf=secrets.token_urlsafe(32)
        self.jobs={};self.job_lock=threading.RLock()
        self._pedagogy=None

    def pedagogy(self):
        if self._pedagogy is None:
            root=Path(__file__).resolve().parents[1]
            pointer=root/"LATEST_PEDAGOGY_WORKSPACE.json"
            if not pointer.is_file():raise ValueError("Chưa chuẩn bị workspace Qwen7B.")
            workspace=Path(json.loads(pointer.read_text(encoding="utf-8"))["workspace"]).resolve()
            if not workspace.is_relative_to(root/"pedagogical_workspaces"):raise ValueError("Workspace Qwen7B không hợp lệ.")
            sys.path.insert(0,str(root/"pedagogy_tools"))
            from pedagogy_web import PedagogyWeb
            self._pedagogy=PedagogyWeb(self,workspace)
        return self._pedagogy

    def send(self,handler,status,data,content_type="application/json; charset=utf-8",headers=None):
        if not isinstance(data,bytes):data=json.dumps(data,ensure_ascii=False).encode("utf-8")
        handler.send_response(status)
        handler.send_header("Content-Type",content_type);handler.send_header("Content-Length",str(len(data)))
        handler.send_header("Cache-Control","no-store");handler.send_header("X-Content-Type-Options","nosniff")
        handler.send_header("Referrer-Policy","same-origin")
        for key,value in (headers or {}).items():handler.send_header(key,value)
        handler.end_headers();handler.wfile.write(data)

    def get(self,handler,parts):
        query=parse_qs(parts.query);arg=lambda name,default="":query.get(name,[default])[0]
        try:
            path=parts.path.rstrip("/")
            if path=="/sft/pedagogy" or path.startswith("/sft/pedagogy/"):
                return self.pedagogy().get(handler,parts)
            if path=="/sft":
                data=(Path(__file__).parent/"sft_review.html").read_text(encoding="utf-8").replace("__CSRF_TOKEN__",self.csrf)
                return self.send(handler,200,data.encode("utf-8"),"text/html; charset=utf-8")
            if path=="/sft/api/catalog":
                manifest=json.loads((self.workspace/"manifest.json").read_text(encoding="utf-8"))
                courses=sorted(manifest.get("courses") or {row["course"] for row in self.store._pages().values()})
                return self.send(handler,200,{"manifest":manifest,"courses":courses})
            if path=="/sft/api/progress":
                data={"pages":self.store.page_progress(),"questions":self.store.question_progress()}
                marker=self.workspace/"auto_triage_progress.json"
                if marker.is_file():
                    try:
                        meta=json.loads(marker.read_text(encoding="utf-8"))
                        progress=(self.workspace/meta["progress_path"]).resolve()
                        if progress.is_relative_to(self.workspace):
                            value=json.loads(progress.read_text(encoding="utf-8"))
                            data["triage"]={"checked":value.get("complete",0),"total":value.get("total",0),
                                            "running":meta.get("status")=="running" and time.time()-progress.stat().st_mtime<180,
                                            "status":meta.get("status","unknown")}
                    except (OSError,ValueError,KeyError,TypeError):pass
                return self.send(handler,200,data)
            if path=="/sft/api/page":
                return self.send(handler,200,self.store.get_page(arg("id")))
            if path=="/sft/api/text":
                page=self.store.get_page(arg("id"))
                route=page.get("automatic_routing",{})
                if route.get("route") not in {"native_text","ocr_text"} or page.get("machine_routing_error"):
                    raise ValueError("Trang này chưa có văn bản tự động đã kiểm tra.")
                target=Path(route["source_text_path"]).resolve()
                if not target.is_relative_to(self.workspace):raise ValueError("Đường dẫn văn bản không hợp lệ.")
                return self.send(handler,200,{"text":target.read_text(encoding="utf-8-sig"),"origin":route["route"],
                                             "text_sha256":route["text_sha256"],"human_verified":False})
            if path in {"/sft/api/pages","/sft/api/questions"}:
                method=self.store.list_pages if path.endswith("/pages") else self.store.list_questions
                result=method(course=arg("course"),status=arg("status","pending"),
                              limit=min(100,max(1,int(arg("limit","1")))),offset=max(0,int(arg("offset","0"))))
                return self.send(handler,200,result)
            if path=="/sft/api/image":
                page=self.store.get_page(arg("id"))
                if arg("identity") and page["identity"]!=arg("identity"):
                    return self.send(handler,409,{"error":"Ảnh nguồn đã thay đổi; tải lại trang để duyệt đúng phiên bản."})
                asset=self.renderer.ensure_image(page)
                return self.send(handler,200,Path(asset["path"]).read_bytes(),"image/png",
                                 {"X-Image-SHA256":asset["sha256"],"X-Page-Identity":page["identity"]})
            if path=="/sft/api/job":
                with self.job_lock:
                    result=self.jobs.get(arg("id"))
                    if result is None:return self.send(handler,404,{"error":"Không có tác vụ này trong phiên máy chủ hiện tại."})
                    return self.send(handler,200,result)
            if path=="/sft/download":
                target=(self.workspace/arg("path")).resolve()
                if not target.is_relative_to(self.workspace) or not target.is_file() or target.suffix.lower() not in {".zip",".ipynb",".json",".jsonl",".txt",".md"}:
                    return self.send(handler,404,{"error":"Không tìm thấy tệp xuất."})
                return self.send(handler,200,target.read_bytes(),"application/octet-stream",
                                 {"Content-Disposition":"attachment; filename=\""+target.name.encode("ascii","ignore").decode("ascii")+"\""})
            return self.send(handler,404,{"error":"Không có đường dẫn này."})
        except (ValueError,KeyError,FileNotFoundError) as error:
            return self.send(handler,400,{"error":str(error)})
        except Exception as error:
            return self.send(handler,500,{"error":f"{type(error).__name__}: {error}"})

    def files_from_result(self,result):
        files=[]
        def visit(value):
            if isinstance(value,dict):
                for item in value.values():visit(item)
            elif isinstance(value,(list,tuple)):
                for item in value:visit(item)
            elif isinstance(value,(str,Path)):
                candidate=Path(value)
                if not candidate.is_absolute():candidate=self.workspace/candidate
                try:
                    candidate=candidate.resolve()
                    if (candidate.is_relative_to(self.workspace) and candidate.is_file()
                            and candidate.suffix.lower() in {".zip",".ipynb",".json",".jsonl",".md",".txt"}):
                        relative=candidate.relative_to(self.workspace).as_posix()
                        files.append({"name":candidate.name,"path":relative})
                except (OSError,ValueError):pass
        visit(result)
        unique={f["path"]:f for f in files}
        return list(unique.values())

    def start_job(self,kind,operation,dedupe_key=None):
        dedupe_key=dedupe_key or kind
        with self.job_lock:
            for identity,value in self.jobs.items():
                if value["kind"]==kind and value.get("dedupe_key")==dedupe_key and value["status"]=="running":return identity
            identity=secrets.token_hex(12)
            self.jobs[identity]={"id":identity,"kind":kind,"dedupe_key":dedupe_key,"status":"running","started":time.time()}
        def run():
            try:
                result=json.loads(json.dumps(operation(),ensure_ascii=False,default=str))
                value={"id":identity,"kind":kind,"status":"complete","result":result,"files":self.files_from_result(result)}
            except Exception as error:
                value={"id":identity,"kind":kind,"status":"failed","error":f"{type(error).__name__}: {error}"}
            with self.job_lock:self.jobs[identity]=value
        threading.Thread(target=run,daemon=True).start()
        return identity

    def post(self,handler,parts):
        origin=handler.headers.get("Origin")
        expected={f"http://127.0.0.1:{handler.server.server_port}",f"http://localhost:{handler.server.server_port}"}
        if handler.headers.get("X-CSRF-Token")!=self.csrf or (origin and origin not in expected):
            return self.send(handler,403,{"error":"Phiên duyệt không hợp lệ. Tải lại web rồi thử lại."})
        try:
            if parts.path.rstrip("/")=="/sft/pedagogy" or parts.path.startswith("/sft/pedagogy/"):
                return self.pedagogy().post(handler,parts)
            length=int(handler.headers.get("Content-Length","0"))
            if parts.path=="/sft/api/import":
                if length<=0 or length>512*1024*1024:raise ValueError("Gói kết quả phải nhỏ hơn 512 MiB và không rỗng.")
                incoming=self.workspace/"incoming";incoming.mkdir(exist_ok=True)
                partial=incoming/(secrets.token_hex(16)+".uploading")
                digest=hashlib.sha256();remaining=length
                try:
                    with partial.open("xb") as output:
                        while remaining:
                            chunk=handler.rfile.read(min(1024*1024,remaining))
                            if not chunk:raise ValueError("Tệp tải lên bị ngắt giữa chừng.")
                            output.write(chunk);digest.update(chunk);remaining-=len(chunk)
                    archive=incoming/(digest.hexdigest()+".zip")
                    if archive.exists():partial.unlink()
                    else:partial.replace(archive)
                except Exception:
                    partial.unlink(missing_ok=True);raise
                from colab_workflow import import_results
                job=self.start_job("import",lambda:import_results(self.workspace,archive),dedupe_key=archive.name)
                return self.send(handler,202,{"job_id":job})
            if length<0 or length>1024*1024:raise ValueError("Yêu cầu quá lớn.")
            payload=json.loads(handler.rfile.read(length) or b"{}")
            if not isinstance(payload,dict):raise ValueError("Nội dung không hợp lệ.")
            if parts.path=="/sft/api/page-decision":
                result=self.store.decide_page(payload["id"],payload["decision"],payload["expected_identity"],
                                              image_sha256=payload.get("image_sha256"),note=payload.get("note",""))
                return self.send(handler,200,{"saved":True,"review":result})
            if parts.path=="/sft/api/question-decision":
                result=self.store.decide_question(payload["id"],payload["decision"],payload["expected_identity"],
                                                  corrected_question=payload.get("corrected_question"),note=payload.get("note",""))
                return self.send(handler,200,{"saved":True,"review":result})
            if parts.path=="/sft/api/export":
                from colab_workflow import export_approved
                job=self.start_job("export",lambda:export_approved(self.workspace))
                return self.send(handler,202,{"job_id":job})
            if parts.path=="/sft/api/colab-assets":
                from colab_workflow import prepare_colab_assets
                job=self.start_job("colab-assets",lambda:prepare_colab_assets(self.workspace))
                return self.send(handler,202,{"job_id":job})
            if parts.path=="/sft/api/extract-text":
                from auto_extract_questions import import_auto_text_questions
                job=self.start_job("extract-text",lambda:import_auto_text_questions(self.workspace))
                return self.send(handler,202,{"job_id":job})
            if parts.path=="/sft/api/export-questions":
                result=self.store.export_approved_questions()
                folder=self.workspace/"approved_questions";folder.mkdir(exist_ok=True)
                stamp=time.strftime("%Y%m%d_%H%M%S")
                path=folder/("questions_"+stamp+"_"+secrets.token_hex(4)+".jsonl")
                if isinstance(result,dict):rows=result.get("questions",result.get("items",[]))
                else:rows=result
                with path.open("w",encoding="utf-8",newline="\n") as output:
                    for row in rows:output.write(json.dumps(row,ensure_ascii=False)+"\n")
                return self.send(handler,200,{"questions":len(rows),"files":self.files_from_result({"path":path})})
            return self.send(handler,404,{"error":"Không có thao tác này."})
        except (ValueError,KeyError,FileNotFoundError) as error:
            return self.send(handler,400,{"error":str(error)})
        except Exception as error:
            return self.send(handler,500,{"error":f"{type(error).__name__}: {error}"})
