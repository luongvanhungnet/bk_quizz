"""Local, dependency-free human review application for v5 preprocessing.

Run: python review_app.py --run PATH_TO_RUN
The model's proposals remain proposals. ReviewStore owns all verification rules.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import threading
import unicodedata
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import secrets
import sys
import traceback
from urllib.parse import parse_qs, unquote, urlsplit

MAX_BODY = 1024 * 1024
WEB = Path(__file__).resolve().parent / "web"
BUCKETS = {"trusted", "uncertain", "critical"}
DECISIONS = {"approve", "correct", "reject", "defer", "pending"}
SUCCESS = {"ok", "success", "completed", "valid"}
INPUT_METHODS = {"keyboard_up": "approve", "click_approve": "approve", "keyboard_down": "reject",
                 "click_reject": "reject", "click_save_correction": "correct"}


def successful_vlm_candidates(record):
    result = []
    for candidate in record.get("candidates", []):
        engine = str(candidate.get("engine", "")).lower()
        if (any(part in engine for part in ("vlm", "qwen", "vision_llm"))
                and candidate.get("status") in SUCCESS and isinstance(candidate.get("text"), str)
                and candidate["text"].strip()):
            result.append(candidate)
    return result


def review_target(record):
    candidates = successful_vlm_candidates(record)
    if not candidates:
        return None
    # A quick approval may never silently approve a native/OCR proposal instead.
    normalized = lambda text: unicodedata.normalize("NFC", text).strip()
    matches = [c for c in candidates if normalized(c["text"]) == record.get("proposed_text", "")]
    candidate = matches[-1] if matches else candidates[-1]
    fingerprint = hashlib.sha256(json.dumps(candidate, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()
    return {"text": normalized(candidate["text"]), "candidate_sha256": fingerprint,
            "ready": bool(matches), "engine": candidate["engine"]}


def _identifier(value: str) -> str:
    value = unquote(value)
    if not value or len(value) > 200 or any(c in value for c in "/\\\x00"):
        raise ValueError("Invalid record identifier")
    return value


def allowed_roots(run: Path, manifest: dict) -> tuple[Path, ...]:
    """Only trusted manifest configuration may declare external asset roots."""
    roots = [run.resolve()]
    declared = manifest.get("asset_root", [])
    if isinstance(declared, str):
        declared = [declared]
    if not isinstance(declared, list):
        raise ValueError("manifest.asset_root must be a path or list of paths")
    for item in declared:
        candidate = Path(item)
        roots.append((candidate if candidate.is_absolute() else run / candidate).resolve())
    return tuple(roots)


def image_file(run: Path, roots: tuple[Path, ...], record: dict, kind: str) -> tuple[bytes, str]:
    if kind not in {"render", "crop", "context"}:
        raise KeyError("Unknown image kind")
    raw_path = record.get(f"{kind}_path")
    if not isinstance(raw_path, str) or not raw_path:
        raise FileNotFoundError("Image unavailable")
    candidate = Path(raw_path)
    candidate = (candidate if candidate.is_absolute() else run / candidate).resolve()
    if not any(candidate.is_relative_to(root) for root in roots):
        raise PermissionError("Image is outside declared asset roots")
    if candidate.stat().st_size > 50 * 1024 * 1024:
        raise ValueError("Image is too large")
    data = candidate.read_bytes()
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        content_type = "image/png"
    elif data.startswith(b"\xff\xd8\xff"):
        content_type = "image/jpeg"
    elif data.startswith((b"GIF87a", b"GIF89a")):
        content_type = "image/gif"
    elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        content_type = "image/webp"
    else:
        raise ValueError("Only raster images are served")
    expected = record.get(f"{kind}_sha256")
    if expected and not hmac.compare_digest(hashlib.sha256(data).hexdigest(), str(expected)):
        raise RuntimeError("Source image hash mismatch; do not review modified evidence")
    return data, content_type


class ReviewHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], run: Path, store=None, scope="vlm"):
        if scope not in {"vlm", "all"}:
            raise ValueError("Review scope must be vlm or all")
        self.scope = scope
        self.run = Path(run).resolve()
        self.manifest = json.loads((self.run / "manifest.json").read_text(encoding="utf-8"))
        self.asset_roots = allowed_roots(self.run, self.manifest)
        if store is None:
            from review_store import ReviewStore
            store = ReviewStore(self.run)
        self.store = store
        self.csrf_token = secrets.token_urlsafe(32)
        self.action_lock = threading.Lock()
        self.completed_actions = {}
        super().__init__(address, ReviewHandler)

    def inventory(self):
        rows, offset = [], 0
        while True:
            page = self.store.list_records(limit=10000, offset=offset)
            rows.extend(page)
            if len(page) < 10000:
                return rows
            offset += len(page)

    def scoped_record(self, identifier):
        record = self.store.get_record(identifier)
        target = review_target(record)
        if self.scope == "vlm" and target is None:
            raise PermissionError("Record is outside successful VLM review scope")
        return {**record, "review_target": target, "review_scope": self.scope}

    def scoped_rows(self, bucket=None, decision=None):
        rows = self.inventory()
        if self.scope == "vlm":
            rows = [row for row in rows if successful_vlm_candidates(row)]
        return [{**r, "review_target": review_target(r), "review_scope": self.scope} for r in rows
                if (not bucket or r.get("machine_bucket") == bucket)
                and (not decision or r.get("review_decision", "pending") == decision)]

    def scoped_stats(self):
        from collections import Counter
        inventory = self.inventory()
        rows = [r for r in inventory if successful_vlm_candidates(r)] if self.scope == "vlm" else inventory
        success_rows = [r for r in inventory if successful_vlm_candidates(r)]
        attempted = [r for r in inventory if any(any(p in str(c.get("engine", "")).lower()
            for p in ("vlm", "qwen", "vision_llm")) for c in r.get("candidates", []))]
        decisions = Counter(r.get("review_decision", "pending") for r in rows)
        return {"scope": self.scope, "total": len(rows), "source_pdf_pages": self.manifest.get("document", {}).get("pages"),
            "vlm_success_outputs": len(success_rows), "vlm_pages": len({r["page"] for r in success_rows}),
            "buckets": dict(Counter(r.get("machine_bucket", "uncertain") for r in rows)),
            "decisions": dict(decisions), "pending": decisions.get("pending", 0),
            "reviewed": len(rows) - decisions.get("pending", 0),
            "human_verified": sum(bool(r.get("human_verified")) for r in rows),
            "stale_reviews": sum(bool(r.get("review_stale")) for r in rows),
            "diagnostics": {"vlm_attempted_records": len(attempted),
                "vlm_failed_or_empty_records": sum(not successful_vlm_candidates(r) for r in attempted),
                "records_without_vlm_output": len(inventory) - len(attempted)},
            "inventory": self.store.stats()}


class ReviewHandler(BaseHTTPRequestHandler):
    server: ReviewHTTPServer

    def _headers(self, status: int, content_type: str, length: int):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()

    def _send(self, status: int, data: bytes, content_type: str):
        self._headers(status, content_type, len(data))
        self.wfile.write(data)

    def _json(self, status: int, data):
        self._send(status, json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8"), "application/json; charset=utf-8")

    def _host_ok(self) -> bool:
        try:
            host = urlsplit("http://" + self.headers.get("Host", "")).hostname
            return host in {"127.0.0.1", "localhost", "::1"}
        except ValueError:
            return False

    def _safe_error(self, exc: Exception):
        if isinstance(exc, (PermissionError,)):
            self._json(403, {"error": str(exc)})
        elif isinstance(exc, (KeyError, FileNotFoundError)):
            self._json(404, {"error": "Record or source image unavailable"})
        elif isinstance(exc, (ValueError, TypeError)):
            self._json(400, {"error": str(exc)})
        elif isinstance(exc, RuntimeError):
            self._json(409, {"error": str(exc)})
        else:
            traceback.print_exc(file=sys.stderr)
            self._json(500, {"error": "Review failed; inspect server log"})

    def do_GET(self):
        if not self._host_ok():
            return self._json(403, {"error": "Localhost Host header required"})
        try:
            url = urlsplit(self.path)
            if url.path == "/api/bootstrap":
                return self._json(200, {"csrf_token": self.server.csrf_token,
                                        "document": self.server.manifest.get("document", {}), "scope": self.server.scope})
            if url.path == "/api/stats":
                return self._json(200, self.server.scoped_stats())
            if url.path == "/api/records":
                query = parse_qs(url.query)
                bucket = query.get("bucket", [None])[0] or None
                decision = query.get("decision", [None])[0] or None
                if bucket and bucket not in BUCKETS:
                    raise ValueError("Invalid bucket")
                if decision and decision not in DECISIONS:
                    raise ValueError("Invalid decision")
                limit = int(query.get("limit", ["100"])[0])
                offset = int(query.get("offset", ["0"])[0])
                if not 1 <= limit <= 100 or offset < 0:
                    raise ValueError("limit must be 1..100 and offset non-negative")
                records = self.server.scoped_rows(bucket=bucket, decision=decision)
                return self._json(200, {"records": records[offset:offset+limit], "offset": offset,
                    "limit": limit, "total": len(records), "scope": self.server.scope})
            prefix = "/api/record/"
            if url.path.startswith(prefix):
                pieces = url.path[len(prefix):].split("/")
                identifier = _identifier(pieces[0])
                record = self.server.scoped_record(identifier)
                if len(pieces) == 1:
                    return self._json(200, {"record": record, "history": self.server.store.history(identifier)})
                if len(pieces) == 3 and pieces[1] == "image":
                    data, content_type = image_file(self.server.run, self.server.asset_roots, record, pieces[2])
                    return self._send(200, data, content_type)
                raise KeyError("Unknown route")
            # Static assets are an explicit inventory, never a user-supplied path.
            static = {"/": ("index.html", "text/html; charset=utf-8"),
                      "/keyboard.js": ("keyboard.js", "text/javascript; charset=utf-8"),
                      "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                      "/style.css": ("style.css", "text/css; charset=utf-8")}
            if url.path not in static:
                raise KeyError("Unknown route")
            filename, content_type = static[url.path]
            self._send(200, (WEB / filename).read_bytes(), content_type)
        except Exception as exc:
            self._safe_error(exc)

    def do_POST(self):
        if not self._host_ok():
            return self._json(403, {"error": "Localhost Host header required"})
        origin = self.headers.get("Origin")
        if origin and origin != "http://" + self.headers.get("Host", ""):
            return self._json(403, {"error": "Cross-origin writes are disabled"})
        token = self.headers.get("X-Review-Token", "")
        if not hmac.compare_digest(token, self.server.csrf_token):
            return self._json(403, {"error": "Missing or invalid review token"})
        if urlsplit(self.path).path != "/api/review":
            return self._json(404, {"error": "Unknown route"})
        try:
            if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                raise ValueError("application/json required")
            if self.headers.get("Transfer-Encoding"):
                raise ValueError("Transfer-Encoding is not supported")
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= MAX_BODY:
                raise ValueError("Request body must be 1 byte to 1 MiB")
            payload = json.loads(self.rfile.read(size))
            if not isinstance(payload, dict):
                raise ValueError("Expected a JSON object")
            accepted = {"record_id", "reviewer", "decision", "text", "evidence", "expected_revision", "acknowledgement_high_risk",
                        "input_method", "action_id", "expected_candidate_sha256"}
            if set(payload) - accepted:
                raise ValueError("Unknown review fields")
            if not isinstance(payload.get("record_id"), str):
                raise ValueError("record_id required")
            _identifier(payload["record_id"])
            for field in ("reviewer", "decision", "text", "expected_revision"):
                if not isinstance(payload.get(field), str):
                    raise ValueError(f"{field} must be a string")
            if payload["decision"] not in DECISIONS - {"pending"}:
                raise ValueError("Invalid review decision")
            if not payload["reviewer"].strip():
                raise ValueError("A named human reviewer is required")
            if type(payload.get("acknowledgement_high_risk", False)) is not bool:
                raise ValueError("acknowledgement_high_risk must be boolean")
            with self.server.action_lock:
                record = self.server.scoped_record(payload["record_id"])
                method = payload.pop("input_method", None)
                action_id = payload.pop("action_id", None)
                target_sha = payload.pop("expected_candidate_sha256", None)
                if self.server.scope == "vlm":
                    target = record["review_target"]
                    if not target["ready"]:
                        raise RuntimeError("VLM is not the selected proposal; do not approve a native/OCR fallback")
                    if target_sha != target["candidate_sha256"]:
                        raise RuntimeError("VLM candidate changed; reload before reviewing")
                    if INPUT_METHODS.get(method) != payload["decision"]:
                        raise ValueError("An explicit human keyboard/click action is required")
                    if not isinstance(action_id, str) or not 16 <= len(action_id) <= 100:
                        raise ValueError("A unique action_id is required")
                    if payload["decision"] == "approve" and payload["text"] != target["text"]:
                        raise ValueError("Approval must target the displayed VLM text; use Edit for corrections")
                    signature = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
                    if action_id in self.server.completed_actions:
                        old_signature, old_result = self.server.completed_actions[action_id]
                        if signature != old_signature:
                            raise RuntimeError("action_id was already used for another decision")
                        return self._json(200, {"review": old_result, "idempotent_replay": True})
                    payload["evidence"] = (f"review_scope=vlm; input_method={method}; candidate_sha256={target_sha}; "
                        "Explicit UI action recorded. UI instructs the human to compare the source slide before deciding.")
                    payload["acknowledgement_high_risk"] = payload["decision"] in {"approve", "correct"}
                elif not isinstance(payload.get("evidence"), str) or not payload["evidence"].strip():
                    raise ValueError("Source evidence is required in all-record audit mode")
                result = self.server.store.submit(**payload)
                if self.server.scope == "vlm":
                    self.server.completed_actions[action_id] = (signature, result)
                    if len(self.server.completed_actions) > 1000:
                        self.server.completed_actions.pop(next(iter(self.server.completed_actions)))
            self._json(201, {"review": result})
        except Exception as exc:
            self._safe_error(exc)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--host", choices=["127.0.0.1", "localhost"], default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--scope", choices=["vlm", "all"], default="vlm", help="Default: successful nonempty VLM outputs only; all is an explicit audit mode")
    args = parser.parse_args()
    server = ReviewHTTPServer((args.host, args.port), args.run, scope=args.scope)
    print(f"Human review: http://{args.host}:{server.server_port}", flush=True)
    print("Ctrl+C to stop. Decisions are append-only; machine proposals are never auto-verified.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
