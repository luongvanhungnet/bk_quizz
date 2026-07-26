import argparse
import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import Settings
from app.db.models import DocumentRecord
from app.models.user_context import safe_user_key
from app.utils.hashing import sha256_file
from app.worker.runtime import worker_runtime


def verify_store(root: Path, expected_owner: str | None = None) -> dict[str, object]:
    pointer = json.loads((root / "active.json").read_text(encoding="utf-8"))
    version = str(pointer["versionId"])
    base = root / "versions" / version
    manifest = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
    chunks = json.loads((base / "chunks.json").read_text(encoding="utf-8"))
    if manifest["vectorsSha256"] != sha256_file(base / "vectors.faiss"):
        raise ValueError(f"vector checksum mismatch: {root.name}")
    if manifest["chunksSha256"] != sha256_file(base / "chunks.json"):
        raise ValueError(f"chunk checksum mismatch: {root.name}")
    if manifest["chunkCount"] != len(chunks):
        raise ValueError(f"chunk count mismatch: {root.name}")
    owner = expected_owner or manifest.get("ownerId")
    if owner and any(chunk.get("ownerId") != owner for chunk in chunks):
        raise ValueError(f"owner mismatch: {root.name}")
    return {"root": str(root), "versionId": version, "chunks": len(chunks)}


def cleanup(root: Path, keep: int) -> int:
    pointer = json.loads((root / "active.json").read_text(encoding="utf-8"))
    active = pointer["versionId"]
    versions = sorted((root / "versions").iterdir(), key=lambda path: path.stat().st_mtime, reverse=True)
    keep_ids = {active, *(path.name for path in versions[:keep])}
    removed = 0
    for path in versions:
        if path.name not in keep_ids:
            shutil.rmtree(path)
            removed += 1
    return removed


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify, rebuild and clean versioned FAISS indexes.")
    parser.add_argument("action", choices=["verify", "rebuild-user", "cleanup", "cleanup-orphans"])
    parser.add_argument("--user-id")
    parser.add_argument("--keep", type=int, default=2)
    parser.add_argument("--retention-hours", type=int, default=24)
    args = parser.parse_args()
    settings = Settings()
    if args.action == "rebuild-user":
        if not args.user_id:
            parser.error("--user-id is required")
        processor, _, _ = worker_runtime()
        processor._documents.rebuild_index(args.user_id)
        return 0
    if args.action == "cleanup-orphans":
        processor, _, _ = worker_runtime()
        database = processor._documents._database
        with database.session() as session:
            expected = {
                (safe_user_key(owner), document_id)
                for owner, document_id in session.query(DocumentRecord.owner_id, DocumentRecord.id).all()
            }
        cutoff = time.time() - args.retention_hours * 3600
        removed = 0
        if settings.user_upload_dir.exists():
            for user_dir in settings.user_upload_dir.iterdir():
                if not user_dir.is_dir():
                    continue
                for child in user_dir.iterdir():
                    if child.name == ".staging":
                        for staged in child.iterdir():
                            if staged.stat().st_mtime < cutoff:
                                staged.unlink()
                                removed += 1
                    elif child.is_dir() and (user_dir.name, child.name) not in expected and child.stat().st_mtime < cutoff:
                        shutil.rmtree(child)
                        removed += 1
        print(json.dumps({"removed": removed}))
        return 0
    roots = []
    if (settings.system_index_dir / "active.json").exists():
        roots.append((settings.system_index_dir, None))
    if settings.user_index_dir.exists():
        roots.extend((path, None) for path in settings.user_index_dir.iterdir() if (path / "active.json").exists())
    if args.action == "verify":
        print(json.dumps([verify_store(root, owner) for root, owner in roots], indent=2))
    else:
        print(json.dumps({str(root): cleanup(root, args.keep) for root, _ in roots}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
