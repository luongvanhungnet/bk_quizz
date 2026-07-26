import pytest

from app.models.document import DocumentChunk
from app.schemas.hybrid import ConversationMessage
from app.services.context_builder import ContextBuilder
from app.services.hybrid_retrieval import HybridCandidate
from app.services.query_rewrite_service import QueryRewriteService


def _chunk(identifier: str, text: str, index: int = 0, document: str = "d") -> DocumentChunk:
    return DocumentChunk(identifier, document, "SYSTEM", "a.txt", "a.txt", "h", 1, index, None, text, "now")


def test_context_deduplicates_overlap_and_preserves_source_marker() -> None:
    first = HybridCandidate(_chunk("a", "abcdefghij nội dung quan trọng"), final_score=2)
    duplicate = HybridCandidate(_chunk("b", "abcdefghij nội dung quan trọng "), final_score=1)
    different = HybridCandidate(_chunk("c", "nội dung hoàn toàn khác", document="d2"), final_score=.5)
    built = ContextBuilder(1000).build([first, duplicate, different], [first.chunk, duplicate.chunk, different.chunk], 3)
    assert [item.candidate.chunk.chunk_id for item in built.sources] == ["a", "c"]
    assert "[S1]" in built.text and "[S2]" in built.text


def test_context_expands_neighbor_and_obeys_budget() -> None:
    first = HybridCandidate(_chunk("a", "main", 1), final_score=2)
    before = _chunk("b", "before", 0)
    after = _chunk("c", "after", 2)
    built = ContextBuilder(1000).build([first], [before, first.chunk, after], 1)
    assert len(built.sources) == 3
    tiny = ContextBuilder(180).build([HybridCandidate(_chunk("x", "z" * 500))], [], 1)
    assert tiny.text.startswith("[S1]")
    assert len(tiny.text) <= 180


@pytest.mark.asyncio
async def test_rewrite_uses_structured_output_and_falls_back() -> None:
    class Gemini:
        async def generate(self, *_args, **_kwargs):
            return type("Result", (), {"answer": '{"standaloneQuestion":"Vì sao Functional Cohesion tốt nhất?","rewritten":true}'})()

    service = QueryRewriteService(True)
    history = [ConversationMessage(role="user", content="Functional Cohesion là gì?")]
    result = await service.rewrite("Tại sao nó tốt nhất?", history, Gemini(), trace_id="t")
    assert result.changed is True
    assert "Functional Cohesion" in result.rewritten

    class Broken:
        async def generate(self, *_args, **_kwargs):
            raise RuntimeError("failure")

    fallback = await service.rewrite("Tại sao nó tốt nhất?", history, Broken(), trace_id="t")
    assert fallback.rewritten == fallback.original
