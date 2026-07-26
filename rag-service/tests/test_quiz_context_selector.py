from types import SimpleNamespace

import pytest

from app.core.exceptions import ServiceError
from app.models.document import DocumentChunk
from app.services.hybrid_retrieval import CorpusView
from app.services.quiz_context_selector import QuizContextSelector


def _chunk(document: str, index: int, text: str) -> DocumentChunk:
    return DocumentChunk(
        chunk_id=f"{document}-{index}",
        document_id=document,
        document_type="USER_UPLOAD",
        filename=f"{document}.txt",
        relative_path=f"{document}.txt",
        file_hash="hash",
        page_number=None,
        chunk_index=index,
        heading=None,
        text=text,
        created_at="now",
        owner_id="user-a",
        source_type="USER_UPLOAD",
    )


def _corpus(chunks: list[DocumentChunk]) -> CorpusView:
    return CorpusView(
        "user",
        SimpleNamespace(chunks=chunks, fingerprint="fingerprint"),
        frozenset({chunk.document_id for chunk in chunks}),
        "user-a",
    )


def test_small_selected_corpus_uses_every_chunk() -> None:
    chunks = [
        _chunk("doc-a", 0, "A" * 120),
        _chunk("doc-a", 1, "B" * 120),
    ]

    result = QuizContextSelector(16000).select(
        "Tiêu đề không liên quan",
        [_corpus(chunks)],
    )

    assert result.mode == "ALL_SELECTED_CONTENT"
    assert [source.candidate.chunk.chunk_id for source in result.context.sources] == [
        "doc-a-0",
        "doc-a-1",
    ]


def test_large_corpus_balances_documents_within_context_budget() -> None:
    chunks = [
        _chunk(document, index, f"Nội dung riêng {document} phần {index}. " * 20)
        for document in ("doc-a", "doc-b", "doc-c")
        for index in range(10)
    ]

    result = QuizContextSelector(3000).select(
        "Kiến thức tổng hợp",
        [_corpus(chunks)],
    )

    selected_documents = {
        source.candidate.chunk.document_id for source in result.context.sources
    }
    assert result.mode == "BALANCED_DIVERSE"
    assert selected_documents == {"doc-a", "doc-b", "doc-c"}
    assert result.context.character_count <= 3000
    assert result.selected_chunks <= 20


def test_ready_document_without_chunks_reports_inconsistent_index() -> None:
    with pytest.raises(ServiceError) as captured:
        QuizContextSelector(16000).select(
            "Quiz",
            [_corpus([])],
        )

    assert captured.value.code == "RAG_INDEX_INCONSISTENT"
    assert captured.value.retryable is False


def test_short_document_reports_specific_error() -> None:
    with pytest.raises(ServiceError) as captured:
        QuizContextSelector(16000).select(
            "Quiz",
            [_corpus([_chunk("doc-a", 0, "Quá ngắn")])],
        )

    assert captured.value.code == "RAG_DOCUMENT_TEXT_INSUFFICIENT"
    assert captured.value.retryable is False
