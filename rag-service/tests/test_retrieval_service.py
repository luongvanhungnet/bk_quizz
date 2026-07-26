from pathlib import Path

from app.services.retrieval_service import RetrievalService
from tests.test_system_indexing import FakeEmbeddingService, make_indexer


def test_search_is_descending_and_applies_threshold(tmp_path: Path) -> None:
    documents = tmp_path / "documents"
    documents.mkdir()
    (documents / "alpha.txt").write_text("alpha alpha", encoding="utf-8")
    (documents / "beta.txt").write_text("beta beta", encoding="utf-8")
    indexer, store = make_indexer(documents, tmp_path / "index")
    indexer.synchronize()
    retrieval = RetrievalService(FakeEmbeddingService(), store, min_score=0.8)

    results = retrieval.search("alpha", top_k=10)

    assert results
    assert [result.score for result in results] == sorted(
        [result.score for result in results], reverse=True
    )
    assert all(result.score >= 0.8 for result in results)
    assert results[0].chunk.filename == "alpha.txt"
