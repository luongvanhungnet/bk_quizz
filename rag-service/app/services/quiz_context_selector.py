import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from app.core.exceptions import ServiceError
from app.models.document import DocumentChunk
from app.services.context_builder import BuiltContext, ContextBuilder
from app.services.hybrid_retrieval import CorpusView, HybridCandidate, tokenize


@dataclass(frozen=True)
class QuizContextSelection:
    context: BuiltContext
    eligible_documents: int
    eligible_chunks: int
    selected_chunks: int
    mode: str


class QuizContextSelector:
    def __init__(
        self,
        max_context_chars: int,
        *,
        max_sources: int = 20,
        min_useful_chars: int = 100,
    ) -> None:
        self._builder = ContextBuilder(max_context_chars)
        self._max_context_chars = max_context_chars
        self._max_sources = max_sources
        self._min_useful_chars = min_useful_chars

    def select(
        self, title: str, corpora: Iterable[CorpusView]
    ) -> QuizContextSelection:
        chunks = [
            chunk
            for corpus in corpora
            for chunk in corpus.chunks
            if self._normalize(chunk.text)
        ]
        document_count = len({chunk.document_id for chunk in chunks})
        if not chunks:
            raise ServiceError(
                409,
                "RAG_INDEX_INCONSISTENT",
                "Tài liệu đã sẵn sàng nhưng chỉ mục không chứa đoạn nội dung. "
                "Vui lòng lập chỉ mục lại tài liệu.",
            )
        useful_chars = len(" ".join(self._normalize(chunk.text) for chunk in chunks))
        if useful_chars < self._min_useful_chars:
            raise ServiceError(
                422,
                "RAG_DOCUMENT_TEXT_INSUFFICIENT",
                "Tài liệu có quá ít nội dung hữu ích để sinh quiz.",
                details=[{
                    "eligibleDocuments": document_count,
                    "eligibleChunks": len(chunks),
                    "usefulCharacters": useful_chars,
                    "minimumUsefulCharacters": self._min_useful_chars,
                }],
            )

        ranked, mode = self._rank(title, chunks)
        context = self._builder.build(ranked, chunks, self._max_sources)
        if not context.sources:
            raise ServiceError(
                409,
                "RAG_INDEX_INCONSISTENT",
                "Không thể tạo context từ chỉ mục tài liệu. "
                "Vui lòng lập chỉ mục lại tài liệu.",
            )
        return QuizContextSelection(
            context=context,
            eligible_documents=document_count,
            eligible_chunks=len(chunks),
            selected_chunks=len(context.sources),
            mode=mode,
        )

    def _rank(
        self, title: str, chunks: list[DocumentChunk]
    ) -> tuple[list[HybridCandidate], str]:
        total_chars = sum(len(chunk.text) for chunk in chunks)
        if len(chunks) <= self._max_sources and total_chars <= self._max_context_chars:
            ordered = sorted(
                chunks,
                key=lambda chunk: (
                    chunk.document_id,
                    chunk.page_number or 0,
                    chunk.slide_number or 0,
                    chunk.chunk_index,
                ),
            )
            return (
                [
                    HybridCandidate(
                        chunk=chunk,
                        final_score=1.0,
                        rrf_score=1.0,
                    )
                    for chunk in ordered
                ],
                "ALL_SELECTED_CONTENT",
            )

        title_tokens = set(tokenize(title))
        by_document: dict[str, list[tuple[float, DocumentChunk]]] = defaultdict(list)
        for chunk in chunks:
            metadata = " ".join(
                value
                for value in (chunk.filename, chunk.heading, chunk.text)
                if value
            )
            chunk_tokens = set(tokenize(metadata))
            lexical = (
                len(title_tokens & chunk_tokens) / len(title_tokens)
                if title_tokens
                else 0.0
            )
            by_document[chunk.document_id].append((lexical, chunk))

        for values in by_document.values():
            values.sort(
                key=lambda item: (
                    -item[0],
                    item[1].page_number or 0,
                    item[1].slide_number or 0,
                    item[1].chunk_index,
                )
            )

        selected: list[tuple[float, DocumentChunk]] = []
        document_ids = sorted(by_document)
        while len(selected) < self._max_sources:
            added = False
            for document_id in document_ids:
                remaining = by_document[document_id]
                if not remaining:
                    continue
                best_index = self._most_diverse_index(remaining, selected)
                selected.append(remaining.pop(best_index))
                added = True
                if len(selected) >= self._max_sources:
                    break
            if not added:
                break
        return (
            [
                HybridCandidate(
                    chunk=chunk,
                    final_score=score,
                    rrf_score=score,
                )
                for score, chunk in selected
            ],
            "BALANCED_DIVERSE",
        )

    def _most_diverse_index(
        self,
        candidates: list[tuple[float, DocumentChunk]],
        selected: list[tuple[float, DocumentChunk]],
    ) -> int:
        if not selected:
            return 0
        selected_grams = [self._trigrams(self._normalize(item[1].text)) for item in selected]
        best_index = 0
        best_score = float("-inf")
        for index, (relevance, chunk) in enumerate(candidates):
            grams = self._trigrams(self._normalize(chunk.text))
            similarity = max(
                self._jaccard(grams, known) for known in selected_grams
            )
            score = 0.7 * relevance + 0.3 * (1.0 - similarity)
            if score > best_score:
                best_index = index
                best_score = score
        return best_index

    @staticmethod
    def _normalize(value: str) -> str:
        normalized = unicodedata.normalize("NFKC", value)
        return re.sub(r"\s+", " ", normalized).strip()

    @staticmethod
    def _trigrams(value: str) -> set[str]:
        folded = value.casefold()
        if len(folded) < 3:
            return {folded}
        return {folded[index : index + 3] for index in range(len(folded) - 2)}

    @staticmethod
    def _jaccard(left: set[str], right: set[str]) -> float:
        union = left | right
        return len(left & right) / len(union) if union else 1.0
