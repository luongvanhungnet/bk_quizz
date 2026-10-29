"""Local source-card retrieval, using SQLite FTS5; no external embeddings/service."""
import argparse
import json
from pathlib import Path
import re
import sqlite3
from common import canonical, read_rows


def rebuild(path, facts):
    with sqlite3.connect(path) as db:
        db.execute("DROP TABLE IF EXISTS facts")
        db.execute("CREATE VIRTUAL TABLE facts USING fts5(id UNINDEXED,course UNINDEXED,split UNINDEXED,concept,definition,payload UNINDEXED)")
        db.executemany("INSERT INTO facts VALUES(?,?,?,?,?,?)", [(f["id"], f["course"], f["split"], f["concept"], f["definition"], canonical(f).decode()) for f in facts])


def retrieve(path, query, *, split="train", course=None, limit=4):
    if split not in {"train", "validation", "test"}: raise ValueError("Explicit valid source partition required")
    words = re.findall(r"[^\W_]{2,}", query, re.UNICODE)[:30]
    if not words: return []
    match = " OR ".join('"'+w.replace('"', '""')+'"' for w in words)
    with sqlite3.connect(Path(path).as_uri()+"?mode=ro", uri=True) as db:
        sql = "SELECT payload FROM facts WHERE facts MATCH ? AND split=?"
        args = [match, split]
        if course: sql += " AND course=?"; args.append(course)
        sql += " ORDER BY bm25(facts,0,0,0,3,1,0) LIMIT ?"; args.append(min(limit, 20))
        return [json.loads(row[0]) for row in db.execute(sql, args)]


if __name__ == "__main__":
    p = argparse.ArgumentParser(); p.add_argument("--index", type=Path, required=True); p.add_argument("--query", required=True)
    p.add_argument("--course"); p.add_argument("--split", default="train"); args = p.parse_args()
    print(canonical(retrieve(args.index, args.query, course=args.course, split=args.split)).decode())
