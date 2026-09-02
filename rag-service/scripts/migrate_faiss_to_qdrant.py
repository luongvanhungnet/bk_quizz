"""Import versioned FAISS snapshots into Qdrant without re-embedding text."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from sqlalchemy import distinct, select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import Settings
from app.db.database import Database
from app.db.models import DocumentRecord, VectorIndexSnapshotRecord
from app.models.user_context import safe_user_key
from app.services.qdrant_vector_store import QdrantVectorStore, build_qdrant_client
from app.services.vector_store import VectorSnapshot, VectorStore


def _vectors(snapshot: VectorSnapshot) -> np.ndarray:
    if not snapshot.chunks:
        dimension = int(
            snapshot.manifest.get("dimension", snapshot.manifest.get("embeddingDimension", 0))
        )
        return np.empty((0, dimension), dtype=np.float32)
    return np.stack(
        [snapshot.index.reconstruct(position) for position in range(len(snapshot.chunks))]
    ).astype(np.float32)


def _owners(database: Database) -> list[str]:
    with database.session() as session:
        return list(
            session.scalars(
                select(distinct(DocumentRecord.owner_id)).where(
                    DocumentRecord.status != "DELETED"
                )
            ).all()
        )


def _already_migrated(database: Database, namespace: str) -> bool:
    with database.session() as session:
        return session.get(VectorIndexSnapshotRecord, namespace) is not None


def migrate(*, settings: Settings, replace: bool, dry_run: bool) -> dict[str, int]:
    database = Database.from_settings(settings)
    database.validate_migrated()
    client = build_qdrant_client(settings)
    imported: dict[str, int] = {}
    try:
        sources: list[tuple[str, VectorStore]] = [
            ("system", VectorStore(settings.system_index_dir, settings.embedding_model))
        ]
        sources.extend(
            (
                f"user:{owner_id}",
                VectorStore(
                    settings.user_index_dir / safe_user_key(owner_id),
                    settings.embedding_model,
                ),
            )
            for owner_id in _owners(database)
        )
        for namespace, source in sources:
            snapshot = source.current
            if snapshot is None:
                continue
            if _already_migrated(database, namespace) and not replace:
                raise SystemExit(
                    f"Namespace {namespace} đã có active Qdrant snapshot; dùng --replace nếu thực sự muốn thay."
                )
            values = _vectors(snapshot)
            imported[namespace] = len(snapshot.chunks)
            if dry_run:
                continue
            target = QdrantVectorStore(
                database=database,
                client=client,
                collection=settings.qdrant_collection,
                namespace=namespace,
                embedding_model=settings.embedding_model,
                dimension=int(values.shape[1]),
                upsert_batch_size=settings.qdrant_upsert_batch_size,
            )
            target.commit(values, snapshot.chunks, snapshot.manifest)
            if len(target.require_snapshot().chunks) != len(snapshot.chunks):
                raise RuntimeError(f"Qdrant verification failed for {namespace}.")
        return imported
    finally:
        client.close()
        database.dispose()


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Migrate BKQuiz FAISS indexes sang Qdrant.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    settings = Settings()
    if settings.vector_store_backend != "qdrant":
        raise SystemExit("Đặt VECTOR_STORE_BACKEND=qdrant trước khi chạy migration.")
    result = migrate(settings=settings, replace=args.replace, dry_run=args.dry_run)
    action = "Kiểm tra" if args.dry_run else "Đã chuyển"
    print(f"{action}: " + ", ".join(f"{key}={value}" for key, value in result.items()))


if __name__ == "__main__":
    main()
