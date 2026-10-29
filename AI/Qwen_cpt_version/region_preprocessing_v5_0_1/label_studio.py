"""Offline Label Studio task export/import; no service calls or auto-approval.

The dependency-free review_app.py is the default interface. This optional bridge
uses standard Label Studio JSON tasks and explicit human annotation results.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import quote

from review_app import allowed_roots, image_file

CONFIG = '''<View>
  <Header value="Slide gốc"/><Image name="slide" value="$slide_url"/>
  <Header value="Vùng cần kiểm duyệt"/><Image name="crop" value="$crop_url"/>
  <Header value="Ngữ cảnh (nếu có; nếu không sẽ lặp vùng gốc)"/><Image name="context" value="$context_url"/>
  <Header value="Các kết quả máy (chưa được xác minh)"/>
  <Text name="machine" value="$machine_text"/>
  <TextArea name="final_text" toName="machine" value="$proposed_text" editable="true" transcription="true" rows="10" maxSubmissions="1"/>
  <Choices name="decision" toName="machine" choice="single" required="true">
    <Choice value="approve"/><Choice value="correct"/><Choice value="reject"/><Choice value="defer"/>
  </Choices>
  <TextArea name="evidence" toName="machine" required="true" editable="true" rows="3" maxSubmissions="1" placeholder="Bằng chứng đã đối chiếu với slide gốc"/>
  <Choices name="high_risk_ack" toName="machine" choice="multiple">
    <Choice value="manually_checked_high_risk"/>
  </Choices>
</View>
'''
IDENTITY = ("record_id", "machine_revision", "source_sha256", "render_sha256", "crop_sha256", "context_sha256")


def _records(store):
    offset = 0
    while True:
        page = store.list_records(limit=100, offset=offset)
        yield from page
        if len(page) < 100:
            break
        offset += len(page)


def export_tasks(run: Path, output: Path, store=None) -> dict:
    run, output = Path(run).resolve(), Path(output).resolve()
    if output.exists():
        raise FileExistsError("Choose a new export directory to preserve previous snapshots")
    if store is None:
        from review_store import ReviewStore
        store = ReviewStore(run)
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    roots = allowed_roots(run, manifest)
    output.mkdir(parents=True)
    (output / "assets").mkdir()
    tasks = []
    for index, record in enumerate(_records(store), start=1):
        urls = {}
        for kind in ("render", "crop") + (("context",) if record.get("context_path") else ()):
            image, content_type = image_file(run, roots, record, kind)
            suffix = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "image/gif": ".gif"}[content_type]
            relative = "assets/" + hashlib.sha256(image).hexdigest() + suffix
            path = output / relative
            if not path.exists():
                path.write_bytes(image)
            urls[kind] = "/data/local-files/?d=" + quote(relative, safe="/")
        data = {"record_id": record["id"],
                **{key: record.get(key) for key in IDENTITY if key != "record_id"},
                "slide_url": urls["render"], "crop_url": urls["crop"],
                "context_url": urls.get("context", urls["crop"]),
                "proposed_text": record.get("proposed_text", ""),
                "machine_text": json.dumps({"page": record["page"], "kind": record["kind"],
                    "bucket": record["machine_bucket"], "risk": record["risk"],
                    "native_text": record.get("native_text", ""), "candidates": record.get("candidates", []),
                    "reasons": record.get("reasons", [])}, ensure_ascii=False, indent=2)}
        tasks.append({"id": index, "data": data})
    (output / "tasks.json").write_text(json.dumps(tasks, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "label_config.xml").write_text(CONFIG, encoding="utf-8")
    metadata = {"tasks": len(tasks), "run": str(run), "auto_verified": 0,
                "local_files_document_root": str(output),
                "references": ["https://labelstud.io/tags/textarea.html", "https://labelstud.io/guide/storage_local"]}
    (output / "export_manifest.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return metadata


def _result_fields(results: list) -> dict:
    fields = {}
    for item in results:
        if not isinstance(item, dict):
            raise ValueError("Malformed annotation result")
        name, value = item.get("from_name"), item.get("value", {})
        if name not in {"final_text", "evidence", "decision", "high_risk_ack"}:
            continue
        if name in fields:
            raise ValueError(f"Duplicate annotation field: {name}")
        if not isinstance(value, dict):
            raise ValueError("Malformed annotation value")
        entries = value.get("text" if name in {"final_text", "evidence"} else "choices", [])
        if not isinstance(entries, list) or not all(isinstance(v, str) for v in entries):
            raise ValueError("Annotation values must be strings")
        if name != "high_risk_ack" and len(entries) != 1:
            raise ValueError(f"Exactly one value required for {name}")
        fields[name] = entries if name == "high_risk_ack" else entries[0]
    return fields


def import_annotations(run: Path, source: Path, reviewer: str, store=None) -> dict:
    if not reviewer.strip():
        raise ValueError("A named human reviewer must authorize this import")
    if store is None:
        from review_store import ReviewStore
        store = ReviewStore(Path(run))
    tasks = json.loads(Path(source).read_text(encoding="utf-8"))
    if not isinstance(tasks, list):
        raise ValueError("Expected Label Studio JSON export as a task list")
    report = {"accepted": [], "skipped": [], "errors": [], "auto_verified": 0}
    for task in tasks:
        task_id = task.get("id") if isinstance(task, dict) else None
        try:
            if not isinstance(task, dict) or not isinstance(task.get("data"), dict):
                raise ValueError("Malformed task")
            data = task["data"]
            record = store.get_record(data["record_id"])
            expected = {"record_id": record["id"], **{key: record.get(key) for key in IDENTITY if key != "record_id"}}
            if any(data.get(key) != expected[key] for key in IDENTITY):
                raise ValueError("Source hashes or machine revision do not match the current record")
            annotations = task.get("annotations", [])
            if not isinstance(annotations, list) or not all(isinstance(a, dict) for a in annotations):
                raise ValueError("annotations must be a list of human annotation objects")
            if not annotations:
                report["skipped"].append({"task": task_id, "reason": "No human annotations; predictions are ignored"})
            for annotation in annotations:
                if annotation.get("was_cancelled") or not annotation.get("result"):
                    report["skipped"].append({"task": task_id, "annotation": annotation.get("id"), "reason": "Cancelled or empty annotation"})
                    continue
                if annotation.get("id") is None:
                    raise ValueError("Human annotation ID required for audit and duplicate detection")
                if not isinstance(annotation["result"], list):
                    raise ValueError("Human annotation result must be a list")
                fields = _result_fields(annotation["result"])
                decision = fields.get("decision")
                if decision not in {"approve", "correct", "reject", "defer"}:
                    raise ValueError("Explicit human decision required")
                evidence = fields.get("evidence", "").strip()
                if not evidence:
                    raise ValueError("Human source evidence required")
                text = fields.get("final_text", "")
                if decision in {"approve", "correct"} and not text.strip():
                    raise ValueError("Non-empty reviewed content required")
                if decision == "approve" and text != record.get("proposed_text", ""):
                    raise ValueError("Edited content requires decision=correct")
                marker = f"Label Studio task {task_id} annotation {annotation['id']}; "
                if any(str(row.get("evidence", "")).startswith(marker) for row in store.history(record["id"])):
                    report["skipped"].append({"task": task_id, "annotation": annotation["id"], "reason": "Already imported"})
                    continue
                result = store.submit(record_id=record["id"], reviewer=reviewer.strip(), decision=decision,
                    text=text, evidence=marker + evidence, expected_revision=record["machine_revision"],
                    acknowledgement_high_risk="manually_checked_high_risk" in fields.get("high_risk_ack", []))
                report["accepted"].append({"task": task_id, "annotation": annotation["id"], "review": result})
        except (KeyError, ValueError, TypeError) as exc:
            report["errors"].append({"task": task_id, "error": str(exc)})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    export = sub.add_parser("export")
    export.add_argument("--run", type=Path, required=True)
    export.add_argument("--out", type=Path, required=True)
    load = sub.add_parser("import")
    load.add_argument("--run", type=Path, required=True)
    load.add_argument("--annotations", type=Path, required=True)
    load.add_argument("--reviewer", required=True)
    load.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "export":
        result = export_tasks(args.run, args.out)
    else:
        if args.report.exists():
            raise FileExistsError("Choose a new import report path")
        result = import_annotations(args.run, args.annotations, args.reviewer)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("errors"):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
