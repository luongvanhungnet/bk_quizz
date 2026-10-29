"""Lazy, identity-bound page rasterization for the two-round exam review UI."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import shutil
import subprocess
import sys
import threading
import uuid

import pymupdf

from prepare_review_workspace import canonical, page_identity, read_jsonl, sha256


class RenderError(RuntimeError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def find_pdftoppm() -> str | None:
    """Desktop launchers do not inherit Codex's injected dependency PATH."""
    executable = shutil.which("pdftoppm")
    if executable:
        return executable
    bundled = Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/Library/bin/pdftoppm.exe"
    return str(bundled) if bundled.is_file() else None


class ReviewRenderer:
    def __init__(self, workspace: Path | str, timeout: float = 45, max_edge: int = 2400):
        self.workspace = Path(workspace).resolve()
        self.timeout = float(timeout)
        self.max_edge = int(max_edge)
        if self.timeout <= 0 or not 128 <= self.max_edge <= 6000:
            raise ValueError("Invalid render limits")
        self.pages = {row["id"]: row for row in read_jsonl(self.workspace / "pages.jsonl")}
        self._locks: dict[str, threading.Lock] = {}
        self._lock = threading.Lock()
        self._capacity = threading.Semaphore(2)

    def _page(self, row: dict) -> dict:
        identity = row.get("id", "")
        if not re.fullmatch(r"rp_[0-9a-f]{24}", identity) or identity not in self.pages:
            raise RenderError("unknown_page", "Unknown page-image ID")
        original = self.pages[identity]
        if page_identity(original) != original.get("identity") or original["id"] != "rp_" + original["identity"][:24]:
            raise RenderError("catalog_identity_changed", "Catalog page identity is not valid")
        for field in ["source_id", "source_sha256", "source_path", "page", "bbox", "tile_index", "render_policy", "identity"]:
            if row.get(field) != original.get(field):
                raise RenderError("page_identity_changed", "Requested page differs from immutable review catalog")
        return original

    def ensure_image(self, page_row: dict) -> dict:
        row = self._page(page_row)
        page_id = row["id"]
        with self._lock:
            lock = self._locks.setdefault(page_id, threading.Lock())
        with lock:
            source = Path(row["source_path"])
            if not source.is_file() or sha256(source) != row["source_sha256"]:
                raise RenderError("source_changed", "Original PDF hash no longer matches the reviewed source")
            assets = self.workspace / "assets"
            image_path, metadata_path = assets / (page_id + ".png"), assets / (page_id + ".json")
            if image_path.exists() or metadata_path.exists():
                if not image_path.is_file() or not metadata_path.is_file():
                    raise RenderError("incomplete_cached_asset", "Cached image has no complete identity proof")
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                if (metadata.get("identity") != row["identity"] or metadata.get("max_edge") != self.max_edge
                        or metadata.get("sha256") != sha256(image_path)):
                    raise RenderError("cached_asset_changed", "Cached image bytes or render identity changed")
                return {"path": str(image_path), "sha256": metadata["sha256"],
                        "width": metadata["width"], "height": metadata["height"]}
            assets.mkdir(parents=True, exist_ok=True)
            work = self.workspace / ".render_tmp"
            work.mkdir(exist_ok=True)
            attempt = page_id + "." + uuid.uuid4().hex
            request_path, temporary_image = work / (attempt + ".json"), work / (attempt + ".png")
            request = {"source_path": str(source), "source_sha256": row["source_sha256"],
                       "page": row["page"], "bbox": row["bbox"], "max_edge": self.max_edge,
                       "engine": "poppler" if "extraction_timeout" in row.get("reasons", []) else "pymupdf",
                       "output": str(temporary_image)}
            request_path.write_text(canonical(request), encoding="utf-8")
            try:
                with self._capacity:
                    result = self._run_worker(request_path)
                if not temporary_image.is_file() or sha256(temporary_image) != result["sha256"]:
                    raise RenderError("invalid_worker_asset", "Renderer did not return an intact image")
                # Recheck after the worker as well, so a source changed mid-render cannot be approved.
                if sha256(source) != row["source_sha256"]:
                    raise RenderError("source_changed", "Source PDF changed during image rendering")
                metadata = {**result, "identity": row["identity"], "source_sha256": row["source_sha256"],
                            "max_edge": self.max_edge, "render_policy": row["render_policy"]}
                metadata_temp = work / (attempt + ".asset.json")
                metadata_temp.write_text(canonical(metadata), encoding="utf-8")
                temporary_image.replace(image_path)
                metadata_temp.replace(metadata_path)
                return {"path": str(image_path), "sha256": result["sha256"],
                        "width": result["width"], "height": result["height"]}
            except Exception as error:
                failures = self.workspace / "render_failures"
                failures.mkdir(exist_ok=True)
                (failures / (attempt + ".json")).write_text(canonical({"page_id": page_id, "identity": row["identity"],
                    "error": str(error), "error_code": getattr(error, "code", type(error).__name__),
                    "human_decision_created": False}), encoding="utf-8")
                raise
            finally:
                for path in work.glob(attempt + ".*"):
                    if path.is_file():
                        path.unlink()

    def _run_worker(self, request_path: Path) -> dict:
        kwargs = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE}
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        else:
            kwargs["start_new_session"] = True
        process = subprocess.Popen([sys.executable, "-X", "utf8", str(Path(__file__).resolve()),
                                    "--worker", str(request_path)], **kwargs)
        try:
            stdout, stderr = process.communicate(timeout=self.timeout)
        except subprocess.TimeoutExpired as error:
            self._terminate(process)
            process.communicate()
            raise RenderError("render_timeout", f"PDF rendering exceeded {self.timeout:g} seconds; source and decisions are unchanged") from error
        if process.returncode:
            raise RenderError("render_worker_failed", stderr.decode("utf-8", errors="replace")[-2000:] or "PDF renderer failed")
        try:
            result = json.loads(stdout.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise RenderError("invalid_worker_response", "PDF renderer returned no valid image metadata") from error
        if not all(field in result for field in ["width", "height", "sha256"]):
            raise RenderError("invalid_worker_response", "Incomplete renderer image metadata")
        return result

    @staticmethod
    def _terminate(process) -> None:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def render_worker(request_path: Path) -> dict:
    request = json.loads(request_path.read_text(encoding="utf-8"))
    source = Path(request["source_path"])
    if sha256(source) != request["source_sha256"]:
        raise ValueError("Source PDF no longer matches expected hash")
    box = request["bbox"]
    if (not isinstance(box, list) or len(box) != 4 or not all(type(v) in [int, float] and math.isfinite(v) for v in box)
            or box[2] <= box[0] or box[3] <= box[1]):
        raise ValueError("Invalid PDF clip geometry")
    with pymupdf.open(source) as document:
        page_number = request["page"]
        if type(page_number) is not int or not 1 <= page_number <= len(document):
            raise ValueError("PDF page is out of range")
        page = document[page_number - 1]
        clip = pymupdf.Rect(box)
        rect = page.rect
        if clip.x0 < rect.x0 - .01 or clip.y0 < rect.y0 - .01 or clip.x1 > rect.x1 + .01 or clip.y1 > rect.y1 + .01:
            raise ValueError("PDF clip escapes source page")
        scale = min(3.0, request["max_edge"] / max(clip.width, clip.height))
        if request.get("engine") == "poppler":
            # The giant Chromium scroll page stalls MuPDF's display-list parser.
            # Poppler clips before rasterization and does not allocate the full strip.
            executable = find_pdftoppm()
            if not executable:
                raise RuntimeError("Bundled pdftoppm is required for this long-page PDF")
            output = Path(request["output"])
            prefix = output.with_suffix("")
            command = [executable, "-f", str(page_number), "-singlefile", "-r", f"{72*scale:.10f}",
                       "-x", str(math.floor(clip.x0*scale)), "-y", str(math.floor(clip.y0*scale)),
                       "-W", str(math.ceil(clip.width*scale)), "-H", str(math.ceil(clip.height*scale)),
                       "-png", str(source), str(prefix)]
            completed = subprocess.run(command, capture_output=True, timeout=35)
            if completed.returncode or not output.is_file():
                raise RuntimeError("Poppler clip failed: " + completed.stderr.decode("utf-8", errors="replace")[-1500:])
            from PIL import Image
            with Image.open(output) as image:
                width, height = image.size
                image.verify()
            return {"width": width, "height": height, "sha256": sha256(output), "engine": "poppler"}
        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), clip=clip, colorspace=pymupdf.csRGB, alpha=False, annots=True)
        data = pixmap.tobytes("png")
        Path(request["output"]).write_bytes(data)
        return {"width": pixmap.width, "height": pixmap.height, "sha256": hashlib.sha256(data).hexdigest(), "engine": "pymupdf"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", type=Path)
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--page-id")
    args = parser.parse_args()
    if args.worker:
        print(canonical(render_worker(args.worker)))
    else:
        renderer = ReviewRenderer(args.workspace)
        row = renderer.pages[args.page_id]
        print(canonical(renderer.ensure_image(row)))


if __name__ == "__main__":
    main()
