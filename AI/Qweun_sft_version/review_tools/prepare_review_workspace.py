"""Prepare immutable page-image review metadata from all unresolved SFT inputs.

This reads the existing release and original PDFs without changing either. PNGs
are generated lazily by review_render.py after a reviewer opens a page.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path

import pymupdf


RENDER_POLICY = "sft-page-v1"
PREPARATION_REVISION = "sft-review-pages-20261024-v1"


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline=None) as stream:
        return [json.loads(line) for line in stream if line.strip()]


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def page_identity(row: dict) -> str:
    payload = {"source_sha256": row["source_sha256"], "page": row["page"],
               "bbox": row["bbox"], "tile_index": row.get("tile_index", 0),
               "render_policy": row.get("render_policy", RENDER_POLICY)}
    return hashlib.sha256(canonical(payload).encode("utf-8")).hexdigest()


def tile_boxes(width: float, height: float) -> list[list[float]]:
    """Keep ordinary pages whole and overlap tiles on unusually long pages."""
    if not all(math.isfinite(v) and v > 0 for v in [width, height]):
        raise ValueError("Invalid source-page geometry")
    width, height = round(float(width), 4), round(float(height), 4)
    if height / width <= 2.4:
        return [[0.0, 0.0, width, height]]
    tile_height = min(height, width * 1.8)
    overlap = min(tile_height * .12, width * .22)
    step = tile_height - overlap
    boxes = []
    top = 0.0
    while top < height:
        bottom = min(top + tile_height, height)
        # A tiny final strip becomes part of a full final tile, not a new image.
        if height - bottom < tile_height * .2:
            bottom = height
            top = max(0.0, bottom - tile_height)
        box = [0.0, round(top, 4), width, round(bottom, 4)]
        if boxes and box == boxes[-1]:
            break
        boxes.append(box)
        if bottom == height:
            break
        top += step
    return boxes


def _write_immutable(path: Path, contents: bytes) -> None:
    if path.exists():
        if path.read_bytes() != contents:
            raise ValueError(f"Existing immutable review catalog changed: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".preparing")
    temporary.write_bytes(contents)
    temporary.replace(path)


def _preview(page: dict, box: list[float], tile_count: int) -> str:
    if tile_count == 1:
        return page.get("text", page.get("raw_text", ""))[:12000]
    left, top, right, bottom = box
    texts = [line.get("text", "") for line in page.get("lines", [])
             if line["bbox"][0] < right and line["bbox"][2] > left
             and line["bbox"][1] < bottom and line["bbox"][3] > top]
    return "\n".join(texts)[:12000]


def prepare_workspace(dataset: Path, workspace: Path, *, verify_sources: bool = True) -> dict:
    dataset, workspace = dataset.resolve(), workspace.resolve()
    inventory = read_jsonl(dataset / "inventory.jsonl")
    sources = {source["source_id"]: source for source in inventory}
    if len(sources) != len(inventory):
        raise ValueError("Duplicate source IDs in original inventory")
    queued: dict[tuple[str, int], dict] = {}

    def add(source_id: str, page: int, reasons: list[str], question_id: str | None = None) -> None:
        if source_id not in sources:
            raise ValueError("Unrecognized queued source: " + source_id)
        if type(page) is not int or not 1 <= page <= sources[source_id]["page_count"]:
            raise ValueError("Queued source page is out of bounds")
        record = queued.setdefault((source_id, page), {"reasons": set(), "question_ids": set()})
        record["reasons"].update(reason for reason in reasons if reason)
        if question_id:
            record["question_ids"].add(question_id)

    for row in read_jsonl(dataset / "pages_review_queue.jsonl"):
        source_id = row["source_id"]
        page = row.get("page")
        pages = range(1, sources[source_id]["page_count"] + 1) if page is None else [page]
        for index in pages:
            add(source_id, index, [row["reason"]])
    for filename, marker in [("questions_quarantine.jsonl", "question_quarantine"),
                             ("release_excluded.jsonl", "release_exclusion")]:
        for row in read_jsonl(dataset / filename):
            for page in row["pages"]:
                add(row["source_id"], page, [marker] + row.get("reasons", []), row["id"])

    by_source = defaultdict(list)
    for source_id, page in queued:
        by_source[source_id].append(page)
    output = []
    checked_sources = []
    for source_number, source in enumerate(inventory, 1):
        source_id = source["source_id"]
        if source_id not in by_source:
            continue
        if verify_sources:
            actual = sha256(Path(source["path"]))
            if actual != source["sha256"]:
                raise ValueError("Original PDF changed: " + source["path"])
            checked_sources.append(source_id)
        extracted_path = dataset / "extracted" / (source_id + ".json")
        extracted = json.loads(extracted_path.read_text(encoding="utf-8"))
        extracted_pages = {p["page"]: p for p in extracted["pages"]}
        fallback_pdf = None
        try:
            for page_number in sorted(by_source[source_id]):
                metadata = queued[(source_id, page_number)]
                native = extracted_pages.get(page_number)
                if native is None:
                    # Header geometry is cheap even for the giant scrolling PDF;
                    # do not retry its expensive text extraction here.
                    if fallback_pdf is None:
                        fallback_pdf = pymupdf.open(source["path"])
                    rect = fallback_pdf[page_number - 1].rect
                    native = {"width": rect.width, "height": rect.height, "text": "", "lines": []}
                boxes = tile_boxes(native["width"], native["height"])
                for tile_index, box in enumerate(boxes):
                    row = {"source_id": source_id, "source_sha256": source["sha256"],
                           "source_path": source["path"], "relative_path": source["relative_path"],
                           "course": source["course"], "page": page_number,
                           "source_pages": source["page_count"], "bbox": box,
                           "source_width": float(native["width"]), "source_height": float(native["height"]),
                           "tile_index": tile_index, "tile_count": len(boxes),
                           "reasons": sorted(metadata["reasons"]), "question_ids": sorted(metadata["question_ids"]),
                           "native_text_preview": _preview(native, box, len(boxes)),
                           "render_policy": RENDER_POLICY, "preparation_revision": PREPARATION_REVISION}
                    if len(boxes) > 1:
                        row["reasons"] = sorted(set(row["reasons"]) | {"long_page_tiled"})
                    row["identity"] = page_identity(row)
                    row["id"] = "rp_" + row["identity"][:24]
                    output.append(row)
        finally:
            if fallback_pdf is not None:
                fallback_pdf.close()
        if source_number % 40 == 0:
            print(canonical({"sources_seen": source_number, "review_images": len(output)}), flush=True)

    if len({row["id"] for row in output}) != len(output):
        raise ValueError("Duplicate prepared page-image identity")
    lines = "".join(canonical(row) + "\n" for row in output).encode("utf-8")
    manifest = {"schema": "bkquiz-sft-review-v1", "preparation_revision": PREPARATION_REVISION,
                "workspace": str(workspace), "dataset_path": str(dataset),
                "source_root": json.loads((dataset / "inventory_summary.json").read_text(encoding="utf-8"))["source_root"],
                "render_policy": RENDER_POLICY, "render_max_edge": 2400,
                "rendering": "lazy bounded worker; no human decision is auto-created",
                "catalog_sha256": hashlib.sha256(lines).hexdigest(),
                "original_sources": len(inventory), "queued_sources": len(by_source),
                "queued_original_pages": len(queued), "review_images": len(output),
                "tiled_original_pages": len({(r["source_id"], r["page"]) for r in output if r["tile_count"] > 1}),
                "extra_tiles": len(output) - len(queued),
                "courses": dict(sorted(Counter(row["course"] for row in output).items())),
                "reasons": dict(sorted(Counter(reason for row in output for reason in row["reasons"]).items())),
                "input_files_sha256": {name: sha256(dataset / name) for name in ["inventory.jsonl", "pages_review_queue.jsonl", "questions_quarantine.jsonl", "release_excluded.jsonl"]},
                "source_sha256_checked": len(checked_sources), "human_decisions_auto_created": 0}
    _write_immutable(workspace / "pages.jsonl", lines)
    _write_immutable(workspace / "manifest.json", (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    report = prepare_workspace(args.dataset, args.workspace)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
