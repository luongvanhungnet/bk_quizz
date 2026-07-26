from dataclasses import dataclass
from typing import Any

from app.models.document import DocumentChunk


@dataclass(frozen=True)
class RetrievalResult:
    chunk: DocumentChunk
    score: float


class RetrievalService:
    def __init__(self, embedding_service: Any, vector_store: Any, min_score: float) -> None:
        self._embedding = embedding_service
        self._store = vector_store
        self._min_score = min_score

    def search(self, question: str, top_k: int) -> list[RetrievalResult]:
        snapshot = self._store.require_snapshot()
        if not snapshot.chunks:
            return []
        query = self._embedding.encode_query(question)
        limit = min(top_k, len(snapshot.chunks))
        scores, positions = snapshot.index.search(query, limit)
        results = [
            RetrievalResult(snapshot.chunks[int(position)], float(score))
            for score, position in zip(scores[0], positions[0])
            if position >= 0 and float(score) >= self._min_score
        ]
        return sorted(results, key=lambda result: result.score, reverse=True)
