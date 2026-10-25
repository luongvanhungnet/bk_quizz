"""Read-only PDF extraction with page geometry and reproducible source hashes."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import unicodedata

import pymupdf


def dump(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize(text: str) -> str:
    return unicodedata.normalize("NFC", text).replace("\x00", "").strip()


def extract(source: Path, root: Path, out: Path) -> dict:
    digest = hashlib.file_digest(source.open("rb"), "sha256").hexdigest()
    source_id = "exam_" + digest[:16]
    relative = source.relative_to(root).as_posix()
    target = out / "extracted" / f"{source_id}.json"
    if target.exists():
        old = json.loads(target.read_text(encoding="utf-8"))
        if old["sha256"] == digest and old["relative_path"] == relative:
            return {k: v for k, v in old.items() if k != "pages"}
    result = {"source_id": source_id, "relative_path": relative,
              "path": str(source.resolve()), "sha256": digest,
              "bytes": source.stat().st_size,
              "course": source.stem.split(" - ")[0], "pages": []}
    try:
        with pymupdf.open(source) as document:
            result["page_count"] = len(document)
            for index, page in enumerate(document):
                lines = []
                for block in page.get_text("dict", flags=pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES)["blocks"]:
                    if block["type"] != 0:
                        continue
                    for line in block["lines"]:
                        spans = [{"text": normalize(span["text"]),
                                  "color": span["color"], "flags": span["flags"],
                                  "font": span["font"], "size": round(span["size"], 2),
                                  "bbox": [round(x, 2) for x in span["bbox"]]}
                                 for span in line["spans"]]
                        lines.append({"text": normalize("".join(s["text"] for s in line["spans"])),
                                      "bbox": [round(x, 2) for x in line["bbox"]], "spans": spans})
                images = [{"bbox": [round(x, 2) for x in item["bbox"]],
                           "width": item["width"], "height": item["height"]}
                          for item in page.get_image_info()]
                annotations = []
                for annotation in page.annots() or []:
                    annotations.append({"type": annotation.type[1],
                                        "bbox": list(annotation.rect),
                                        "colors": annotation.colors,
                                        "content": annotation.info.get("content", "")})
                text = normalize(page.get_text(sort=True))
                result["pages"].append({"page": index + 1, "width": page.rect.width,
                                        "height": page.rect.height, "text": text,
                                        "raw_text": normalize(page.get_text()),
                                        "lines": lines, "images": images,
                                        "annotations": annotations,
                                        "drawing_count": len(page.get_drawings())})
        result["native_chars"] = sum(len(p["text"]) for p in result["pages"])
        result["low_text_pages"] = sum(len(re.sub(r"\s", "", p["text"])) < 80 for p in result["pages"])
        result["status"] = "extracted"
        dump(target, result)
    except Exception as error:
        result.update(status="error", error=f"{type(error).__name__}: {error}")
        dump(target, result)
    return {k: v for k, v in result.items() if k != "pages"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--single", type=Path)
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()
    if args.single:
        extract(args.single, args.source, args.out)
        return
    args.out.mkdir(parents=True, exist_ok=True)
    sources = sorted(p for p in args.source.rglob("*") if p.is_file())
    records = []
    for index, source in enumerate(sources, 1):
        if source.suffix.lower() == ".pdf":
            with source.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            source_id = "exam_" + digest[:16]
            target = args.out / "extracted" / (source_id + ".json")
            if not target.exists():
                try:
                    process = subprocess.Popen([sys.executable, "-X", "utf8", str(Path(__file__).resolve()),
                                                "--source", str(args.source), "--out", str(args.out),
                                                "--single", str(source)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    try:
                        _, stderr = process.communicate(timeout=args.timeout)
                    except subprocess.TimeoutExpired:
                        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True)
                        process.communicate()
                        raise
                    if stderr:
                        (args.out / "logs").mkdir(exist_ok=True)
                        (args.out / "logs" / (source_id + ".stderr.log")).write_bytes(stderr)
                    if process.returncode or not target.exists():
                        raise RuntimeError(f"PDF worker exited {process.returncode}")
                except (subprocess.TimeoutExpired, RuntimeError) as error:
                    with pymupdf.open(source) as pdf:
                        pages = len(pdf)
                    dump(target, {"source_id":source_id,"relative_path":source.relative_to(args.source).as_posix(),
                                  "path":str(source.resolve()),"sha256":digest,"bytes":source.stat().st_size,
                                  "course":source.stem.split(" - ")[0],"page_count":pages,
                                  "status":"extraction_timeout" if isinstance(error,subprocess.TimeoutExpired) else "error",
                                  "error":str(error),"pages":[]})
            cached = json.loads(target.read_text(encoding="utf-8"))
            record = {k:v for k,v in cached.items() if k!="pages"}
        else:
            record = {"relative_path": source.relative_to(args.source).as_posix(), "status": "unsupported"}
        records.append(record)
        if index % 20 == 0 or index == len(sources):
            print(json.dumps({"done": index, "total": len(sources), "last": source.name}, ensure_ascii=False), flush=True)
    (args.out / "inventory.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
    stats = {"source_root": str(args.source.resolve()), "files": len(records),
             "statuses": dict(Counter(r["status"] for r in records)),
             "pages": sum(r.get("page_count", 0) for r in records),
             "native_chars": sum(r.get("native_chars", 0) for r in records),
             "low_text_pages": sum(r.get("low_text_pages", 0) for r in records),
             "courses": dict(sorted(Counter(r.get("course", "unknown") for r in records).items()))}
    dump(args.out / "inventory_summary.json", stats)
    print(json.dumps(stats, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
