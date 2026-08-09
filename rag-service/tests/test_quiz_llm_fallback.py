import json
from dataclasses import dataclass, replace
from typing import Any

import httpx
import pytest

from app.core.config import Settings
from app.main import build_quiz_providers
from app.schemas.hybrid import GroundedQuizOutput
from app.services.gemini_quiz_providers import GeminiApiKeyProvider, GeminiOAuthProvider
from app.services.gemini_service import GeminiResult, TokenUsage
from app.services.ollama_qwen_provider import (
    OllamaQwenProvider,
    build_batches,
)
from app.services.quiz_llm_provider import (
    LLMErrorCategory,
    LLMProviderError,
    QuizLLMCommand,
    QuizLLMPart,
    QuizLLMResult,
    QuizLLMRouter,
)
from app.services.structured_schema import provider_json_schema


@dataclass
class FakeProvider:
    name: str
    outcome: QuizLLMResult | Exception
    model: str = "test-model"
    calls: int = 0

    async def generate_quiz(self, command: QuizLLMCommand) -> QuizLLMResult:
        self.calls += 1
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome

    async def close(self) -> None:
        return None

    async def health(self) -> dict[str, Any]:
        return {"configured": True}


def _question(index: int, slot: str | None = None) -> dict[str, Any]:
    citation = {"sourceId": "S1", "evidenceQuote": "Grounded evidence"}
    return {
        "type": "SINGLE_CHOICE",
        "difficulty": "EASY",
        "planSlotId": slot,
        "prompt": f"Question {index}?",
        "explanation": "Grounded evidence",
        "options": [
            {"text": "A", "correct": True},
            {"text": "B", "correct": False},
            {"text": "C", "correct": False},
            {"text": "D", "correct": False},
        ],
        "acceptedAnswers": [],
        "questionCitations": [citation],
        "answerCitations": [citation],
        "explanationCitations": [citation],
    }


def _result(provider: str, count: int) -> QuizLLMResult:
    return QuizLLMResult(
        answer=json.dumps({"questions": [_question(index) for index in range(count)]}),
        model="test-model",
        usage=TokenUsage(1, 1, 2),
        provider=provider,
    )


def _command(count: int = 1) -> QuizLLMCommand:
    return QuizLLMCommand(
        message="Generate",
        system_instruction="System",
        response_schema=GroundedQuizOutput,
        question_count=count,
        batch_index=0,
        trace_id="trace-1",
    )


def test_quiz_provider_defaults_use_stable_batch_sizes() -> None:
    fields = Settings.model_fields
    assert fields["gemini_batch_size"].default == 10
    assert fields["gemini_oauth_timeout_seconds"].default == 120
    assert fields["ollama_max_questions_per_call"].default == 2
    assert fields["ollama_max_output_tokens"].default == 2400


@pytest.mark.asyncio
async def test_quiz_provider_order_prefers_api_key_before_oauth(
    settings: Settings,
) -> None:
    configured = settings.model_copy(update={
        "gemini_api_key": "configured",
        "gemini_oauth_enabled": True,
        "ollama_enabled": True,
    })

    providers = build_quiz_providers(configured, object())

    assert [provider.name for provider in providers] == [
        "gemini_api_key",
        "gemini_oauth",
        "ollama",
    ]
    for provider in providers:
        await provider.close()


@pytest.mark.asyncio
async def test_missing_api_key_is_reported_before_oauth_fallback(
    settings: Settings,
) -> None:
    events: list[dict[str, Any]] = []

    async def capture(event: dict[str, Any]) -> None:
        events.append(event)

    configured = settings.model_copy(update={
        "gemini_api_key": "",
        "gemini_oauth_enabled": True,
        "ollama_enabled": False,
    })
    providers = build_quiz_providers(configured, None)
    await providers[1].close()
    providers[1] = FakeProvider(
        "gemini_oauth", _result("gemini_oauth", 1)
    )
    router = QuizLLMRouter(
        providers, failure_threshold=1, cooldown_seconds=300
    )

    result = await router.generate_quiz(
        replace(_command(), event_sink=capture)
    )

    assert result.provider == "gemini_oauth"
    assert any(
        event.get("errorCode") == "GEMINI_API_NOT_CONFIGURED"
        for event in events
    )
    await router.close()


@pytest.mark.asyncio
async def test_router_always_attempts_api_key_even_when_its_circuit_is_open() -> None:
    api_key = FakeProvider(
        "gemini_api_key",
        LLMProviderError(
            LLMErrorCategory.TIMEOUT,
            "timeout",
            fallback_eligible=True,
            retryable=True,
        ),
    )
    oauth = FakeProvider("gemini_oauth", _result("gemini_oauth", 1))
    router = QuizLLMRouter(
        [api_key, oauth], failure_threshold=1, cooldown_seconds=300
    )

    await router.generate_quiz(_command())
    await router.generate_quiz(replace(_command(), trace_id="trace-2"))

    assert [api_key.calls, oauth.calls] == [2, 2]


@pytest.mark.asyncio
async def test_router_stops_after_first_success() -> None:
    api_key = FakeProvider("gemini_api_key", _result("gemini_api_key", 1))
    oauth = FakeProvider("gemini_oauth", _result("gemini_oauth", 1))
    ollama = FakeProvider("ollama", _result("ollama", 1))
    router = QuizLLMRouter(
        [api_key, oauth, ollama], failure_threshold=1, cooldown_seconds=300
    )

    result = await router.generate_quiz(_command())

    assert result.provider == "gemini_api_key"
    assert [api_key.calls, oauth.calls, ollama.calls] == [1, 0, 0]


@pytest.mark.asyncio
async def test_oauth_request_incompatibility_falls_back_to_ollama() -> None:
    api_key = FakeProvider(
        "gemini_api_key",
        LLMProviderError(
            LLMErrorCategory.AUTHENTICATION,
            "API key bị từ chối.",
            fallback_eligible=True,
            code="GEMINI_API_AUTHENTICATION_FAILED",
        ),
    )
    oauth = FakeProvider(
        "gemini_oauth",
        LLMProviderError(
            LLMErrorCategory.INVALID_REQUEST,
            "Gemini OAuth không tương thích với yêu cầu sinh quiz.",
            fallback_eligible=True,
            code="GEMINI_OAUTH_REQUEST_INCOMPATIBLE",
        ),
    )
    ollama = FakeProvider("ollama", _result("ollama", 1))
    router = QuizLLMRouter(
        [api_key, oauth, ollama], failure_threshold=1, cooldown_seconds=300
    )

    result = await router.generate_quiz(_command())

    assert result.provider == "ollama"
    assert [api_key.calls, oauth.calls, ollama.calls] == [1, 1, 1]


@pytest.mark.asyncio
async def test_router_emits_provider_failure_and_ollama_fallback_events() -> None:
    events: list[dict[str, Any]] = []

    async def capture(event: dict[str, Any]) -> None:
        events.append(event)

    oauth = FakeProvider(
        "gemini_oauth",
        LLMProviderError(
            LLMErrorCategory.TIMEOUT,
            "timeout",
            fallback_eligible=True,
            retryable=True,
        ),
    )
    api_key = FakeProvider(
        "gemini_api_key",
        LLMProviderError(
            LLMErrorCategory.QUOTA,
            "quota",
            fallback_eligible=True,
            retryable=True,
        ),
    )
    ollama = FakeProvider("ollama", _result("ollama", 1))
    router = QuizLLMRouter(
        [oauth, api_key, ollama],
        failure_threshold=1,
        cooldown_seconds=300,
    )

    await router.generate_quiz(replace(_command(), event_sink=capture))

    assert [event["type"] for event in events] == [
        "PROVIDER_STARTED",
        "PROVIDER_FAILED",
        "FALLBACK_STARTED",
        "PROVIDER_STARTED",
        "PROVIDER_FAILED",
        "FALLBACK_STARTED",
        "PROVIDER_STARTED",
        "PROVIDER_COMPLETED",
    ]
    assert events[5]["provider"] == "ollama"
    assert events[5]["message"] == (
        "Gemini không thể hoàn tất yêu cầu. Đang chuyển sang Ollama Qwen."
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "category",
    [
        LLMErrorCategory.AUTHENTICATION,
        LLMErrorCategory.QUOTA,
        LLMErrorCategory.TIMEOUT,
        LLMErrorCategory.UNAVAILABLE,
    ],
)
async def test_router_falls_back_for_provider_errors(category: LLMErrorCategory) -> None:
    api_key = FakeProvider(
        "gemini_api_key",
        LLMProviderError(category, "failed", fallback_eligible=True),
    )
    oauth = FakeProvider("gemini_oauth", _result("gemini_oauth", 1))
    ollama = FakeProvider("ollama", _result("ollama", 1))
    router = QuizLLMRouter(
        [api_key, oauth, ollama], failure_threshold=1, cooldown_seconds=300
    )

    result = await router.generate_quiz(_command())

    assert result.provider == "gemini_oauth"
    assert [api_key.calls, oauth.calls, ollama.calls] == [1, 1, 0]


@pytest.mark.asyncio
async def test_router_does_not_fallback_for_invalid_request() -> None:
    failed = FakeProvider(
        "gemini_api_key",
        LLMProviderError(
            LLMErrorCategory.INVALID_REQUEST,
            "bad request",
            fallback_eligible=False,
        ),
    )
    oauth = FakeProvider(
        "gemini_oauth",
        LLMProviderError(
            LLMErrorCategory.TIMEOUT,
            "timeout",
            fallback_eligible=True,
        ),
    )
    ollama = FakeProvider("ollama", _result("ollama", 1))
    router = QuizLLMRouter(
        [failed, oauth, ollama], failure_threshold=1, cooldown_seconds=300
    )

    with pytest.raises(LLMProviderError):
        await router.generate_quiz(_command())

    assert oauth.calls == 0


@pytest.mark.asyncio
async def test_router_skips_open_provider_circuit() -> None:
    api_key = FakeProvider(
        "gemini_api_key",
        LLMProviderError(
            LLMErrorCategory.AUTHENTICATION,
            "bad credentials",
            fallback_eligible=True,
        ),
    )
    oauth = FakeProvider(
        "gemini_oauth",
        LLMProviderError(
            LLMErrorCategory.TIMEOUT,
            "timeout",
            fallback_eligible=True,
        ),
    )
    ollama = FakeProvider("ollama", _result("ollama", 1))
    router = QuizLLMRouter(
        [api_key, oauth, ollama], failure_threshold=1, cooldown_seconds=300
    )

    await router.generate_quiz(_command())
    await router.generate_quiz(_command())

    assert api_key.calls == 2
    assert oauth.calls == 1
    assert ollama.calls == 2


@pytest.mark.asyncio
async def test_router_falls_back_after_malformed_provider_json() -> None:
    malformed = FakeProvider(
        "gemini_api_key",
        QuizLLMResult(
            answer="{not-json",
            model="bad",
            usage=TokenUsage(0, 0, 0),
            provider="gemini_api_key",
        ),
    )
    oauth = FakeProvider("gemini_oauth", _result("gemini_oauth", 1))
    router = QuizLLMRouter(
        [malformed, oauth], failure_threshold=1, cooldown_seconds=300
    )

    result = await router.generate_quiz(_command())

    assert result.provider == "gemini_oauth"


@pytest.mark.parametrize(
    ("total", "expected"),
    [
        (4, [4]),
        (5, [4, 1]),
        (10, [4, 4, 2]),
        (40, [4] * 10),
    ],
)
def test_build_batches(total: int, expected: list[int]) -> None:
    assert build_batches(total, 4) == expected


def test_ollama_schema_is_inlined_but_keeps_all_fields_required() -> None:
    schema = provider_json_schema(GroundedQuizOutput)
    serialized = json.dumps(schema)

    assert "$defs" not in schema
    assert "$ref" not in serialized
    question_schema = schema["properties"]["questions"]["items"]
    assert set(question_schema["required"]) == set(question_schema["properties"])


@pytest.mark.asyncio
async def test_ollama_batches_sequentially_and_disables_thinking(
    settings: Settings,
) -> None:
    requests: list[dict[str, Any]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        requests.append(payload)
        user_message = payload["messages"][1]["content"]
        count = int(user_message.split("COUNT=")[1].split()[0])
        start = sum(
            int(item["messages"][1]["content"].split("COUNT=")[1].split()[0])
            for item in requests[:-1]
        )
        questions = [
            _question(start + index, f"SLOT-{start + index}")
            for index in range(count)
        ]
        return httpx.Response(
            200,
            json={
                "message": {"role": "assistant", "content": json.dumps({"questions": questions})},
                "prompt_eval_count": 10,
                "eval_count": 20,
            },
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://ollama.test",
    )
    configured = settings.model_copy(update={
        "ollama_max_questions_per_call": 2,
        "ollama_max_output_tokens": 2400,
    })
    provider = OllamaQwenProvider(configured, client=client)
    parts = (
        QuizLLMPart("COUNT=2 generate", 2, ("SLOT-0", "SLOT-1")),
        QuizLLMPart("COUNT=2 generate", 2, ("SLOT-2", "SLOT-3")),
        QuizLLMPart("COUNT=1 generate", 1, ("SLOT-4",)),
    )
    command = _command(5)
    command = QuizLLMCommand(
        **{**command.__dict__, "ollama_parts": parts, "allowed_source_ids": frozenset({"S1"})}
    )

    result = await provider.generate_quiz(command)

    assert len(GroundedQuizOutput.model_validate_json(result.answer).questions) == 5
    assert len(requests) == 3
    assert all(item["think"] is False for item in requests)
    assert all(item["stream"] is False for item in requests)
    assert all(item["options"]["num_ctx"] == 4096 for item in requests)
    assert all(item["options"]["num_predict"] == 2400 for item in requests)
    assert requests[0]["format"]["properties"]["questions"]["items"]["properties"][
        "planSlotId"
    ]["enum"] == ["SLOT-0", "SLOT-1"]
    await client.aclose()


@pytest.mark.asyncio
async def test_ollama_retries_semantically_similar_prompt_with_exclusions(
    settings: Settings,
) -> None:
    requests: list[dict[str, Any]] = []
    prompts = [
        "Functional cohesion xảy ra khi mọi thành phần cùng phục vụ một chức năng?",
        "Functional cohesion xảy ra nếu mọi thành phần cùng phục vụ một chức năng?",
        "BM25 được sử dụng để tìm kiếm loại thông tin nào?",
    ]

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        requests.append(payload)
        slot = payload["format"]["properties"]["questions"]["items"][
            "properties"
        ]["planSlotId"]["enum"][0]
        question = _question(len(requests), slot)
        question["prompt"] = prompts[len(requests) - 1]
        return httpx.Response(200, json={
            "message": {"content": json.dumps({"questions": [question]})},
            "done_reason": "stop",
        })

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://ollama.test"
    )
    provider = OllamaQwenProvider(settings, client=client)
    command = QuizLLMCommand(**{
        **_command(2).__dict__,
        "ollama_parts": (
            QuizLLMPart("Context A", 1, ("SLOT-0",)),
            QuizLLMPart("Context B", 1, ("SLOT-1",)),
        ),
        "allowed_source_ids": frozenset({"S1"}),
    })

    result = await provider.generate_quiz(command)

    assert len(requests) == 3
    retry_message = requests[2]["messages"][1]["content"]
    assert "Already generated questions:" in retry_message
    assert (
        "DO NOT generate questions equivalent or semantically similar"
        in retry_message
    )
    assert len(GroundedQuizOutput.model_validate_json(result.answer).questions) == 2
    await client.aclose()


@pytest.mark.asyncio
async def test_ollama_splits_a_truncated_two_question_response(
    settings: Settings,
) -> None:
    requests: list[dict[str, Any]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        requests.append(payload)
        schema = payload["format"]["properties"]["questions"]
        count = schema["maxItems"]
        slots = schema["items"]["properties"]["planSlotId"]["enum"]
        if count == 2:
            return httpx.Response(200, json={
                "message": {"content": "{\"questions\":["},
                "done_reason": "length",
                "eval_count": 1600,
            })
        questions = [_question(int(slot.rsplit("-", 1)[1]), slot) for slot in slots]
        return httpx.Response(200, json={
            "message": {"content": json.dumps({"questions": questions})},
            "done_reason": "stop",
        })

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://ollama.test"
    )
    provider = OllamaQwenProvider(
        settings.model_copy(update={"ollama_max_questions_per_call": 2}),
        client=client,
    )
    command = _command(2)
    command = QuizLLMCommand(**{
        **command.__dict__,
        "ollama_parts": (
            QuizLLMPart("COUNT=2", 2, ("SLOT-0", "SLOT-1")),
        ),
        "allowed_source_ids": frozenset({"S1"}),
    })

    result = await provider.generate_quiz(command)

    assert len(GroundedQuizOutput.model_validate_json(result.answer).questions) == 2
    assert [request["format"]["properties"]["questions"]["maxItems"] for request in requests] == [
        2,
        1,
        1,
    ]
    await client.aclose()


@pytest.mark.asyncio
async def test_ollama_rejects_fabricated_citation(settings: Settings) -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        question = _question(0, "SLOT-0")
        for key in (
            "questionCitations",
            "answerCitations",
            "explanationCitations",
        ):
            question[key][0]["sourceId"] = "FABRICATED"
        return httpx.Response(
            200,
            json={"message": {"content": json.dumps({"questions": [question]})}},
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://ollama.test"
    )
    provider = OllamaQwenProvider(settings, client=client)
    command = _command()
    command = QuizLLMCommand(
        **{
            **command.__dict__,
            "ollama_parts": (QuizLLMPart("COUNT=1", 1, ("SLOT-0",)),),
            "allowed_source_ids": frozenset({"S1"}),
        }
    )

    with pytest.raises(LLMProviderError) as raised:
        await provider.generate_quiz(command)

    assert raised.value.category == LLMErrorCategory.INVALID_RESPONSE
    assert calls == settings.ollama_batch_max_retries + 1
    await client.aclose()


class OAuthResponse:
    def __init__(self, status_code: int, body: dict[str, Any]) -> None:
        self.status_code = status_code
        self._body = body
        self.text = json.dumps(body)

    def json(self) -> dict[str, Any]:
        return self._body


class OAuthSession:
    def __init__(self, response: OAuthResponse) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def post(self, url: str, **kwargs: Any) -> OAuthResponse:
        self.calls.append({"url": url, **kwargs})
        return self.response


@pytest.mark.asyncio
async def test_oauth_batches_twenty_questions_into_ten_and_ten(
    settings: Settings,
) -> None:
    class BatchSession:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        def post(self, url: str, **kwargs: Any) -> OAuthResponse:
            self.calls.append({"url": url, **kwargs})
            question_schema = kwargs["json"]["generationConfig"]["responseSchema"][
                "properties"
            ]["questions"]
            slots = question_schema["items"]["properties"]["planSlotId"]["enum"]
            return OAuthResponse(200, {
                "candidates": [{
                    "content": {
                        "parts": [{
                            "text": json.dumps({
                                    "questions": [
                                        _question(
                                            int(slot.rsplit("-", 1)[1]), slot
                                        )
                                        for slot in slots
                                ],
                            }),
                        }],
                    },
                }],
                "usageMetadata": {
                    "promptTokenCount": 2,
                    "candidatesTokenCount": 3,
                    "totalTokenCount": 5,
                },
            })

        def close(self) -> None:
            return None

    session = BatchSession()
    configured = settings.model_copy(update={
        "gemini_oauth_timeout_seconds": 120,
        "gemini_batch_size": 10,
    })
    provider = GeminiOAuthProvider(configured, session=session)
    parts = tuple(
        QuizLLMPart(
            message=f"Generate part {part_index}",
            question_count=10,
            plan_slot_ids=tuple(
                f"SLOT-{index}"
                for index in range(part_index * 10, (part_index + 1) * 10)
            ),
        )
        for part_index in range(2)
    )
    command = QuizLLMCommand(
        **{**_command(20).__dict__, "gemini_parts": parts}
    )

    result = await provider.generate_quiz(command)
    output = GroundedQuizOutput.model_validate_json(result.answer)

    assert len(session.calls) == 2
    assert [len(
        call["json"]["generationConfig"]["responseSchema"]["properties"][
            "questions"
        ]["items"]["properties"]["planSlotId"]["enum"]
    ) for call in session.calls] == [10, 10]
    assert [question.planSlotId for question in output.questions] == [
        f"SLOT-{index}" for index in range(20)
    ]
    assert result.usage.total_tokens == 10
    assert all(call["timeout"] == 120 for call in session.calls)


@pytest.mark.asyncio
async def test_oauth_retries_only_duplicate_slot_with_exclusion_prompt(
    settings: Settings,
) -> None:
    class DuplicateSession:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        def post(self, url: str, **kwargs: Any) -> OAuthResponse:
            self.calls.append({"url": url, **kwargs})
            slot = kwargs["json"]["generationConfig"]["responseSchema"][
                "properties"
            ]["questions"]["items"]["properties"]["planSlotId"]["enum"][0]
            prompt_index = 0 if len(self.calls) < 3 else 1
            return OAuthResponse(200, {
                "candidates": [{
                    "content": {"parts": [{"text": json.dumps({
                        "questions": [_question(prompt_index, slot)],
                    })}]},
                }],
                "usageMetadata": {},
            })

        def close(self) -> None:
            return None

    session = DuplicateSession()
    provider = GeminiOAuthProvider(
        settings.model_copy(update={"gemini_oauth_timeout_seconds": 120}),
        session=session,
    )
    command = QuizLLMCommand(**{
        **_command(2).__dict__,
        "gemini_parts": (
            QuizLLMPart("Context A", 1, ("SLOT-0",)),
            QuizLLMPart("Context B", 1, ("SLOT-1",)),
        ),
    })

    result = await provider.generate_quiz(command)

    assert len(session.calls) == 3
    retry_message = session.calls[2]["json"]["contents"][0]["parts"][0]["text"]
    assert "Already generated questions:" in retry_message
    assert (
        "DO NOT generate questions equivalent or semantically similar"
        in retry_message
    )
    assert [
        question.planSlotId
        for question in GroundedQuizOutput.model_validate_json(
            result.answer
        ).questions
    ] == ["SLOT-0", "SLOT-1"]


@pytest.mark.asyncio
async def test_api_key_provider_uses_the_same_ten_question_batches() -> None:
    class BatchGeminiService:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        async def generate(self, message: str, **kwargs: Any) -> GeminiResult:
            self.calls.append({"message": message, **kwargs})
            schema = kwargs["response_schema"]["properties"]["questions"]
            slots = schema["items"]["properties"]["planSlotId"]["enum"]
            return GeminiResult(
                answer=json.dumps({
                        "questions": [
                            _question(int(slot.rsplit("-", 1)[1]), slot)
                            for slot in slots
                    ],
                }),
                model="gemini-key-test",
                usage=TokenUsage(1, 2, 3),
            )

    service = BatchGeminiService()
    provider = GeminiApiKeyProvider(service, "gemini-key-test")
    parts = tuple(
        QuizLLMPart(
            message=f"Generate part {part_index}",
            question_count=10,
            plan_slot_ids=tuple(
                f"SLOT-{index}"
                for index in range(part_index * 10, (part_index + 1) * 10)
            ),
        )
        for part_index in range(2)
    )
    command = QuizLLMCommand(
        **{**_command(20).__dict__, "gemini_parts": parts}
    )

    result = await provider.generate_quiz(command)

    assert len(service.calls) == 2
    for call in service.calls:
        questions_schema = call["response_schema"]["properties"]["questions"]
        assert "minItems" not in questions_schema
        assert "maxItems" not in questions_schema
        assert questions_schema["items"]["properties"]["planSlotId"]["enum"]
    assert len(GroundedQuizOutput.model_validate_json(result.answer).questions) == 20
    assert result.usage.total_tokens == 6


@pytest.mark.asyncio
async def test_api_key_provider_retries_duplicate_slot_only() -> None:
    class DuplicateGeminiService:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        async def generate(self, message: str, **kwargs: Any) -> GeminiResult:
            self.calls.append({"message": message, **kwargs})
            schema = kwargs["response_schema"]["properties"]["questions"]
            slot = schema["items"]["properties"]["planSlotId"]["enum"][0]
            prompt_index = 0 if len(self.calls) < 3 else 1
            return GeminiResult(
                answer=json.dumps({
                    "questions": [_question(prompt_index, slot)],
                }),
                model="gemini-key-test",
                usage=TokenUsage(1, 1, 2),
            )

    service = DuplicateGeminiService()
    provider = GeminiApiKeyProvider(service, "gemini-key-test")
    command = QuizLLMCommand(**{
        **_command(2).__dict__,
        "gemini_parts": (
            QuizLLMPart("Context A", 1, ("SLOT-0",)),
            QuizLLMPart("Context B", 1, ("SLOT-1",)),
        ),
    })

    result = await provider.generate_quiz(command)

    assert len(service.calls) == 3
    assert "Already generated questions:" in service.calls[2]["message"]
    assert len(GroundedQuizOutput.model_validate_json(result.answer).questions) == 2


@pytest.mark.asyncio
async def test_api_key_provider_returns_usable_partial_result_after_repair_exhausted() -> None:
    class PartialGeminiService:
        def __init__(self) -> None:
            self.calls = 0

        async def generate(self, message: str, **kwargs: Any) -> GeminiResult:
            self.calls += 1
            slots = kwargs["response_schema"]["properties"]["questions"][
                "items"
            ]["properties"]["planSlotId"]["enum"]
            questions = [_question(0, slots[0])] if self.calls == 1 else []
            return GeminiResult(
                answer=json.dumps({"questions": questions}),
                model="gemini-key-test",
                usage=TokenUsage(1, 1, 2),
            )

    service = PartialGeminiService()
    provider = GeminiApiKeyProvider(service, "gemini-key-test")
    command = QuizLLMCommand(**{
        **_command(2).__dict__,
        "gemini_parts": (
            QuizLLMPart("Context", 2, ("SLOT-0", "SLOT-1")),
        ),
    })

    result = await provider.generate_quiz(command)

    output = GroundedQuizOutput.model_validate_json(result.answer)
    assert service.calls == 2
    assert [question.planSlotId for question in output.questions] == ["SLOT-0"]


@pytest.mark.asyncio
async def test_oauth_provider_uses_adc_rest_contract(settings: Settings) -> None:
    session = OAuthSession(OAuthResponse(200, {
        "candidates": [{
            "content": {
                "parts": [{"text": _result("gemini_oauth", 1).answer}],
            },
        }],
        "usageMetadata": {
            "promptTokenCount": 2,
            "candidatesTokenCount": 3,
            "totalTokenCount": 5,
        },
    }))
    configured = settings.model_copy(update={
        "gemini_oauth_quota_project": "quota-project",
        "gemini_oauth_model": "gemini-test",
    })
    provider = GeminiOAuthProvider(configured, session=session)

    result = await provider.generate_quiz(_command())

    assert result.provider == "gemini_oauth"
    assert result.usage.total_tokens == 5
    assert session.calls[0]["headers"]["x-goog-user-project"] == "quota-project"
    assert session.calls[0]["json"]["generationConfig"]["responseMimeType"] == "application/json"
    questions_schema = session.calls[0]["json"]["generationConfig"][
        "responseSchema"
    ]["properties"]["questions"]
    assert "minItems" not in questions_schema
    assert "maxItems" not in questions_schema
    assert session.calls[0]["url"].endswith("/v1/models/gemini-test:generateContent")


@pytest.mark.asyncio
async def test_oauth_401_is_fallback_eligible(settings: Settings) -> None:
    session = OAuthSession(OAuthResponse(401, {"error": {"message": "unauthorized"}}))
    provider = GeminiOAuthProvider(settings, session=session)

    with pytest.raises(LLMProviderError) as raised:
        await provider.generate_quiz(_command())

    assert raised.value.category == LLMErrorCategory.AUTHENTICATION
    assert raised.value.fallback_eligible is True


@pytest.mark.asyncio
async def test_oauth_400_is_provider_specific_and_fallback_eligible(
    settings: Settings,
) -> None:
    session = OAuthSession(OAuthResponse(400, {
        "error": {
            "status": "INVALID_ARGUMENT",
            "message": "response schema is not supported for this provider",
            "details": [{"reason": "UNSUPPORTED_SCHEMA"}],
        }
    }))
    provider = GeminiOAuthProvider(settings, session=session)

    with pytest.raises(LLMProviderError) as raised:
        await provider.generate_quiz(_command())

    assert raised.value.category == LLMErrorCategory.INVALID_REQUEST
    assert raised.value.code == "GEMINI_OAUTH_REQUEST_INCOMPATIBLE"
    assert raised.value.fallback_eligible is True
