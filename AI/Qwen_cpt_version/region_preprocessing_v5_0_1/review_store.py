"""Local append-only human decisions, bound to exact machine/source revisions."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import uuid
from collections import Counter
from contextlib import contextmanager
from pathlib import Path

from models import canonical_hash


class ReviewStore:
    def __init__(self, run: Path):
        self.run = Path(run).resolve()
        self.database = self.run / "human_reviews.sqlite3"
        self.manifest = json.loads((self.run / "manifest.json").read_text(encoding="utf-8-sig"))
        self._records()  # Fail early before creating a database for an invalid run.
        with self._connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS reviews (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    record_id TEXT NOT NULL,
                    created_ns INTEGER NOT NULL,
                    review_id TEXT UNIQUE NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS reviews_record_idx ON reviews(record_id,sequence);
                CREATE TRIGGER IF NOT EXISTS reviews_no_update BEFORE UPDATE ON reviews
                    BEGIN SELECT RAISE(ABORT,'reviews are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS reviews_no_delete BEFORE DELETE ON reviews
                    BEGIN SELECT RAISE(ABORT,'reviews are append-only'); END;
            """)

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.database, timeout=30)
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            with connection:
                yield connection
        finally:
            connection.close()

    def _records(self) -> dict[str, dict]:
        records = {}
        for line in (self.run / "records.jsonl").read_text(encoding="utf-8-sig").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            if record["id"] in records:
                raise ValueError("duplicate record id: " + record["id"])
            records[record["id"]] = record
        return records

    @staticmethod
    def _identity(record):
        identity = {key: record.get(key) for key in ("id", "machine_revision", "source_sha256", "render_sha256", "crop_sha256", "context_sha256")}
        identity["proposal_sha256"] = canonical_hash(record.get("proposed_text", ""))
        return identity

    def history(self, record_id: str) -> list[dict]:
        if record_id not in self._records():
            raise KeyError(record_id)
        with self._connect() as connection:
            rows = connection.execute("SELECT sequence,payload FROM reviews WHERE record_id=? ORDER BY sequence", (record_id,)).fetchall()
        return [dict(json.loads(payload), sequence=sequence) for sequence, payload in rows]

    def _decorate(self, record: dict, last: dict | None) -> dict:
        record = dict(record)
        current = bool(last and last.get("identity") == self._identity(record))
        record["latest_review"] = last
        record["review_decision"] = last["decision"] if current else "pending"
        record["review_stale"] = bool(last and not current)
        record["human_verified"] = current and last["decision"] in {"approve", "correct"}
        return record

    def _latest(self):
        with self._connect() as connection:
            rows = connection.execute("SELECT r.payload FROM reviews r JOIN (SELECT record_id,MAX(sequence) s FROM reviews GROUP BY record_id) x ON r.sequence=x.s").fetchall()
        return {value["record_id"]: value for (payload,) in rows for value in [json.loads(payload)]}

    def get_record(self, record_id: str) -> dict:
        record = self._records().get(record_id)
        if record is None:
            raise KeyError(record_id)
        return self._decorate(record, self._latest().get(record_id))

    def list_records(self, bucket=None, decision=None, limit=100, offset=0) -> list[dict]:
        if bucket not in {None, "trusted", "uncertain", "critical"}:
            raise ValueError("unknown machine bucket")
        if decision not in {None, "pending", "approve", "correct", "reject", "defer"}:
            raise ValueError("unknown human decision")
        if not 1 <= int(limit) <= 10000 or int(offset) < 0:
            raise ValueError("invalid pagination")
        latest = self._latest()
        rows = [self._decorate(record, latest.get(record["id"])) for record in self._records().values()]
        rows = [row for row in rows if (bucket is None or row.get("machine_bucket") == bucket)
                and (decision is None or row["review_decision"] == decision)]
        return rows[int(offset):int(offset) + int(limit)]

    def _verify_assets(self, record):
        manifest = json.loads((self.run / "manifest.json").read_text(encoding="utf-8-sig"))
        source_sha = manifest.get("document", {}).get("sha256")
        if source_sha and source_sha != record.get("source_sha256"):
            raise ValueError("stale_source_hash: record does not match document manifest")
        for prefix in ("render", "crop", "context"):
            relative, digest = record.get(prefix + "_path"), record.get(prefix + "_sha256")
            if not relative:
                continue
            target = (self.run / relative).resolve()
            if not target.is_relative_to(self.run) or not target.is_file():
                raise ValueError("source asset unavailable or outside run: " + prefix)
            if digest and hashlib.sha256(target.read_bytes()).hexdigest() != digest:
                raise ValueError("stale_source_hash: " + prefix)

    def submit(self, record_id, reviewer, decision, text, evidence, expected_revision,
               acknowledgement_high_risk=False) -> dict:
        reviewer = str(reviewer or "").strip()
        evidence = str(evidence or "").strip()
        if not reviewer:
            raise ValueError("reviewer is required")
        if decision not in {"approve", "correct", "reject", "defer"}:
            raise ValueError("unknown human decision")
        if decision != "defer" and not evidence:
            raise ValueError("source evidence or rejection reason is required")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            record = self._records().get(record_id)
            if record is None:
                raise KeyError(record_id)
            if not expected_revision or expected_revision != record.get("machine_revision"):
                raise ValueError("stale_revision: reload the current machine result before reviewing")
            self._verify_assets(record)
            if decision in {"approve", "correct"} and record.get("risk") == "high" and not acknowledgement_high_risk:
                raise ValueError("high-risk content requires explicit source-check acknowledgement")
            proposed = record.get("proposed_text", "")
            if decision == "approve" and text is not None and text != proposed:
                raise ValueError("approve cannot change text; use correct for an edited transcript")
            accepted_text = proposed if decision == "approve" else str(text or "") if decision == "correct" else ""
            if decision in {"approve", "correct"} and not accepted_text.strip():
                raise ValueError("accepted transcript cannot be empty")
            review = {"review_id": str(uuid.uuid4()), "record_id": record_id, "created_ns": time.time_ns(),
                      "reviewer": reviewer, "decision": decision, "text": str(text or ""),
                      "accepted_text": accepted_text, "evidence": evidence,
                      "acknowledgement_high_risk": bool(acknowledgement_high_risk),
                      "identity": self._identity(record), "machine_revision": record["machine_revision"],
                      "source_sha256": record.get("source_sha256"), "render_sha256": record.get("render_sha256"),
                      "crop_sha256": record.get("crop_sha256"), "machine_bucket": record.get("machine_bucket"),
                      "context_sha256": record.get("context_sha256"),
                      "risk": record.get("risk"), "split": record.get("split"), "group_id": record.get("group_id"),
                      "machine_proposed_text": proposed, "record_snapshot_sha256": canonical_hash(record),
                      "human_verified": decision in {"approve", "correct"},
                      "eligible_for_training": decision in {"approve", "correct"} and record.get("split") == "train"}
            cursor = connection.execute("INSERT INTO reviews(record_id,created_ns,review_id,payload) VALUES (?,?,?,?)",
                                        (record_id, review["created_ns"], review["review_id"], json.dumps(review, ensure_ascii=False, allow_nan=False)))
            review["sequence"] = cursor.lastrowid
            return review

    def stats(self) -> dict:
        latest = self._latest()
        rows = [self._decorate(record, latest.get(record["id"])) for record in self._records().values()]
        buckets = Counter(row.get("machine_bucket", "uncertain") for row in rows)
        decisions = Counter(row["review_decision"] for row in rows)
        return {"total": len(rows), "buckets": dict(buckets), "decisions": dict(decisions),
                "pending": decisions.get("pending", 0), "reviewed": len(rows) - decisions.get("pending", 0),
                "human_verified": sum(bool(row["human_verified"]) for row in rows),
                "eligible_for_training": sum(bool(row["human_verified"]) and row.get("split") == "train" for row in rows),
                "high_risk": sum(row.get("risk") == "high" for row in rows),
                "stale_reviews": sum(bool(row["review_stale"]) for row in rows)}
