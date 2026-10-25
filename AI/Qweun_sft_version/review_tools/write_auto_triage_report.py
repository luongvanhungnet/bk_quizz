"""Verify the applied routing against real data without making review choices."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

from colab_runtime.runtime import atomic_json, atomic_bytes
from sft_review_store import SFTReviewStore, file_sha256


def verify(workspace):
    workspace = Path(workspace).resolve()
    store = SFTReviewStore(workspace)
    manifest = json.loads((workspace / "manifest.json").read_text(encoding="utf-8"))
    pointer = json.loads((workspace / "auto_routing_current.json").read_text(encoding="utf-8"))
    for field in ("policy", "routing"):
        path = (workspace / pointer[field + "_path"]).resolve()
        if not path.is_relative_to(workspace) or file_sha256(path) != pointer[field + "_sha256"]:
            raise ValueError("Applied routing snapshot changed")
    pages = store.list_pages(status="all", limit=10000)["items"]
    progress = store._progress(pages, 1)
    baseline = json.loads((workspace / "auto_triage_20261025/HUMAN_REVIEWS_BEFORE_AUTO_TRIAGE.json").read_text(encoding="utf-8"))
    with sqlite3.connect(store.database) as connection:
        events = [list(row) for row in connection.execute("SELECT sequence,stage,record_id,payload FROM review_events ORDER BY sequence")]
    history_preserved = events[:len(baseline["events"])] == baseline["events"]
    release = Path(manifest["dataset_path"])
    frozen_manifest = json.loads((release / "release_manifest.json").read_text(encoding="utf-8"))
    frozen_errors = [name for name, expected in frozen_manifest["files_sha256"].items()
                     if not (release / name).is_file() or file_sha256(release / name) != expected]
    machine_errors = [{"page_id": p["id"], "error": p["machine_routing_error"]} for p in pages if p.get("machine_routing_error")]
    manual = [{"page_id": p["id"], "identity": p["identity"], "course": p["course"], "relative_path": p["relative_path"],
               "page": p["page"], "bbox": p["bbox"], "status": p["status"],
               "automatic_routing": p.get("automatic_routing"), "human_review": p.get("effective_review")}
              for p in pages if p["manual_review_required"]]
    manual_path = workspace / "auto_triage_20261025/manual_review_queue.jsonl"
    atomic_bytes(manual_path, ("\n".join(json.dumps(row, ensure_ascii=False) for row in manual) + ("\n" if manual else "")).encode("utf-8"))
    native = sum(p.get("automatic_routing", {}).get("route") == "native_text" and p["status"] == "auto_text" for p in pages)
    ocr = sum(p.get("automatic_routing", {}).get("route") == "ocr_text" and p["status"] == "auto_text" for p in pages)
    report = {"schema": "bkquiz-auto-triage-validation-v1", "created_utc": datetime.now(timezone.utc).isoformat(),
              "pages": progress, "text_routes": {"native_text": native, "ocr_text": ocr},
              "questions": store.question_progress(), "policy_pointer": pointer,
              "manual_target": 500, "manual_target_met": progress["manual_pending"] < 500,
              "manual_queue_not_capped": True, "manual_queue_path": str(manual_path),
              "catalogue_sha256": file_sha256(workspace / "pages.jsonl"),
              "catalogue_unchanged": file_sha256(workspace / "pages.jsonl") == manifest["catalog_sha256"],
              "human_history_preserved": history_preserved, "human_events_before": len(baseline["events"]),
              "human_events_now": len(events), "additional_human_events": len(events) - len(baseline["events"]),
              "frozen_release_files_verified": len(frozen_manifest["files_sha256"]), "frozen_release_errors": frozen_errors,
              "machine_routing_errors": machine_errors, "round2_human_approval_required": True,
              "gpu_inference_performed": False, "ocr_confidence_is_vlm_failure_probability": False,
              "invariants_pass": bool(history_preserved and not frozen_errors and not machine_errors
                                      and file_sha256(workspace / "pages.jsonl") == manifest["catalog_sha256"])}
    atomic_json(workspace / "AUTO_TRIAGE_VALIDATION_REPORT.json", report)
    print(json.dumps({k: v for k, v in report.items() if k not in {"pages", "policy_pointer", "machine_routing_errors"}}, ensure_ascii=False, indent=2))
    print(json.dumps({"page_counts": progress["counts"], "machine_routing_errors": len(machine_errors)}, ensure_ascii=False))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args(); verify(args.workspace)
