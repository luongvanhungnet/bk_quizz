from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.services.gemini_service import GeminiResult, TokenUsage
from tests.test_system_indexing import FakeEmbeddingService


class ApiGeminiService:
    async def generate(self, *args: object, **kwargs: object) -> GeminiResult:
        return GeminiResult(
            "Thông tin được lấy từ tài liệu. [S1]",
            "test-model",
            TokenUsage(10, 5, 15),
        )


def configured_settings(settings: Settings, tmp_path: Path) -> Settings:
    documents = tmp_path / "documents"
    documents.mkdir()
    (documents / "guide.md").write_text(
        "# Cohesion\n\nFunctional cohesion là loại cohesion tốt nhất.",
        encoding="utf-8",
    )
    return settings.model_copy(
        update={
            "gemini_api_key": "secret",
            "system_documents_dir": documents,
            "system_index_dir": tmp_path / "index",
            "rag_min_score": -1,
            "rag_max_top_k": 2,
        }
    )


def test_reindex_list_search_and_ask(settings: Settings, tmp_path: Path) -> None:
    configured = configured_settings(settings, tmp_path)
    with TestClient(
        create_app(
            settings=configured,
            gemini_service=ApiGeminiService(),
            embedding_service=FakeEmbeddingService(),
        )
    ) as client:
        headers = {"X-Internal-API-Key": "test-internal-key"}
        reindex = client.post("/api/v1/system-documents/reindex", headers=headers)
        listing = client.get("/api/v1/system-documents", headers=headers)
        search = client.post(
            "/api/v1/rag/search",
            headers=headers,
            json={"question": "Functional cohesion", "topK": 2},
        )
        ask = client.post(
            "/api/v1/rag/ask",
            headers=headers,
            json={"question": "Functional cohesion là gì?", "topK": 2},
        )

    assert reindex.status_code == 200
    assert reindex.json()["newFiles"] == 1
    assert listing.status_code == 200
    assert listing.json()["items"][0]["relativePath"] == "guide.md"
    assert search.status_code == 200
    assert search.json()["results"][0]["filename"] == "guide.md"
    assert "relativePath" not in search.json()["results"][0]
    assert ask.status_code == 200
    assert ask.json()["sources"][0]["sourceId"] == "S1"


def test_rag_api_auth_and_dynamic_top_k_limit(
    settings: Settings, tmp_path: Path
) -> None:
    configured = configured_settings(settings, tmp_path)
    with TestClient(
        create_app(settings=configured, embedding_service=FakeEmbeddingService())
    ) as client:
        unauthorized = client.post(
            "/api/v1/rag/search", json={"question": "Question"}
        )
        too_many = client.post(
            "/api/v1/rag/search",
            headers={"X-Internal-API-Key": "test-internal-key"},
            json={"question": "Question", "topK": 3},
        )

    assert unauthorized.status_code == 401
    assert too_many.status_code == 422
    assert too_many.json()["code"] == "RAG_TOP_K_EXCEEDED"
