import asyncio
import json
import logging
import re
import time
import unicodedata
from collections.abc import Awaitable, Callable
from typing import Any

import google.auth
from google.auth.transport.requests import AuthorizedSession

from app.core.config import Settings
from app.core.exceptions import ServiceError
from app.schemas.hybrid import GroundedQuizOutput
from app.services.gemini_service import GeminiService, TokenUsage
from app.services.quiz_llm_provider import (
    LLMErrorCategory,
    LLMProviderError,
    QuizLLMCommand,
    QuizLLMPart,
    QuizLLMResult,
)
from app.services.structured_schema import provider_json_schema

GEMINI_SCOPE = "https://www.googleapis.com/auth/generative-language"
LOGGER = logging.getLogger("uvicorn.error")
EXCLUSION_INSTRUCTION = """
Already generated questions:
{questions}

DO NOT generate questions equivalent or semantically similar
to any question above.
""".strip()


def _normalize_prompt(value: str) -> str:
    return re.sub(
        r"\s+", " ", unicodedata.normalize("NFKC", value)
    ).strip().casefold()


def _trigrams(value: str) -> set[str]:
    return (
        {value}
        if len(value) < 3
        else {value[index:index + 3] for index in range(len(value) - 2)}
    )


def _equivalent_prompt(value: str, accepted: list[str]) -> bool:
    normalized = _normalize_prompt(value)
    grams = _trigrams(normalized)
    for existing in accepted:
        other = _normalize_prompt(existing)
        if normalized == other:
            return True
        other_grams = _trigrams(other)
        union = grams | other_grams
        similarity = len(grams & other_grams) / len(union) if union else 1.0
        if similarity >= 0.85:
            return True
    return False


def _retry_message(message: str, accepted: list[str]) -> str:
    questions = "\n".join(f"- {question}" for question in accepted[-50:])
    return message + "\n\n" + EXCLUSION_INSTRUCTION.format(questions=questions)


async def _generate_parts(
    command: QuizLLMCommand,
    provider_label: str,
    generate_part: Callable[
        [QuizLLMPart], Awaitable[tuple[GroundedQuizOutput, TokenUsage]]
    ],
) -> tuple[list[Any], TokenUsage]:
    parts = command.gemini_parts or (
        QuizLLMPart(command.message, command.question_count),
    )
    questions: list[Any] = []
    accepted_prompts: list[str] = []
    input_tokens = output_tokens = total_tokens = 0
    for part_index, original_part in enumerate(parts):
        accepted_part: list[Any] = []
        accepted_slots: set[str] = set()
        for attempt in range(2):
            missing_slots = tuple(
                slot
                for slot in original_part.plan_slot_ids
                if slot not in accepted_slots
            )
            missing_count = (
                len(missing_slots)
                if original_part.plan_slot_ids
                else original_part.question_count - len(accepted_part)
            )
            part = QuizLLMPart(
                message=(
                    _retry_message(
                        original_part.message, accepted_prompts
                    )
                    if accepted_prompts
                    else original_part.message
                ),
                question_count=missing_count,
                plan_slot_ids=missing_slots,
            )
            if command.event_sink is not None:
                await command.event_sink({
                    "type": (
                        "PART_STARTED"
                        if attempt == 0
                        else "RETRYING_MISSING_SLOTS"
                    ),
                    "level": "INFO" if attempt == 0 else "WARNING",
                    "message": (
                        f"Đang tạo phần {part_index + 1}/{len(parts)} bằng "
                        f"{_provider_display_name(provider_label)}."
                        if attempt == 0
                        else f"Đang tạo lại {missing_count} câu còn thiếu hoặc bị trùng."
                    ),
                    "provider": provider_label,
                    "batchIndex": command.batch_index,
                    "partIndex": part_index,
                    "totalParts": len(parts),
                    "requestedQuestions": missing_count,
                })
            started = time.perf_counter()
            try:
                output, usage = await generate_part(part)
            except LLMProviderError as error:
                LOGGER.warning(json.dumps({
                    "requestId": command.trace_id,
                    "provider": provider_label,
                    "modelBatchIndex": command.batch_index,
                    "partIndex": part_index,
                    "totalParts": len(parts),
                    "attempt": attempt + 1,
                    "requestedQuestions": missing_count,
                    "sourceBlockCount": _focus_source_count(part.message),
                    "success": False,
                    "errorCode": error.category.value,
                    "latencyMs": round(
                        (time.perf_counter() - started) * 1000
                    ),
                }, ensure_ascii=False, separators=(",", ":")))
                raise
            input_tokens += usage.input_tokens
            output_tokens += usage.output_tokens
            total_tokens += usage.total_tokens
            duplicate_count = 0
            accepted_before = len(accepted_part)
            for question in output.questions:
                if _equivalent_prompt(question.prompt, accepted_prompts):
                    duplicate_count += 1
                    continue
                accepted_prompts.append(question.prompt)
                accepted_part.append(question)
                if question.planSlotId:
                    accepted_slots.add(question.planSlotId)
            LOGGER.info(json.dumps({
                "requestId": command.trace_id,
                "provider": provider_label,
                "modelBatchIndex": command.batch_index,
                "partIndex": part_index,
                "totalParts": len(parts),
                "attempt": attempt + 1,
                "requestedQuestions": missing_count,
                "sourceBlockCount": _focus_source_count(part.message),
                "validQuestions": len(accepted_part) - accepted_before,
                "duplicateQuestions": duplicate_count,
                "outputTokens": usage.output_tokens,
                "success": True,
                "latencyMs": round(
                    (time.perf_counter() - started) * 1000
                ),
            }, ensure_ascii=False, separators=(",", ":")))
            if command.event_sink is not None:
                await command.event_sink({
                    "type": "PART_COMPLETED",
                    "level": "SUCCESS",
                    "message": (
                        f"Đã hoàn tất phần {part_index + 1}/{len(parts)}: "
                        f"{len(accepted_part) - accepted_before} câu đúng cấu trúc."
                    ),
                    "provider": provider_label,
                    "batchIndex": command.batch_index,
                    "partIndex": part_index,
                    "totalParts": len(parts),
                    "validQuestions": len(accepted_part) - accepted_before,
                    "duplicateQuestions": duplicate_count,
                })
            if len(accepted_part) == original_part.question_count:
                break
        if not accepted_part:
            raise LLMProviderError(
                LLMErrorCategory.INVALID_RESPONSE,
                f"{provider_label} không tạo được câu hỏi nào có thể sử dụng.",
                fallback_eligible=True,
            )
        if (
            len(accepted_part) != original_part.question_count
            and command.event_sink is not None
        ):
            await command.event_sink({
                "type": "QUESTION_COUNT_INCOMPLETE",
                "level": "WARNING",
                "message": (
                    f"{provider_label} chỉ tạo được {len(accepted_part)}/"
                    f"{original_part.question_count} câu có thể sử dụng."
                ),
                "provider": provider_label,
                "batchIndex": command.batch_index,
                "partIndex": part_index,
                "requestedQuestions": original_part.question_count,
                "savedQuestions": len(accepted_part),
            })
        if original_part.plan_slot_ids:
            by_slot = {
                question.planSlotId: question for question in accepted_part
            }
            accepted_part = [
                by_slot[slot]
                for slot in original_part.plan_slot_ids
                if slot in by_slot
            ]
        questions.extend(accepted_part)
    return questions, TokenUsage(input_tokens, output_tokens, total_tokens)


def _provider_display_name(provider: str) -> str:
    return {
        "gemini_oauth": "Gemini OAuth",
        "gemini_api_key": "Gemini API key",
    }.get(provider, provider)


def _focus_source_count(message: str) -> int:
    match = re.search(r"focusSourceIds=(\[[^\r\n]*\])", message)
    if match is None:
        return 0
    try:
        value = json.loads(match.group(1))
    except ValueError:
        return 0
    return len(value) if isinstance(value, list) else 0


def _map_service_error(error: ServiceError) -> LLMProviderError:
    code = error.code
    if code in {
        "GEMINI_API_AUTHENTICATION_FAILED",
        "GEMINI_MODEL_NOT_AVAILABLE",
    }:
        category = (
            LLMErrorCategory.AUTHENTICATION
            if code == "GEMINI_API_AUTHENTICATION_FAILED"
            else LLMErrorCategory.UNAVAILABLE
        )
        return LLMProviderError(
            category,
            error.message,
            fallback_eligible=True,
            code=code,
        )
    if code in {
        "GEMINI_RATE_LIMITED",
        "GEMINI_USER_RATE_LIMITED",
        "GEMINI_QUOTA_EXHAUSTED",
    }:
        return LLMProviderError(
            LLMErrorCategory.QUOTA,
            error.message,
            fallback_eligible=True,
            retryable=True,
            retry_after_seconds=error.retry_after_seconds,
        )
    if code in {"GEMINI_TIMEOUT", "GEMINI_UNAVAILABLE", "AI_SERVICE_TEMPORARILY_UNAVAILABLE"}:
        category = (
            LLMErrorCategory.TIMEOUT
            if code == "GEMINI_TIMEOUT"
            else LLMErrorCategory.UNAVAILABLE
        )
        return LLMProviderError(
            category,
            error.message,
            fallback_eligible=True,
            retryable=True,
            retry_after_seconds=error.retry_after_seconds,
        )
    if code == "GEMINI_SAFETY_BLOCKED":
        return LLMProviderError(
            LLMErrorCategory.SAFETY, error.message, fallback_eligible=False
        )
    if code == "GEMINI_API_REQUEST_INCOMPATIBLE":
        return LLMProviderError(
            LLMErrorCategory.INVALID_REQUEST,
            error.message,
            fallback_eligible=True,
            code=code,
        )
    return LLMProviderError(
        LLMErrorCategory.INVALID_RESPONSE,
        error.message,
        fallback_eligible=True,
    )


class GeminiApiKeyProvider:
    name = "gemini_api_key"

    def __init__(self, service: GeminiService, model: str) -> None:
        self._service = service
        self.model = model

    async def generate_quiz(self, command: QuizLLMCommand) -> QuizLLMResult:
        async def generate_part(
            part: QuizLLMPart,
        ) -> tuple[GroundedQuizOutput, TokenUsage]:
            response_schema = provider_json_schema(command.response_schema)
            questions_schema = response_schema["properties"]["questions"]
            if part.plan_slot_ids:
                questions_schema["items"]["properties"]["planSlotId"] = {
                    "type": "string",
                    "enum": list(part.plan_slot_ids),
                }
            try:
                result = await self._service.generate(
                    part.message,
                    system_instruction=command.system_instruction,
                    trace_id=command.trace_id,
                    response_schema=response_schema,
                    max_output_tokens=command.max_output_tokens,
                    max_attempts=1,
                )
            except ServiceError as error:
                raise _map_service_error(error) from error
            try:
                output = GroundedQuizOutput.model_validate_json(result.answer)
            except Exception as exception:
                raise LLMProviderError(
                    LLMErrorCategory.INVALID_RESPONSE,
                    "Gemini API key không trả về quiz đúng cấu trúc.",
                    fallback_eligible=True,
                ) from exception
            if len(output.questions) > part.question_count:
                raise LLMProviderError(
                    LLMErrorCategory.INVALID_RESPONSE,
                    "Gemini API key trả về nhiều câu hơn yêu cầu.",
                    fallback_eligible=True,
                )
            if part.plan_slot_ids:
                returned_slots = [question.planSlotId for question in output.questions]
                if (
                    any(not slot for slot in returned_slots)
                    or len(set(returned_slots)) != len(returned_slots)
                    or not set(returned_slots).issubset(set(part.plan_slot_ids))
                ):
                    raise LLMProviderError(
                        LLMErrorCategory.INVALID_RESPONSE,
                        "Gemini API key trả về sai kế hoạch câu hỏi.",
                        fallback_eligible=True,
                    )
            return output, result.usage

        questions, usage = await _generate_parts(
            command, self.name, generate_part
        )
        return QuizLLMResult(
            answer=GroundedQuizOutput(questions=questions).model_dump_json(),
            model=self.model,
            usage=usage,
            provider=self.name,
            generated_by_provider={self.name: len(questions)},
        )

    async def close(self) -> None:
        return None

    async def health(self) -> dict[str, Any]:
        return {
            "configured": True,
            "reachable": None,
            "model": self.model,
        }


class GeminiOAuthProvider:
    name = "gemini_oauth"

    def __init__(
        self,
        settings: Settings,
        *,
        session: Any | None = None,
    ) -> None:
        self.model = settings.gemini_oauth_model
        self._timeout = settings.gemini_oauth_timeout_seconds
        self._quota_project = settings.gemini_oauth_quota_project
        self._session = session
        self._owns_session = session is None
        self._configuration_error: str | None = None
        if self._session is None:
            try:
                credentials, _ = google.auth.default(
                    scopes=[GEMINI_SCOPE],
                    quota_project_id=self._quota_project or None,
                )
                self._quota_project = (
                    self._quota_project
                    or str(getattr(credentials, "quota_project_id", "") or "")
                )
                if not self._quota_project:
                    raise ValueError("OAuth ADC chưa có quota project.")
                self._session = AuthorizedSession(credentials)
            except Exception as exception:
                self._configuration_error = type(exception).__name__

    async def generate_quiz(self, command: QuizLLMCommand) -> QuizLLMResult:
        generated, combined_usage = await _generate_parts(
            command,
            self.name,
            lambda part: self._generate_part(command, part),
        )
        return QuizLLMResult(
            answer=GroundedQuizOutput(questions=generated).model_dump_json(),
            model=self.model,
            usage=combined_usage,
            provider=self.name,
            generated_by_provider={self.name: len(generated)},
        )

    async def _generate_part(
        self,
        command: QuizLLMCommand,
        part: QuizLLMPart,
    ) -> tuple[GroundedQuizOutput, TokenUsage]:
        if self._session is None:
            raise LLMProviderError(
                LLMErrorCategory.AUTHENTICATION,
                "Gemini OAuth ADC chưa được cấu hình hợp lệ.",
                fallback_eligible=True,
            )
        url = (
            "https://generativelanguage.googleapis.com/v1/models/"
            f"{self.model}:generateContent"
        )
        response_schema = provider_json_schema(command.response_schema)
        questions_schema = response_schema["properties"]["questions"]
        if part.plan_slot_ids:
            questions_schema["items"]["properties"]["planSlotId"] = {
                "type": "string",
                "enum": list(part.plan_slot_ids),
            }
        payload = {
            "systemInstruction": {
                "parts": [{"text": command.system_instruction}],
            },
            "contents": [{
                "role": "user",
                "parts": [{"text": part.message}],
            }],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": command.max_output_tokens,
                "responseMimeType": "application/json",
                "responseSchema": response_schema,
            },
        }
        headers = {
            "Content-Type": "application/json",
            "x-goog-user-project": self._quota_project,
        }
        try:
            response = await asyncio.to_thread(
                self._session.post,
                url,
                json=payload,
                headers=headers,
                timeout=self._timeout,
            )
        except Exception as exception:
            raise LLMProviderError(
                LLMErrorCategory.TIMEOUT,
                "Gemini OAuth không phản hồi.",
                fallback_eligible=True,
                retryable=True,
            ) from exception

        if response.status_code >= 400:
            self._raise_http_error(response)
        try:
            body = response.json()
            candidate = body["candidates"][0]
            answer = "".join(
                part.get("text", "")
                for part in candidate["content"]["parts"]
                if isinstance(part, dict)
            ).strip()
            if not answer:
                raise ValueError("empty answer")
            usage = body.get("usageMetadata", {})
        except (KeyError, IndexError, TypeError, ValueError) as exception:
            raise LLMProviderError(
                LLMErrorCategory.INVALID_RESPONSE,
                "Gemini OAuth không trả về quiz đúng cấu trúc.",
                fallback_eligible=True,
            ) from exception
        input_tokens = int(usage.get("promptTokenCount", 0) or 0)
        output_tokens = int(usage.get("candidatesTokenCount", 0) or 0)
        total_tokens = int(
            usage.get("totalTokenCount", input_tokens + output_tokens)
            or input_tokens + output_tokens
        )
        try:
            output = GroundedQuizOutput.model_validate_json(answer)
        except Exception as exception:
            raise LLMProviderError(
                LLMErrorCategory.INVALID_RESPONSE,
                "Gemini OAuth không trả về quiz đúng cấu trúc.",
                fallback_eligible=True,
            ) from exception
        if len(output.questions) > part.question_count:
            raise LLMProviderError(
                LLMErrorCategory.INVALID_RESPONSE,
                "Gemini OAuth trả về nhiều câu hơn yêu cầu.",
                fallback_eligible=True,
            )
        if part.plan_slot_ids:
            returned_slots = [question.planSlotId for question in output.questions]
            if (
                any(not slot for slot in returned_slots)
                or len(set(returned_slots)) != len(returned_slots)
                or not set(returned_slots).issubset(set(part.plan_slot_ids))
            ):
                raise LLMProviderError(
                    LLMErrorCategory.INVALID_RESPONSE,
                    "Gemini OAuth trả về sai kế hoạch câu hỏi.",
                    fallback_eligible=True,
                )
        return output, TokenUsage(input_tokens, output_tokens, total_tokens)

    def _raise_http_error(self, response: Any) -> None:
        status = int(response.status_code)
        text = str(getattr(response, "text", "") or "")
        normalized = text.casefold()
        try:
            body = response.json()
        except (TypeError, ValueError):
            body = {}
        error = body.get("error", {}) if isinstance(body, dict) else {}
        upstream_status = str(error.get("status", "") or "")
        details = error.get("details", []) if isinstance(error, dict) else []
        reasons = [
            str(item.get("reason", ""))[:80]
            for item in details
            if isinstance(item, dict) and item.get("reason")
        ]
        headers = getattr(response, "headers", {}) or {}
        upstream_request_id = str(
            headers.get("x-request-id")
            or headers.get("x-guploader-uploadid")
            or ""
        )[:120]
        LOGGER.warning(json.dumps({
            "provider": self.name,
            "model": self.model,
            "httpStatus": status,
            "upstreamStatus": upstream_status[:80],
            "upstreamReasons": reasons,
            "upstreamRequestId": upstream_request_id,
        }, ensure_ascii=False, separators=(",", ":")))
        if "safety" in normalized:
            raise LLMProviderError(
                LLMErrorCategory.SAFETY,
                "Gemini OAuth chặn phản hồi theo chính sách an toàn.",
                fallback_eligible=False,
            )
        if status == 400:
            raise LLMProviderError(
                LLMErrorCategory.INVALID_REQUEST,
                "Gemini OAuth không tương thích với yêu cầu sinh quiz; đang chuyển nhà cung cấp.",
                fallback_eligible=True,
                code="GEMINI_OAUTH_REQUEST_INCOMPATIBLE",
            )
        category = (
            LLMErrorCategory.AUTHENTICATION
            if status in {401, 403}
            else LLMErrorCategory.QUOTA
            if status == 429
            else LLMErrorCategory.TIMEOUT
            if status == 408
            else LLMErrorCategory.UNAVAILABLE
        )
        fallback = status in {401, 403, 404, 408, 429, 500, 502, 503, 504}
        raise LLMProviderError(
            category,
            "Gemini OAuth tạm thời không khả dụng.",
            fallback_eligible=fallback,
            retryable=status in {408, 429, 500, 502, 503, 504},
        )

    async def close(self) -> None:
        if self._owns_session and self._session is not None:
            await asyncio.to_thread(self._session.close)

    async def health(self) -> dict[str, Any]:
        return {
            "configured": self._session is not None,
            "reachable": None,
            "model": self.model,
            "errorCode": self._configuration_error,
            "quotaProjectConfigured": bool(self._quota_project),
        }
