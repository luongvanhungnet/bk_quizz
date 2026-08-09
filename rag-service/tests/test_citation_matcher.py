from types import SimpleNamespace

import numpy as np

from app.services.citation_matcher import CitationInput, CitationMatcher


def _source(source_id: str, text: str):
    return SimpleNamespace(source_id=source_id, text=text)


def test_normalized_match_returns_the_exact_source_span() -> None:
    source = _source(
        "S1",
        "Embedding là “vector số” biểu diễn ý nghĩa.\nHai văn bản gần nhau.",
    )
    matcher = CitationMatcher(mode="lexical")

    [result] = matcher.resolve(
        [CitationInput("c1", "S1", 'embedding là "vector số"  biểu diễn ý nghĩa')],
        {"S1": source},
    )

    assert result is not None
    assert result.source_id == "S1"
    assert result.canonical_quote == "Embedding là “vector số” biểu diễn ý nghĩa"
    assert result.method == "NORMALIZED"


class SemanticEmbedding:
    def encode_documents(self, texts: list[str]) -> np.ndarray:
        vectors = []
        for text in texts:
            lowered = text.casefold()
            if "bảo trì" in lowered or "maintainability" in lowered:
                vectors.append([1.0, 0.0])
            else:
                vectors.append([0.0, 1.0])
        return np.asarray(vectors, dtype=np.float32)


def test_semantic_match_can_correct_the_declared_source() -> None:
    sources = {
        "S1": _source("S1", "Embedding biểu diễn văn bản bằng một vector số."),
        "S2": _source(
            "S2",
            "Content Coupling làm giảm khả năng bảo trì của hệ thống. "
            "Thiết kế nên giảm truy cập trực tiếp vào nội bộ module.",
        ),
    }
    matcher = CitationMatcher(
        mode="semantic",
        embedding_service=SemanticEmbedding(),
        semantic_same_source_min_score=0.72,
        semantic_cross_source_min_score=0.80,
        uniqueness_margin=0.08,
    )

    [result] = matcher.resolve(
        [CitationInput("c1", "S1", "Kiểu phụ thuộc này khiến phần mềm khó bảo trì")],
        sources,
    )

    assert result is not None
    assert result.source_id == "S2"
    assert result.method == "SEMANTIC_CROSS_SOURCE"
    assert result.canonical_quote == "Content Coupling làm giảm khả năng bảo trì của hệ thống."


def test_semantic_match_rejects_ambiguous_sources() -> None:
    sources = {
        "S1": _source("S1", "Content Coupling làm giảm khả năng bảo trì."),
        "S2": _source("S2", "Phụ thuộc nội bộ khiến maintainability suy giảm."),
    }
    matcher = CitationMatcher(
        mode="semantic",
        embedding_service=SemanticEmbedding(),
        semantic_cross_source_min_score=0.80,
        uniqueness_margin=0.08,
    )

    [result] = matcher.resolve(
        [CitationInput("c1", "UNKNOWN", "Thiết kế này khó bảo trì")],
        sources,
    )

    assert result is None


def test_semantic_embedding_failure_degrades_to_unverified_match() -> None:
    class BrokenEmbedding:
        def encode_documents(self, texts: list[str]):
            raise RuntimeError("inference failed")

    matcher = CitationMatcher(
        mode="semantic",
        embedding_service=BrokenEmbedding(),
        lexical_min_score=0.99,
    )
    sources = {
        "S1": _source(
            "S1",
            "Functional cohesion gom cac thanh phan cung thuc hien mot chuc nang duy nhat.",
        )
    }

    result = matcher.resolve(
        [CitationInput("q1", "S1", "Cac thanh phan cua module huong ve cung mot nhiem vu")],
        sources,
    )

    assert result == [None]


def test_twenty_citations_across_many_sources_survive_semantic_outage() -> None:
    class BrokenEmbedding:
        def encode_documents(self, texts: list[str]):
            raise RuntimeError("runtime unavailable")

    sources = {
        f"S{index}": _source(
            f"S{index}",
            f"Tai lieu {index} chua mot doan kien thuc du dai de tao cua so citation.",
        )
        for index in range(20)
    }
    citations = [
        CitationInput(
            f"q{index}", f"S{index}",
            f"Cach dien dat khac cua kien thuc trong tai lieu thu {index}",
        )
        for index in range(20)
    ]
    matcher = CitationMatcher(
        mode="semantic",
        embedding_service=BrokenEmbedding(),
        lexical_min_score=0.99,
    )

    result = matcher.resolve(citations, sources)

    assert result == [None] * 20
    assert matcher.last_degraded_error_code == "CITATION_SEMANTIC_UNAVAILABLE"
