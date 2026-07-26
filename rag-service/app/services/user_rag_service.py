import asyncio
from typing import Any

from app.services.hybrid_retrieval import CorpusView


class UserRagService:
    def __init__(self, document_service: Any, user_indexes: Any, system_store: Any, pipeline: Any) -> None:
        self._documents = document_service
        self._user_indexes = user_indexes
        self._system_store = system_store
        self._pipeline = pipeline

    async def prepare_corpora(
        self, owner_id: str, document_ids: list[str] | None, include_system: bool
    ) -> list[CorpusView]:
        allowed = await asyncio.to_thread(self._documents.ready_ids, owner_id, document_ids)
        all_ready = await asyncio.to_thread(self._documents.ready_ids, owner_id, None)
        consistent = await asyncio.to_thread(
            self._user_indexes.is_consistent, owner_id, all_ready
        )
        if not consistent:
            await asyncio.to_thread(self._documents.rebuild_index, owner_id)
        corpora: list[CorpusView] = []
        user_snapshot = await asyncio.to_thread(self._user_indexes.snapshot_for, owner_id)
        if user_snapshot is not None:
            corpora.append(CorpusView(
                "user", user_snapshot, frozenset(allowed), owner_id
            ))
        if include_system and self._system_store.current is not None:
            corpora.append(CorpusView("system", self._system_store.current))
        return corpora

    async def search(
        self,
        *,
        owner_id: str,
        question: str,
        top_k: int,
        document_ids: list[str] | None,
        include_system: bool,
        history: list[Any],
        gemini_service: Any | None,
        trace_id: str,
        mode: str = "hybrid",
    ) -> tuple[Any, list[CorpusView]]:
        corpora = await self.prepare_corpora(owner_id, document_ids, include_system)
        result = await self._pipeline.search(
            question,
            history,
            gemini_service,
            corpora,
            top_k,
            namespace=f"user:{owner_id}",
            trace_id=trace_id,
            mode=mode,
        )
        return result, corpora

    async def ask(self, *, search: Any, corpora: list[CorpusView], top_k: int, gemini_service: Any | None, trace_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        return await self._pipeline.ask(
            search, corpora, top_k, gemini_service, trace_id=trace_id
        )

    async def document_chunks(self, owner_id: str, document_id: str) -> list[Any]:
        await asyncio.to_thread(self._documents.ready_ids, owner_id, [document_id])
        all_ready = await asyncio.to_thread(self._documents.ready_ids, owner_id, None)
        if not await asyncio.to_thread(self._user_indexes.is_consistent, owner_id, all_ready):
            await asyncio.to_thread(self._documents.rebuild_index, owner_id)
        snapshot = await asyncio.to_thread(self._user_indexes.snapshot_for, owner_id)
        if snapshot is None:
            return []
        return sorted(
            (chunk for chunk in snapshot.chunks if chunk.document_id == document_id),
            key=lambda chunk: chunk.chunk_index,
        )
