"""Append-only two-round exam review, bound to exact PDF/image/VLM identities.

This module never manufactures human approval. Machine imports, immutable source
catalogues and human review events have separate storage and provenance.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from contextlib import contextmanager
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
import threading
import time
from typing import Any
import uuid
from owner_exclusion import OwnerExclusionPolicy, install_owner_exclusion


HASH_RE = re.compile(r"^[0-9a-f]{64}$")
ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,160}$")


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def page_identity(row: dict) -> str:
    """The exact noncircular catalogue contract shared with the page preparer."""
    return canonical_hash({"source_sha256": row["source_sha256"], "page": row["page"],
                           "bbox": row["bbox"], "tile_index": row.get("tile_index", 0),
                           "render_policy": row.get("render_policy", "sft-page-v1")})


def question_identity(row: dict) -> str:
    if row.get("extraction_origin") in {"native_text", "ocr_text"}:
        return canonical_hash({"page_id": row["page_id"], "text_sha256": row["text_sha256"],
                               "result_sha256": row["result_sha256"], "question": row["question"],
                               "extraction_origin": row["extraction_origin"]})
    return canonical_hash({"page_id": row["page_id"], "image_sha256": row["image_sha256"],
                           "result_sha256": row["result_sha256"], "question": row["question"]})


def _validate_question(value: Any) -> None:
    if not isinstance(value, dict) or not isinstance(value.get("prompt"), str) or not value["prompt"].strip():
        raise ValueError("question requires a nonempty prompt")
    if len(value["prompt"]) > 100000:
        raise ValueError("question prompt is too large")
    if "options" in value:
        if not isinstance(value["options"], list) or len(value["options"]) > 100:
            raise ValueError("question options must be a list with at most 100 entries")
        for option in value["options"]:
            if not isinstance(option, dict) or not isinstance(option.get("text"), str):
                raise ValueError("each question option requires text")
    if "answer" in value and not isinstance(value["answer"], (dict, str, list)):
        raise ValueError("question answer must preserve a structured answer, string or list")
    if "solution" in value and not isinstance(value["solution"], str):
        raise ValueError("question solution must be a string")
    if "flags" in value and (not isinstance(value["flags"], list) or any(not isinstance(v, str) for v in value["flags"])):
        raise ValueError("question flags must be a list of strings")
    canonical(value)  # Reject NaN and values that cannot be represented in JSON.


class SFTReviewStore:
    def __init__(self, workspace: Path | str):
        self.workspace = Path(workspace).resolve()
        self.database = self.workspace / "human_reviews.sqlite3"
        self._catalog_lock = threading.RLock()
        self._hash_lock = threading.RLock()
        self._hash_cache: dict[str, tuple[tuple, str]] = {}
        self._catalog_stamp = None
        self._catalog: dict[str, dict] = {}
        self._routing_lock = threading.RLock()
        self._routing_stamp = None
        self._routing_records: dict[str, dict] = {}
        self._routing_metadata: dict = {}
        self._routing_error: str | None = None
        self._json_by_hash: dict[str, Any] = {}
        self._text_nonempty_by_hash: dict[str, bool] = {}
        self._workspace_paths: dict[str, Path] = {}
        self._image_paths: dict[str, Path] = {}
        self._owner_exclusion_policy = OwnerExclusionPolicy(self.workspace)
        manifest = json.loads((self.workspace / "manifest.json").read_text(encoding="utf-8-sig"))
        if manifest.get("schema") != "bkquiz-sft-review-v1":
            raise ValueError("unsupported SFT review workspace schema")
        self._pages()  # Validate immutable catalogue before creating a database.
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS review_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    stage INTEGER NOT NULL CHECK(stage IN (1,2)),
                    record_id TEXT NOT NULL,
                    review_id TEXT NOT NULL UNIQUE,
                    created_ns INTEGER NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS review_events_record ON review_events(stage,record_id,sequence);
                CREATE TABLE IF NOT EXISTS machine_questions (
                    id TEXT PRIMARY KEY,
                    page_id TEXT NOT NULL,
                    identity TEXT NOT NULL,
                    result_sha256 TEXT NOT NULL,
                    batch_id TEXT NOT NULL,
                    imported_ns INTEGER NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS machine_questions_page ON machine_questions(page_id);
                CREATE TABLE IF NOT EXISTS machine_batches (
                    batch_id TEXT PRIMARY KEY,
                    payload_sha256 TEXT NOT NULL,
                    created_ns INTEGER NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS page_result_versions (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    page_id TEXT NOT NULL,
                    result_sha256 TEXT NOT NULL,
                    batch_id TEXT NOT NULL,
                    created_ns INTEGER NOT NULL,
                    UNIQUE(page_id,result_sha256)
                );
            """)
            for table in ("review_events", "machine_questions", "machine_batches", "page_result_versions"):
                for operation in ("UPDATE", "DELETE"):
                    connection.execute(f"CREATE TRIGGER IF NOT EXISTS {table}_no_{operation.lower()} BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT,'append-only table'); END")

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.database, timeout=30)
        try:
            connection.execute("PRAGMA foreign_keys=ON")
            with connection:
                yield connection
        finally:
            connection.close()

    def _pages(self) -> dict[str, dict]:
        path = self.workspace / "pages.jsonl"
        stamp = (path.stat().st_mtime_ns, path.stat().st_size)
        with self._catalog_lock:
            if stamp != self._catalog_stamp:
                records = {}
                # Iteration uses physical lines, preserving U+2028/U+2029 in strings.
                with path.open(encoding="utf-8-sig") as stream:
                    for number, line in enumerate(stream, 1):
                        if not line.strip():
                            continue
                        row = json.loads(line)
                        identity = row.get("id")
                        if not isinstance(identity, str) or not ID_RE.fullmatch(identity):
                            raise ValueError(f"invalid page ID on line {number}")
                        if identity in records:
                            raise ValueError("duplicate page ID: " + identity)
                        if not isinstance(row.get("page"), int) or isinstance(row["page"], bool) or row["page"] < 1:
                            raise ValueError("invalid source page number")
                        box = row.get("bbox")
                        if not isinstance(box, list) or len(box) != 4 or not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in box):
                            raise ValueError("invalid page bounding box")
                        if box[2] <= box[0] or box[3] <= box[1]:
                            raise ValueError("page bounding box is empty")
                        if not HASH_RE.fullmatch(row.get("source_sha256", "")):
                            raise ValueError("invalid page source hash")
                        if not isinstance(row.get("source_path"), str):
                            raise ValueError("page source_path is required")
                        if not isinstance(row.get("source_id"), str) or not row["source_id"]:
                            raise ValueError("page source_id is required")
                        if row.get("identity") != page_identity(row):
                            raise ValueError("page identity does not match catalogue content: " + identity)
                        records[identity] = row
                self._catalog, self._catalog_stamp = records, stamp
            return self._catalog

    def _hash(self, path: Path) -> str:
        # Boundary-sensitive paths are resolved by their callers. Hashing
        # follows the current file and compares size/mtime/ctime on every use;
        # reopening every parent directory here adds substantial Windows IO.
        path = Path(path).absolute()
        stat = path.stat()
        stamp = (stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
        with self._hash_lock:
            cached = self._hash_cache.get(str(path))
            if cached is None or cached[0] != stamp:
                cached = (stamp, file_sha256(path))
                self._hash_cache[str(path)] = cached
            return cached[1]

    def _image_path(self, page: dict) -> Path:
        if page["id"] in self._image_paths:
            return self._image_paths[page["id"]]
        target = (self.workspace / "assets" / (page["id"] + ".png")).resolve()
        if not target.is_relative_to((self.workspace / "assets").resolve()):
            raise ValueError("image path escapes workspace")
        self._image_paths[page["id"]] = target
        return target

    def _verify_source(self, page: dict) -> None:
        source = Path(page["source_path"])
        if not source.is_file() or self._hash(source) != page["source_sha256"]:
            raise ValueError("stale_source_hash: original PDF is missing or changed")

    def _verify_image(self, page: dict, expected: str) -> Path:
        if not isinstance(expected, str) or not HASH_RE.fullmatch(expected):
            raise ValueError("image_sha256 is required for image approval")
        image = self._image_path(page)
        if not image.is_file() or self._hash(image) != expected:
            raise ValueError("stale_image_hash: rendered image is missing or changed")
        return image

    def _workspace_file(self, value: str) -> Path:
        if not isinstance(value, str) or not value or Path(value).is_absolute():
            raise ValueError("automatic routing paths must be workspace-relative")
        if value in self._workspace_paths:
            return self._workspace_paths[value]
        path = (self.workspace / value).resolve()
        if not path.is_relative_to(self.workspace):
            raise ValueError("automatic routing path escapes workspace")
        self._workspace_paths[value] = path
        return path

    @staticmethod
    def _file_stamp(path: Path) -> tuple:
        stat = path.stat()
        return (stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)

    def _routing(self) -> tuple[dict, dict, str | None]:
        """Read immutable machine routing without ever changing human events."""
        pointer_path = self.workspace / "auto_routing_current.json"
        if not pointer_path.is_file():
            return {}, {}, None
        with self._routing_lock:
            try:
                pointer_stamp = self._file_stamp(pointer_path)
                if self._routing_stamp is not None and pointer_stamp == self._routing_stamp[0]:
                    policy_cached = Path(self._routing_metadata["policy_path"])
                    routing_cached = Path(self._routing_metadata["routing_path"])
                    if (pointer_stamp, self._file_stamp(policy_cached), self._file_stamp(routing_cached)) == self._routing_stamp:
                        return self._routing_records, self._routing_metadata, self._routing_error
                pointer = json.loads(pointer_path.read_text(encoding="utf-8-sig"))
                if not isinstance(pointer, dict) or pointer.get("schema") != "bkquiz-sft-auto-routing-pointer-v1":
                    raise ValueError("unsupported automatic routing pointer")
                policy_path = self._workspace_file(pointer["policy_path"])
                routing_path = self._workspace_file(pointer["routing_path"])
                stamp = (self._file_stamp(pointer_path), self._file_stamp(policy_path), self._file_stamp(routing_path))
                if stamp == self._routing_stamp:
                    return self._routing_records, self._routing_metadata, self._routing_error
                for path, field in [(policy_path, "policy_sha256"), (routing_path, "routing_sha256")]:
                    wanted = pointer.get(field)
                    if not isinstance(wanted, str) or not HASH_RE.fullmatch(wanted) or self._hash(path) != wanted:
                        raise ValueError("automatic routing " + field + " does not match current file")
                policy = json.loads(policy_path.read_text(encoding="utf-8-sig"))
                if (not isinstance(policy, dict) or policy.get("schema") != "bkquiz-sft-auto-routing-policy-v1"
                        or policy.get("automatic_stage1_authorized") is not True
                        or not policy.get("authorization") or not isinstance(policy.get("policy_id"), str)
                        or not ID_RE.fullmatch(policy["policy_id"])):
                    raise ValueError("automatic routing policy lacks explicit user authorization")
                records = {}
                pages = self._pages()
                with routing_path.open(encoding="utf-8-sig") as stream:
                    for line in stream:
                        if not line.strip():
                            continue
                        row = json.loads(line)
                        if not isinstance(row, dict):
                            raise ValueError("automatic routing row must be an object")
                        page_id = row.get("page_id")
                        if page_id not in pages or page_id in records:
                            raise ValueError("automatic routing contains an unknown/duplicate page")
                        if row.get("policy_id") != policy["policy_id"]:
                            raise ValueError("automatic routing policy identity changed")
                        if row.get("route") not in {"native_text", "ocr_text", "auto_vlm", "manual", "blank"}:
                            raise ValueError("unsupported automatic route")
                        if row.get("route") != "manual" and (row.get("automatic") is not True or row.get("human_verified") is not False):
                            raise ValueError("machine route must not impersonate human review")
                        if "risk_score" in row and (type(row["risk_score"]) not in {int, float} or not math.isfinite(row["risk_score"])):
                            raise ValueError("invalid automatic risk score")
                        records[page_id] = row
                metadata = {"policy_id": policy["policy_id"], "policy_sha256": pointer["policy_sha256"],
                            "routing_sha256": pointer["routing_sha256"], "policy_path": str(policy_path),
                            "routing_path": str(routing_path)}
                self._routing_records, self._routing_metadata, self._routing_error = records, metadata, None
                self._routing_stamp = stamp
                return records, metadata, None
            except (OSError, ValueError, KeyError, TypeError) as error:
                # Fail open to the manual queue, never to automatic processing.
                self._routing_stamp = None
                self._routing_records, self._routing_metadata = {}, {}
                self._routing_error = str(error)
                return {}, {}, self._routing_error

    def _verified_json(self, path: Path, expected: str) -> Any:
        if self._hash(path) != expected:
            raise ValueError("automatic evidence hash changed")
        with self._hash_lock:
            if expected not in self._json_by_hash:
                body = path.read_bytes()
                if hashlib.sha256(body).hexdigest() != expected:
                    raise ValueError("automatic evidence changed while being read")
                self._json_by_hash[expected] = json.loads(body.decode("utf-8-sig"))
            return self._json_by_hash[expected]

    def _automatic_route(self, page: dict, routing_snapshot=None, verified_sources=None) -> tuple[dict | None, str | None]:
        records, metadata, error = self._routing() if routing_snapshot is None else routing_snapshot
        if error:
            return None, error
        route = records.get(page["id"])
        if route is None:
            return None, None
        try:
            if route.get("identity") != page["identity"]:
                raise ValueError("automatic routing page identity changed")
            result = dict(route)
            result.update(policy_sha256=metadata["policy_sha256"], routing_sha256=metadata["routing_sha256"],
                          routing_identity=canonical_hash(route))
            if route["route"] == "manual":
                return result, None
            source_key = (page["source_path"], page["source_sha256"])
            if verified_sources is None or source_key not in verified_sources:
                self._verify_source(page)
                if verified_sources is not None: verified_sources.add(source_key)
            evidence_path = self._workspace_file(route["analysis_path"])
            if not isinstance(route.get("analysis_sha256"), str) or not HASH_RE.fullmatch(route["analysis_sha256"]) or self._hash(evidence_path) != route["analysis_sha256"]:
                raise ValueError("automatic analysis evidence is missing or changed")
            evidence = self._verified_json(evidence_path, route["analysis_sha256"])
            if not isinstance(evidence, dict) or evidence.get("page_id") != page["id"] or evidence.get("identity") != page["identity"]:
                raise ValueError("automatic analysis does not belong to this page identity")
            if evidence.get("source_sha256", page["source_sha256"]) != page["source_sha256"]:
                raise ValueError("automatic analysis source hash changed")
            if route["route"] in {"native_text", "ocr_text"}:
                text_path = self._workspace_file(route["text_path"])
                if (not isinstance(route.get("text_sha256"), str) or not HASH_RE.fullmatch(route["text_sha256"])
                        or self._hash(text_path) != route["text_sha256"]):
                    raise ValueError("automatic extracted text is missing or changed")
                with self._hash_lock:
                    if route["text_sha256"] not in self._text_nonempty_by_hash:
                        body = text_path.read_bytes()
                        if hashlib.sha256(body).hexdigest() != route["text_sha256"]:
                            raise ValueError("automatic text changed while being read")
                        self._text_nonempty_by_hash[route["text_sha256"]] = bool(body.decode("utf-8-sig").strip())
                    if not self._text_nonempty_by_hash[route["text_sha256"]]:
                        raise ValueError("automatic extracted text is empty")
                result["source_text_path"] = str(text_path)
            elif route["route"] == "auto_vlm":
                image = self._image_path(page); image_meta = image.with_suffix(".json")
                if image.exists() or image_meta.exists():
                    if not image.is_file() or not image_meta.is_file():
                        raise ValueError("automatic VLM image has incomplete render identity")
                    render = self._verified_json(image_meta, self._hash(image_meta))
                    if (not isinstance(render, dict) or render.get("identity") != page["identity"] or render.get("source_sha256") != page["source_sha256"]
                            or render.get("sha256") != self._hash(image)):
                        raise ValueError("automatic VLM cached image changed")
                    result.update(image_sha256=render["sha256"], image_path=str(image))
            return result, None
        except (OSError, ValueError, KeyError, TypeError) as error:
            return None, str(error)

    @staticmethod
    def _latest_in(connection: sqlite3.Connection, stage: int) -> dict[str, dict]:
        rows = connection.execute("SELECT e.sequence,e.payload FROM review_events e JOIN (SELECT record_id,MAX(sequence) s FROM review_events WHERE stage=? GROUP BY record_id) x ON e.sequence=x.s", (stage,)).fetchall()
        return {row["record_id"]: dict(row, sequence=sequence) for sequence, payload in rows for row in [json.loads(payload)]}

    def _latest(self, stage: int) -> dict[str, dict]:
        with self._connect() as connection:
            return self._latest_in(connection, stage)

    def owner_exclusion_snapshot(self) -> dict:
        records, metadata, error = self._owner_exclusion_policy.load()
        return dict(metadata, error=error, excluded_items=len(records) if error is None else None)

    def _decorate_page(self, page: dict, last: dict | None, routing_snapshot=None, verified_sources=None, owner_snapshot=None) -> dict:
        row = dict(page)
        excluded, exclusion, exclusion_error = self._owner_exclusion_policy.lookup(page, owner_snapshot)
        if excluded is not None or exclusion_error is not None:
            # Export permission is distinct from historical human review. The
            # owner's later instruction revokes processing even after approval.
            row.update(latest_review=last, effective_review=None, status="excluded", human_verified=False,
                       review_stale=bool(last and last.get("identity") != page["identity"]),
                       historical_review_decision=last.get("decision") if last else None,
                       manual_review_required=False, export_excluded=True, review_origin="owner_exclusion_policy",
                       owner_exclusion_policy_id=exclusion.get("policy_id"), owner_exclusion_policy_sha256=exclusion.get("policy_sha256"),
                       owner_exclusion_ledger_sha256=exclusion.get("ledger_sha256"))
            if exclusion_error is not None:
                row["owner_exclusion_error"] = exclusion_error
                row["exclusion_reason"] = "owner_exclusion_invalid_fail_closed"
            else:
                row["exclusion_reason"] = excluded["reason"]
            return row
        current = bool(last and last.get("identity") == page["identity"])
        asset_error = None
        if current and last["decision"] == "approve":
            try:
                self._verify_source(page)
                self._verify_image(page, last.get("image_sha256"))
            except (ValueError, OSError) as error:
                asset_error = str(error)
                current = False
        row.update(latest_review=last, effective_review=last if current else None,
                   status=last["decision"] if current else "stale" if last else "pending",
                   review_stale=bool(last and not current), human_verified=bool(current and last["decision"] == "approve"))
        if current and last["decision"] == "approve":
            row.update(image_sha256=last["image_sha256"], image_path=str(self._image_path(page)))
        if asset_error:
            row["asset_error"] = asset_error
        automatic, routing_error = self._automatic_route(page, routing_snapshot, verified_sources)
        if automatic is not None:
            row.update(automatic_routing=automatic, routing_policy_id=automatic["policy_id"],
                       routing_policy_sha256=automatic["policy_sha256"], routing_identity=automatic["routing_identity"])
        if routing_error:
            row["machine_routing_error"] = routing_error
        # Every existing human event takes precedence, even if it now needs
        # review again. Machine routing cannot turn an explicit defer/reject or
        # an old human approval into a fresh human approval.
        if last is None and automatic is not None and automatic["route"] != "manual":
            route = automatic["route"]
            status = "auto_text" if route in {"native_text", "ocr_text"} else "auto_vlm" if route == "auto_vlm" else "auto_blank"
            row.update(status=status, automatic=True, review_origin="automatic_policy", human_verified=False)
            for field in ("image_sha256", "image_path", "source_text_path", "text_sha256"):
                if field in automatic:
                    row[field] = automatic[field]
        row["manual_review_required"] = row["status"] in {"pending", "defer", "stale"}
        return row

    def get_page(self, identity: str) -> dict:
        page = self._pages().get(identity)
        if page is None:
            raise KeyError(identity)
        return self._decorate_page(page, self._latest(1).get(identity))

    @staticmethod
    def _matches_status(row: dict, status: str | None) -> bool:
        if status in (None, "", "all"):
            return True
        if status == "pending":
            return row["status"] in {"pending", "defer", "stale"}
        return row["status"] == status

    @staticmethod
    def _paginate(rows: list[dict], limit: int, offset: int) -> dict:
        if isinstance(limit, bool) or isinstance(offset, bool) or not 1 <= int(limit) <= 10000 or int(offset) < 0:
            raise ValueError("invalid pagination")
        return {"items": rows[int(offset):int(offset) + int(limit)], "total": len(rows), "limit": int(limit), "offset": int(offset)}

    def list_pages(self, course: str = "", status: str = "pending", reason: str = "", limit: int = 50, offset: int = 0) -> dict:
        if status not in {None, "", "all", "pending", "approve", "reject", "defer", "stale", "auto_text", "auto_vlm", "auto_blank", "excluded"}:
            raise ValueError("unknown page status")
        latest = self._latest(1)
        routing_snapshot = self._routing(); verified_sources = set()
        owner_snapshot = self._owner_exclusion_policy.load()
        rows = [self._decorate_page(page, latest.get(page["id"]), routing_snapshot, verified_sources, owner_snapshot) for page in self._pages().values()
                if not course or page.get("course") == course]
        rows = [r for r in rows if self._matches_status(r, status) and (not reason or reason in r.get("reasons", []))]
        return self._paginate(rows, limit, offset)

    @staticmethod
    def _progress(rows: list[dict], stage: int) -> dict:
        counts = Counter(r["status"] for r in rows)
        result = {"total": len(rows), "counts": dict(counts), "pending": sum(counts[s] for s in ("pending", "defer", "stale")),
                  "approved": counts["approve"] + counts["correct"], "rejected": counts["reject"],
                  "deferred": counts["defer"], "stale": counts["stale"], "blocked": counts["blocked"],
                  "superseded": counts["superseded"], "completed": counts["approve"] + counts["correct"] + counts["reject"]}
        result["excluded"] = counts["excluded"]
        if stage == 1:
            result.update(manual_pending=result["pending"], automatic_text=counts["auto_text"],
                          automatic_vlm=counts["auto_vlm"], automatic_blank=counts["auto_blank"],
                          automatic_total=sum(counts[s] for s in ("auto_text", "auto_vlm", "auto_blank")),
                          vlm_eligible=counts["approve"] + counts["auto_vlm"])
            result["completed"] += result["automatic_total"] + counts["excluded"]
        courses = defaultdict(Counter)
        for row in rows:
            courses[row.get("course", "")][row["status"]] += 1
            courses[row.get("course", "")]["total"] += 1
        result["courses"] = {name: dict(values) for name, values in sorted(courses.items())}
        result["stage"] = stage
        return result

    def page_progress(self) -> dict:
        latest = self._latest(1)
        routing_snapshot = self._routing(); verified_sources = set()
        owner_snapshot = self._owner_exclusion_policy.load()
        result = self._progress([self._decorate_page(p, latest.get(p["id"]), routing_snapshot, verified_sources, owner_snapshot) for p in self._pages().values()], 1)
        result["owner_exclusion"] = self.owner_exclusion_snapshot()
        return result

    def _append_event(self, connection, stage: int, identity: str, payload: dict) -> dict:
        payload = dict(payload, stage=stage, record_id=identity, review_id=str(uuid.uuid4()), created_ns=time.time_ns(), reviewer="local_user")
        cursor = connection.execute("INSERT INTO review_events(stage,record_id,review_id,created_ns,payload) VALUES (?,?,?,?,?)",
                                    (stage, identity, payload["review_id"], payload["created_ns"], canonical(payload)))
        return dict(payload, sequence=cursor.lastrowid)

    def decide_page(self, identity: str, decision: str, expected_identity: str, image_sha256: str | None = None, note: str = "") -> dict:
        if decision not in {"approve", "reject", "defer"}:
            raise ValueError("unknown page decision")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            page = self._pages().get(identity)
            if page is None:
                raise KeyError(identity)
            if not expected_identity or expected_identity != page["identity"]:
                raise ValueError("stale_identity: reload the current page before reviewing")
            if self._decorate_page(page, self._latest_in(connection, 1).get(identity)).get("export_excluded"):
                raise ValueError("owner_excluded: change the explicit exclusion policy before reviewing this page")
            self._verify_source(page)
            if decision == "approve":
                self._verify_image(page, image_sha256)
            elif image_sha256:
                self._verify_image(page, image_sha256)
            return self._append_event(connection, 1, identity, {"decision": decision, "identity": page["identity"],
                                      "source_sha256": page["source_sha256"], "image_sha256": image_sha256,
                                      "note": str(note or ""), "human_verified": decision == "approve"})

    def selected_pages(self) -> list[dict]:
        latest = self._latest(1)
        routing_snapshot = self._routing(); verified_sources = set()
        owner_snapshot = self._owner_exclusion_policy.load()
        rows = [self._decorate_page(p, latest.get(p["id"]), routing_snapshot, verified_sources, owner_snapshot) for p in self._pages().values()]
        return [r for r in rows if r["status"] == "approve"]

    def vlm_eligible_pages(self) -> list[dict]:
        """Human permissions plus separately attributed authorized auto routes.

        Unlike selected_pages, an automatic candidate may not have a rendered
        PNG yet. The exporter must render and call verify_vlm_page before use.
        """
        latest = self._latest(1)
        routing_snapshot = self._routing(); verified_sources = set()
        owner_snapshot = self._owner_exclusion_policy.load()
        rows = [self._decorate_page(p, latest.get(p["id"]), routing_snapshot, verified_sources, owner_snapshot) for p in self._pages().values()]
        return [r for r in rows if r["status"] in {"approve", "auto_vlm"}]

    def _assert_routing_snapshot(self, page: dict, routing_policy_id: str | None, routing_identity: str | None,
                                 routing_policy_sha256: str | None = None) -> None:
        if not routing_policy_id or routing_policy_id != page.get("routing_policy_id"):
            raise ValueError("automatic routing policy is no longer current")
        if not routing_identity or routing_identity != page.get("routing_identity"):
            raise ValueError("automatic routing evidence is no longer current")
        if routing_policy_sha256 is not None and routing_policy_sha256 != page.get("routing_policy_sha256"):
            raise ValueError("automatic routing policy hash is no longer current")

    def verify_vlm_page(self, page_id: str, image_sha256: str, routing_policy_id: str | None = None,
                        routing_identity: str | None = None, routing_policy_sha256: str | None = None) -> dict:
        page = self.get_page(page_id)
        if page.get("export_excluded"):
            raise ValueError("owner_excluded: page cannot be used for VLM")
        self._verify_source(page)
        self._verify_image(page, image_sha256)
        if page["status"] == "approve":
            if page.get("image_sha256") != image_sha256:
                raise ValueError("imported image does not match stage1 approval")
            return page
        if page["status"] != "auto_vlm":
            raise ValueError("page is not currently approved for VLM: " + page_id)
        self._assert_routing_snapshot(page, routing_policy_id, routing_identity, routing_policy_sha256)
        if page.get("image_sha256") != image_sha256:
            raise ValueError("automatic VLM image differs from its verified render identity")
        return page

    def verify_text_page(self, page_id: str, text_sha256: str, policy_id: str,
                         routing_identity: str | None = None, routing_policy_sha256: str | None = None) -> dict:
        page = self.get_page(page_id)
        if page.get("export_excluded"):
            raise ValueError("owner_excluded: page cannot be used for text extraction")
        automatic = page.get("automatic_routing", {})
        if page["status"] not in {"auto_text", "approve"} or automatic.get("route") not in {"native_text", "ocr_text"}:
            raise ValueError("page is not currently authorized for automatic text extraction")
        self._assert_routing_snapshot(page, policy_id, routing_identity, routing_policy_sha256)
        if automatic.get("text_sha256") != text_sha256:
            raise ValueError("extracted text does not match automatic routing evidence")
        return page

    def _assert_question_permission(self, question: dict, page: dict, approved: dict) -> None:
        if approved.get("export_excluded"):
            raise ValueError("owner_excluded: source page is excluded by the owner's processing policy")
        origin = question.get("extraction_origin")
        if origin in {"native_text", "ocr_text"}:
            automatic = approved.get("automatic_routing", {})
            if approved["status"] not in {"auto_text", "approve"} or automatic.get("route") != origin:
                raise ValueError("page is not currently authorized for automatic text extraction")
            self._assert_routing_snapshot(approved, question.get("routing_policy_id"), question.get("routing_identity"),
                                          question.get("routing_policy_sha256"))
            if question.get("text_sha256") != automatic.get("text_sha256"):
                raise ValueError("extracted text does not match automatic routing evidence")
            if "source_text_path" in question and Path(question["source_text_path"]).resolve() != Path(automatic["source_text_path"]).resolve():
                raise ValueError("imported source text path differs from routing evidence")
            return
        if approved["status"] not in {"approve", "auto_vlm"}:
            raise ValueError("page is not currently approved for VLM: " + page["id"])
        if question.get("image_sha256") != approved.get("image_sha256") or not approved.get("image_sha256"):
            raise ValueError("imported image does not match stage1 approval")
        if approved["status"] == "auto_vlm":
            self._assert_routing_snapshot(approved, question.get("routing_policy_id"), question.get("routing_identity"),
                                          question.get("routing_policy_sha256"))

    def _normalise_question(self, row: dict, pages: dict[str, dict], page_reviews: dict[str, dict], approved_pages: dict | None = None) -> dict:
        value = dict(row)
        if not isinstance(value.get("id"), str) or not ID_RE.fullmatch(value["id"]):
            raise ValueError("invalid machine question ID")
        page = pages.get(value.get("page_id"))
        if page is None:
            raise ValueError("unknown imported page")
        approved = approved_pages.get(page["id"]) if approved_pages is not None else None
        if approved is None:
            approved = self._decorate_page(page, page_reviews.get(page["id"]))
            if approved_pages is not None:
                approved_pages[page["id"]] = approved
        self._assert_question_permission(value, page, approved)
        if not HASH_RE.fullmatch(value.get("result_sha256", "")):
            raise ValueError("result_sha256 is required for machine result provenance")
        expected_source = {"page_identity": page["identity"], "source_id": page["source_id"],
                           "source_sha256": page["source_sha256"], "page": page["page"], "bbox": page["bbox"]}
        for field, expected_value in expected_source.items():
            if field in value and value[field] != expected_value:
                raise ValueError("imported source provenance mismatch: " + field)
        if "source_path" in value and Path(value["source_path"]).resolve() != Path(page["source_path"]).resolve():
            raise ValueError("imported source provenance mismatch: source_path")
        _validate_question(value.get("question"))
        expected = question_identity(value)
        if value.get("identity") not in (None, expected):
            raise ValueError("machine question identity does not match result content")
        value.update(identity=expected, page_identity=page["identity"], source_id=page["source_id"],
                     source_sha256=page["source_sha256"], source_path=page["source_path"],
                     course=page.get("course", ""), page=page["page"], bbox=page["bbox"])
        return value

    def import_questions(self, rows: list[dict], batch_id: str) -> dict:
        if not isinstance(batch_id, str) or not batch_id.strip() or len(batch_id) > 256:
            raise ValueError("batch_id is required")
        if not isinstance(rows, list) or not rows:
            raise ValueError("successful question import requires at least one question")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            pages = self._pages(); reviews = self._latest_in(connection, 1)
            approved_pages = {}
            values = [self._normalise_question(row, pages, reviews, approved_pages) for row in rows]
            if len({r["id"] for r in values}) != len(values):
                raise ValueError("duplicate question ID inside import")
            payload_sha256 = canonical_hash(sorted(values, key=lambda r: r["id"]))
            previous = connection.execute("SELECT payload_sha256,payload FROM machine_batches WHERE batch_id=?", (batch_id,)).fetchone()
            if previous:
                if previous[0] != payload_sha256:
                    raise ValueError("batch ID conflicts with immutable imported result")
                receipt = json.loads(previous[1])
                return dict(receipt, imported=0, idempotent=True)
            versions = defaultdict(set)
            for row in values:
                versions[row["page_id"]].add(row["result_sha256"])
            if any(len(v) != 1 for v in versions.values()):
                raise ValueError("one import contains conflicting VLM result revisions for the same page")
            existing = {}
            for row in values:
                old = connection.execute("SELECT payload FROM machine_questions WHERE id=?", (row["id"],)).fetchone()
                if old and old[0] != canonical(row):
                    raise ValueError("question ID conflicts with immutable machine result: " + row["id"])
                existing[row["id"]] = bool(old)
            for page_id, result_set in versions.items():
                result_hash = next(iter(result_set))
                current = connection.execute("SELECT result_sha256 FROM page_result_versions WHERE page_id=? ORDER BY sequence DESC LIMIT 1", (page_id,)).fetchone()
                known = connection.execute("SELECT 1 FROM page_result_versions WHERE page_id=? AND result_sha256=?", (page_id, result_hash)).fetchone()
                if known and current and current[0] != result_hash:
                    raise ValueError("stale_result_revision: cannot reactivate an older imported VLM result")
            # A batch can contain many questions per image. Verify each image once
            # up front and once before writes, rather than once per question.
            rechecked = set()
            for row in values:
                marker = (row["page_id"], row.get("extraction_origin"), row.get("text_sha256"), row.get("image_sha256"), row.get("routing_identity"))
                if marker in rechecked:
                    continue
                page = pages[row["page_id"]]
                current_page = self._decorate_page(page, reviews.get(page["id"]))
                self._assert_question_permission(row, page, current_page)
                self._verify_source(page)
                if row.get("extraction_origin") not in {"native_text", "ocr_text"}:
                    self._verify_image(page, row["image_sha256"])
                rechecked.add(marker)
            now = time.time_ns(); imported = 0
            for row in values:
                if not existing[row["id"]]:
                    connection.execute("INSERT INTO machine_questions(id,page_id,identity,result_sha256,batch_id,imported_ns,payload) VALUES (?,?,?,?,?,?,?)",
                                       (row["id"], row["page_id"], row["identity"], row["result_sha256"], batch_id, now, canonical(row)))
                    imported += 1
            for page_id, result_set in versions.items():
                connection.execute("INSERT OR IGNORE INTO page_result_versions(page_id,result_sha256,batch_id,created_ns) VALUES (?,?,?,?)",
                                   (page_id, next(iter(result_set)), batch_id, now))
            receipt = {"batch_id": batch_id, "questions": len(values), "imported": imported,
                       "pages": len(versions), "payload_sha256": payload_sha256, "created_ns": now,
                       "human_review_events_created": 0, "idempotent": False}
            connection.execute("INSERT INTO machine_batches(batch_id,payload_sha256,created_ns,payload) VALUES (?,?,?,?)",
                               (batch_id, payload_sha256, now, canonical(receipt)))
            return receipt

    def import_text_questions(self, rows: list[dict], batch_id: str) -> dict:
        if any(row.get("extraction_origin") not in {"native_text", "ocr_text"} for row in rows):
            raise ValueError("text question import requires native_text or ocr_text origin")
        return self.import_questions(rows, batch_id)

    @staticmethod
    def _questions_in(connection) -> dict[str, dict]:
        return {identity: json.loads(payload) for identity, payload in connection.execute("SELECT id,payload FROM machine_questions ORDER BY imported_ns,id")}

    @staticmethod
    def _versions_in(connection) -> dict[str, str]:
        return dict(connection.execute("SELECT v.page_id,v.result_sha256 FROM page_result_versions v JOIN (SELECT page_id,MAX(sequence) s FROM page_result_versions GROUP BY page_id) x ON v.sequence=x.s"))

    def _decorate_question(self, question: dict, last: dict | None, page_reviews: dict, versions: dict, catalogue: dict | None = None, page_states: dict | None = None) -> dict:
        row = dict(question)
        approved = None
        page = (self._pages() if catalogue is None else catalogue).get(question["page_id"])
        dependency_error = None
        if page is None or page["identity"] != question.get("page_identity"):
            dependency_error = "source page catalogue identity changed"
        else:
            approved = page_states.get(page["id"]) if page_states is not None else None
            if approved is None:
                approved = self._decorate_page(page, page_reviews.get(page["id"]))
                if page_states is not None:
                    page_states[page["id"]] = approved
            try:
                self._assert_question_permission(question, page, approved)
            except (ValueError, OSError, KeyError) as error:
                dependency_error = str(error)
        superseded = versions.get(question["page_id"]) != question["result_sha256"]
        current = bool(last and last.get("identity") == question["identity"] and not dependency_error and not superseded)
        status = "superseded" if superseded else "blocked" if dependency_error else last["decision"] if current else "stale" if last else "pending"
        row.update(status=status, latest_review=last, effective_review=last if current else None,
                   review_stale=bool(last and not current), human_verified=bool(current and last["decision"] in {"approve", "correct"}),
                   accepted_question=last.get("accepted_question") if current and last["decision"] in {"approve", "correct"} else None)
        if dependency_error:
            row["dependency_error"] = dependency_error
        if page is not None and approved is not None and approved.get("export_excluded"):
            row.update(export_excluded=True, manual_review_required=False,
                       owner_exclusion_policy_id=approved.get("owner_exclusion_policy_id"),
                       owner_exclusion_policy_sha256=approved.get("owner_exclusion_policy_sha256"))
        return row

    def get_question(self, identity: str) -> dict:
        with self._connect() as connection:
            questions = self._questions_in(connection)
            if identity not in questions:
                raise KeyError(identity)
            return self._decorate_question(questions[identity], self._latest_in(connection, 2).get(identity),
                                           self._latest_in(connection, 1), self._versions_in(connection))

    def list_questions(self, course: str = "", status: str = "pending", limit: int = 50, offset: int = 0, page_id: str = "") -> dict:
        if status not in {None, "", "all", "pending", "approve", "correct", "reject", "defer", "stale", "blocked", "superseded"}:
            raise ValueError("unknown question status")
        with self._connect() as connection:
            questions = self._questions_in(connection); latest = self._latest_in(connection, 2)
            pages = self._latest_in(connection, 1); versions = self._versions_in(connection)
            catalogue = self._pages()
            page_states = {}
            rows = [self._decorate_question(q, latest.get(q["id"]), pages, versions, catalogue, page_states) for q in questions.values()
                    if (not course or q.get("course") == course) and (not page_id or q["page_id"] == page_id)]
        return self._paginate([r for r in rows if self._matches_status(r, status)], limit, offset)

    def question_progress(self) -> dict:
        with self._connect() as connection:
            questions = self._questions_in(connection); latest = self._latest_in(connection, 2)
            pages = self._latest_in(connection, 1); versions = self._versions_in(connection)
            catalogue = self._pages()
            page_states = {}
            rows = [self._decorate_question(q, latest.get(q["id"]), pages, versions, catalogue, page_states) for q in questions.values()]
        return self._progress(rows, 2)

    def decide_question(self, identity: str, decision: str, expected_identity: str, corrected_question: dict | None = None, note: str = "") -> dict:
        if decision not in {"approve", "correct", "reject", "defer"}:
            raise ValueError("unknown question decision")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            questions = self._questions_in(connection)
            question = questions.get(identity)
            if question is None:
                raise KeyError(identity)
            if not expected_identity or expected_identity != question["identity"]:
                raise ValueError("stale_identity: reload the current VLM result before reviewing")
            current = self._decorate_question(question, self._latest_in(connection, 2).get(identity),
                                             self._latest_in(connection, 1), self._versions_in(connection))
            if current["status"] in {"blocked", "superseded"}:
                raise ValueError("stale_dependency: " + current.get("dependency_error", "a newer VLM result supersedes this question"))
            if decision == "correct":
                _validate_question(corrected_question)
                accepted = corrected_question
            elif decision == "approve":
                if corrected_question is not None and canonical(corrected_question) != canonical(question["question"]):
                    raise ValueError("approve cannot change machine text; use correct")
                accepted = question["question"]
            else:
                if corrected_question is not None:
                    raise ValueError("rejected/deferred decisions cannot change machine text")
                accepted = None
            provenance = {key: question[key] for key in ("image_sha256", "extraction_origin", "text_sha256",
                          "routing_policy_id", "routing_identity", "routing_policy_sha256") if key in question}
            return self._append_event(connection, 2, identity, {"decision": decision, "identity": question["identity"],
                                      "page_id": question["page_id"], "page_identity": question["page_identity"],
                                      **provenance, "result_sha256": question["result_sha256"],
                                      "machine_question": question["question"], "accepted_question": accepted,
                                      "note": str(note or ""), "human_verified": decision in {"approve", "correct"}})

    def history(self, stage: int, identity: str) -> list[dict]:
        if stage not in {1, 2}:
            raise ValueError("unknown review stage")
        with self._connect() as connection:
            rows = connection.execute("SELECT sequence,payload FROM review_events WHERE stage=? AND record_id=? ORDER BY sequence", (stage, identity)).fetchall()
        return [dict(json.loads(payload), sequence=sequence) for sequence, payload in rows]

    def export_approved_questions(self) -> list[dict]:
        with self._connect() as connection:
            questions = self._questions_in(connection); latest = self._latest_in(connection, 2)
            pages = self._latest_in(connection, 1); versions = self._versions_in(connection)
            catalogue = self._pages()
            page_states = {}
            rows = [self._decorate_question(q, latest.get(q["id"]), pages, versions, catalogue, page_states) for q in questions.values()]
        return [r for r in rows if r["human_verified"] and r["status"] in {"approve", "correct"}]

    def progress(self) -> dict:
        return {"stage1": self.page_progress(), "stage2": self.question_progress(), "human_decisions_auto_created": 0}

    overall_progress = progress
