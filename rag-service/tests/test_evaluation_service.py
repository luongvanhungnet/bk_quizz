from types import SimpleNamespace

import pytest

from app.services.evaluation_service import RetrievalEvaluationService


def candidate(document: str, page: int):
    chunk = SimpleNamespace(document_id=document, page_number=page)
    return SimpleNamespace(chunk=chunk)


@pytest.mark.asyncio
async def test_evaluation_metrics_are_exact() -> None:
    class Documents:
        def ready_ids(self, _owner, requested):
            return set(requested)

    class Rag:
        calls = 0
        async def search(self, **_kwargs):
            self.calls += 1
            values = [candidate("d1", 10), candidate("other", 1)] if self.calls == 1 else []
            return SimpleNamespace(retrieval=SimpleNamespace(candidates=values)), []

    items = [
        SimpleNamespace(question="q1", expectedDocumentIds=["d1"], expectedPageNumbers=[10]),
        SimpleNamespace(question="q2", expectedDocumentIds=["d2"], expectedPageNumbers=[]),
    ]
    result = await RetrievalEvaluationService(Rag(), Documents()).evaluate(
        "user", items, 2, "hybrid", trace_id="t"
    )
    assert result["hitRate"] == 0.5
    assert result["recall"] == 0.5
    assert result["mrr"] == 0.5
    assert result["queryCount"] == 2
