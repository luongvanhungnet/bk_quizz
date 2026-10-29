"""Source-aware comparisons on one region, without voting or rewriting facts."""
from __future__ import annotations

import copy
import re
import unicodedata
from difflib import SequenceMatcher

from models import canonical_hash

VERSION = "v5-cross-validation-2"
_SUCCESS = {"ok", "success", "completed", "valid"}
_DERIVED = {"machine_revision", "machine_bucket", "proposed_text", "reasons", "risk", "cross_validation"}


def normalize_text(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).split())


def _role(candidate: dict) -> str:
    engine = candidate.get("engine", "").lower()
    evidence = candidate.get("evidence") or {}
    backend = str(candidate.get("backend_family") or (evidence.get("backend_family", "") if isinstance(evidence, dict) else "")).lower()
    if any(part in engine for part in ("qwen", "vlm", "vision_llm")):
        return "vlm"
    if any(part in engine for part in ("formula", "math")):
        return "math_recognition"
    if "table" in engine:
        return "table_recognition"
    if "paddle" in backend or ("docling" in engine and backend == "docling_default_ocr"):
        return "ocr"
    if "ocr" in engine or "paddle" in engine:
        return "ocr"
    if "docling" in engine and (not backend or "native" not in backend):
        return "unknown_parser"
    if "mineru" in engine:
        return "unknown_parser"
    if any(part in engine for part in ("native", "pymupdf", "pptx", "docling")):
        return "native_pdf" if "pptx" not in engine else "pptx"
    return engine


def _family(candidate: dict) -> str:
    evidence = candidate.get("evidence") or {}
    explicit = candidate.get("backend_family") or candidate.get("lineage")
    if isinstance(evidence, dict):
        explicit = explicit or evidence.get("backend_family") or evidence.get("lineage")
    raw = str(explicit).lower() if explicit else _role(candidate)
    if "paddle" in raw:
        return "paddle"
    if raw in {"native_pdf", "pymupdf", "native"} or "docling_native" in raw:
        return "native_pdf"
    return raw


def _corruption(text: str) -> list[str]:
    flags = []
    if "\ufffd" in text:
        flags.append("replacement_character")
    if any(unicodedata.category(c) == "Co" for c in text):
        flags.append("unmapped_private_glyph")
    if any(unicodedata.category(c) == "Cc" and c not in "\n\r\t" for c in text):
        flags.append("control_character")
    if re.search(r"(?:Ã.|Â.|áº|á»){2,}", text):
        flags.append("suspected_mojibake")
    return flags


def _numbers(text: str) -> list[str]:
    return sorted(re.findall(r"(?<![\w.])[+−-]?\d+(?:[.,]\d+)*(?:%|°)?", text))


def _operators(text: str) -> list[str]:
    return sorted(re.findall(r"[+−\-×÷=<>≤≥∑∏∈∉∞∂√^]", text))


def _same_region(candidate: dict, record: dict) -> bool:
    # Missing identity is not a mismatch, but cannot establish agreement (see _region_bound).
    evidence = candidate.get("evidence") or {}
    if not isinstance(evidence, dict):
        return True
    for key in ("region_id", "crop_sha256", "source_sha256", "render_sha256", "context_sha256"):
        expected = record.get("id") if key == "region_id" else record.get(key)
        if evidence.get(key) and expected and evidence[key] != expected:
            return False
    if evidence.get("input_file_sha256") and record.get("crop_sha256") and evidence["input_file_sha256"] != record["crop_sha256"]:
        return False
    return True


def _region_bound(candidate: dict, record: dict) -> bool:
    evidence = candidate.get("evidence") or {}
    if not isinstance(evidence, dict) or not record.get("source_sha256") or evidence.get("source_sha256") != record["source_sha256"]:
        return False
    if not _same_region(candidate, record):
        return False
    region_id = evidence.get("region_id")
    crop = evidence.get("crop_sha256") or evidence.get("input_file_sha256")
    full_slide = record.get("bbox") == [0, 0, 1000, 1000]
    return bool((region_id and region_id == record.get("id"))
                or (crop and crop == record.get("crop_sha256"))
                or (full_slide and evidence.get("render_sha256") and evidence["render_sha256"] == record.get("render_sha256")))


def formula_structure_issues(text: str) -> list[str]:
    """Conservative diagnostics only; never repair a symbol or demand native/LaTeX equality."""
    issues = _corruption(text)
    depth = 0
    for match in re.finditer(r"(?<!\\)[{}]", text):
        depth += 1 if match.group() == "{" else -1
        if depth < 0:
            break
    if depth != 0:
        issues.append("latex_unbalanced_braces")
    normalized = normalize_text(text)
    if re.search(r"(\\(?:frac|dfrac|tfrac|sqrt|sum|prod|int|cdot|times|mathrm|mathcal|operatorname))\s*(?:\1\s*){5,}", normalized):
        issues.append("latex_repeated_command")
    if len(normalized) >= 36:
        # Detect whole-response loops, not legitimate repeated matrix cells or sum terms.
        for count in range(3, 9):
            if len(normalized) % count == 0:
                size = len(normalized) // count
                chunk = normalized[:size]
                if normalized == chunk * count and ("=" in chunk or "\\" in chunk):
                    issues.append("latex_repeated_whole_expression")
                    break
    return sorted(set(issues))


def _priority(candidate: dict, kind: str) -> int:
    family = candidate["_role"]
    if kind in {"diagram", "chart", "image"}:
        order = ["vlm", "pptx", "native_pdf", "ocr"]
    elif kind == "formula":
        order = ["math_recognition", "pptx", "native_pdf", "ocr", "vlm"]
    elif kind == "table":
        order = ["table_recognition", "pptx", "native_pdf", "ocr", "vlm"]
    else:
        order = ["pptx", "native_pdf", "ocr", "vlm"]
    return order.index(family) if family in order else len(order)


def cross_validate(record: dict) -> dict:
    """Return a new record. `trusted` is machine risk, never human verification.

    Native extraction and an independent OCR must agree for low-risk auto-trust.
    VLM prose is assessed as a description, never treated as a transcript vote.
    """
    result = copy.deepcopy(record)
    reasons, usable, rejected, comparisons = [], [], [], []
    candidates = copy.deepcopy(record.get("candidates", []))
    if record.get("native_text") and not any(_role(c) in {"native_pdf", "pptx"} for c in candidates):
        candidates.insert(0, {"engine": "pymupdf_native", "text": record["native_text"], "status": "ok",
                              "evidence": {"source_sha256": record.get("source_sha256"), "region_id": record.get("id"),
                                           "derived_from": "record.native_text"}})
    for index, candidate in enumerate(candidates):
        text = candidate.get("text") or ""
        status = candidate.get("status", "ok")
        faults = formula_structure_issues(text) if _role(candidate) == "math_recognition" else _corruption(text)
        candidate_evidence = candidate.get("evidence") or {}
        if (_role(candidate) == "math_recognition" and isinstance(candidate_evidence, dict)
                and candidate_evidence.get("structural_errors")):
            faults = sorted(set(faults + ["reported_formula_structure_error"]))
        evidence_matches = _same_region(candidate, record)
        region_bound = _region_bound(candidate, record)
        entry = {"candidate_index": index, "engine": candidate.get("engine", "unknown"),
                 "lineage": _family(candidate), "role": _role(candidate), "status": status, "corruption": faults,
                 "source_evidence_matches": evidence_matches, "region_evidence_bound": region_bound}
        if status not in _SUCCESS or not normalize_text(text) or faults or not evidence_matches:
            entry["usable"] = False
            rejected.append(entry)
            if faults:
                reasons.extend("candidate_" + fault for fault in faults)
            if not evidence_matches:
                reasons.append("candidate_source_identity_mismatch")
            continue
        entry["usable"] = True
        candidate["_family"] = _family(candidate)
        candidate["_role"] = _role(candidate)
        candidate["_index"] = index
        candidate["_bound"] = region_bound
        usable.append(candidate)
        comparisons.append(entry)
    kind = record.get("kind", "text")
    context = " ".join(str(record.get(k, "")) for k in ("native_text", "title", "context_text"))
    exercise = bool(record.get("exercise_answer") or re.search(r"\b(?:đáp án|lời giải|solution|answer key)\b", context, re.I))
    math_content = bool(record.get("contains_formula") or re.search(
        r"\\(?:frac|sum|int|sqrt)\b|[∑∏∫√≤≥≠]|[a-zA-Z0-9)]\s*[=<>+−×÷]\s*[a-zA-Z0-9(]|O\s*\([^\n)]{1,50}\)", context))
    high_risk = (record.get("risk") == "high" or kind in {"formula", "table", "diagram", "chart", "code"}
                 or exercise or math_content)
    proposed, selected, matched, conflicts = "", None, [], []
    if usable:
        selected = sorted(usable, key=lambda c: _priority(c, kind))[0]
        proposed = unicodedata.normalize("NFC", selected["text"]).strip()
        transcripts = [c for c in usable if c["_role"] != "vlm"]
        # Compare literal text only for transcript-like records. Math vs LaTeX is not literal agreement.
        if kind in {"text", "code"}:
            for candidate in transcripts:
                if candidate is selected:
                    continue
                similarity = SequenceMatcher(None, normalize_text(proposed), normalize_text(candidate["text"]), autojunk=False).ratio()
                independent = candidate["_family"] != selected["_family"]
                exact = normalize_text(proposed) == normalize_text(candidate["text"])
                roles = {candidate["_role"], selected["_role"]}
                ocr_confirmation = (independent and "ocr" in roles and bool(roles & {"native_pdf", "pptx"})
                                    and candidate["_bound"] and selected["_bound"])
                candidate_evidence = candidate.get("evidence") or {}
                if isinstance(candidate_evidence, dict) and candidate_evidence.get("geometry_status") == "unknown_or_invalid":
                    ocr_confirmation = False
                numeric_conflict = (_numbers(proposed) != _numbers(candidate["text"])
                                    or _operators(proposed) != _operators(candidate["text"]))
                row = {"selected_index": selected["_index"], "other_index": candidate["_index"],
                       "independent": independent, "normalized_exact": exact,
                       "independent_ocr_confirmation": ocr_confirmation,
                       "similarity": round(similarity, 6), "numeric_conflict": numeric_conflict}
                comparisons.append(row)
                if ocr_confirmation and exact:
                    matched.append(row)
                elif not exact:
                    conflicts.append(row)
        if conflicts:
            reasons.append("independent_extractors_disagree")
            if any(c["numeric_conflict"] for c in conflicts):
                reasons.append("numeric_or_sign_disagreement")
        if high_risk:
            reasons.append("high_risk_requires_human_review")
        if math_content:
            reasons.append("mathematical_content_requires_source_review")
        if selected["_role"] == "vlm":
            reasons.append("vlm_description_requires_source_review")
            if re.search(r"(?:không rõ|không đọc|không đủ|mờ|unclear|unreadable|cannot determine|not enough)", proposed, re.I):
                reasons.append("vlm_reports_partial_or_uncertain_observation")
        if not matched and kind in {"text", "code"}:
            reasons.append("no_independent_exact_transcript_confirmation")
        if not selected["_bound"]:
            reasons.append("selected_candidate_region_evidence_unbound")
        bucket = "trusted" if matched and not high_risk and not conflicts and not rejected else "uncertain"
    else:
        pending = record.get("pending_engines") or any(c.get("status") in {"pending", "not_run", "queued"} for c in candidates)
        bucket = "uncertain" if pending else "critical"
        reasons.append("extraction_pending" if pending else "no_usable_extraction")
    if record.get("pending_engines"):
        reasons.append("extractors_pending")
        if bucket == "trusted":
            bucket = "uncertain"
    if record.get("image_quality", {}).get("issue_flags"):
        reasons.append("source_image_quality_requires_review")
        if bucket == "trusted":
            bucket = "uncertain"
    formula_errors = [c for c in candidates if _role(c) == "math_recognition" and c.get("status") not in _SUCCESS | {"pending", "not_run", "queued"}]
    if kind == "formula" and formula_errors:
        reasons.append("extractor_formula_structure_error")
        corrupt = any((c.get("evidence") or {}).get("structural_errors") for c in formula_errors if isinstance(c.get("evidence"), dict))
        if corrupt:
            bucket = "critical"
    if kind == "formula" and any(_role(c) == "math_recognition" and
                                (formula_structure_issues(c.get("text") or "") or
                                 (isinstance(c.get("evidence"), dict) and c["evidence"].get("structural_errors")))
                                for c in candidates):
        bucket = "critical"
        reasons.append("extractor_formula_structure_error")
    if record.get("source_integrity_error"):
        bucket = "critical"
        reasons.append("source_integrity_error")
    if "candidate_source_identity_mismatch" in reasons:
        bucket = "critical"
    result.update({"machine_bucket": bucket, "risk": "high" if high_risk else "low",
                   "proposed_text": proposed, "reasons": sorted(set(reasons)),
                   "cross_validation": {"version": VERSION, "selected_engine": selected.get("engine") if selected else None,
                                        "selected_lineage": selected.get("_family") if selected else None,
                                        "comparisons": comparisons, "rejected_candidates": rejected,
                                        "semantic_verified": False, "policy": "source_aware_no_majority_vote"}})
    # The revision binds all machine input/output and provenance; a second call is stable.
    revision_payload = {k: v for k, v in result.items() if k not in _DERIVED and k not in {"latest_review", "review_decision"}}
    revision_payload.update({k: result[k] for k in ("machine_bucket", "risk", "proposed_text", "reasons", "cross_validation")})
    result["machine_revision"] = canonical_hash(revision_payload)
    return result
