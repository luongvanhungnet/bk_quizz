from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

from PIL import Image

from prepare_review_workspace import canonical, page_identity, prepare_workspace, read_jsonl, tile_boxes
from review_render import RenderError, ReviewRenderer, find_pdftoppm


def put(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(canonical(row) + "\n" for row in rows), encoding="utf-8", newline="\n")


def review_fixture(root: Path) -> tuple[Path, dict]:
    source = root / "source.pdf"
    source.write_bytes(b"immutable PDF fixture; worker mocked")
    row = {"source_id": "source_1", "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
           "source_path": str(source), "relative_path": "source.pdf", "course": "test", "page": 1,
           "bbox": [0.0, 0.0, 612.0, 792.0], "tile_index": 0, "tile_count": 1,
           "render_policy": "sft-page-v1", "reasons": [], "question_ids": [], "native_text_preview": ""}
    row["identity"] = page_identity(row)
    row["id"] = "rp_" + row["identity"][:24]
    workspace = root / "review"
    put(workspace / "pages.jsonl", [row])
    return workspace, row


def fake_worker(request_path: Path) -> dict:
    request = json.loads(request_path.read_text(encoding="utf-8"))
    path = Path(request["output"])
    Image.new("RGB", (25, 30), "white").save(path)
    return {"width": 25, "height": 30, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "engine": "fixture"}


class CatalogPreparationTests(unittest.TestCase):
    def test_union_keeps_each_page_once_and_merges_reasons(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dataset = root / "dataset"
            source = root / "original.pdf"
            source.write_bytes(b"original unchanged source")
            source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
            inventory = {"source_id": "source_1", "path": str(source), "relative_path": "original.pdf",
                         "sha256": source_hash, "course": "test", "page_count": 3}
            put(dataset / "inventory.jsonl", [inventory])
            (dataset / "inventory_summary.json").write_text(json.dumps({"source_root": str(root)}), encoding="utf-8")
            extracted = {"pages": [{"page": i, "width": 600, "height": 800,
                                      "text": "native\u2028text", "lines": []} for i in range(1, 4)]}
            (dataset / "extracted").mkdir()
            (dataset / "extracted/source_1.json").write_text(json.dumps(extracted), encoding="utf-8")
            put(dataset / "pages_review_queue.jsonl", [{"source_id": "source_1", "page": 1, "reason": "ocr_required"}])
            put(dataset / "questions_quarantine.jsonl", [{"id": "question_1", "source_id": "source_1", "pages": [1, 2], "reasons": ["bad_formula"]}])
            put(dataset / "release_excluded.jsonl", [{"id": "question_2", "source_id": "source_1", "pages": [2], "reasons": ["bad_source_key"]}])
            workspace = root / "review"
            report = prepare_workspace(dataset, workspace)
            rows = read_jsonl(workspace / "pages.jsonl")
            self.assertEqual(report["queued_original_pages"], 2)
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["question_ids"], ["question_1"])
            self.assertIn("ocr_required", rows[0]["reasons"])
            self.assertEqual(rows[1]["question_ids"], ["question_1", "question_2"])
            self.assertEqual(rows[0]["native_text_preview"], "native\u2028text")
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), source_hash)
            self.assertEqual(report["human_decisions_auto_created"], 0)
            self.assertFalse(list(workspace.glob("*.sqlite*")))
            before = (workspace / "pages.jsonl").read_bytes()
            prepare_workspace(dataset, workspace)
            self.assertEqual((workspace / "pages.jsonl").read_bytes(), before)

    def test_long_tiles_have_overlap_cover_every_point_and_stay_readable(self):
        boxes = tile_boxes(1440, 60565)
        self.assertGreater(len(boxes), 20)
        self.assertEqual(boxes[0][1], 0)
        self.assertEqual(boxes[-1][3], 60565)
        for index, box in enumerate(boxes):
            self.assertLessEqual((box[3] - box[1]) / (box[2] - box[0]), 1.80001)
            if index:
                self.assertLess(box[1], boxes[index - 1][3])
                self.assertGreater(box[1], boxes[index - 1][1])

    def test_page_identity_is_exact_bound_source_clip_contract(self):
        row = {"source_sha256": "a" * 64, "page": 2, "bbox": [0.0, 10.0, 600.0, 800.0], "tile_index": 1}
        payload = {**row, "render_policy": "sft-page-v1"}
        expected = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        self.assertEqual(page_identity(row), expected)
        changed = {**row, "page": 3}
        self.assertNotEqual(page_identity(row), page_identity(changed))


class LazyRenderingTests(unittest.TestCase):
    def test_desktop_poppler_fallback_does_not_need_codex_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            bundled = home / ".cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/Library/bin/pdftoppm.exe"
            bundled.parent.mkdir(parents=True)
            bundled.write_bytes(b"bundled dependency fixture")
            with patch("review_render.shutil.which", return_value=None), patch("review_render.Path.home", return_value=home):
                self.assertEqual(find_pdftoppm(), str(bundled))

    def test_cache_is_exact_image_identity_and_source_stays_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace, row = review_fixture(Path(tmp))
            renderer = ReviewRenderer(workspace)
            with patch.object(renderer, "_run_worker", side_effect=fake_worker) as worker:
                result = renderer.ensure_image(row)
                self.assertEqual(renderer.ensure_image(row), result)
                self.assertEqual(worker.call_count, 1)
            self.assertTrue(Path(result["path"]).is_file())
            self.assertEqual(Path(row["source_path"]).read_bytes(), b"immutable PDF fixture; worker mocked")

    def test_source_or_cached_image_tampering_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace, row = review_fixture(Path(tmp))
            renderer = ReviewRenderer(workspace)
            with patch.object(renderer, "_run_worker", side_effect=fake_worker):
                result = renderer.ensure_image(row)
            Path(result["path"]).write_bytes(b"tampered")
            with self.assertRaisesRegex(RenderError, "Cached image bytes"):
                renderer.ensure_image(row)
            Path(row["source_path"]).write_bytes(b"source tampered")
            with self.assertRaisesRegex(RenderError, "Original PDF hash"):
                renderer.ensure_image(row)

    def test_invalid_requested_page_cannot_override_catalog_clip_or_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace, row = review_fixture(Path(tmp))
            renderer = ReviewRenderer(workspace)
            for field, value in [("bbox", [0, 0, 10000, 10000]), ("source_path", "other.pdf")]:
                altered = {**row, field: value}
                with self.assertRaisesRegex(RenderError, "differs from immutable"):
                    renderer.ensure_image(altered)

    def test_concurrent_requests_render_same_page_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace, row = review_fixture(Path(tmp))
            renderer = ReviewRenderer(workspace)
            def slow_worker(path):
                time.sleep(.03)
                return fake_worker(path)
            with patch.object(renderer, "_run_worker", side_effect=slow_worker) as worker:
                with ThreadPoolExecutor(max_workers=5) as pool:
                    results = list(pool.map(lambda _: renderer.ensure_image(row), range(5)))
                self.assertEqual(worker.call_count, 1)
                self.assertEqual(len({r["sha256"] for r in results}), 1)

    def test_failure_never_publishes_partial_png_or_human_decision(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace, row = review_fixture(Path(tmp))
            renderer = ReviewRenderer(workspace)
            def fails(path):
                request = json.loads(path.read_text(encoding="utf-8"))
                Path(request["output"]).write_bytes(b"partial")
                raise RenderError("render_timeout", "timed out")
            with patch.object(renderer, "_run_worker", side_effect=fails):
                with self.assertRaisesRegex(RenderError, "timed out"):
                    renderer.ensure_image(row)
            self.assertFalse((workspace / "assets" / (row["id"] + ".png")).exists())
            self.assertFalse(list(workspace.glob("*.sqlite*")))
            self.assertEqual(list((workspace / ".render_tmp").glob("*")), [])
            records = list((workspace / "render_failures").glob("*.json"))
            self.assertEqual(len(records), 1)
            self.assertFalse(json.loads(records[0].read_text())["human_decision_created"])

    def test_timeout_terminates_worker_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace, row = review_fixture(Path(tmp))
            renderer = ReviewRenderer(workspace, timeout=.01)
            with patch("review_render.subprocess.Popen") as popen, patch.object(renderer, "_terminate") as terminate:
                process = popen.return_value
                process.communicate.side_effect = [subprocess.TimeoutExpired("worker", .01), (b"", b"")]
                with self.assertRaisesRegex(RenderError, "exceeded"):
                    renderer._run_worker(Path(tmp) / "request.json")
                terminate.assert_called_once_with(process)


if __name__ == "__main__":
    unittest.main()
