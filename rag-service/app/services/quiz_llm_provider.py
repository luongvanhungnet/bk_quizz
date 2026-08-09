import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Protocol

from app.services.gemini_service import TokenUsage

LOGGER = logging.getLogger("uvicorn.error")


class LLMErrorCategory(StrEnum):
    AUTHENTICATION = "LLM_AUTHENTICATION_ERROR"
    QUOTA = "LLM_QUOTA_ERROR"
    TIMEOUT = "LLM_TIMEOUT_ERROR"
    UNAVAILABLE = "LLM_UNAVAILABLE"
    INVALID_REQUEST = "LLM_INVALID_REQUEST"
    INVALID_RESPONSE = "LLM_INVALID_RESPONSE"
    SAFETY = "LLM_SAFETY_BLOCKED"


class LLMProviderError(Exception):
    def __init__(
        self,
        category: LLMErrorCategory,
        message: str,
        *,
        fallback_eligible: bool,
        retryable: bool = False,
        retry_after_seconds: int | None = None,
        code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.code = code or category.value
        self.fallback_eligible = fallback_eligible
        self.retryable = retryable
        self.retry_after_seconds = retry_after_seconds


@dataclass(frozen=True)
class QuizLLMPart:
    message: str
    question_count: int
    plan_slot_ids: tuple[str, ...] = ()
    plan_slots: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class QuizLLMCommand:
    message: str
    system_instruction: str
    response_schema: Any
    question_count: int
    batch_index: int
    trace_id: str
    max_output_tokens: int = 32768
    gemini_parts: tuple[QuizLLMPart, ...] = ()
    ollama_parts: tuple[QuizLLMPart, ...] = ()
    allowed_source_ids: frozenset[str] = frozenset()
    event_sink: Callable[[dict[str, Any]], Awaitable[None]] | None = None


@dataclass(frozen=True)
class QuizLLMResult:
    answer: str
    model: str
    usage: TokenUsage
    provider: str
    generated_by_provider: dict[str, int] = field(default_factory=dict)
    providers_used: tuple[str, ...] = ()


class QuizLLMProvider(Protocol):
    name: str
    model: str

    async def generate_quiz(self, command: QuizLLMCommand) -> QuizLLMResult: ...

    async def close(self) -> None: ...

    async def health(self) -> dict[str, Any]: ...


class UnavailableQuizLLMProvider:
    def __init__(
        self,
        *,
        name: str,
        model: str,
        error_code: str,
        message: str,
    ) -> None:
        self.name = name
        self.model = model
        self._error_code = error_code
        self._message = message

    async def generate_quiz(self, command: QuizLLMCommand) -> QuizLLMResult:
        raise LLMProviderError(
            LLMErrorCategory.AUTHENTICATION,
            self._message,
            fallback_eligible=True,
            code=self._error_code,
        )

    async def close(self) -> None:
        return None

    async def health(self) -> dict[str, Any]:
        return {
            "configured": False,
            "available": False,
            "model": self.model,
            "errorCode": self._error_code,
        }


def validate_structured_result(
    answer: str,
    schema: Any,
    expected_count: int,
) -> None:
    try:
        output = schema.model_validate_json(answer)
    except Exception as exception:
        raise LLMProviderError(
            LLMErrorCategory.INVALID_RESPONSE,
            "AI không trả về JSON đúng cấu trúc quiz.",
            fallback_eligible=True,
        ) from exception
    questions = getattr(output, "questions", None)
    if not isinstance(questions, list) or len(questions) != expected_count:
        raise LLMProviderError(
            LLMErrorCategory.INVALID_RESPONSE,
            "AI trả về sai số lượng câu hỏi.",
            fallback_eligible=True,
        )


class ProviderCircuitBreaker:
    def __init__(self, threshold: int, cooldown_seconds: int) -> None:
        self._threshold = threshold
        self._cooldown_seconds = cooldown_seconds
        self._failures = 0
        self._opened_at: float | None = None
        self._probe_lock = asyncio.Lock()

    @property
    def state(self) -> str:
        if self._opened_at is None:
            return "CLOSED"
        if time.monotonic() - self._opened_at < self._cooldown_seconds:
            return "OPEN"
        return "HALF_OPEN"

    async def allow(self) -> bool:
        if self.state == "CLOSED":
            return True
        if self.state == "OPEN":
            return False
        if self._probe_lock.locked():
            return False
        await self._probe_lock.acquire()
        return True

    def success(self) -> None:
        self._failures = 0
        self._opened_at = None
        if self._probe_lock.locked():
            self._probe_lock.release()

    def failure(self) -> None:
        self._failures += 1
        if self._failures >= self._threshold:
            self._opened_at = time.monotonic()
        if self._probe_lock.locked():
            self._probe_lock.release()


class QuizLLMRouter:
    def __init__(
        self,
        providers: Sequence[QuizLLMProvider],
        *,
        failure_threshold: int,
        cooldown_seconds: int,
    ) -> None:
        self._providers = list(providers)
        self._circuits = {
            provider.name: ProviderCircuitBreaker(failure_threshold, cooldown_seconds)
            for provider in providers
        }
        self.last_attempts: list[dict[str, Any]] = []
        self._last_trace_id: str | None = None

    async def generate_quiz(self, command: QuizLLMCommand) -> QuizLLMResult:
        if command.trace_id != self._last_trace_id:
            self.last_attempts = []
            self._last_trace_id = command.trace_id
        last_error: LLMProviderError | None = None
        provider_errors: list[LLMProviderError] = []
        attempted: list[str] = []
        for index, provider in enumerate(self._providers):
            circuit = self._circuits[provider.name]
            # Gemini API key is the canonical first provider and must be
            # attempted for every generation request. Its circuit remains
            # observable in health, but never silently changes provider order.
            always_attempt = index == 0 and provider.name == "gemini_api_key"
            if not always_attempt and not await circuit.allow():
                self._log_attempt(
                    command, provider, False, "LLM_CIRCUIT_OPEN",
                    self._next_provider(index), 0,
                )
                continue
            attempted.append(provider.name)
            await self._emit(
                command,
                "PROVIDER_STARTED",
                "INFO",
                self._provider_started_message(provider.name),
                provider=provider.name,
                model=provider.model,
            )
            started = time.perf_counter()
            try:
                result = await provider.generate_quiz(command)
                validate_structured_result(
                    result.answer, command.response_schema, command.question_count
                )
                circuit.success()
                self._log_attempt(
                    command, provider, True, None, None,
                    round((time.perf_counter() - started) * 1000),
                )
                await self._emit(
                    command,
                    "PROVIDER_COMPLETED",
                    "SUCCESS",
                    f"{self._provider_label(provider.name)} đã tạo xong câu hỏi.",
                    provider=provider.name,
                    model=provider.model,
                )
                generated = {name: 0 for name in attempted}
                generated.update(result.generated_by_provider)
                return replace(
                    result,
                    providers_used=tuple(attempted),
                    generated_by_provider=generated,
                )
            except LLMProviderError as error:
                last_error = error
                provider_errors.append(error)
                if error.fallback_eligible:
                    circuit.failure()
                else:
                    circuit.success()
                fallback_to = (
                    self._next_provider(index) if error.fallback_eligible else None
                )
                self._log_attempt(
                    command, provider, False, error.code, fallback_to,
                    round((time.perf_counter() - started) * 1000),
                )
                await self._emit(
                    command,
                    "PROVIDER_FAILED",
                    "WARNING" if error.fallback_eligible else "ERROR",
                    str(error),
                    provider=provider.name,
                    model=provider.model,
                    errorCode=error.code,
                    retryable=error.retryable,
                )
                if fallback_to is not None:
                    await self._emit(
                        command,
                        "FALLBACK_STARTED",
                        "WARNING",
                        self._fallback_message(fallback_to),
                        provider=fallback_to,
                        fallbackFrom=provider.name,
                        errorCode=error.code,
                    )
                if not error.fallback_eligible:
                    raise
            except Exception as exception:
                last_error = LLMProviderError(
                    LLMErrorCategory.UNAVAILABLE,
                    "Nhà cung cấp AI gặp lỗi nội bộ.",
                    fallback_eligible=True,
                    retryable=True,
                )
                provider_errors.append(last_error)
                circuit.failure()
                self._log_attempt(
                    command,
                    provider,
                    False,
                    last_error.category.value,
                    self._next_provider(index),
                    round((time.perf_counter() - started) * 1000),
                )
                fallback_to = self._next_provider(index)
                await self._emit(
                    command,
                    "PROVIDER_FAILED",
                    "WARNING",
                    f"{self._provider_label(provider.name)} gặp lỗi.",
                    provider=provider.name,
                    model=provider.model,
                    errorCode=last_error.category.value,
                    retryable=True,
                )
                if fallback_to is not None:
                    await self._emit(
                        command,
                        "FALLBACK_STARTED",
                        "WARNING",
                        self._fallback_message(fallback_to),
                        provider=fallback_to,
                        fallbackFrom=provider.name,
                        errorCode=last_error.category.value,
                    )
                LOGGER.warning(
                    "quiz_llm_provider_unexpected provider=%s type=%s",
                    provider.name,
                    type(exception).__name__,
                )
        incompatible_codes = {
            "GEMINI_API_REQUEST_INCOMPATIBLE",
            "GEMINI_OAUTH_REQUEST_INCOMPATIBLE",
        }
        if provider_errors and all(
            error.code in incompatible_codes for error in provider_errors
        ):
            raise LLMProviderError(
                LLMErrorCategory.INVALID_REQUEST,
                "Các nhà cung cấp AI không tương thích với yêu cầu sinh quiz.",
                fallback_eligible=False,
                code="LLM_PROVIDER_REQUEST_INCOMPATIBLE",
            )
        if last_error is not None:
            raise last_error
        raise LLMProviderError(
            LLMErrorCategory.UNAVAILABLE,
            "Không có nhà cung cấp AI sinh quiz nào khả dụng.",
            fallback_eligible=True,
            retryable=True,
        )

    async def close(self) -> None:
        for provider in self._providers:
            await provider.close()

    async def health(self) -> dict[str, Any]:
        states: dict[str, Any] = {}
        for provider in self._providers:
            state = await provider.health()
            state["circuit"] = self._circuits[provider.name].state
            states[provider.name] = state
        return states

    def _next_provider(self, index: int) -> str | None:
        return (
            self._providers[index + 1].name
            if index + 1 < len(self._providers)
            else None
        )

    def _log_attempt(
        self,
        command: QuizLLMCommand,
        provider: QuizLLMProvider,
        success: bool,
        error_code: str | None,
        fallback_to: str | None,
        latency_ms: int,
    ) -> None:
        item = {
            "requestId": command.trace_id,
            "provider": provider.name,
            "model": provider.model,
            "batchIndex": command.batch_index,
            "requestedQuestions": command.question_count,
            "success": success,
            "errorCode": error_code,
            "fallbackTo": fallback_to,
            "latencyMs": latency_ms,
        }
        self.last_attempts.append(item)
        LOGGER.info(json.dumps(item, ensure_ascii=False, separators=(",", ":")))

    async def _emit(
        self,
        command: QuizLLMCommand,
        event_type: str,
        level: str,
        message: str,
        **details: Any,
    ) -> None:
        if command.event_sink is None:
            return
        await command.event_sink({
            "type": event_type,
            "level": level,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "batchIndex": command.batch_index,
            **details,
        })

    @staticmethod
    def _provider_label(provider: str) -> str:
        return {
            "gemini_oauth": "Gemini OAuth",
            "gemini_api_key": "Gemini API key",
            "ollama": "Ollama Qwen",
        }.get(provider, provider)

    @classmethod
    def _provider_started_message(cls, provider: str) -> str:
        return f"Đang gọi {cls._provider_label(provider)} để tạo câu hỏi."

    @staticmethod
    def _fallback_message(provider: str) -> str:
        if provider == "ollama":
            return "Gemini không thể hoàn tất yêu cầu. Đang chuyển sang Ollama Qwen."
        return f"Đang chuyển sang {QuizLLMRouter._provider_label(provider)}."


AsyncResultValidator = Callable[[QuizLLMResult], Awaitable[QuizLLMResult]]
