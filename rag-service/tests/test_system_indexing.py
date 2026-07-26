from pathlib import Path

import numpy as np

from app.core.exceptions import ServiceError
from app.services.chunking_service import ChunkingService
from app.services.document_parser import DocumentParser
from app.services.system_indexing_service import SystemIndexingService
from app.services.vector_store import VectorStore


class FakeEmbeddingService:
    model_name = "fake-model"
    dimension = 3

    @staticmethod
    def _encode(text: str) -> np.ndarray:
        lowered = text.casefold()
        vector = np.array(
            [lowered.count("alpha"), lowered.count("beta"), 1.0], dtype=np.float32
        )
        return vector / np.linalg.norm(vector)

    def encode_documents(self, texts: list[str]) -> np.ndarray:
        return np.stack([self._encode(text) for text in texts]).astype(np.float32)

    def encode_query(self, text: str) -> np.ndarray:
        return self._encode(text).reshape(1, -1).astype(np.float32)


def make_indexer(documents: Path, indexes: Path) -> tuple[SystemIndexingService, VectorStore]:
    vector_store = VectorStore(indexes, "fake-model")
    service = SystemIndexingService(
        documents_dir=documents,
        parser=DocumentParser(),
        chunker=ChunkingService(100, 20),
        embedding_service=FakeEmbeddingService(),
        vector_store=vector_store,
    )
    return service, vector_store


def test_incremental_index_skips_duplicates_and_removes_deleted(tmp_path: Path) -> None:
    documents = tmp_path / "documents"
    indexes = tmp_path / "index"
    documents.mkdir()
    (documents / "a.txt").write_text("alpha content", encoding="utf-8")
    (documents / "duplicate.txt").write_text("alpha content", encoding="utf-8")
    service, vector_store = make_indexer(documents, indexes)

    first = service.synchronize()
    service, vector_store = make_indexer(documents, indexes)
    second = service.synchronize()
    (documents / "a.txt").unlink()
    third = service.synchronize()

    assert first.new_files == 1
    assert first.duplicate_files == 1
    assert second.skipped_files == 1
    assert vector_store.require_snapshot().index.ntotal == len(
        vector_store.require_snapshot().chunks
    )
    assert third.deleted_files == 1
    assert third.total_documents == 1


def test_changed_file_is_reindexed(tmp_path: Path) -> None:
    documents = tmp_path / "documents"
    indexes = tmp_path / "index"
    documents.mkdir()
    path = documents / "a.txt"
    path.write_text("alpha", encoding="utf-8")
    service, store = make_indexer(documents, indexes)
    service.synchronize()

    path.write_text("beta changed", encoding="utf-8")
    result = service.synchronize()

    assert result.updated_files == 1
    assert store.require_snapshot().chunks[0].text == "beta changed"


def test_vector_artifact_count_matches_chunks(tmp_path: Path) -> None:
    documents = tmp_path / "documents"
    indexes = tmp_path / "index"
    documents.mkdir()
    (documents / "many.txt").write_text("alpha " * 100, encoding="utf-8")
    service, store = make_indexer(documents, indexes)

    service.synchronize()
    snapshot = store.require_snapshot()

    assert snapshot.index.ntotal == len(snapshot.chunks)
    assert (indexes / "vectors.faiss").exists()
    assert (indexes / "chunks.json").exists()
    assert (indexes / "manifest.json").exists()


def test_changed_embedding_model_requires_rebuild(tmp_path: Path) -> None:
    documents = tmp_path / "documents"
    indexes = tmp_path / "index"
    documents.mkdir()
    (documents / "a.txt").write_text("alpha", encoding="utf-8")
    service, _ = make_indexer(documents, indexes)
    service.synchronize()

    incompatible = VectorStore(indexes, "different-model")

    try:
        incompatible.require_snapshot()
    except ServiceError as error:
        assert error.code == "SYSTEM_INDEX_REBUILD_REQUIRED"
    else:
        raise AssertionError("Expected model mismatch to require a rebuild")
