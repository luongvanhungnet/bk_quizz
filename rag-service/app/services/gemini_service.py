import asyncio
import logging
import random
import time
from collections import defaultdict, deque
from contextvars import ContextVar
from dataclasses import dataclass
from time import perf_counter
from typing import Any

import httpx
from google import genai
from google.genai import errors, types
from prometheus_client import Counter, Histogram

from app.core.config import Settings
from app.core.exceptions import ServiceError

LOGGER = logging.getLogger("uvicorn.error")
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
GEMINI_USER_CONTEXT: ContextVar[str | None] = ContextVar("gemini_user_context", default=None)
GEMINI_CALLS = Counter("rag_gemini_calls_total", "Gemini calls", ["result"])
GEMINI_LATENCY = Histogram("rag_gemini_duration_seconds", "Gemini call latency")


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int
    output_tokens: int
    total_tokens: int


@dataclass(frozen=True)
class GeminiResult:
    answer: str
    model: str
    usage: TokenUsage


class GeminiService:
    def __init__(self, settings: Settings, client: Any | None = None) -> None:
        if not settings.gemini_api_key:
            raise ServiceError(
                503,
                "GEMINI_NOT_CONFIGURED",
                "Gemini chưa được cấu hình cho dịch vụ này.",
            )
        self._settings = settings
        self._semaphore = asyncio.Semaphore(settings.gemini_max_concurrency)
        self._owns_client = client is None
        self._client = client or genai.Client(
            api_key=settings.gemini_api_key,
            http_options=types.HttpOptions(
                timeout=int(settings.gemini_timeout_seconds * 1000),
                retry_options=types.HttpRetryOptions(attempts=1),
                base_url=settings.gemini_api_base_url,
            ),
        )
        self._global_calls: deque[float] = deque()
        self._user_calls: dict[str, deque[float]] = defaultdict(deque)
        self._consecutive_failures = 0
        self._circuit_opened_at: float | None = None

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aio.aclose()

    async def generate(
        self,
        message: str,
        *,
        system_instruction: str,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
        trace_id: str | None = None,
        thinking_level: types.ThinkingLevel | None = None,
        response_schema: Any | None = None,
        user_id: str | None = None,
        max_attempts: int | None = None,
    ) -> GeminiResult:
        self._check_circuit()
        self._check_rate_limit(user_id or GEMINI_USER_CONTEXT.get())
        started_at = perf_counter()
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=(
                self._settings.gemini_temperature
                if temperature is None
                else temperature
            ),
            max_output_tokens=(
                self._settings.gemini_max_output_tokens
                if max_output_tokens is None
                else max_output_tokens
            ),
            thinking_config=(
                types.ThinkingConfig(thinking_level=thinking_level)
                if thinking_level is not None
                else None
            ),
            response_mime_type="application/json" if response_schema is not None else None,
            response_schema=response_schema,
        )

        async with self._semaphore:
            attempts = (
                self._settings.effective_gemini_max_attempts
                if max_attempts is None
                else max(1, max_attempts)
            )
            for attempt in range(1, attempts + 1):
                try:
                    response = await self._client.aio.models.generate_content(
                        model=self._settings.gemini_model,
                        contents=message,
                        config=config,
                    )
                    result = self._to_result(response)
                    self._consecutive_failures = 0
                    self._circuit_opened_at = None
                    GEMINI_CALLS.labels("success").inc()
                    GEMINI_LATENCY.observe(perf_counter() - started_at)
                    LOGGER.info(
                        "Gemini request completed trace_id=%s model=%s latency_ms=%d "
                        "attempts=%d input_tokens=%d output_tokens=%d total_tokens=%d",
                        trace_id or "unknown",
                        self._settings.gemini_model,
                        round((perf_counter() - started_at) * 1000),
                        attempt,
                        result.usage.input_tokens,
                        result.usage.output_tokens,
                        result.usage.total_tokens,
                    )
                    return result
                except Exception as exception:
                    GEMINI_CALLS.labels("error").inc()
                    self._record_failure()
                    if not self._is_retryable(exception):
                        raise self._map_exception(exception) from exception
                    if attempt == attempts:
                        raise self._map_exception(exception) from exception

                    delay = self._settings.gemini_retry_initial_delay_seconds * (
                        2 ** (attempt - 1)
                    ) + random.uniform(0, 0.25)
                    delay = self._retry_after(exception, delay)
                    LOGGER.warning(
                        "Gemini transient failure model=%s attempt=%d/%d type=%s",
                        self._settings.gemini_model,
                        attempt,
                        attempts,
                        type(exception).__name__,
                    )
                    await asyncio.sleep(delay)

        raise ServiceError(503, "GEMINI_UNAVAILABLE", "Gemini tạm thời không khả dụng.")

    def _check_rate_limit(self, user_id: str | None) -> None:
        now = time.monotonic()
        cutoff = now - 60
        while self._global_calls and self._global_calls[0] <= cutoff:
            self._global_calls.popleft()
        if len(self._global_calls) >= self._settings.gemini_global_rpm:
            raise ServiceError(
                429, "GEMINI_RATE_LIMITED", "Đã đạt giới hạn sử dụng Gemini.",
                retryable=True, retry_after_seconds=60,
            )
        self._global_calls.append(now)
        if user_id:
            calls = self._user_calls[user_id]
            while calls and calls[0] <= cutoff:
                calls.popleft()
            if len(calls) >= self._settings.gemini_user_rpm:
                raise ServiceError(
                    429, "GEMINI_USER_RATE_LIMITED", "Đã đạt giới hạn Gemini của người dùng.",
                    retryable=True, retry_after_seconds=60,
                )
            calls.append(now)

    def _check_circuit(self) -> None:
        if self._circuit_opened_at is None:
            return
        if time.monotonic() - self._circuit_opened_at < self._settings.circuit_open_seconds:
            raise ServiceError(
                503, "AI_SERVICE_TEMPORARILY_UNAVAILABLE",
                "Dịch vụ AI đang tạm ngắt để phục hồi.",
                retryable=True, retry_after_seconds=self._settings.circuit_open_seconds,
            )
        self._circuit_opened_at = None

    def _record_failure(self) -> None:
        self._consecutive_failures += 1
        if self._consecutive_failures >= self._settings.circuit_failure_threshold:
            self._circuit_opened_at = time.monotonic()

    @staticmethod
    def _retry_after(exception: Exception, fallback: float) -> float:
        response = getattr(exception, "response", None)
        headers = getattr(response, "headers", {}) or {}
        try:
            return max(fallback, float(headers.get("Retry-After", 0) or 0))
        except (TypeError, ValueError):
            return fallback

    def _to_result(self, response: Any) -> GeminiResult:
        candidates = getattr(response, "candidates", None) or []
        finish_reason = str(getattr(candidates[0], "finish_reason", "")) if candidates else ""
        if "SAFETY" in finish_reason.upper():
            raise ServiceError(422, "GEMINI_SAFETY_BLOCKED", "Gemini đã chặn phản hồi theo chính sách an toàn.")
        try:
            answer = response.text
        except (AttributeError, ValueError):
            answer = None
        if not answer or not answer.strip():
            raise ServiceError(
                502,
                "GEMINI_EMPTY_RESPONSE",
                "Gemini không trả về nội dung hợp lệ.",
            )

        metadata = getattr(response, "usage_metadata", None)
        input_tokens = int(getattr(metadata, "prompt_token_count", 0) or 0)
        output_tokens = int(getattr(metadata, "candidates_token_count", 0) or 0)
        total_tokens = int(
            getattr(metadata, "total_token_count", input_tokens + output_tokens)
            or input_tokens + output_tokens
        )
        return GeminiResult(
            answer=answer.strip(),
            model=self._settings.gemini_model,
            usage=TokenUsage(input_tokens, output_tokens, total_tokens),
        )

    @staticmethod
    def _is_retryable(exception: Exception) -> bool:
        if isinstance(exception, ServiceError):
            return False
        if isinstance(
            exception,
            (httpx.TimeoutException, httpx.TransportError, TimeoutError),
        ):
            return True
        return isinstance(exception, errors.APIError) and exception.code in RETRYABLE_STATUS_CODES

    @staticmethod
    def _map_exception(exception: Exception) -> ServiceError:
        if isinstance(exception, ServiceError):
            return exception
        if isinstance(exception, errors.APIError):
            response_body = getattr(exception, "details", None)
            error_body = (
                response_body.get("error", response_body)
                if isinstance(response_body, dict)
                else {}
            )
            upstream_status = str(
                getattr(exception, "status", None)
                or error_body.get("status", "")
                or ""
            )
            upstream_reason = str(error_body.get("reason", "") or "")
            response = getattr(exception, "response", None)
            headers = getattr(response, "headers", {}) or {}
            upstream_request_id = str(
                headers.get("x-request-id")
                or headers.get("x-guploader-uploadid")
                or ""
            )[:120]
            LOGGER.warning(
                "gemini_api_error http_status=%s upstream_status=%s "
                "upstream_reason=%s upstream_request_id=%s",
                exception.code,
                upstream_status[:80],
                upstream_reason[:80],
                upstream_request_id,
            )
            if exception.code == 429:
                quota_exhausted = "quota" in str(exception).casefold()
                return ServiceError(
                    429,
                    "GEMINI_QUOTA_EXHAUSTED" if quota_exhausted else "GEMINI_RATE_LIMITED",
                    "Đã đạt giới hạn sử dụng Gemini. Vui lòng thử lại sau.",
                )
            if exception.code in {401, 403}:
                return ServiceError(
                    503,
                    "GEMINI_API_AUTHENTICATION_FAILED",
                    "Cấu hình xác thực Gemini không hợp lệ.",
                )
            if exception.code in {400, 404, 422}:
                return ServiceError(
                    502,
                    (
                        "GEMINI_MODEL_NOT_AVAILABLE"
                        if exception.code == 404
                        else "GEMINI_API_REQUEST_INCOMPATIBLE"
                    ),
                    (
                        "Model Gemini hiện không khả dụng."
                        if exception.code == 404
                        else "Gemini API không tương thích với yêu cầu sinh quiz."
                    ),
                    details=[{
                        "httpStatus": exception.code,
                        "upstreamStatus": upstream_status[:80],
                        "upstreamReason": upstream_reason[:80],
                        "upstreamRequestId": upstream_request_id or None,
                    }],
                )
        if isinstance(exception, (httpx.TimeoutException, TimeoutError)):
            return ServiceError(
                504, "GEMINI_TIMEOUT", "Gemini không phản hồi trong thời gian cho phép.",
                retryable=True, retry_after_seconds=5,
            )
        return ServiceError(
            503,
            "GEMINI_UNAVAILABLE",
            "Gemini tạm thời không khả dụng. Vui lòng thử lại sau.",
        )
