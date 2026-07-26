import asyncio
from dataclasses import dataclass
from time import perf_counter
from typing import Any

from app.services.context_builder import ContextBuilder
from app.services.hybrid_retrieval import CorpusView, HybridSearchResult


@dataclass(frozen=True)
class PipelineSearchResult:
    original_query: str
    rewritten_query: str
    rewrite_attempted: bool
    retrieval: HybridSearchResult
    rewrite_ms: float


class RagPipelineService:
    def __init__(self, hybrid: Any, rewriter: Any, context_builder: ContextBuilder, grounding: Any) -> None:
        self._hybrid = hybrid
        self._rewriter = rewriter
        self._context = context_builder
        self._grounding = grounding

    async def search(
        self,
        question: str,
        history: list[Any],
        gemini_service: Any | None,
        corpora: list[CorpusView],
        top_k: int,
        *,
        namespace: str,
        trace_id: str,
        mode: str = "hybrid",
    ) -> PipelineSearchResult:
        started = perf_counter()
        rewritten = await self._rewriter.rewrite(
            question, history, gemini_service, trace_id=trace_id
        )
        rewrite_ms = (perf_counter() - started) * 1000
        retrieval = await asyncio.to_thread(
            self._hybrid.search,
            rewritten.rewritten,
            corpora,
            top_k,
            namespace=namespace,
            mode=mode,
        )
        return PipelineSearchResult(
            rewritten.original,
            rewritten.rewritten,
            rewritten.attempted,
            retrieval,
            round(rewrite_ms, 3),
        )

    async def ask(
        self,
        search: PipelineSearchResult,
        corpora: list[CorpusView],
        top_k: int,
        gemini_service: Any | None,
        *,
        trace_id: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        started = perf_counter()
        available = [chunk for corpus in corpora for chunk in corpus.chunks]
        context = self._context.build(search.retrieval.candidates, available, top_k)
        context_ms = (perf_counter() - started) * 1000
        answer = await self._grounding.answer(
            search.rewritten_query, context, gemini_service, trace_id=trace_id
        )
        debug = self.debug_payload(search, context.character_count, context.sources)
        debug["timingsMs"]["context"] = round(context_ms, 3)
        return answer, debug

    @staticmethod
    def debug_payload(search: PipelineSearchResult, context_chars: int = 0, selected: list[Any] | None = None) -> dict[str, Any]:
        def candidate(item: Any) -> dict[str, Any]:
            return {
                "chunkId": item.chunk.chunk_id,
                "documentId": item.chunk.document_id,
                "filename": item.chunk.filename,
                "preview": " ".join(item.chunk.text.split())[:200],
                "vectorScore": item.vector_score,
                "bm25Score": item.bm25_score,
                "rrfScore": round(item.rrf_score, 8),
                "rerankScore": item.rerank_score,
            }
        timings = dict(search.retrieval.timings_ms)
        timings["rewrite"] = search.rewrite_ms
        return {
            "originalQuery": search.original_query,
            "rewrittenQuery": search.rewritten_query,
            "rewriteAttempted": search.rewrite_attempted,
            "vectorCandidates": [candidate(item) for item in search.retrieval.vector_candidates],
            "bm25Candidates": [candidate(item) for item in search.retrieval.bm25_candidates],
            "selectedChunks": [candidate(item.candidate) for item in (selected or [])],
            "contextCharacterCount": context_chars,
            "cacheHit": search.retrieval.cache_hit,
            "timingsMs": timings,
        }
