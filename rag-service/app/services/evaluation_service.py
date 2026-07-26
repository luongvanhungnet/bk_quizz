from time import perf_counter
from typing import Any

import numpy as np

from app.core.exceptions import ServiceError


class RetrievalEvaluationService:
    def __init__(self, user_rag_service: Any, document_service: Any) -> None:
        self._rag = user_rag_service
        self._documents = document_service

    async def evaluate(
        self,
        owner_id: str,
        items: list[Any],
        k: int,
        mode: str,
        *,
        trace_id: str,
    ) -> dict[str, Any]:
        if not items or len(items) > 200:
            raise ServiceError(422, "INVALID_EVALUATION_DATASET", "Dataset phải có từ 1 đến 200 câu hỏi.")
        hits: list[float] = []
        recalls: list[float] = []
        reciprocals: list[float] = []
        latencies: list[float] = []
        for item in items:
            expected = set(item.expectedDocumentIds)
            self._documents.ready_ids(owner_id, list(expected))
            started = perf_counter()
            search, _ = await self._rag.search(
                owner_id=owner_id,
                question=item.question,
                top_k=k,
                document_ids=None,
                include_system=False,
                history=[],
                gemini_service=None,
                trace_id=trace_id,
                mode=mode,
            )
            latencies.append((perf_counter() - started) * 1000)
            expected_pages = set(item.expectedPageNumbers)
            found_documents: set[str] = set()
            first_rank: int | None = None
            for rank, candidate in enumerate(search.retrieval.candidates, start=1):
                chunk = candidate.chunk
                relevant = chunk.document_id in expected and (
                    not expected_pages or chunk.page_number in expected_pages
                )
                if relevant:
                    found_documents.add(chunk.document_id)
                    first_rank = first_rank or rank
            hits.append(1.0 if first_rank else 0.0)
            recalls.append(len(found_documents) / len(expected))
            reciprocals.append(1.0 / first_rank if first_rank else 0.0)
        return {
            "mode": mode,
            "k": k,
            "queryCount": len(items),
            "hitRate": round(float(np.mean(hits)), 6),
            "recall": round(float(np.mean(recalls)), 6),
            "mrr": round(float(np.mean(reciprocals)), 6),
            "meanLatencyMs": round(float(np.mean(latencies)), 3),
            "p50LatencyMs": round(float(np.percentile(latencies, 50)), 3),
            "p95LatencyMs": round(float(np.percentile(latencies, 95)), 3),
        }
