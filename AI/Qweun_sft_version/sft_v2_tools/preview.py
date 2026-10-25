"""Read-only source/reference viewer. Does not manufacture review decisions."""
from pathlib import Path
from common import canonical, read_rows
from prepare_theory import WORK
from build_release import RELEASE


def build():
    rows=[s for part in ('train','validation','test') for s in read_rows(WORK/(part+'.samples.jsonl'))]
    data=canonical(rows).decode().replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    html='''<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>BKQuiz · Pilot SFT-v2</title><style>
*{box-sizing:border-box}body{margin:0;background:#f3f5f8;color:#182438;font:16px/1.6 system-ui}header{padding:25px 5%;background:#182f4c;color:white}h1{margin:0;font-size:25px}header p{margin:7px 0}main{max-width:1320px;margin:22px auto;padding:0 22px;display:grid;grid-template-columns:300px 1fr;gap:22px}aside,article{background:white;border:1px solid #d9e0e9;border-radius:10px;padding:18px}aside{align-self:start;position:sticky;top:15px}label,select,input{display:block;width:100%}select,input{padding:9px;margin-bottom:12px;border:1px solid #b9c6d7;border-radius:5px}#items{max-height:60vh;overflow:auto}button{display:block;border:0;background:#eef3fa;text-align:left;padding:9px;margin:5px 0;width:100%;cursor:pointer;color:#172f53}button:hover{background:#d9e6fa}.badge{display:inline-block;padding:3px 9px;border-radius:15px;background:#e4edf8;font-size:13px;margin:3px}li{padding:6px}.correct{color:#075c39;background:#e5f5ec}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f5f7fa;padding:13px;border-radius:6px;font:14px/1.7 ui-monospace,monospace}details{margin:12px 0}h2{line-height:1.4;font-size:21px}h3{font-size:17px;margin:24px 0 7px}small{color:#52667c}@media(max-width:800px){main{display:block}aside{position:static;margin-bottom:16px}#items{max-height:180px}}
</style><header><h1>BKQuiz · Lý thuyết → Quiz · SFT-v2</h1><p>270 train ·30 validation ·100 test. Chỉ dùng source text native đã hoàn tất.</p><p>Tham chiếu được tạo từ cặp khái niệm–mô tả và kiểm tra theo nguồn. Chưa được chuyên gia xác nhận; không phải bộ suy luận tình huống mở.</p></header>
<main><aside><label>Phần dữ liệu<select id="split"><option value="">Tất cả</option><option>train</option><option>validation</option><option>test</option></select></label><label>Học phần<select id="course"><option value="">Tất cả</option></select></label><label>Tìm kiếm<input id="search" placeholder="Khái niệm hoặc mã mẫu"></label><small id="count"></small><div id="items"></div></aside><article id="detail"></article></main>
<script id="data" type="application/json">__DATA__</script><script>
const rows=JSON.parse(document.getElementById('data').textContent),$=id=>document.getElementById(id);
const text=(tag,value,parent,cls)=>{const n=document.createElement(tag);n.textContent=value;if(cls)n.className=cls;parent.append(n);return n};
for(const c of [...new Set(rows.map(r=>r.course))].sort()){const o=document.createElement('option');o.textContent=c;$('course').append(o)}
function show(r){const a=$('detail');a.replaceChildren();text('span',r.split,a,'badge');text('span',r.course,a,'badge');text('span',r.training_task,a,'badge');text('small',r.id,a);text('h2',r.reference.prompt,a);const opts=document.createElement('ol');opts.type='A';for(const o of r.reference.options)text('li',o.text+(o.correct?' ✓':''),opts,o.correct?'correct':'');a.append(opts);text('h3','Căn cứ',a);text('p',r.reference.principle,a);text('h3','Áp dụng',a);text('p',r.reference.application,a);text('h3','Đối chiếu phương án sai',a);for(const d of r.reference.distractor_explanations)text('p',String.fromCharCode(65+d.option)+'. '+d.reason+' ['+d.evidence_ids.join(', ')+']',a);text('h3','Nguồn nguyên văn',a);for(const e of r.evidence){const d=document.createElement('details');d.open=true;text('summary',e.id+' ·Trang '+e.page+' ·'+e.source_id,d);text('pre',e.text,d);text('small','SHA256 PDF: '+e.source_sha256,d);a.append(d)}const d=document.createElement('details');text('summary','JSON đầu ra thực sự dùng cho SFT / tham chiếu test',d);text('pre',r.messages.at(-1).content,d);a.append(d);text('small','Chế độ chỉ đọc; trang này không tạo sự kiện duyệt hoặc đổi dataset đã khóa.',a)}
function refresh(){const s=$('split').value,c=$('course').value,q=$('search').value.toLowerCase();const rr=rows.filter(r=>(!s||r.split===s)&&(!c||r.course===c)&&(!q||(r.id+' '+r.reference.prompt).toLowerCase().includes(q)));$('items').replaceChildren();$('count').textContent=rr.length+' mẫu';for(const r of rr){const b=document.createElement('button');b.textContent=r.course+' ·'+r.reference.prompt.slice(0,70);b.onclick=()=>show(r);$('items').append(b)}if(rr.length)show(rr[0]);else $('detail').replaceChildren()}
for(const id of ['split','course','search'])$(id).addEventListener('input',refresh);refresh();
</script></html>'''.replace('__DATA__',data)
    (RELEASE/'preview.html').write_text(html,encoding='utf-8')
    return RELEASE/'preview.html'


if __name__=='__main__':print(build())
