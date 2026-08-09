import asyncio
import json
import logging
import re
import time
import unicodedata
from typing import Any

import httpx
from pydantic import ValidationError

from app.core.config import Settings
from app.schemas.hybrid import GroundedQuizOutput, GroundedQuizQuestionOutput
from app.services.gemini_service import TokenUsage
from app.services.quiz_llm_provider import (
    LLMErrorCategory,
    LLMProviderError,
    QuizLLMCommand,
    QuizLLMPart,
    QuizLLMResult,
)
from app.services.structured_schema import provider_json_schema

LOGGER = logging.getLogger("uvicorn.error")
QWEN_QUIZ_SUFFIX = """
Chỉ trả lời bằng JSON đúng schema, không markdown và không văn bản bên ngoài JSON.
Chỉ dùng kiến thức trong context; không suy đoán hoặc tạo dữ kiện mới.
Tạo đúng số câu được yêu cầu, có đáp án hợp lệ và không tạo câu trùng.
Mỗi planSlotId phải kiểm tra một ý kiến thức khác và có đáp án đúng khác các slot còn lại.
Mọi citation chỉ được dùng sourceId xuất hiện trong context; không bịa metadata tài liệu.
evidenceQuote phải là đoạn nguyên văn trong phần nội dung nguồn, không kèm nhãn "Nội dung:" hoặc metadata.
Tuân thủ loại câu, planSlotId, Cognitive Level và complexity constraint được cung cấp.
Prompt chỉ một câu; giải thích chỉ một câu; mỗi option tối đa 8 từ.
Mỗi evidenceQuote tối đa 20 từ và không lặp lại toàn bộ context.
Không trả hoặc mô tả quá trình suy luận nội bộ.
""".strip()
QWEN_DUPLICATE_EXCLUSION = """
Already generated questions:
{questions}

DO NOT generate questions equivalent or semantically similar
to any question above.
""".strip()


def build_batches(total: int, max_batch_size: int) -> list[int]:
    if total < 0:
        raise ValueError("total must not be negative")
    if max_batch_size < 1:
        raise ValueError("max_batch_size must be positive")
    batches: list[int] = []
    remaining = total
    while remaining:
        size = min(max_batch_size, remaining)
        batches.append(size)
        remaining -= size
    return batches


class OllamaQwenProvider:
    name = "ollama"

    def __init__(
        self,
        settings: Settings,
        *,
        client: httpx.AsyncClient | Any | None = None,
    ) -> None:
        self.model = settings.ollama_model
        self._base_url = settings.ollama_base_url
        self._context_size = settings.ollama_context_size
        self._max_output_tokens = settings.ollama_max_output_tokens
        self._temperature = settings.ollama_temperature
        self._keep_alive = settings.ollama_keep_alive
        self._max_questions = settings.ollama_max_questions_per_call
        self._max_retries = settings.ollama_batch_max_retries
        self._semaphore = asyncio.Semaphore(1)
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(settings.ollama_timeout_seconds),
            limits=httpx.Limits(max_connections=1, max_keepalive_connections=1),
        )

    async def generate_quiz(self, command: QuizLLMCommand) -> QuizLLMResult:
        parts = command.ollama_parts or tuple(
            QuizLLMPart(command.message, size)
            for size in build_batches(command.question_count, self._max_questions)
        )
        if any(part.question_count > self._max_questions for part in parts):
            raise LLMProviderError(
                LLMErrorCategory.INVALID_REQUEST,
                "Qwen không được tạo quá bốn câu trong một request.",
                fallback_eligible=False,
            )
        accepted: list[GroundedQuizQuestionOutput] = []
        accepted_prompts: dict[str, str] = {}
        input_tokens = output_tokens = total_tokens = 0
        async with self._semaphore:
            for part_index, part in enumerate(parts):
                if command.event_sink is not None:
                    await command.event_sink({
                        "type": "PART_STARTED",
                        "level": "INFO",
                        "message": (
                            f"Đang tạo phần {part_index + 1}/{len(parts)} "
                            "bằng Ollama Qwen."
                        ),
                        "provider": self.name,
                        "batchIndex": command.batch_index,
                        "partIndex": part_index,
                        "totalParts": len(parts),
                        "requestedQuestions": part.question_count,
                    })
                started = time.perf_counter()
                part_questions, usage = await self._generate_part(
                    command,
                    part,
                    accepted_prompts,
                    part_index,
                    len(parts),
                )
                LOGGER.info(json.dumps({
                    "requestId": command.trace_id,
                    "provider": self.name,
                    "model": self.model,
                    "batchIndex": command.batch_index,
                    "partIndex": part_index,
                    "totalParts": len(parts),
                    "requestedQuestions": part.question_count,
                    "sourceBlockCount": self._focus_source_count(part.message),
                    "validQuestions": len(part_questions),
                    "success": True,
                    "latencyMs": round((time.perf_counter() - started) * 1000),
                }, ensure_ascii=False, separators=(",", ":")))
                if command.event_sink is not None:
                    await command.event_sink({
                        "type": "PART_COMPLETED",
                        "level": "SUCCESS",
                        "message": (
                            f"Đã hoàn tất phần {part_index + 1}/{len(parts)}: "
                        f"{len(part_questions)} câu đúng cấu trúc."
                        ),
                        "provider": self.name,
                        "batchIndex": command.batch_index,
                        "partIndex": part_index,
                        "totalParts": len(parts),
                        "validQuestions": len(part_questions),
                    })
                accepted.extend(part_questions)
                input_tokens += usage.input_tokens
                output_tokens += usage.output_tokens
                total_tokens += usage.total_tokens
        if not accepted:
            raise LLMProviderError(
                LLMErrorCategory.INVALID_RESPONSE,
                "Qwen không tạo được câu hỏi nào có thể sử dụng.",
                fallback_eligible=True,
            )
        output = GroundedQuizOutput(questions=accepted)
        return QuizLLMResult(
            answer=output.model_dump_json(),
            model=self.model,
            usage=TokenUsage(input_tokens, output_tokens, total_tokens),
            provider=self.name,
            generated_by_provider={self.name: len(accepted)},
        )

    async def _generate_part(
        self,
        command: QuizLLMCommand,
        part: QuizLLMPart,
        accepted_prompts: dict[str, str],
        part_index: int,
        total_parts: int,
    ) -> tuple[list[GroundedQuizQuestionOutput], TokenUsage]:
        accepted: list[GroundedQuizQuestionOutput] = []
        accepted_slots: set[str] = set()
        usage_total = TokenUsage(0, 0, 0)
        attempts = self._max_retries + 1
        for attempt in range(attempts):
            missing_slots = tuple(
                slot for slot in part.plan_slot_ids if slot not in accepted_slots
            )
            missing_count = (
                len(missing_slots)
                if part.plan_slot_ids
                else part.question_count - len(accepted)
            )
            if missing_count <= 0:
                break
            message = part.message
            if part.plan_slots and missing_slots:
                selected_plans = [
                    slot
                    for slot in part.plan_slots
                    if str(slot.get("planSlotId")) in missing_slots
                ]
                message += (
                    "\nKế hoạch DUY NHẤT áp dụng cho response này là: "
                    + json.dumps(selected_plans, ensure_ascii=False)
                    + ". Không tạo câu cho slot khác."
                )
            if accepted_prompts:
                excluded = list(accepted_prompts.values())[-20:]
                message += (
                    "\n"
                    + QWEN_DUPLICATE_EXCLUSION.format(
                        questions="\n".join(
                            f"- {prompt}" for prompt in excluded
                        )
                    )
                )
            if accepted:
                message += (
                    "\nYêu cầu bổ sung: chỉ tạo chính xác "
                    f"{missing_count} câu còn thiếu"
                    + (
                        f" cho planSlotId {list(missing_slots)}."
                        if missing_slots
                        else "."
                    )
                )
            body = await self._request(
                message=self._compact_message(message),
                system_instruction=command.system_instruction + "\n" + QWEN_QUIZ_SUFFIX,
                schema=command.response_schema,
                allowed_plan_slot_ids=missing_slots,
                expected_questions=missing_count,
            )
            usage = self._usage(body)
            usage_total = TokenUsage(
                usage_total.input_tokens + usage.input_tokens,
                usage_total.output_tokens + usage.output_tokens,
                usage_total.total_tokens + usage.total_tokens,
            )
            candidates = self._extract_candidates(body)
            rejected_slots = 0
            rejected_citations = 0
            rejected_duplicates = 0
            for question in candidates:
                if part.plan_slot_ids:
                    if (
                        not question.planSlotId
                        or question.planSlotId not in missing_slots
                        or question.planSlotId in accepted_slots
                    ):
                        rejected_slots += 1
                        continue
                if not self._citations_allowed(
                    question, command.allowed_source_ids
                ):
                    rejected_citations += 1
                    continue
                prompt_key = self._normalize(question.prompt)
                if self._is_duplicate(question.prompt, accepted_prompts):
                    rejected_duplicates += 1
                    continue
                accepted_prompts[prompt_key] = question.prompt
                accepted.append(question)
                if question.planSlotId:
                    accepted_slots.add(question.planSlotId)
                if len(accepted) == part.question_count:
                    break
            if len(accepted) == part.question_count:
                break
            if command.event_sink is not None:
                await command.event_sink({
                    "type": "RETRYING_MISSING_SLOTS",
                    "level": "WARNING",
                    "message": (
                        f"Qwen đang tạo lại {part.question_count - len(accepted)} "
                        "câu còn thiếu hoặc bị trùng."
                    ),
                    "provider": self.name,
                    "batchIndex": command.batch_index,
                    "partIndex": part_index,
                    "totalParts": total_parts,
                    "duplicateQuestions": rejected_duplicates,
                    "rejectedCitations": rejected_citations,
                })
            LOGGER.warning(json.dumps({
                "requestId": command.trace_id,
                "provider": self.name,
                "model": self.model,
                "batchIndex": command.batch_index,
                "partIndex": part_index,
                "totalParts": total_parts,
                "subBatchAttempt": attempt + 1,
                "requestedQuestions": missing_count,
                "sourceBlockCount": self._focus_source_count(part.message),
                "parsedCandidates": len(candidates),
                "acceptedQuestions": len(accepted),
                "rejectedSlots": rejected_slots,
                "rejectedCitations": rejected_citations,
                "rejectedDuplicates": rejected_duplicates,
                "doneReason": body.get("done_reason"),
                "outputTokens": usage.output_tokens,
                "success": False,
                "errorCode": "OLLAMA_OUTPUT_INCOMPLETE",
            }, ensure_ascii=False, separators=(",", ":")))
            if (
                body.get("done_reason") == "length"
                and not candidates
                and missing_count > 1
            ):
                recovered: list[GroundedQuizQuestionOutput] = []
                groups: list[tuple[str, ...]]
                if missing_slots:
                    midpoint = (len(missing_slots) + 1) // 2
                    groups = [
                        missing_slots[:midpoint],
                        missing_slots[midpoint:],
                    ]
                else:
                    first_size = (missing_count + 1) // 2
                    groups = [tuple("" for _ in range(first_size))]
                    groups.append(tuple("" for _ in range(missing_count - first_size)))
                for group in groups:
                    if not group:
                        continue
                    slot_ids = tuple(slot for slot in group if slot)
                    target = (
                        f" các planSlotId {list(slot_ids)}"
                        if slot_ids
                        else ""
                    )
                    split_part = QuizLLMPart(
                        message=(
                            part.message
                            + "\nYêu cầu thay thế: chỉ tạo chính xác "
                            + f"{len(group)} câu{target}; bỏ qua các slot còn lại."
                        ),
                        question_count=len(group),
                        plan_slot_ids=slot_ids,
                        plan_slots=tuple(
                            slot
                            for slot in part.plan_slots
                            if str(slot.get("planSlotId")) in slot_ids
                        ),
                    )
                    split_questions, split_usage = await self._generate_part(
                        command,
                        split_part,
                        accepted_prompts,
                        part_index,
                        total_parts,
                    )
                    recovered.extend(split_questions)
                    usage_total = TokenUsage(
                        usage_total.input_tokens + split_usage.input_tokens,
                        usage_total.output_tokens + split_usage.output_tokens,
                        usage_total.total_tokens + split_usage.total_tokens,
                    )
                if len(recovered) == missing_count:
                    accepted.extend(recovered)
                    break
            if attempt + 1 == attempts:
                if not accepted:
                    raise LLMProviderError(
                        LLMErrorCategory.INVALID_RESPONSE,
                        "Qwen không tạo được câu hỏi nào có thể sử dụng sau lần sửa giới hạn.",
                        fallback_eligible=True,
                    )
                if command.event_sink is not None:
                    await command.event_sink({
                        "type": "QUESTION_COUNT_INCOMPLETE",
                        "level": "WARNING",
                        "message": (
                            f"Qwen chỉ tạo được {len(accepted)}/"
                            f"{part.question_count} câu có thể sử dụng."
                        ),
                        "provider": self.name,
                        "batchIndex": command.batch_index,
                        "partIndex": part_index,
                        "requestedQuestions": part.question_count,
                        "savedQuestions": len(accepted),
                    })
                break
        return accepted, usage_total

    async def _request(
        self,
        *,
        message: str,
        system_instruction: str,
        schema: Any,
        allowed_plan_slot_ids: tuple[str, ...],
        expected_questions: int,
    ) -> dict[str, Any]:
        output_schema = provider_json_schema(schema)
        questions_schema = output_schema["properties"]["questions"]
        questions_schema["minItems"] = expected_questions
        questions_schema["maxItems"] = expected_questions
        question_schema = questions_schema["items"]
        if allowed_plan_slot_ids:
            question_schema["properties"]["planSlotId"] = {
                "type": "string",
                "enum": list(allowed_plan_slot_ids),
            }
        self._limit_quiz_schema(question_schema)
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": message},
            ],
            "stream": False,
            "think": False,
            "format": output_schema,
            "options": {
                "num_ctx": self._context_size,
                "num_predict": self._max_output_tokens,
                "temperature": self._temperature,
            },
            "keep_alive": self._keep_alive,
        }
        try:
            response = await self._client.post("/api/chat", json=payload)
        except (httpx.TimeoutException, httpx.TransportError) as exception:
            raise LLMProviderError(
                LLMErrorCategory.TIMEOUT,
                "Ollama không phản hồi trong thời gian cho phép.",
                fallback_eligible=True,
                retryable=True,
            ) from exception
        if response.status_code >= 400:
            status = response.status_code
            category = (
                LLMErrorCategory.INVALID_REQUEST
                if status == 400
                else LLMErrorCategory.UNAVAILABLE
            )
            raise LLMProviderError(
                category,
                "Ollama từ chối yêu cầu." if status == 400 else "Ollama không khả dụng.",
                fallback_eligible=status != 400,
                retryable=status in {408, 429, 500, 502, 503, 504},
            )
        try:
            return response.json()
        except ValueError as exception:
            raise LLMProviderError(
                LLMErrorCategory.INVALID_RESPONSE,
                "Ollama trả về response không hợp lệ.",
                fallback_eligible=True,
            ) from exception

    @staticmethod
    def _limit_quiz_schema(question_schema: dict[str, Any]) -> None:
        """Keep local-model output bounded without weakening server validation."""
        properties = question_schema["properties"]
        properties["prompt"]["maxLength"] = 600
        properties["explanation"]["maxLength"] = 600
        properties["options"]["maxItems"] = 4
        properties["acceptedAnswers"]["maxItems"] = 8
        option_schema = properties["options"]["items"]
        option_schema["properties"]["text"]["maxLength"] = 300
        for field in (
            "questionCitations",
            "answerCitations",
            "explanationCitations",
        ):
            properties[field]["maxItems"] = 1
            citation_schema = properties[field]["items"]
            citation_schema["properties"]["evidenceQuote"]["maxLength"] = 300
        profile = properties.get("complexityProfile")
        if isinstance(profile, dict):
            candidates = profile.get("anyOf", [])
            profile_schema = next(
                (item for item in candidates if item.get("type") == "object"),
                None,
            )
            if profile_schema:
                profile_properties = profile_schema["properties"]
                profile_properties["conceptsUsed"]["maxItems"] = 6
                summary = profile_properties.get("novelScenarioSummary")
                if isinstance(summary, dict):
                    for candidate in summary.get("anyOf", []):
                        if candidate.get("type") == "string":
                            candidate["maxLength"] = 300

    @staticmethod
    def _extract_candidates(body: dict[str, Any]) -> list[GroundedQuizQuestionOutput]:
        try:
            raw_answer = body["message"]["content"]
            raw = json.loads(raw_answer)
            questions = raw.get("questions", [])
            if not isinstance(questions, list):
                return []
        except (KeyError, TypeError, ValueError):
            return []
        valid: list[GroundedQuizQuestionOutput] = []
        for item in questions:
            try:
                valid.append(GroundedQuizQuestionOutput.model_validate(item))
            except ValidationError:
                continue
        return valid

    @staticmethod
    def _citations_allowed(
        question: GroundedQuizQuestionOutput,
        allowed: frozenset[str],
    ) -> bool:
        if not allowed:
            return True
        citations = (
            question.questionCitations
            + question.answerCitations
            + question.explanationCitations
        )
        return bool(citations) and all(item.sourceId in allowed for item in citations)

    @staticmethod
    def _normalize(text: str) -> str:
        normalized = unicodedata.normalize("NFKC", text).casefold()
        return re.sub(r"\s+", " ", normalized).strip()

    @classmethod
    def _is_duplicate(
        cls,
        prompt: str,
        accepted_prompts: dict[str, str],
    ) -> bool:
        normalized = cls._normalize(prompt)
        if normalized in accepted_prompts:
            return True
        grams = cls._trigrams(normalized)
        for existing in accepted_prompts:
            other_grams = cls._trigrams(existing)
            union = grams | other_grams
            similarity = (
                len(grams & other_grams) / len(union) if union else 1.0
            )
            if similarity >= 0.85:
                return True
        return False

    @staticmethod
    def _trigrams(value: str) -> set[str]:
        if len(value) < 3:
            return {value}
        return {
            value[index:index + 3] for index in range(len(value) - 2)
        }

    @staticmethod
    def _focus_source_count(message: str) -> int:
        match = re.search(r"focusSourceIds=(\[[^\r\n]*\])", message)
        if match is None:
            return 0
        try:
            value = json.loads(match.group(1))
        except ValueError:
            return 0
        return len(value) if isinstance(value, list) else 0

    @staticmethod
    def _usage(body: dict[str, Any]) -> TokenUsage:
        input_tokens = int(body.get("prompt_eval_count", 0) or 0)
        output_tokens = int(body.get("eval_count", 0) or 0)
        return TokenUsage(input_tokens, output_tokens, input_tokens + output_tokens)

    def _compact_message(self, message: str) -> str:
        start = message.find("<context>")
        end = message.rfind("</context>")
        if start < 0 or end <= start:
            return message
        prefix = message[: start + len("<context>")]
        suffix = message[end:]
        context = message[start + len("<context>"):end].strip()
        # Reserve roughly half of the configured window for schema and output.
        context_budget = max(1000, self._context_size * 2)
        if len(context) <= context_budget:
            return message
        selected: list[str] = []
        used = 0
        for block in context.split("\n\n"):
            needed = len(block) + (2 if selected else 0)
            if used + needed > context_budget:
                continue
            selected.append(block)
            used += needed
        return prefix + "\n" + "\n\n".join(selected) + "\n" + suffix

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def health(self) -> dict[str, Any]:
        try:
            response = await self._client.get("/api/tags", timeout=5)
            response.raise_for_status()
            models = response.json().get("models", [])
            available = any(
                item.get("name") == self.model or item.get("model") == self.model
                for item in models
            )
            return {
                "configured": True,
                "reachable": True,
                "model": self.model,
                "modelAvailable": available,
            }
        except Exception:
            return {
                "configured": True,
                "reachable": False,
                "model": self.model,
                "modelAvailable": False,
            }
