from fastapi.testclient import TestClient
from google.genai import types

from app.core.config import Settings
from app.main import create_app
from app.services.gemini_service import GeminiResult, TokenUsage


class HealthGeminiService:
    async def generate(
        self,
        message: str,
        *,
        system_instruction: str,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
        trace_id: str | None = None,
        thinking_level: types.ThinkingLevel | None = None,
    ) -> GeminiResult:
        assert message == "Chỉ trả lời đúng một từ: OK"
        assert temperature == 0
        assert max_output_tokens == 64
        assert thinking_level == types.ThinkingLevel.MINIMAL
        return GeminiResult("OK", "test-model", TokenUsage(1, 1, 2))


def test_health_is_public_and_does_not_require_gemini(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "BKQuiz RAG Service",
        "environment": "test",
        "geminiConfigured": False,
    }


def test_health_reports_gemini_configured(settings: Settings) -> None:
    configured = settings.model_copy(update={"gemini_api_key": "secret"})

    with TestClient(create_app(settings=configured)) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["geminiConfigured"] is True


def test_gemini_health_requires_internal_key(client: TestClient) -> None:
    response = client.get("/api/v1/health/gemini")

    assert response.status_code == 401
    assert response.json()["code"] == "INVALID_INTERNAL_API_KEY"
    assert response.json()["message"] == "Khóa truy cập nội bộ không hợp lệ."


def test_gemini_health_calls_configured_service(settings: Settings) -> None:
    configured = settings.model_copy(update={"gemini_api_key": "secret"})
    with TestClient(
        create_app(settings=configured, gemini_service=HealthGeminiService())
    ) as client:
        response = client.get(
            "/api/v1/health/gemini",
            headers={"X-Internal-API-Key": "test-internal-key"},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["model"] == "test-model"
    assert response.json()["message"] == "Kết nối Gemini hoạt động bình thường."


def test_unknown_endpoint_uses_standard_error_contract(client: TestClient) -> None:
    response = client.get("/api/v1/not-found")

    assert response.status_code == 404
    assert response.json()["code"] == "HTTP_ERROR"
    assert response.json()["message"] == "Không tìm thấy endpoint được yêu cầu."
    assert response.headers["X-Request-Id"] == response.json()["traceId"]


def test_non_utf8_json_body_uses_specific_error_contract(client: TestClient) -> None:
    body = '{"message":"Embedding l\u00e0 g\u00ec?"}'.encode("cp1252")

    response = client.post(
        "/api/v1/chat",
        headers={
            "Content-Type": "application/json",
            "X-Internal-API-Key": "test-internal-key",
        },
        content=body,
    )

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_JSON_BODY"
    assert response.json()["message"] == "Nội dung JSON phải hợp lệ và được mã hóa UTF-8."
    assert response.headers["X-Request-Id"] == response.json()["traceId"]


def test_malformed_json_body_uses_specific_error_contract(client: TestClient) -> None:
    response = client.post(
        "/api/v1/chat",
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "X-Internal-API-Key": "test-internal-key",
        },
        content=b'{"message":',
    )

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_JSON_BODY"
    assert response.json()["message"] == "Nội dung JSON phải hợp lệ và được mã hóa UTF-8."
