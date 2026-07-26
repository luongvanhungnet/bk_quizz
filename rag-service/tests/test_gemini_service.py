from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from google.genai import errors

from app.core.config import Settings
from app.core.exceptions import ServiceError
from app.services.gemini_service import GeminiService


def response(text: str = "OK") -> SimpleNamespace:
    return SimpleNamespace(
        text=text,
        usage_metadata=SimpleNamespace(
            prompt_token_count=1,
            candidates_token_count=2,
            total_token_count=3,
        ),
    )


def fake_client(side_effect: object) -> SimpleNamespace:
    generate_content = AsyncMock(side_effect=side_effect)
    return SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    )


@pytest.mark.asyncio
async def test_generate_retries_transient_errors(settings: Settings) -> None:
    client = fake_client(
        [httpx.ReadTimeout("timeout"), errors.APIError(503, {"message": "busy"}), response()]
    )
    service = GeminiService(
        settings.model_copy(update={"gemini_api_key": "secret"}), client=client
    )

    with patch("app.services.gemini_service.asyncio.sleep", new=AsyncMock()):
        result = await service.generate("Xin chào", system_instruction="Trả lời ngắn.")

    assert result.answer == "OK"
    assert result.usage.total_tokens == 3
    assert client.aio.models.generate_content.await_count == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
async def test_generate_does_not_retry_permanent_errors(
    settings: Settings, status: int
) -> None:
    client = fake_client(errors.APIError(status, {"message": "rejected"}))
    service = GeminiService(
        settings.model_copy(update={"gemini_api_key": "secret"}), client=client
    )

    with pytest.raises(ServiceError):
        await service.generate("Xin chào", system_instruction="Trả lời ngắn.")

    assert client.aio.models.generate_content.await_count == 1


@pytest.mark.asyncio
async def test_rate_limit_is_mapped_after_last_attempt(settings: Settings) -> None:
    client = fake_client(errors.APIError(429, {"message": "quota"}))
    service = GeminiService(
        settings.model_copy(update={"gemini_api_key": "secret"}), client=client
    )

    with patch("app.services.gemini_service.asyncio.sleep", new=AsyncMock()):
        with pytest.raises(ServiceError) as raised:
            await service.generate("Xin chào", system_instruction="Trả lời ngắn.")

    assert raised.value.status_code == 429
    assert raised.value.code == "GEMINI_QUOTA_EXHAUSTED"
    assert client.aio.models.generate_content.await_count == 4
