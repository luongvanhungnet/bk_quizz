"""Evidence-based stage-one routing. No human decision or SFT approval is made.

The manual queue has no size cap: thresholds describe observable extraction
problems. OCR confidence is not a calibrated probability of VLM success.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import time

from auto_extract_questions import extract_questions
from colab_runtime.runtime import atomic_json, atomic_bytes


REVISION = "exam-page-routing-v1"
AUTHORIZATION = "dùng orc để tự động duyệt những ảnh có thể trích xuất txt từ pdf, còn những ảnh có tỷ lệ cao là không thể tự động trích xuất thông tin thông qua vlm thì mới dữ lại trạng thái cần duyệt để người dùng duyệt thủ công. mục tiêu là dưới 500 ảnh cần duyệt thủ công."
VISUAL = re.compile(r"hình\s+(?:vẽ|bên|sau|dưới|trên)|sơ\s*đồ|đồ\s*thị|biểu\s*đồ|bảng\s+(?:sau|dưới|bên|trên)|ma\s*trận|(?:following|shown|below|above)\s+(?:figure|table|diagram)|\b(?:diagram|plot|matrix)\b", re.I)
MATH = re.compile(r"[=^∫∑∏√∞∂∇∈∉⊂⊃⊆⊇∪∩∀∃∧∨¬⇒⇔→←↔⟹⟺≤≥≠±×÷α-ωΑ-Ω₀-₉⁰¹²³⁴⁵⁶⁷⁸⁹☐☑☒■□✓✔✗✘●○◯]|\b(?:sin|cos|tan|lim)\s*\(")
QUIZ_UI = re.compile(r"Select\s+(?:one|all)|Choose\s+(?:one|all)|Trả\s*lời\s*(?:đúng|sai)|\b(?:Corrected|Incorrect|Correct|Marks|Points?|Auto-graded)\b|đạt\s+\d+\s*/\s*\d+|Câu\s*hỏi\s*#|Finish\s+review", re.I)
ESSAY = re.compile(r"\b(?:Giải\s*thích|Trình\s*bày|Phân\s*tích|Mô\s*tả|Chứng\s*minh|Explain|Describe|Discuss|Prove)\b", re.I)
UNSUPPORTED_TEXT_STRUCTURE = re.compile(r"\[\s*(?:0|100)\s*\]|^\s*Sol\s*:", re.I | re.M)
LAYOUT_FLAGS = {"embedded_figure_requires_review", "visual_reference_requires_review", "math_layout_requires_review", "flattened_table_requires_review", "long_page_tiled"}


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def read_jsonl(path):
    with Path(path).open(encoding="utf-8-sig") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def text_layout_safe(native, text):
    """Favor VLM whenever plain text might omit visual source evidence."""
    flags = set(native.get("source_risk_flags", []))
    return (not flags.intersection(LAYOUT_FLAGS | {"unsupported_or_corrupt_glyph", "repeated_character_corruption"})
            and not VISUAL.search(text) and not MATH.search(text)
            and not QUIZ_UI.search(text)
            and native.get("native_math_font_ratio", 0) == 0
            and native.get("native_color_ratio", 0) == 0
            and native.get("annotation_count", 0) == 0 and native.get("widget_count", 0) == 0
            and native.get("native_emphasis_ratio", 0) == 0
            and not native.get("visual_answer_markings")
            and native.get("drawing_count", 0) == 0)


def parsed_text_safe(parsed, text):
    questions = parsed["questions"]
    if any(re.search(r"^\s*[A-H][.)]\s+", q.get("source_context", ""), re.M | re.I) for q in questions):
        return False
    if questions and any(q["options"] for q in questions) and not questions[-1]["options"]:
        return False  # A final MCQ stem continues onto the next page.
    return (bool(questions) and not parsed["requires_vlm"]
            and "unsegmented_page_text" not in parsed.get("flags", [])
            and not re.search(r"^\s*(?:\d+[.)]\s*)?(?:Nội\s*dung\s*\d|Mục\s*lục|Table\s+of\s+contents)", text, re.I | re.M)
            and not UNSUPPORTED_TEXT_STRUCTURE.search(text))


def explicit_essay_questions(parsed):
    for question in parsed["questions"]:
        prompt = question["prompt"]
        context = question.get("source_context", "")
        if context and prompt.startswith(context): prompt = prompt[len(context):].strip()
        prompt = re.sub(r"^(?:Hãy|Please)\s+", "", prompt, flags=re.I)
        if not ESSAY.match(prompt): return False
    return bool(parsed["questions"])


def classify(native, ocr=None, text=""):
    """Return route, heuristic score, reasons; never truncate by a quota."""
    chars = native.get("native_chars", 0)
    safe = text_layout_safe(native, text)
    clean_native = (chars >= 180 and native.get("native_words", 0) >= 20
                    and native.get("native_bad_glyphs", 0) == 0
                    and native.get("native_long_word_ratio", 1) < .01
                    and native.get("native_letters_ratio", 0) >= .4)
    if clean_native and safe and native.get("image_count", 1) == 0:
        parsed = extract_questions(text, footer_text=native.get("footer_text"))
        if parsed_text_safe(parsed, text):
            return "native_text", 5, ["Lớp chữ PDF đầy đủ; không phát hiện phụ thuộc hình, công thức hoặc dấu đáp án bằng màu."]
    # Native-rich PDFs can be rendered by VLM even if their plain text loses
    # symbols or diagrams. Do not mistake missing answer keys for bad images.
    if chars >= 300 and (ocr is None or ocr.get("status") == "native_skipped"):
        return "auto_vlm", 20, ["PDF có lớp chữ; dùng VLM để giữ hình, công thức, bố cục và dấu trên nguồn."]
    if ocr is None:
        return "manual", 100, ["Chưa có bằng chứng OCR hoàn tất cho ảnh này."]
    if ocr.get("status") == "error":
        return "manual", 100, ["Không dựng hoặc không đọc được ảnh trong giới hạn xử lý; cần kiểm tra nguồn."]
    m = ocr.get("image_metrics") or {}
    o = ocr.get("ocr") or {}
    words = o.get("word_count", 0)
    confidence = o.get("weighted_confidence") or 0
    ink = m.get("ink_fraction", 1)
    # Require both near-white pixels and negligible text; sparse diagrams,
    # faint scans and dark failed renders cannot be silently called blank.
    if (chars == 0 and words == 0 and ink == 0 and m.get("gray_std", 999) < 1
            and m.get("glyph_like_components", 999) == 0 and native.get("annotation_count", 0) == 0):
        return "blank", 0, ["Ảnh gần như trắng, không có lớp chữ hoặc vùng ký tự đáng kể."]
    if ocr.get("status") not in {"ok", "native_skipped", "blank_candidate"}:
        return "manual", 100, ["Trạng thái OCR chưa đủ căn cứ để chuyển tự động."]
    if ocr.get("status") == "native_skipped":
        return "auto_vlm", 25, ["Trang có lớp chữ; chuyển VLM vì TXT chưa giữ đủ nội dung."]
    glyph_height = m.get("median_glyph_height")
    tiny = glyph_height is not None and glyph_height < 5 and m.get("small_glyph_fraction", 0) > .65
    blurred = m.get("laplacian_variance", 999) < 45
    faint = m.get("gray_std", 999) < 10 and ink > .002
    # Dark UI backgrounds and photographed margins distort raw gray<210
    # components. Do not treat a dark page alone as an unreadable page.
    dark_background = ink > .5 and m.get("gray_mean", 255) < 210
    if dark_background: tiny = False
    if chars < 80 and confidence < 45 and words < 25 and (tiny or blurred or faint):
        issues = []
        if tiny: issues.append("ký tự rất nhỏ")
        if blurred: issues.append("ảnh mờ")
        if faint: issues.append("chữ nhạt")
        return "manual", 90, ["OCR đọc yếu đồng thời có dấu hiệu " + ", ".join(issues) + "; cần người xem ảnh."]
    if chars < 80 and words < 6:
        return "manual", 80, ["OCR thu được quá ít chữ; cần phân biệt hình/công thức đọc được với ảnh hỏng hoặc viết tay khó đọc."]
    # OCR text alone is intentionally strict: retain nearly all dark source
    # pixels inside recognized word boxes, plus layout checks. Otherwise VLM.
    ocr_text = o.get("text", "")
    coverage = m.get("ocr_ink_coverage", 0)
    if (safe and native.get("native_math_font_ratio", 0) == 0 and not VISUAL.search(ocr_text) and not MATH.search(ocr_text)
            and not QUIZ_UI.search(ocr_text) and ESSAY.search(ocr_text)
            and confidence >= 90 and words >= 30 and o.get("word_fraction_conf_ge60", 0) >= .97
            and o.get("word_fraction_conf_lt40", 1) <= .01 and coverage >= .97):
        parsed = extract_questions(ocr_text)
        # A circle/checkbox identifying an answer can occupy far less than3%
        # of ink. MCQ scans therefore retain their image even with high OCR.
        if (parsed_text_safe(parsed, ocr_text) and explicit_essay_questions(parsed)
                and not any(q["options"] for q in parsed["questions"])):
            return "ocr_text", 10, ["OCR đọc rõ; các vùng chữ nhận dạng bao phủ gần hết nét mực và không phát hiện phụ thuộc hình."]
    return "auto_vlm", 30 if confidence >= 60 else 50, ["Ảnh có nội dung đọc được; chuyển VLM để giữ các phần OCR/TXT có thể bỏ sót."]


def build(workspace, evidence_dir, *, activate=False, allow_incomplete=False):
    workspace = Path(workspace).resolve(); evidence_dir = Path(evidence_dir).resolve()
    if not evidence_dir.is_relative_to(workspace):
        raise ValueError("Evidence must stay inside the review workspace")
    pages = read_jsonl(workspace / "pages.jsonl")
    native = {r["page_id"]: r for r in read_jsonl(evidence_dir / "native_features.jsonl")}
    metrics_path = evidence_dir / "ocr_metrics.jsonl"
    probes = {}
    if metrics_path.is_file():
        with metrics_path.open("rb") as stream:
            for body in stream:
                if not body.strip(): continue
                value = json.loads(body)
                if value["id"] in probes: raise ValueError("Duplicate OCR evidence in completed index")
                fingerprint = hashlib.sha256(body.strip() + b"\n").hexdigest()
                if value.get("ocr"): value["ocr"].pop("words", None)
                probes[value["id"]] = (value, fingerprint)
    extra_path = evidence_dir / "extra_pdf_features.jsonl"
    extras = {r["page_id"]: r for r in read_jsonl(extra_path)} if extra_path.is_file() else {}
    footer_path = evidence_dir / "native_footer_evidence.jsonl"
    footers = {r["page_id"]: r for r in read_jsonl(footer_path)} if footer_path.is_file() else {}
    override_path = evidence_dir / "visual_routing_overrides.jsonl"
    overrides = {}
    if override_path.is_file():
        for row in read_jsonl(override_path):
            if row["page_id"] in overrides: raise ValueError("Duplicate visual routing override")
            if (row.get("route") not in {"auto_vlm", "manual"} or row.get("human_verified") is not False
                    or row.get("reviewer_kind") != "machine_visual_audit" or not row.get("reason")):
                raise ValueError("Visual audit must preserve machine attribution and explicit evidence")
            image = (workspace / row["image_path"]).resolve()
            if not image.is_relative_to(workspace) or sha(image) != row["image_sha256"]:
                raise ValueError("Visual audit image missing or changed")
            overrides[row["page_id"]] = row
    if set(native) != {p["id"] for p in pages}:
        raise ValueError("Native evidence does not cover the immutable page catalogue")
    policy = {"schema": "bkquiz-sft-auto-routing-policy-v1", "revision": REVISION,
              "automatic_stage1_authorized": True, "authorization": {"origin": "user_request", "text": AUTHORIZATION},
              "manual_target_below": 500, "manual_queue_is_not_capped": True,
              "ocr_confidence_is_vlm_failure_probability": False,
              "human_decisions_take_precedence": True, "round2_human_review_required": True,
              "native_text_rule": "clean>=180chars,>=20words; zero raster images, no math/visual/color/quizUI/layout dependence; parser precheck",
              "ocr_text_rule": "confidence>=90,>=30words,ge60>=.97,lt40<=.01,ink_coverage>=.97,layout precheck,no MCQ or quizUI",
              "manual_rule": "render/OCR errors, insufficient evidence, weak OCR with degraded pixels, or fewer than6 OCR words; no rank cutoff",
              "native_feature_sha256": sha(evidence_dir / "native_features.jsonl"),
              "extra_pdf_features_sha256": sha(extra_path) if extra_path.is_file() else None,
              "native_footer_evidence_sha256": sha(footer_path) if footer_path.is_file() else None,
              "visual_routing_overrides_sha256": sha(override_path) if override_path.is_file() else None,
              "implementation_sha256": sha(Path(__file__)),
              "completed_ocr_metrics_sha256": sha(metrics_path) if metrics_path.is_file() else None,
              "catalogue_sha256": sha(workspace / "pages.jsonl")}
    policy["policy_id"] = "ocr_auto_20261025_" + hashlib.sha256(canonical(policy).encode()).hexdigest()[:12]
    prepared = []; incomplete = []; versions = Counter()
    for page in pages:
        n = dict(native[page["id"]])
        if n["identity"] != page["identity"]:
            raise ValueError("Native evidence changed: " + page["id"])
        extra = extras.get(page["id"], {})
        if extra.get("identity") == page["identity"] and extra.get("status") == "ok":
            for field in ("annotation_count", "widget_count", "native_emphasis_ratio"):
                n[field] = extra.get(field, 1)
        else:
            n.update(annotation_count=1, widget_count=1, native_emphasis_ratio=1)
        text_path = workspace / n["text_path"]
        potential_text = n.get("native_chars", 0) >= 180 and n.get("image_count", 1) == 0 and text_layout_safe(n, "")
        text = ""
        if potential_text:
            if sha(text_path) != n["text_sha256"]: raise ValueError("Native text changed: " + page["id"])
            if sha(workspace / n["analysis_path"]) != n["analysis_sha256"]: raise ValueError("Native evidence changed: " + page["id"])
            text = text_path.read_text(encoding="utf-8-sig")
        footer = footers.get(page["id"])
        if footer:
            proof_path = (workspace / footer["analysis_path"]).resolve()
            if (footer.get("identity") != page["identity"] or footer.get("source_sha256") != page["source_sha256"]
                    or not proof_path.is_relative_to(workspace) or sha(proof_path) != footer["analysis_sha256"]):
                raise ValueError("Native footer evidence changed: " + page["id"])
            proof = json.loads(proof_path.read_text(encoding="utf-8"))
            if (proof.get("revision") != "native-page-number-footer-v2-separated-template"
                    or proof.get("native_text_file_sha256") != n["text_sha256"]):
                raise ValueError("Native footer proof is incomplete: " + page["id"])
            n.update(footer_text=footer["footer_text"], footer_bbox=footer["footer_bbox"],
                     footer_evidence_path=footer["analysis_path"], footer_evidence_sha256=footer["analysis_sha256"])
        opath = evidence_dir / "ocr" / (page["id"] + ".json")
        if metrics_path.is_file():
            o, osha = probes.get(page["id"], (None, None))
        else:
            obody = opath.read_bytes() if opath.is_file() else None
            o = json.loads(obody) if obody is not None else None
            osha = hashlib.sha256(obody).hexdigest() if obody is not None else None
        if o:
            version = o.get("config", {}).get("version", "unknown"); versions[version] += 1
            if (o.get("page_identity") != page["identity"] or o.get("source_sha256") != page["source_sha256"]
                    or version != "sft-ocr-probe-v3"):
                o = None
            elif o.get("ocr"): o["ocr"].pop("words", None)
        if o is None: incomplete.append(page["id"])
        route, score, reasons = classify(n, o, text)
        override = overrides.get(page["id"])
        if override:
            if override.get("identity") != page["identity"] or override.get("source_sha256") != page["source_sha256"]:
                raise ValueError("Visual routing audit is stale: " + page["id"])
            route = override["route"]
            score = 40 if route == "auto_vlm" else 90
            reasons = [override["reason"], "Đã đối chiếu ảnh gốc bằng kiểm tra thị giác của máy; vẫn cần duyệt câu hỏi ở đợt 2."]
        prepared.append((page, n, o, opath, route, score, reasons, osha if o else None))
    if set(overrides) - {p["id"] for p in pages}: raise ValueError("Visual audit contains unknown page IDs")
    if incomplete and not allow_incomplete:
        raise ValueError(f"OCR evidence incomplete/stale for {len(incomplete)} images; no policy activated")
    # Snapshot identity binds the exact OCR evidence used. Subsequent probes
    # create a new run instead of editing published analysis files.
    evidence_keys = [(p[0]["id"], p[7], p[4], p[5]) for p in prepared]
    run_id = hashlib.sha256(canonical({"policy": policy, "evidence": evidence_keys}).encode()).hexdigest()[:20]
    run = evidence_dir / "routing_runs" / run_id
    run.mkdir(parents=True, exist_ok=True)
    # Analysis bytes do not depend on the policy/run name. Reuse verified
    # content identities from prior snapshots instead of rewriting thousands
    # of unchanged tiny files when only a few audited routes change.
    known_analysis = {}
    for previous in (evidence_dir / "routing_runs").glob("*/routing.jsonl"):
        for previous_row in read_jsonl(previous):
            known_analysis[previous_row["analysis_sha256"]] = previous_row["analysis_path"]
    routes = []
    for page, n, o, opath, route, score, reasons, osha in prepared:
        evidence = {"schema": "bkquiz-page-routing-analysis-v1", "page_id": page["id"], "identity": page["identity"],
                    "source_sha256": page["source_sha256"], "route": route, "risk_score": score,
                    "reasons": reasons, "native_analysis_path": n["analysis_path"], "native_analysis_sha256": n["analysis_sha256"],
                    "native_metrics": {k: v for k, v in n.items() if k not in {"analysis_path", "analysis_sha256"}},
                    "ocr_evidence_path": opath.relative_to(workspace).as_posix() if o else None,
                    "ocr_evidence_sha256": osha,
                    "ocr_metrics": {k: v for k, v in (o or {}).get("ocr", {}).items() if k not in {"words", "text"}},
                    "image_metrics": (o or {}).get("image_metrics", {}), "human_verified": False,
                    "visual_audit": overrides.get(page["id"]),
                    "score_interpretation": "heuristic screening score; not a measured VLM failure probability"}
        analysis_bytes = (json.dumps(evidence, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
        analysis_sha = hashlib.sha256(analysis_bytes).hexdigest()
        reused = known_analysis.get(analysis_sha)
        if reused:
            analysis = workspace / reused
            if sha(analysis) != analysis_sha: raise ValueError("Previous immutable analysis changed")
        else:
            analysis = run / "analysis" / (page["id"] + ".json")
            atomic_bytes(analysis, analysis_bytes)
        row = {"page_id": page["id"], "identity": page["identity"], "policy_id": policy["policy_id"],
               "route": route, "automatic": True, "human_verified": False, "risk_score": score, "reasons": reasons,
               "analysis_path": analysis.relative_to(workspace).as_posix(), "analysis_sha256": analysis_sha}
        if route == "native_text":
            row.update(text_path=n["text_path"], text_sha256=n["text_sha256"])
            for key in ("footer_text", "footer_bbox", "footer_evidence_path", "footer_evidence_sha256"):
                if key in n: row[key] = n[key]
        if route == "ocr_text":
            path = run / "ocr_text" / (page["id"] + ".txt")
            atomic_bytes(path, o["ocr"]["text"].encode("utf-8"))
            row.update(text_path=path.relative_to(workspace).as_posix(), text_sha256=sha(path))
        routes.append(row)
    policy_path = run / "policy.json"; routing_path = run / "routing.jsonl"
    atomic_json(policy_path, policy)
    atomic_bytes(routing_path, ("\n".join(canonical(row) for row in routes) + "\n").encode("utf-8"))
    report = {"schema": "bkquiz-auto-routing-report-v1", "run_id": run_id, "policy_id": policy["policy_id"],
              "pages": len(pages), "routes": dict(Counter(r["route"] for r in routes)),
              "incomplete_ocr": incomplete, "ocr_versions": dict(versions), "automatic_human_events_created": 0,
              "round2_human_review_required": True, "activated": activate, "created_unix": int(time.time()),
              "policy_path": str(policy_path), "routing_path": str(routing_path),
              "manual_target_met_by_machine_routes": sum(r["route"] == "manual" for r in routes) < 500}
    snapshot_report = {k: v for k, v in report.items() if k not in {"created_unix", "activated"}}
    atomic_json(run / "report.json", snapshot_report)
    if activate:
        pointer = {"schema": "bkquiz-sft-auto-routing-pointer-v1", "policy_path": policy_path.relative_to(workspace).as_posix(),
                   "policy_sha256": sha(policy_path), "routing_path": routing_path.relative_to(workspace).as_posix(),
                   "routing_sha256": sha(routing_path)}
        atomic_json(workspace / "auto_routing_current.json", pointer)
    atomic_json(run / "execution_receipts" / (str(time.time_ns()) + ".json"), report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True); parser.add_argument("--activate", action="store_true")
    parser.add_argument("--allow-incomplete", action="store_true")
    args = parser.parse_args(); build(args.workspace, args.evidence_dir, activate=args.activate, allow_incomplete=args.allow_incomplete)
