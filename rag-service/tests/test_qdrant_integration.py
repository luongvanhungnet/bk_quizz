import os
import uuid

import numpy as np
import pytest
from qdrant_client import QdrantClient

from app.core.config import Settings
from app.db.database import Database
from app.db.models import DocumentRecord, VectorIndexSnapshotRecord
from app.models.document import DocumentChunk
from app.models.user_context import safe_user_key
from app.services.qdrant_vector_store import QdrantVectorStore
from app.services.vector_store import VectorStore
from scripts.migrate_faiss_to_qdrant import migrate


def _chunk(identifier: str, document_id: str, owner_id: str, text: str) -> DocumentChunk:
    return DocumentChunk(
        chunk_id=str(uuid.uuid5(uuid.NAMESPACE_URL, identifier)),
        document_id=document_id,
        document_type="USER_UPLOAD",
        filename=f"{document_id}.txt",
        relative_path=f"{document_id}.txt",
        file_hash="a" * 64,
        page_number=1,
        chunk_index=0,
        heading=None,
        text=text,
        created_at="2026-01-01T00:00:00Z",
        owner_id=owner_id,
        source_type="USER_UPLOAD",
    )


@pytest.mark.integration
def test_qdrant_versions_and_tenant_filters(tmp_path) -> None:
    url = os.getenv("QDRANT_TEST_URL", "").strip()
    if not url:
        pytest.skip("QDRANT_TEST_URL is not configured")
    collection = f"bkquiz_test_{uuid.uuid4().hex}"
    client = QdrantClient(url=url)
    database = Database(
        f"sqlite:///{(tmp_path / 'qdrant.db').as_posix()}", create_for_tests=True
    )
    try:
        first = QdrantVectorStore(
            database=database,
            client=client,
            collection=collection,
            namespace="user:alice",
            embedding_model="test-model",
            dimension=2,
        )
        alice = _chunk("alice-1", "doc-alice", "alice", "alpha")
        first.commit(
            np.asarray([[1.0, 0.0]], dtype=np.float32),
            [alice],
            {"ownerId": "alice", "chunkCount": 1},
        )
        other = QdrantVectorStore(
            database=database,
            client=client,
            collection=collection,
            namespace="user:bob",
            embedding_model="test-model",
            dimension=2,
        )
        bob = _chunk("bob-1", "doc-bob", "bob", "beta")
        other.commit(
            np.asarray([[1.0, 0.0]], dtype=np.float32),
            [bob],
            {"ownerId": "bob", "chunkCount": 1},
        )

        scores, positions = first.require_snapshot().index.search_filtered(
            np.asarray([[1.0, 0.0]], dtype=np.float32),
            5,
            {"doc-alice"},
            "alice",
        )
        assert scores.shape == (1, 1)
        assert positions.tolist() == [[0]]
        assert first.require_snapshot().chunks[0].owner_id == "alice"

        replacement = _chunk("alice-2", "doc-new", "alice", "new")
        first.commit(
            np.asarray([[0.0, 1.0]], dtype=np.float32),
            [replacement],
            {"ownerId": "alice", "chunkCount": 1},
        )
        reloaded = QdrantVectorStore(
            database=database,
            client=client,
            collection=collection,
            namespace="user:alice",
            embedding_model="test-model",
            dimension=2,
        )
        assert [chunk.document_id for chunk in reloaded.require_snapshot().chunks] == ["doc-new"]
    finally:
        if client.collection_exists(collection):
            client.delete_collection(collection)
        client.close()
        database.dispose()


@pytest.mark.integration
def test_faiss_migration_preserves_chunks(tmp_path, monkeypatch) -> None:
    url = os.getenv("QDRANT_TEST_URL", "").strip()
    if not url:
        pytest.skip("QDRANT_TEST_URL is not configured")
    collection = f"bkquiz_migration_{uuid.uuid4().hex}"
    database_url = f"sqlite:///{(tmp_path / 'metadata.db').as_posix()}"
    database = Database(database_url, create_for_tests=True)
    owner_id = "migration-owner"
    document_id = str(uuid.uuid4())
    with database.session() as session:
        session.add(
            DocumentRecord(
                id=document_id,
                owner_id=owner_id,
                source_type="USER_UPLOAD",
                original_filename="migration.txt",
                stored_filename="original-file",
                mime_type="text/plain",
                file_size=5,
                file_hash="b" * 64,
                status="READY",
                chunk_count=1,
            )
        )
        session.commit()
    user_index_dir = tmp_path / "indexes"
    source = VectorStore(user_index_dir / safe_user_key(owner_id), "test-model")
    chunk = _chunk("migrated", document_id, owner_id, "migrated text")
    source.commit(
        np.asarray([[1.0, 0.0]], dtype=np.float32),
        [chunk],
        {"ownerId": owner_id, "embeddingModel": "test-model", "dimension": 2},
    )
    settings = Settings(
        app_env="test",
        gemini_model="test-model",
        spring_boot_internal_api_key="test-internal-key",
        database_url=database_url,
        embedding_model="test-model",
        vector_store_backend="qdrant",
        qdrant_url=url,
        qdrant_collection=collection,
        user_index_dir=user_index_dir,
        system_index_dir=tmp_path / "system-index",
    )
    monkeypatch.setattr(Database, "validate_migrated", lambda self: None)
    client = QdrantClient(url=url)
    try:
        result = migrate(settings=settings, replace=False, dry_run=False)
        assert result == {f"user:{owner_id}": 1}
        with database.session() as session:
            record = session.get(VectorIndexSnapshotRecord, f"user:{owner_id}")
            assert record is not None
        points, _ = client.scroll(
            collection_name=collection, limit=10, with_payload=True
        )
        assert [point.payload["chunkId"] for point in points] == [chunk.chunk_id]
    finally:
        if client.collection_exists(collection):
            client.delete_collection(collection)
        client.close()
        database.dispose()
