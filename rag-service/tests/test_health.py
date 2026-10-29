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
        response_schema: object | None = None,
    ) -> GeminiResult:
        assert message == "Trả về JSON xác nhận trạng thái kết nối."
        assert temperature == 0
        assert max_output_tokens == 256
        assert thinking_level == types.ThinkingLevel.MINIMAL
        assert response_schema is not None
        return GeminiResult('{"status":"OK"}', "test-model", TokenUsage(1, 1, 2))


class HealthQuizRouter:
    async def health(self):
        return {
            "gemini_api_key": {"configured": True},
            "gemini_oauth": {"configured": True},
            "ollama": {
                "configured": True,
                "reachable": True,
                "model": "qwen3:1.7b",
                "modelAvailable": True,
            },
        }


def test_llm_health_reports_batch_configuration_and_provider_order(
    settings: Settings,
) -> None:
    configured = settings.model_copy(update={
        "gemini_batch_size": 10,
        "gemini_oauth_timeout_seconds": 120,
        "ollama_max_questions_per_call": 2,
        "ollama_max_output_tokens": 2400,
    })
    with TestClient(create_app(
        settings=configured,
        quiz_llm_router=HealthQuizRouter(),
    )) as client:
        response = client.get(
            "/api/v1/health/llm",
            headers={"X-Internal-API-Key": "test-internal-key"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["providerOrder"] == [
        "gemini_api_key",
        "gemini_oauth",
        "ollama",
    ]
    assert body["geminiBatchSize"] == 10
    assert body["geminiOAuthTimeoutSeconds"] == 120
    assert body["ollamaMaxQuestionsPerCall"] == 2
    assert body["ollamaMaxOutputTokens"] == 2400


def test_v2_capabilities_require_internal_key_and_report_generation_contract(
    client: TestClient,
) -> None:
    unauthorized = client.get("/api/v2/capabilities")
    assert unauthorized.status_code == 401

    response = client.get(
        "/api/v2/capabilities",
        headers={"X-Internal-API-Key": "test-internal-key"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "quizGenerationContract": "cognitive-repair-v1",
        "capabilities": {
            "questionPlan": True,
            "acceptedQuestions": True,
                "streaming": True,
                "partialCognitiveRepair": True,
                "structuredOutputCheckpoint": True,
            },
        "buildRevision": "development",
    }


def test_health_is_public_and_does_not_require_gemini(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "BKQuiz RAG Service",
        "environment": "test",
        "geminiConfigured": False,
    }


def test_cloud_run_startup_health_excludes_worker_dependencies(client: TestClient) -> None:
    response = client.get("/health/startup")

    assert response.status_code == 200
    assert response.json()["status"] == "UP"
    assert response.json()["checks"] == {
        "database": "UP",
        "storage": "UP",
        "vectorStore": "UP",
        "embedding": "UP",
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
    assert response.json()["credentialSource"] == "injected"
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
