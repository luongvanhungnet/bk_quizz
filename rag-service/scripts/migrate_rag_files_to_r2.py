"""Copy durable RAG source files from local storage to Cloudflare R2."""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

from sqlalchemy import select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import Settings  # noqa: E402
from app.db.database import Database  # noqa: E402
from app.db.models import DocumentRecord  # noqa: E402
from app.models.user_context import safe_user_key  # noqa: E402
from app.services.document_object_storage import create_document_object_storage  # noqa: E402


def migrate(*, settings: Settings, dry_run: bool, delete_local: bool) -> dict[str, int]:
    if settings.document_storage_backend != "r2":
        raise RuntimeError("DOCUMENT_STORAGE_BACKEND phải là r2 để chạy migration.")
    database = Database.from_settings(settings)
    database.validate_migrated()
    storage = create_document_object_storage(settings)
    result = {"copied": 0, "existing": 0, "missing": 0}
    try:
        with database.session() as session:
            records = session.scalars(
                select(DocumentRecord)
                .where(DocumentRecord.status != "DELETED")
                .order_by(DocumentRecord.owner_id, DocumentRecord.id)
            ).all()
        for record in records:
            owner_key = safe_user_key(record.owner_id)
            source = (
                settings.user_upload_dir
                / owner_key
                / record.id
                / record.stored_filename
            )
            if storage.exists(owner_key, record.id, record.stored_filename):
                result["existing"] += 1
                continue
            if not source.is_file():
                result["missing"] += 1
                print(f"MISSING document={record.id}")
                continue
            if dry_run:
                result["copied"] += 1
                print(f"COPY document={record.id} bytes={record.file_size}")
                continue
            settings.document_staging_dir.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                dir=settings.document_staging_dir, delete=False, suffix=".migration"
            ) as handle:
                temporary = Path(handle.name)
            try:
                shutil.copy2(source, temporary)
                storage.store(
                    temporary, owner_key, record.id, record.stored_filename
                )
                if not storage.exists(owner_key, record.id, record.stored_filename):
                    raise RuntimeError(f"Không xác minh được object cho document {record.id}.")
                result["copied"] += 1
                if delete_local:
                    source.unlink(missing_ok=True)
            finally:
                temporary.unlink(missing_ok=True)
        return result
    finally:
        close = getattr(storage, "close", None)
        if callable(close):
            close()
        database.dispose()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--delete-local", action="store_true")
    args = parser.parse_args()
    result = migrate(
        settings=Settings(), dry_run=args.dry_run, delete_local=args.delete_local
    )
    print(" ".join(f"{key}={value}" for key, value in result.items()))
    if result["missing"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
