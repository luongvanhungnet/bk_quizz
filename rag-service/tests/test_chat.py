from dataclasses import dataclass

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.services.gemini_service import GeminiResult, TokenUsage


@dataclass
class FakeGeminiService:
    last_message: str | None = None
    last_system_instruction: str | None = None

    async def generate(
        self,
        message: str,
        *,
        system_instruction: str,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
        trace_id: str | None = None,
    ) -> GeminiResult:
        self.last_message = message
        self.last_system_instruction = system_instruction
        return GeminiResult(
            answer="Đây là câu trả lời.",
            model="test-model",
            usage=TokenUsage(input_tokens=4, output_tokens=6, total_tokens=10),
        )


class FailingGeminiService:
    async def generate(self, *args: object, **kwargs: object) -> GeminiResult:
        raise RuntimeError("GEMINI_API_KEY=must-not-leak")


def test_chat_returns_answer_and_usage(settings: Settings) -> None:
    service = FakeGeminiService()
    configured = settings.model_copy(update={"gemini_api_key": "secret"})

    with TestClient(
        create_app(settings=configured, gemini_service=service)
    ) as client:
        response = client.post(
            "/api/v1/chat",
            headers={"X-Internal-API-Key": "test-internal-key"},
            json={"message": "  Giải thích RAG  "},
        )

    assert response.status_code == 200
    assert response.json() == {
        "answer": "Đây là câu trả lời.",
        "model": "test-model",
        "usage": {"inputTokens": 4, "outputTokens": 6, "totalTokens": 10},
    }
    assert service.last_message == "Giải thích RAG"
    assert service.last_system_instruction


def test_unexpected_error_does_not_leak_secret(settings: Settings) -> None:
    configured = settings.model_copy(update={"gemini_api_key": "secret"})
    with TestClient(
        create_app(settings=configured, gemini_service=FailingGeminiService()),
        raise_server_exceptions=False,
    ) as client:
        response = client.post(
            "/api/v1/chat",
            headers={"X-Internal-API-Key": "test-internal-key"},
            json={"message": "Xin chào"},
        )

    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL_ERROR"
    assert "must-not-leak" not in response.text
