from types import SimpleNamespace

import faiss
import numpy as np

import app.services.hybrid_retrieval as hybrid_module
from app.models.document import DocumentChunk
from app.services.hybrid_retrieval import (
    CorpusView,
    HybridRetrievalService,
    normalize_query,
    tokenize,
)


def _chunk(identifier: str, text: str) -> DocumentChunk:
    return DocumentChunk(identifier, identifier, "SYSTEM", f"{identifier}.txt", f"{identifier}.txt", "h", None, 0, None, text, "now")


class Embedding:
    def encode_query(self, _: str) -> np.ndarray:
        return np.array([[1.0, 0.0]], dtype=np.float32)


class Reranker:
    available = False

    def score(self, _query, _passages):
        return None


def _service() -> HybridRetrievalService:
    return HybridRetrievalService(
        embedding_service=Embedding(), reranker=Reranker(), hybrid_enabled=True,
        vector_candidates=30, bm25_candidates=30, rrf_k=60,
        rerank_candidates=20, rerank_min_candidates=2,
        min_vector_score=-1, cache_size=10,
        cache_ttl_seconds=60,
    )


def test_tokenizer_preserves_technical_codes() -> None:
    assert normalize_query("  API   FOR UPDATE  ") == "API FOR UPDATE"
    tokens = tokenize("FOR UPDATE SKIP_LOCKED và C++ /api/v1")
    assert "skip_locked" in tokens
    assert "c++" in tokens
    assert "/api/v1" in tokens


def test_bm25_and_rrf_merge_stable_ranks() -> None:
    chunks = [
        _chunk("a", "mã BK-2026 đặc biệt"),
        _chunk("b", "nội dung diễn đạt khác"),
        _chunk("c", "tài liệu không liên quan"),
    ]
    index = faiss.IndexFlatIP(2)
    index.add(np.array([[0.1, 0.9], [1.0, 0.0], [0.0, 1.0]], dtype=np.float32))
    snapshot = SimpleNamespace(chunks=chunks, index=index, fingerprint="v1")
    result = _service().search("BK-2026", [CorpusView("system", snapshot)], 2, namespace="system")
    assert result.bm25_candidates[0].chunk.chunk_id == "a"
    assert "a" in {item.chunk.chunk_id for item in result.candidates}
    assert all(item.rrf_score > 0 for item in result.candidates)


def test_reranker_changes_order_and_cache_is_snapshot_aware() -> None:
    class ReverseReranker:
        available = True
        def score(self, _query, passages):
            return list(range(len(passages)))

    service = _service()
    service._reranker = ReverseReranker()
    chunks = [_chunk("a", "alpha"), _chunk("b", "beta")]
    index = faiss.IndexFlatIP(2)
    index.add(np.array([[1.0, 0.0], [0.5, 0.5]], dtype=np.float32))
    snapshot = SimpleNamespace(chunks=chunks, index=index, fingerprint="v1")
    first = service.search("alpha", [CorpusView("system", snapshot)], 2, namespace="tenant-a")
    second = service.search("alpha", [CorpusView("system", snapshot)], 2, namespace="tenant-a")
    assert first.candidates[0].chunk.chunk_id != "a"
    assert second.cache_hit is True
    changed = SimpleNamespace(chunks=chunks, index=index, fingerprint="v2")
    assert service.search("alpha", [CorpusView("system", changed)], 2, namespace="tenant-a").cache_hit is False


def test_bm25_corpus_is_built_once_per_snapshot(monkeypatch) -> None:
    builds = 0
    original = hybrid_module.BM25Okapi

    def counting_bm25(tokens):
        nonlocal builds
        builds += 1
        return original(tokens)

    monkeypatch.setattr(hybrid_module, "BM25Okapi", counting_bm25)
    chunks = [_chunk("a", "alpha beta"), _chunk("b", "gamma delta")]
    index = faiss.IndexFlatIP(2)
    index.add(np.array([[1.0, 0.0], [0.5, 0.5]], dtype=np.float32))
    snapshot = SimpleNamespace(chunks=chunks, index=index, fingerprint="v1")
    service = _service()

    service.search("alpha", [CorpusView("system", snapshot)], 1, namespace="system")
    service.search("gamma", [CorpusView("system", snapshot)], 1, namespace="system")

    assert builds == 1


def test_vector_search_requests_only_candidate_budget() -> None:
    class TrackingIndex:
        ntotal = 100

        def __init__(self) -> None:
            self.requested = 0

        def search(self, _query, limit):
            self.requested = limit
            return (
                np.ones((1, limit), dtype=np.float32),
                np.arange(limit, dtype=np.int64).reshape(1, -1),
            )

    index = TrackingIndex()
    chunks = [_chunk(str(index), f"chunk {index}") for index in range(100)]
    snapshot = SimpleNamespace(chunks=chunks, index=index, fingerprint="v1")

    _service().search("chunk", [CorpusView("system", snapshot)], 5, namespace="system")

    assert index.requested == 30


def test_reranker_is_skipped_below_minimum_candidates() -> None:
    class TrackingReranker:
        available = True

        def __init__(self) -> None:
            self.calls = 0

        def score(self, _query, _passages):
            self.calls += 1
            return [1.0]

    reranker = TrackingReranker()
    service = _service()
    service._reranker = reranker
    service._rerank_min_candidates = 3
    chunks = [_chunk("a", "alpha")]
    index = faiss.IndexFlatIP(2)
    index.add(np.array([[1.0, 0.0]], dtype=np.float32))

    service.search(
        "alpha",
        [CorpusView("system", SimpleNamespace(chunks=chunks, index=index, fingerprint="v1"))],
        1,
        namespace="system",
    )

    assert reranker.calls == 0
