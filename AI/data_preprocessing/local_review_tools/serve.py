"""Course selector for the unchanged v5 review UI, with physical-LF JSONL reads."""
from pathlib import Path
import argparse
from contextlib import closing
import html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import sqlite3
import sys
import threading
import weakref
from urllib.parse import parse_qs, urlsplit

ROOT=Path(__file__).resolve().parent
RUNTIME=ROOT.parent/'colab_orchestrator_v5'
CORE=ROOT.parent.parent/'Qwen_cpt_version/region_preprocessing_v5_0_1'
sys.path.insert(0,str(RUNTIME));sys.path.insert(0,str(CORE))
from common import verify_release
from jsonl_adapter import read_jsonl
from review_store import ReviewStore
from review_app import ReviewHTTPServer, ReviewHandler, successful_vlm_candidates


class CachedReviewStore(ReviewStore):
    _cache_lock=threading.RLock()
    _cache_owner=None

    def __init__(self,run):
        self._record_lock=threading.RLock();self._record_cache=None;self._record_stamp=None
        super().__init__(run)

    def _records(self):
        with self._cache_lock,self._record_lock:
            owner=self._cache_owner() if self._cache_owner is not None else None
            if owner is not None and owner is not self:
                with owner._record_lock:
                    owner._record_cache=None;owner._record_stamp=None
            CachedReviewStore._cache_owner=weakref.ref(self)
            path=self.run/'records.jsonl';st=path.stat();stamp=(st.st_mtime_ns,st.st_size)
            if stamp!=self._record_stamp:
                values=read_jsonl(path);records={r['id']:r for r in values}
                if len(records)!=len(values):raise ValueError('Duplicate record ID')
                self._record_cache=records;self._record_stamp=stamp
            return self._record_cache


class CourseHandler(ReviewHandler):
    def _send(self,status,data,content_type):
        if content_type.startswith('text/html') and status==200:
            title=html.escape(self.server.course_title)
            nav=f'<nav><a href="{self.server.hub_url}">← Danh sách học phần</a> · <strong>{title}</strong></nav>'
            data=data.replace(b'<body>',b'<body>'+nav.encode('utf-8'),1)
            if self.server.scope=='all':
                text=data.decode('utf-8')
                text=text.replace('BKQuiz · Duyệt mô tả VLM','BKQuiz · Kiểm tra toàn bộ dữ liệu')
                text=text.replace('Không có mô tả VLM thành công, có nội dung để kiểm duyệt trong bộ lọc này. Các lần chạy lỗi hoặc chưa chạy chỉ xuất hiện trong kiểm kê.',
                    'Không có mẫu dữ liệu phù hợp với bộ lọc hiện tại.')
                text=text.replace('Chỉ dữ liệu VLM thành công, có nội dung nằm trong hàng đợi mặc định.',
                    'Chế độ này hiển thị toàn bộ kết quả máy, gồm text, bảng, công thức và vùng chưa trích xuất được.')
                data=text.encode('utf-8')
        return super()._send(status,data,content_type)


class ReviewHub:
    def __init__(self,workspace,base_port=8766,hub_url='http://127.0.0.1:8765/',sft_workspace=None):
        verify_release(CORE)
        self.workspace=Path(workspace).resolve()
        self.catalog=json.loads((self.workspace/'review_catalog.json').read_text(encoding='utf-8'))
        self.documents={d['document_id']:d for d in self.catalog['documents']}
        self.base_port=base_port;self.hub_url=hub_url;self.servers={};self.stores={};self.lock=threading.RLock()
        self._vlm_identities={}
        self.sft_workspace=Path(sft_workspace or ROOT.parent.parent/'Qweun_sft_version/review_workspaces/exams_20261024').resolve()
        self._sft_app=None

    def sft_app(self):
        with self.lock:
            if not (self.sft_workspace/'manifest.json').is_file():raise ValueError('Chưa có hàng đợi duyệt đề thi SFT.')
            if self._sft_app is None:
                sys.path.insert(0,str(ROOT.parent.parent/'Qweun_sft_version/review_tools'))
                from sft_review_web import SFTReviewWeb
                self._sft_app=SFTReviewWeb(self.sft_workspace)
            return self._sft_app

    def vlm_progress(self):
        """Read current decisions without creating or writing review databases."""
        progress={}
        with self.lock:
            for document_id,d in self.documents.items():
                run=Path(d['run']).resolve()
                if not run.is_relative_to(self.workspace/'runs'):raise ValueError('Run escapes workspace')
                total=int(d['vlm_records']);completed=0
                database=run/'human_reviews.sqlite3'
                latest=[]
                if database.is_file():
                    with closing(sqlite3.connect(database.as_uri()+'?mode=ro',uri=True)) as connection:
                        latest=connection.execute('SELECT r.record_id,r.payload FROM reviews r JOIN '
                            '(SELECT record_id,MAX(sequence) s FROM reviews GROUP BY record_id) x ON r.sequence=x.s').fetchall()
                if latest:
                    path=run/'records.jsonl';st=path.stat();stamp=(st.st_mtime_ns,st.st_size)
                    cached=self._vlm_identities.get(document_id)
                    if cached is None or cached[0]!=stamp:
                        identities={}
                        # Keep only small VLM identities; do not load all courses into the record cache.
                        with path.open(encoding='utf-8-sig') as source:
                            for line in source:
                                if not line.strip():continue
                                record=json.loads(line)
                                if successful_vlm_candidates(record):identities[record['id']]=ReviewStore._identity(record)
                        self._vlm_identities[document_id]=(stamp,identities)
                    identities=self._vlm_identities[document_id][1];total=len(identities)
                    for record_id,payload in latest:
                        review=json.loads(payload)
                        if (record_id in identities and review.get('identity')==identities[record_id]
                                and review.get('decision') in {'approve','correct','reject'}):completed+=1
                progress[document_id]={'remaining':total-completed,'total':total}
        return progress

    def open_course(self,document_id,scope):
        if document_id not in self.documents or scope not in {'vlm','all'}:raise ValueError('Unknown course or scope')
        key=(document_id,scope)
        with self.lock:
            if key not in self.servers:
                d=self.documents[document_id];run=Path(d['run']).resolve()
                if not run.is_relative_to(self.workspace/'runs'):raise ValueError('Run escapes workspace')
                if document_id not in self.stores:self.stores[document_id]=CachedReviewStore(run)
                position=list(self.documents).index(document_id)
                port=self.base_port+position*2+(scope=='all') if self.base_port else 0
                server=ReviewHTTPServer(('127.0.0.1',port),run,store=self.stores[document_id],scope=scope)
                server.course_title=d.get('title',d['course']);server.hub_url=self.hub_url
                server.RequestHandlerClass=CourseHandler
                threading.Thread(target=server.serve_forever,daemon=True).start();self.servers[key]=server
            return f'http://127.0.0.1:{self.servers[key].server_port}/'

    def close(self):
        for server in self.servers.values():server.shutdown();server.server_close()

    def page(self):
        rows=[];progress=self.vlm_progress()
        for d in self.documents.values():
            doc=html.escape(d['document_id'],quote=True);title=html.escape(d.get('title',d['course']))
            counts=progress[d['document_id']]
            rows.append(f'<tr><td><strong>{html.escape(d["course"])}</strong><br>{title}</td>'
                f'<td>{d.get("imported_pages","?")} / {d.get("source_pages","?")}</td>'
                f'<td data-vlm-progress="{doc}">{counts["remaining"]}/{counts["total"]}</td><td>{d.get("critical_records","?")}</td>'
                f'<td><a href="/open?doc={doc}&amp;scope=vlm">Duyệt mô tả VLM</a><br>'
                f'<a href="/open?doc={doc}&amp;scope=all">Kiểm tra toàn bộ</a></td></tr>')
        total=self.catalog.get('totals',{})
        return ('<!doctype html><html lang="vi"><meta charset="utf-8"><title>BKQuiz · Kiểm duyệt dữ liệu</title>'
            '<style>body{font:16px system-ui;margin:40px auto;max-width:1200px;padding:0 20px;color:#172033;background:#f6f8fc}'
            'h1{margin-bottom:8px}table{width:100%;border-collapse:collapse;background:white}th,td{text-align:left;padding:16px;border-bottom:1px solid #dde3ed}'
            'th{background:#e8eef8}a{color:#174eaf;line-height:1.8}p{line-height:1.6}aside{background:#e8eef8;padding:16px;margin:20px 0}small{color:#566477}</style>'
            '<h1>Kiểm duyệt dữ liệu preprocessing</h1>'
            +('<aside><strong>Đề thi SFT · Duyệt hai đợt</strong><br>'
              '<a href="/sft/?stage=1">Đợt 1 · Chọn ảnh cho VLM trên Colab</a> · '
              '<a href="/sft/?stage=2">Đợt 2 · Duyệt câu hỏi đã tách</a><br>'
              '<small>Ảnh chưa được chấp nhận không đưa vào VLM. Kết quả VLM tiếp tục chờ bạn duyệt từng câu.</small></aside>'
              if (self.sft_workspace/'manifest.json').is_file() else '')+
            f'<p><strong>{len(self.documents)} học phần · {total.get("pages","?")} trang · {total.get("units","?")} gói</strong></p>'
            '<aside>Chọn học phần để mở giao diện kiểm duyệt đã có. <strong>Duyệt mô tả VLM</strong> chỉ hiện kết quả VLM thành công; '
            '<strong>Kiểm tra toàn bộ</strong> mở cả text, công thức, bảng và các vùng chưa trích xuất được.<br>'
            'Phím ←/→ chuyển mẫu · ↑ chấp nhận · ↓ loại bỏ · nút Sửa để chỉnh nội dung. Đối chiếu ảnh nguồn trước khi lưu.<br>'
            'Quyết định được lưu riêng cho mỗi học phần; dữ liệu máy không tự được phê duyệt.</aside>'
            '<table><thead><tr><th>Học phần</th><th>Trang đã nhập</th><th>Kết quả VLM<br><small>Còn lại/tổng số</small></th><th>Vùng critical</th><th>Mở kiểm duyệt</th></tr></thead><tbody>'
            +''.join(rows)+'</tbody></table><p><small>Số còn lại tự cập nhật mỗi 15 giây và khi quay lại trang. '
            'Mẫu tạm hoãn hoặc cần duyệt lại vẫn được tính vào số còn lại.<br>'
            'Máy chủ chỉ lắng nghe trên máy này. Đóng tab không làm mất quyết định đã lưu.</small></p>'
            '<script>let updating=false;async function refreshProgress(){'
            'if(document.hidden||updating)return;updating=true;try{'
            'const response=await fetch("/api/progress",{cache:"no-store"});if(!response.ok)return;'
            'const progress=await response.json();document.querySelectorAll("[data-vlm-progress]").forEach(cell=>{'
            'const counts=progress[cell.dataset.vlmProgress];if(counts)cell.textContent=counts.remaining+"/"+counts.total;});'
            '}catch(error){}finally{updating=false;}}'
            'window.addEventListener("focus",refreshProgress);window.addEventListener("pageshow",refreshProgress);'
            'document.addEventListener("visibilitychange",refreshProgress);setInterval(refreshProgress,15000);</script></html>').encode('utf-8')


class HubHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.headers.get('Host') not in {f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}:
            self.send_error(403);return
        parts=urlsplit(self.path)
        try:
            if parts.path=='/sft' or parts.path.startswith('/sft/'):
                return self.server.hub.sft_app().get(self,parts)
            if parts.path=='/open':
                q=parse_qs(parts.query);location=self.server.hub.open_course(q.get('doc',[''])[0],q.get('scope',['vlm'])[0])
                self.send_response(302);self.send_header('Location',location);self.send_header('Content-Length','0');self.end_headers();return
            if parts.path not in {'/','/api/catalog','/api/progress'}:self.send_error(404);return
            if parts.path=='/':data=self.server.hub.page()
            else:
                value=self.server.hub.vlm_progress() if parts.path=='/api/progress' else self.server.hub.catalog
                data=json.dumps(value,ensure_ascii=False).encode('utf-8')
            self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8' if parts.path=='/' else 'application/json; charset=utf-8')
            self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(data)))
            self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(data)
        except Exception as exc:
            self.send_error(400,explain=str(exc))

    def do_POST(self):
        if self.headers.get('Host') not in {f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}:
            self.send_error(403);return
        parts=urlsplit(self.path)
        if parts.path.startswith('/sft/'):
            try:return self.server.hub.sft_app().post(self,parts)
            except Exception as exc:self.send_error(400,explain=str(exc));return
        self.send_error(404)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',type=Path,default=ROOT.parent/'workspaces/unit100_v6_20261022')
    parser.add_argument('--sft-workspace',type=Path,default=None)
    parser.add_argument('--port',type=int,default=8765);args=parser.parse_args()
    hub=ReviewHub(args.workspace,base_port=args.port+1,hub_url=f'http://127.0.0.1:{args.port}/',sft_workspace=args.sft_workspace)
    server=ThreadingHTTPServer(('127.0.0.1',args.port),HubHandler);server.hub=hub
    print(f'Review hub: http://127.0.0.1:{args.port}/ ({len(hub.documents)} courses)',flush=True)
    try:server.serve_forever()
    finally:server.server_close();hub.close()


if __name__=='__main__':main()
