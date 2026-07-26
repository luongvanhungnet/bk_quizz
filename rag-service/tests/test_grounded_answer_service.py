import pytest

from app.core.exceptions import ServiceError
from app.models.document import DocumentChunk
from app.services.context_builder import BuiltContext, ContextSource
from app.services.gemini_service import GeminiResult, TokenUsage
from app.services.grounded_answer_service import NO_CONTEXT_ANSWER, GroundedAnswerService
from app.services.hybrid_retrieval import HybridCandidate


def context() -> BuiltContext:
    chunk = DocumentChunk("c", "d", "SYSTEM", "a.txt", "a.txt", "h", 1, 0, None, "facts", "now")
    source = ContextSource("S1", HybridCandidate(chunk, final_score=.9), "facts")
    return BuiltContext("[S1]\nfacts", [source], 10)


class Gemini:
    def __init__(self, answers):
        self.answers = iter(answers)
        self.calls = 0
    async def generate(self, *_args, **_kwargs):
        self.calls += 1
        return GeminiResult(next(self.answers), "test", TokenUsage(1, 1, 2))


@pytest.mark.asyncio
async def test_grounding_filters_unused_sources_and_handles_insufficient() -> None:
    gemini = Gemini(['{"answer":"Đúng [S1]","usedSourceIds":["S1"],"insufficientContext":false}'])
    result = await GroundedAnswerService().answer("q", context(), gemini, trace_id="t")
    assert result["sources"][0]["sourceId"] == "S1"
    assert result["insufficientContext"] is False

    insufficient = Gemini(['{"answer":"x","usedSourceIds":[],"insufficientContext":true}'])
    result = await GroundedAnswerService().answer("q", context(), insufficient, trace_id="t")
    assert result["answer"] == NO_CONTEXT_ANSWER
    assert result["sources"] == []


@pytest.mark.asyncio
async def test_invalid_source_is_repaired_once_or_rejected() -> None:
    repaired = Gemini([
        '{"answer":"x","usedSourceIds":["S9"],"insufficientContext":false}',
        '{"answer":"x [S1]","usedSourceIds":["S1"],"insufficientContext":false}',
    ])
    result = await GroundedAnswerService().answer("q", context(), repaired, trace_id="t")
    assert repaired.calls == 2 and result["sources"]

    broken = Gemini([
        '{"answer":"x","usedSourceIds":["S9"],"insufficientContext":false}',
        '{"answer":"x","usedSourceIds":["S8"],"insufficientContext":false}',
    ])
    with pytest.raises(ServiceError, match="nguồn") as captured:
        await GroundedAnswerService().answer("q", context(), broken, trace_id="t")
    assert captured.value.code == "GROUNDED_RESPONSE_INVALID"


@pytest.mark.asyncio
async def test_no_context_does_not_call_gemini() -> None:
    gemini = Gemini([])
    result = await GroundedAnswerService().answer("q", BuiltContext("", [], 0), gemini, trace_id="t")
    assert result["answer"] == NO_CONTEXT_ANSWER
    assert gemini.calls == 0
