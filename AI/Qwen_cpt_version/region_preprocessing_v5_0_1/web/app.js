"use strict";
const $ = id => document.getElementById(id);
const PAGE_SIZE = 100;
const state = {token:"", scope:"vlm", records:[], offset:0, total:0, index:-1, current:null,
  busy:false, editing:false, dirty:false, sourceReady:false, reviewer:""};
const decisions = {pending:"Chưa duyệt", approve:"Đã duyệt", correct:"Đã sửa", reject:"Đã loại", defer:"Để lại"};
async function api(path, options={}) {
  const response = await fetch(path, options), data = await response.json();
  if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
  return data;
}
function message(text) { $("message").textContent = text; }
function block(tag, text, parent, className) {
  const element = document.createElement(tag); element.textContent = text;
  if (className) element.className = className; parent.appendChild(element); return element;
}
function controls() {
  for (const id of ["previous","next","reload","decision","changeReviewer"]) $(id).disabled = state.busy || state.editing;
  for (const id of ["approve","reject"]) $(id).disabled = state.busy || state.editing || !state.current || !state.sourceReady;
  $("edit").disabled = state.busy || state.editing || !state.current;
  for (const id of ["saveCorrection","cancelEdit"]) $(id).disabled = state.busy;
  for (const button of $("records").children) button.disabled = state.busy || state.editing;
}
async function locked(action) {
  if (state.busy) return;
  state.busy = true; controls();
  try { await action(); } catch (error) { message(error.message); }
  finally { state.busy = false; controls(); }
}
function targetText(record) { return state.scope === "vlm" ? record.review_target.text : record.proposed_text || ""; }
function drawList() {
  $("records").replaceChildren();
  state.records.forEach((record, index) => {
    const button = block("button", `Trang ${record.page}\n${decisions[record.review_decision || "pending"]}`, $("records"));
    button.type = "button"; button.classList.toggle("active", index === state.index);
    button.onclick = () => { if (!state.editing) locked(() => select(index)); };
  });
  $("range").textContent = state.total ? `${state.offset+1}–${state.offset+state.records.length} / ${state.total} kết quả` : "0 kết quả";
  controls();
}
async function stats() {
  const data = await api("/api/stats");
  $("stats").textContent = state.scope === "vlm"
    ? `${data.vlm_success_outputs} kết quả VLM trên ${data.vlm_pages} / ${data.source_pdf_pages ?? "?"} trang PDF · ${data.pending} chưa duyệt · ${data.reviewed} đã xử lý`
    : `${data.total} mẫu · chế độ kiểm tra toàn bộ dữ liệu`;
  $("inventoryStats").textContent = JSON.stringify({source_pdf_pages:data.source_pdf_pages,
    successful_vlm_pages:data.vlm_pages, successful_vlm_records:data.vlm_success_outputs,
    diagnostics:data.diagnostics, full_inventory:data.inventory}, null, 2);
}
async function loadPage(offset=0, index=0) {
  const query = new URLSearchParams({offset:String(offset), limit:String(PAGE_SIZE)});
  if ($("decision").value) query.set("decision", $("decision").value);
  const data = await api(`/api/records?${query}`);
  state.records = data.records; state.total = data.total; state.offset = offset;
  if (!state.records.length && offset > 0 && state.total > 0)
    return loadPage(Math.floor((state.total-1)/PAGE_SIZE)*PAGE_SIZE,PAGE_SIZE-1);
  state.current = null; state.index = -1; state.sourceReady = false;
  $("detail").hidden = !state.records.length; $("empty").hidden = !!state.records.length;
  if (state.records.length) await select(Math.min(index, state.records.length-1));
  drawList(); await stats();
}
async function select(index) {
  const row = state.records[index]; if (!row) return;
  const data = await api(`/api/record/${encodeURIComponent(row.id)}`);
  state.current = data.record; state.index = index; state.sourceReady = false;
  state.editing = false; state.dirty = false;
  render(data.record, data.history); drawList(); message("");
}
function render(record, history) {
  $("detail").hidden = false;
  $("recordTitle").textContent = `Trang ${record.page} · ${state.index+state.offset+1} / ${state.total}`;
  $("vlmText").textContent = targetText(record);
  $("reviewStatus").textContent = record.review_stale ? "Nguồn đã thay đổi; cần duyệt lại." : decisions[record.review_decision || "pending"];
  if (state.scope === "vlm" && !record.review_target.ready) message("VLM chưa được chọn làm đề xuất. Hệ thống sẽ chặn quyết định để tránh duyệt nhầm native/OCR.");
  for (const kind of ["render","crop","context"]) {
    const path = `/api/record/${encodeURIComponent(record.id)}/image/${kind}`;
    $(kind).src = path; $(kind+"Link").href = path;
    if (kind !== "render") $(kind+"Figure").hidden = !record[kind+"_path"];
  }
  state.sourceReady = $("render").complete && $("render").naturalWidth > 0 && $("render").currentSrc === $("render").src;
  $("editPanel").hidden = true; $("finalText").readOnly = true; $("finalText").value = targetText(record);
  $("metadata").textContent = JSON.stringify({id:record.id,page:record.page,bbox:record.bbox,source_sha256:record.source_sha256,
    render_sha256:record.render_sha256,crop_sha256:record.crop_sha256,context_sha256:record.context_sha256,
    machine_revision:record.machine_revision,review_target:record.review_target,split:record.split},null,2);
  $("reasons").replaceChildren(); (record.reasons||[]).forEach(reason => block("li",reason,$("reasons")));
  $("candidates").replaceChildren(); (record.candidates||[]).forEach(candidate => {
    const card = block("div","",$("candidates"),"candidate");
    block("strong",`${candidate.engine} · ${candidate.status}`,card); block("pre",candidate.text||"Không có nội dung",card);
  });
  $("history").replaceChildren();
  for (const item of [...history].reverse()) {
    const card = block("div","",$("history"),"history-item");
    block("strong",`${item.reviewer} · ${decisions[item.decision]||item.decision}`,card);
    block("pre",item.accepted_text ?? item.text ?? "",card); block("p",item.evidence||"",card);
  }
  if (!history.length) block("p","Chưa có quyết định của con người.",$("history"));
}
async function navigate(direction) {
  if (state.editing || state.dirty) { message("Lưu hoặc Hủy bản sửa trước khi chuyển mẫu."); return false; }
  const plan = ReviewKeys.navigationPlan(state.index,state.records.length,state.offset,state.total,direction,PAGE_SIZE);
  if (!plan) return false;
  if (plan.offset !== state.offset) await loadPage(plan.offset,plan.index); else await select(plan.index);
  return true;
}
function ensureReviewer() {
  if (state.reviewer) return true;
  $("reviewerDialog").showModal(); $("reviewerName").focus(); return false;
}
async function decide(decision, method) {
  if (!state.current || !ensureReviewer() || !state.sourceReady) return;
  if (decision !== "correct" && (state.editing || state.dirty)) return;
  const record = state.current;
  if (decision !== "correct" && record.review_decision === decision && !record.review_stale) { message("Quyết định này đã được lưu. Không ghi lặp."); return; }
  const text = decision === "correct" ? $("finalText").value : decision === "approve" ? targetText(record) : "";
  if (decision === "correct" && (!state.editing || !text.trim())) { message("Bản sửa cần có nội dung."); return; }
  const payload = {record_id:record.id,reviewer:state.reviewer,decision,text,expected_revision:record.machine_revision,
    expected_candidate_sha256:record.review_target?.candidate_sha256 || null,input_method:method,action_id:crypto.randomUUID(),
    evidence:`Explicit UI action: ${method}. The interface instructs source comparison before deciding.`,
    acknowledgement_high_risk:decision === "approve" || decision === "correct"};
  const response = await api("/api/review",{method:"POST",headers:{"Content-Type":"application/json","X-Review-Token":state.token},body:JSON.stringify(payload)});
  state.editing = false; state.dirty = false;
  state.records[state.index] = {...record,latest_review:response.review,review_decision:decision,review_stale:false};
  if ($("decision").value) await loadPage(state.offset,state.index);
  else { const advanced = await navigate(1); if (!advanced) await select(state.index); }
  await stats(); message(`Đã lưu: ${decisions[decision]}.`);
}
function beginEdit() {
  if (!state.current || state.busy) return;
  state.editing = true; state.dirty = false; $("editPanel").hidden = false; $("finalText").readOnly = false;
  $("finalText").value = state.current.latest_review?.accepted_text || targetText(state.current);
  $("finalText").focus(); controls();
}
function cancelEdit() { state.editing=false; state.dirty=false; $("editPanel").hidden=true; $("finalText").readOnly=true; controls(); }
$("render").onload = () => {state.sourceReady=$("render").complete && $("render").naturalWidth>0 && $("render").currentSrc===$("render").src;controls();};
$("render").onerror = () => {state.sourceReady=false;controls();message("Không tải được slide gốc. Quyết định bị khóa.");};
$("previous").onclick = () => locked(() => navigate(-1)); $("next").onclick = () => locked(() => navigate(1));
$("approve").onclick = () => locked(() => decide("approve","click_approve"));
$("reject").onclick = () => locked(() => decide("reject","click_reject"));
$("edit").onclick = beginEdit; $("cancelEdit").onclick = cancelEdit;
$("saveCorrection").onclick = () => locked(() => decide("correct","click_save_correction"));
$("finalText").oninput = () => {if(state.editing)state.dirty=true;};
$("reload").onclick = () => locked(() => loadPage(state.offset,state.index));
$("decision").onchange = () => locked(() => loadPage());
$("changeReviewer").onclick = () => {$("reviewerName").value=state.reviewer;$("reviewerDialog").showModal();};
$("reviewerForm").onsubmit = event => {event.preventDefault();const name=$("reviewerName").value.trim();if(!name)return;
  state.reviewer=name;localStorage.setItem("bkquizReviewer",name);$("changeReviewer").textContent=`Người duyệt: ${name}`;$("reviewerDialog").close();controls();};
document.addEventListener("keydown", event => {
  const action = ReviewKeys.actionForKey(event,state); if(!action)return; event.preventDefault();
  if(action==="previous"||action==="next")locked(() => navigate(action==="previous"?-1:1));
  else locked(() => decide(action,action==="approve"?"keyboard_up":"keyboard_down"));
});
window.addEventListener("beforeunload",event => {if(state.dirty){event.preventDefault();event.returnValue="";}});
(async () => {
  try {const boot=await api("/api/bootstrap");state.token=boot.csrf_token;state.scope=boot.scope;
    if(state.scope==="all"){$("title").textContent="Kiểm tra toàn bộ dữ liệu";$("textTitle").textContent="Đề xuất máy · chế độ kiểm tra toàn bộ";}
    state.reviewer=localStorage.getItem("bkquizReviewer")||"";$("changeReviewer").textContent=`Người duyệt: ${state.reviewer||"chưa chọn"}`;
    await locked(() => loadPage()); ensureReviewer();
  } catch(error){message(error.message);}
})();
