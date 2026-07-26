import re
import unicodedata
from dataclasses import dataclass, replace
from time import perf_counter
from typing import Any

import numpy as np
from prometheus_client import Counter
from rank_bm25 import BM25Okapi

from app.models.document import DocumentChunk
from app.services.bounded_cache import LruCache, TtlLruCache

TOKEN_PATTERN = re.compile(r"[^\s,;!?()\[\]{}\"'<>]+", re.UNICODE)
RETRIEVAL_CACHE = Counter(
    "rag_retrieval_cache_total",
    "Hybrid retrieval cache lookups",
    ["result"],
)
BM25_CORPUS_CACHE = Counter(
    "rag_bm25_corpus_cache_total",
    "BM25 corpus cache lookups",
    ["result"],
)


def normalize_query(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split())


def tokenize(value: str) -> list[str]:
    return [token.casefold() for token in TOKEN_PATTERN.findall(normalize_query(value))]


@dataclass(frozen=True)
class CorpusView:
    name: str
    snapshot: Any
    allowed_document_ids: frozenset[str] | None = None
    owner_id: str | None = None

    @property
    def chunks(self) -> list[DocumentChunk]:
        return [
            chunk
            for chunk in self.snapshot.chunks
            if (
                self.allowed_document_ids is None
                or chunk.document_id in self.allowed_document_ids
            )
            and (self.owner_id is None or chunk.owner_id == self.owner_id)
        ]


@dataclass(frozen=True)
class HybridCandidate:
    chunk: DocumentChunk
    vector_score: float | None = None
    bm25_score: float | None = None
    rrf_score: float = 0.0
    rerank_score: float | None = None
    final_score: float = 0.0


@dataclass(frozen=True)
class HybridSearchResult:
    candidates: list[HybridCandidate]
    vector_candidates: list[HybridCandidate]
    bm25_candidates: list[HybridCandidate]
    timings_ms: dict[str, float]
    cache_hit: bool = False


class HybridRetrievalService:
    def __init__(
        self,
        *,
        embedding_service: Any,
        reranker: Any,
        hybrid_enabled: bool,
        vector_candidates: int,
        bm25_candidates: int,
        rrf_k: int,
        rerank_candidates: int,
        rerank_min_candidates: int,
        min_vector_score: float,
        cache_size: int,
        cache_ttl_seconds: int,
    ) -> None:
        self._embedding = embedding_service
        self._reranker = reranker
        self._hybrid_enabled = hybrid_enabled
        self._vector_limit = vector_candidates
        self._bm25_limit = bm25_candidates
        self._rrf_k = rrf_k
        self._rerank_limit = rerank_candidates
        self._rerank_min_candidates = rerank_min_candidates
        self._min_vector_score = min_vector_score
        self._cache: TtlLruCache[tuple[Any, ...], HybridSearchResult] = TtlLruCache(
            cache_size, cache_ttl_seconds
        )
        self._bm25_corpora: LruCache[
            tuple[Any, ...], tuple[list[DocumentChunk], BM25Okapi]
        ] = LruCache(cache_size)

    def clear_cache(self) -> None:
        self._cache.clear()
        self._bm25_corpora.clear()

    def search(
        self,
        question: str,
        corpora: list[CorpusView],
        top_k: int,
        *,
        namespace: str,
        mode: str = "hybrid",
    ) -> HybridSearchResult:
        normalized = normalize_query(question)
        fingerprints = tuple(
            (view.name, view.snapshot.fingerprint, tuple(sorted(view.allowed_document_ids or ())))
            for view in corpora
        )
        hybrid = self._hybrid_enabled and mode == "hybrid"
        key = (namespace, normalized, top_k, hybrid, self._reranker.available, fingerprints)
        cached = self._cache.get(key)
        if cached is not None:
            RETRIEVAL_CACHE.labels("hit").inc()
            return replace(cached, cache_hit=True)
        RETRIEVAL_CACHE.labels("miss").inc()

        total_started = perf_counter()
        vector_started = perf_counter()
        vector = self._vector_search(normalized, corpora)
        vector_ms = (perf_counter() - vector_started) * 1000
        bm25: list[HybridCandidate] = []
        bm25_ms = 0.0
        if hybrid:
            bm25_started = perf_counter()
            bm25 = self._bm25_search(normalized, corpora)
            bm25_ms = (perf_counter() - bm25_started) * 1000
            fusion_started = perf_counter()
            fused = self._fuse(vector, bm25)
            fusion_ms = (perf_counter() - fusion_started) * 1000
        else:
            fused = [replace(item, rrf_score=item.vector_score or 0.0, final_score=item.vector_score or 0.0) for item in vector]
            fusion_ms = 0.0

        rerank_started = perf_counter()
        reranked = self._rerank(normalized, fused) if hybrid else fused
        rerank_ms = (perf_counter() - rerank_started) * 1000
        result = HybridSearchResult(
            candidates=reranked[:top_k],
            vector_candidates=vector,
            bm25_candidates=bm25,
            timings_ms={
                "vector": round(vector_ms, 3),
                "bm25": round(bm25_ms, 3),
                "fusion": round(fusion_ms, 3),
                "rerank": round(rerank_ms, 3),
                "total": round((perf_counter() - total_started) * 1000, 3),
            },
        )
        self._cache.put(key, result)
        return result

    def _vector_search(self, question: str, corpora: list[CorpusView]) -> list[HybridCandidate]:
        query = self._embedding.encode_query(question)
        values: list[HybridCandidate] = []
        for view in corpora:
            snapshot = view.snapshot
            if not snapshot.chunks:
                continue
            filtered_positions = [
                position
                for position, chunk in enumerate(snapshot.chunks)
                if (
                    view.allowed_document_ids is None
                    or chunk.document_id in view.allowed_document_ids
                )
                and (view.owner_id is None or chunk.owner_id == view.owner_id)
            ]
            if len(filtered_positions) != len(snapshot.chunks):
                scores, positions = self._filtered_vector_search(
                    snapshot.index, query, filtered_positions
                )
            else:
                limit = min(len(snapshot.chunks), self._vector_limit)
                scores, positions = snapshot.index.search(query, limit)
            for score, position in zip(scores[0], positions[0]):
                if position < 0 or float(score) < self._min_vector_score:
                    continue
                chunk = snapshot.chunks[int(position)]
                values.append(HybridCandidate(chunk=chunk, vector_score=float(score)))
        return sorted(values, key=lambda item: (-(item.vector_score or 0), item.chunk.chunk_id))[: self._vector_limit]

    def _filtered_vector_search(
        self, index: Any, query: Any, allowed_positions: list[int]
    ) -> tuple[Any, Any]:
        if not allowed_positions:
            return (
                np.empty((1, 0), dtype=np.float32),
                np.empty((1, 0), dtype=np.int64),
            )

        ids = np.asarray(allowed_positions, dtype=np.int64)
        try:
            vectors = np.asarray(index.reconstruct_batch(ids), dtype=np.float32)
        except (AttributeError, TypeError):
            vectors = np.vstack(
                [np.asarray(index.reconstruct(int(position)), dtype=np.float32) for position in ids]
            )
        similarities = vectors @ np.asarray(query[0], dtype=np.float32)
        limit = min(len(ids), self._vector_limit)
        ranked = np.argsort(-similarities, kind="stable")[:limit]
        return similarities[ranked].reshape(1, -1), ids[ranked].reshape(1, -1)

    def _bm25_search(self, question: str, corpora: list[CorpusView]) -> list[HybridCandidate]:
        query_tokens = tokenize(question)
        if not query_tokens:
            return []
        corpus_key = tuple(
            (
                view.name,
                view.snapshot.fingerprint,
                tuple(sorted(view.allowed_document_ids or ())),
                view.owner_id,
            )
            for view in corpora
        )
        corpus = self._bm25_corpora.get(corpus_key)
        if corpus is None:
            BM25_CORPUS_CACHE.labels("miss").inc()
            chunks = [chunk for view in corpora for chunk in view.chunks]
            if not chunks:
                return []
            corpus_tokens = [tokenize(chunk.text) or [""] for chunk in chunks]
            corpus = (chunks, BM25Okapi(corpus_tokens))
            self._bm25_corpora.put(corpus_key, corpus)
        else:
            BM25_CORPUS_CACHE.labels("hit").inc()
        chunks, bm25 = corpus
        scores = bm25.get_scores(query_tokens)
        values = [
            HybridCandidate(chunk=chunk, bm25_score=float(score))
            for chunk, score in zip(chunks, scores)
            if float(score) > 0
        ]
        return sorted(values, key=lambda item: (-(item.bm25_score or 0), item.chunk.chunk_id))[: self._bm25_limit]

    def _fuse(self, vector: list[HybridCandidate], bm25: list[HybridCandidate]) -> list[HybridCandidate]:
        values: dict[str, HybridCandidate] = {}
        for ranked in (vector, bm25):
            for rank, item in enumerate(ranked, start=1):
                current = values.get(item.chunk.chunk_id, HybridCandidate(item.chunk))
                values[item.chunk.chunk_id] = replace(
                    current,
                    vector_score=item.vector_score if item.vector_score is not None else current.vector_score,
                    bm25_score=item.bm25_score if item.bm25_score is not None else current.bm25_score,
                    rrf_score=current.rrf_score + 1.0 / (self._rrf_k + rank),
                )
        return sorted(
            (replace(item, final_score=item.rrf_score) for item in values.values()),
            key=lambda item: (-item.rrf_score, item.chunk.chunk_id),
        )

    def _rerank(self, question: str, candidates: list[HybridCandidate]) -> list[HybridCandidate]:
        if len(candidates) < self._rerank_min_candidates:
            return candidates
        selected = candidates[: self._rerank_limit]
        scores = self._reranker.score(question, [item.chunk.text for item in selected])
        if scores is None:
            return candidates
        reranked = [
            replace(item, rerank_score=score, final_score=score)
            for item, score in zip(selected, scores)
        ]
        reranked.sort(key=lambda item: (-item.final_score, -item.rrf_score, item.chunk.chunk_id))
        return reranked + candidates[self._rerank_limit :]
