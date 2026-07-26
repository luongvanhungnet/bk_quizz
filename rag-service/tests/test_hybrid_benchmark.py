from types import SimpleNamespace

import faiss
import numpy as np

from app.models.document import DocumentChunk
from app.services.hybrid_retrieval import CorpusView, HybridRetrievalService


def chunk(identifier: str, text: str) -> DocumentChunk:
    return DocumentChunk(identifier, identifier, "SYSTEM", f"{identifier}.txt", f"{identifier}.txt", "h", None, 0, None, text, "now")


def test_small_benchmark_hybrid_improves_keyword_hit_rate_and_mrr() -> None:
    class Embedding:
        def encode_query(self, _):
            return np.array([[1.0, 0.0]], dtype=np.float32)
    class NoReranker:
        available = False
        def score(self, *_):
            return None
    chunks = [
        chunk("wrong", "khái niệm tổng quát"),
        chunk("other", "tài liệu khác"),
        chunk("expected", "mã duy nhất BK-LOCK-2026"),
    ]
    index = faiss.IndexFlatIP(2)
    index.add(np.array([[1.0, 0.0], [.8, .2], [.1, .9]], dtype=np.float32))
    snapshot = SimpleNamespace(chunks=chunks, index=index, fingerprint="benchmark-v1")
    service = HybridRetrievalService(
        embedding_service=Embedding(), reranker=NoReranker(), hybrid_enabled=True,
        vector_candidates=30, bm25_candidates=30, rrf_k=60, rerank_candidates=20,
        rerank_min_candidates=3,
        min_vector_score=-1, cache_size=10, cache_ttl_seconds=60,
    )
    corpus = [CorpusView("system", snapshot)]
    baseline = service.search("BK-LOCK-2026", corpus, 1, namespace="benchmark", mode="baseline")
    hybrid = service.search("BK-LOCK-2026", corpus, 1, namespace="benchmark", mode="hybrid")
    baseline_hit = float(baseline.candidates[0].chunk.document_id == "expected")
    hybrid_hit = float(hybrid.candidates[0].chunk.document_id == "expected")
    assert baseline_hit == 0.0
    assert hybrid_hit == 1.0
