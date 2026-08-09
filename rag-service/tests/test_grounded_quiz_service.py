from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.schemas.hybrid import GroundedQuizOutput
from app.schemas.user_document import GroundedQuizRequest
from app.services.citation_matcher import CitationMatcher
from app.services.gemini_service import TokenUsage
from app.services.grounded_quiz_service import (
    CognitiveBatchValidationError,
    GroundedQuizService,
)
from app.services.quiz_llm_provider import (
    LLMErrorCategory,
    LLMProviderError,
    QuizLLMResult,
)


def test_grounded_quiz_request_accepts_twenty_and_rejects_twenty_one_questions() -> None:
    accepted = GroundedQuizRequest.model_validate({
        "documentIds": ["00000000-0000-0000-0000-000000000001"],
        "title": "Twenty questions",
        "cognitiveMode": "L3",
        "questionCounts": {"singleChoice": 20, "multipleSelect": 0, "fillBlank": 0},
    })
    assert accepted.questionCounts.singleChoice == 20

    with pytest.raises(ValidationError):
        GroundedQuizRequest.model_validate({
            "documentIds": ["00000000-0000-0000-0000-000000000001"],
            "title": "Batch too large",
            "cognitiveMode": "L3",
            "questionCounts": {
                "singleChoice": 21,
                "multipleSelect": 0,
                "fillBlank": 0,
            },
        })


def test_cognitive_contract_normalizes_a_null_checkpoint_to_an_empty_list() -> None:
    payload = {
        "documentIds": ["330acff6-dbcb-4260-9051-4ff15398a3b6"],
        "title": "L2 contract regression",
        "difficulty": "MEDIUM",
        "cognitiveMode": "L2",
        "questionCounts": {
            "singleChoice": 10,
            "multipleSelect": 0,
            "fillBlank": 0,
        },
        "batchIndex": 0,
        "totalBatches": 1,
        "questionPlan": [
            {
                "planSlotId": f"B1Q{index}",
                "questionType": "SINGLE_CHOICE",
                "cognitiveLevel": "L2",
                "constraint": {
                    "cognitiveLevel": "L2",
                    "conceptMin": 1,
                    "conceptMax": 2,
                    "reasoningMin": 1,
                    "reasoningMax": 1,
                    "requiresNovelScenario": False,
                    "answerDirectlyPresent": False,
                    "requiresComparison": False,
                    "scoreMin": 3,
                    "scoreMax": 4,
                },
            }
            for index in range(1, 11)
        ],
        "excludedPrompts": [],
        "acceptedQuestions": None,
    }

    request = GroundedQuizRequest.model_validate(payload)

    assert request.acceptedQuestions == []
    assert request.difficultyPlan is None
    assert len(request.questionPlan or []) == 10


def test_provider_request_error_is_not_reported_as_grounding_failure() -> None:
    mapped = GroundedQuizService._provider_service_error(
        LLMProviderError(
            LLMErrorCategory.INVALID_REQUEST,
            "Gemini API không tương thích với request.",
            fallback_eligible=False,
            code="LLM_PROVIDER_REQUEST_INCOMPATIBLE",
        )
    )

    assert mapped.code == "LLM_PROVIDER_REQUEST_INCOMPATIBLE"
    assert mapped.retryable is False


def test_invalid_provider_output_remains_grounded_quiz_invalid() -> None:
    mapped = GroundedQuizService._provider_service_error(
        LLMProviderError(
            LLMErrorCategory.INVALID_RESPONSE,
            "Output không hợp lệ.",
            fallback_eligible=True,
        )
    )

    assert mapped.code == "GROUNDED_QUIZ_INVALID"
    assert mapped.retryable is True


def test_mixed_difficulty_is_distributed_to_concrete_question_levels() -> None:
    distribute = GroundedQuizService._concrete_difficulties

    assert distribute("MIXED", 1) == ["MEDIUM"]
    assert distribute("MIXED", 2) == ["EASY", "HARD"]
    assert distribute("MIXED", 3) == ["EASY", "MEDIUM", "HARD"]
    assert distribute("MIXED", 4) == ["EASY", "MEDIUM", "HARD", "EASY"]
    assert distribute("HARD", 4) == ["HARD"] * 4


def test_explicit_batch_difficulty_plan_overrides_local_mixed_cycle() -> None:
    assert GroundedQuizService._difficulty_plan(
        "MIXED", 2, ["MEDIUM", "HARD"]
    ) == ["MEDIUM", "HARD"]


def test_provider_parts_split_twenty_slots_and_rotate_context_sources() -> None:
    request = GroundedQuizRequest.model_validate({
        "documentIds": ["00000000-0000-0000-0000-000000000001"],
        "title": "Twenty questions",
        "difficulty": "MEDIUM",
        "difficultyPlan": ["MEDIUM"] * 20,
        "questionCounts": {
            "singleChoice": 20,
            "multipleSelect": 0,
            "fillBlank": 0,
        },
    })
    sources = [
        SimpleNamespace(
            source_id=f"S{index + 1}",
            text=f"Complete source body {index + 1}",
            candidate=SimpleNamespace(chunk=SimpleNamespace(
                source_type="USER",
                document_type="USER",
                filename=f"source-{index + 1}.txt",
                page_number=index + 1,
                slide_number=None,
                heading=f"Heading {index + 1}",
            )),
        )
        for index in range(4)
    ]

    parts = GroundedQuizService._provider_parts(request, sources, 10)
    local_parts = GroundedQuizService._provider_parts(request, sources, 2)

    assert [part.question_count for part in parts] == [10, 10]
    assert [part.question_count for part in local_parts] == [2] * 10
    assert "focusSourceIds=[\"S1\", \"S3\"]" in parts[0].message
    assert "focusSourceIds=[\"S2\", \"S4\"]" in parts[1].message
    assert "Complete source body 1" in parts[0].message
    assert "Complete source body 2" in parts[1].message


def test_cognitive_profile_score_and_constraints_are_verified() -> None:
    question = SimpleNamespace(
        type="SINGLE_CHOICE",
        planSlotId="B1Q1",
        cognitiveLevel="L3",
        complexityProfile={
            "conceptCount": 2,
            "reasoningStepCount": 1,
            "requiresNovelScenario": True,
            "answerDirectlyPresent": False,
            "requiresComparison": False,
            "conceptsUsed": ["Cohesion", "Module"],
            "novelScenarioSummary": "Một module kiểm tra mật khẩu mới",
        },
        acceptedAnswers=[],
        options=[],
    )
    plan = [{
        "planSlotId": "B1Q1",
        "questionType": "SINGLE_CHOICE",
        "cognitiveLevel": "L3",
        "constraint": {
            "conceptMin": 1, "conceptMax": 2,
            "reasoningMin": 1, "reasoningMax": 2,
            "requiresNovelScenario": True,
            "answerDirectlyPresent": False,
            "requiresComparison": False,
            "scoreMin": 5, "scoreMax": 7,
        },
    }]

    result = GroundedQuizService()._validate_cognitive(
        question, 0, plan, {}, []
    )

    assert result["complexityProfile"]["complexityScore"] == 5


def test_cognitive_validator_reports_every_reason_without_stopping_at_first_mismatch() -> None:
    question = SimpleNamespace(
        type="SINGLE_CHOICE",
        planSlotId="B1Q2",
        cognitiveLevel="L2",
        complexityProfile={
            "conceptCount": 1,
            "reasoningStepCount": 0,
            "requiresNovelScenario": False,
            "answerDirectlyPresent": True,
            "requiresComparison": False,
            "conceptsUsed": ["Cohesion"],
            "novelScenarioSummary": None,
        },
        acceptedAnswers=[],
        options=[],
    )
    plan = {
        "planSlotId": "B1Q2",
        "questionType": "SINGLE_CHOICE",
        "cognitiveLevel": "L3",
        "constraint": {
            "conceptMin": 1, "conceptMax": 2,
            "reasoningMin": 1, "reasoningMax": 2,
            "requiresNovelScenario": True,
            "answerDirectlyPresent": False,
            "requiresComparison": False,
            "scoreMin": 5, "scoreMax": 7,
        },
    }

    result, violations = GroundedQuizService()._evaluate_cognitive(
        question, plan, {}, []
    )

    assert result is not None
    assert {item["reason"] for item in violations} == {
        "LEVEL_MISMATCH",
        "REASONING_STEPS_OUT_OF_RANGE",
        "NOVEL_SCENARIO_REQUIRED",
        "DIRECT_ANSWER_NOT_ALLOWED",
        "SCORE_OUT_OF_RANGE",
    }
    assert all(item["planSlotId"] == "B1Q2" for item in violations)
    assert all(item["requestedCognitiveLevel"] == "L3" for item in violations)


def test_cognitive_questions_are_ordered_by_plan_slot_instead_of_model_array_order() -> None:
    output = GroundedQuizOutput.model_validate({
        "questions": [
            _minimal_output_question("B1Q2", "L3"),
            _minimal_output_question("B1Q1", "L3"),
        ]
    })
    plan = [
        {"planSlotId": "B1Q1"},
        {"planSlotId": "B1Q2"},
    ]

    ordered = GroundedQuizService._order_questions_by_plan(output, plan)

    assert [question.planSlotId for question in ordered] == ["B1Q1", "B1Q2"]


def test_build_questions_collects_all_cognitive_rejections_and_keeps_valid_slots() -> None:
    valid = _minimal_output_question("B1Q1", "L3")
    invalid = _minimal_output_question("B1Q2", "L2")
    invalid["complexityProfile"] = {
        "conceptCount": 1,
        "reasoningStepCount": 0,
        "requiresNovelScenario": False,
        "answerDirectlyPresent": True,
        "requiresComparison": False,
        "conceptsUsed": ["A"],
        "novelScenarioSummary": None,
    }
    output = GroundedQuizOutput.model_validate({"questions": [valid, invalid]})
    constraint = {
        "conceptMin": 1, "conceptMax": 2,
        "reasoningMin": 1, "reasoningMax": 2,
        "requiresNovelScenario": True,
        "answerDirectlyPresent": False,
        "requiresComparison": False,
        "scoreMin": 5, "scoreMax": 7,
    }
    plan = [
        {"planSlotId": "B1Q1", "questionType": "SINGLE_CHOICE", "cognitiveLevel": "L3", "constraint": constraint},
        {"planSlotId": "B1Q2", "questionType": "SINGLE_CHOICE", "cognitiveLevel": "L3", "constraint": constraint},
    ]
    source = SimpleNamespace(
        source_id="S1",
        text="Nguồn hợp lệ",
        candidate=SimpleNamespace(chunk=SimpleNamespace(
            chunk_id="chunk-1", document_id="document-1", filename="source.txt",
            page_number=None, slide_number=None, chunk_index=0, heading=None,
        )),
    )

    with pytest.raises(CognitiveBatchValidationError) as captured:
        GroundedQuizService()._build_questions(
            output,
            {"SINGLE_CHOICE": 2, "MULTIPLE_SELECT": 0, "FILL_BLANK": 0},
            {"S1": source},
            ["MEDIUM", "MEDIUM"],
            plan,
        )

    assert [item["planSlotId"] for item in captured.value.accepted] == ["B1Q1"]
    assert captured.value.rejected_slot_ids == ("B1Q2",)
    assert {item["reason"] for item in captured.value.failures} >= {
        "LEVEL_MISMATCH",
        "REASONING_STEPS_OUT_OF_RANGE",
        "NOVEL_SCENARIO_REQUIRED",
    }


def _minimal_output_question(slot_id: str, level: str) -> dict[str, object]:
    citation = {"sourceId": "S1", "evidenceQuote": "Nguồn hợp lệ"}
    return {
        "type": "SINGLE_CHOICE",
        "planSlotId": slot_id,
        "cognitiveLevel": level,
        "complexityProfile": {
            "conceptCount": 2,
            "reasoningStepCount": 1,
            "requiresNovelScenario": True,
            "answerDirectlyPresent": False,
            "requiresComparison": False,
            "conceptsUsed": ["A", "B"],
            "novelScenarioSummary": "Tình huống mới",
        },
        "prompt": f"Câu hỏi {slot_id}",
        "explanation": "Giải thích",
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


def _question_plan(slot_id: str, level: str) -> dict[str, object]:
    return {
        "planSlotId": slot_id,
        "questionType": "SINGLE_CHOICE",
        "cognitiveLevel": level,
        "constraint": {
            "conceptMin": 1,
            "conceptMax": 2,
            "reasoningMin": 1,
            "reasoningMax": 2,
            "requiresNovelScenario": True,
            "answerDirectlyPresent": False,
            "requiresComparison": False,
            "scoreMin": 5,
            "scoreMax": 7,
        },
    }


def test_cognitive_quality_failure_returns_usable_question_with_warning() -> None:
    output = GroundedQuizOutput.model_validate({
        "questions": [_minimal_output_question("B1Q1", "L2")]
    })
    source = _source_fixture()
    plan = [{
        "planSlotId": "B1Q1",
        "questionType": "SINGLE_CHOICE",
        "cognitiveLevel": "L3",
        "constraint": {
            "conceptMin": 1, "conceptMax": 2,
            "reasoningMin": 1, "reasoningMax": 2,
            "requiresNovelScenario": True,
            "answerDirectlyPresent": False,
            "requiresComparison": False,
            "scoreMin": 5, "scoreMax": 7,
        },
    }]

    questions = GroundedQuizService()._build_questions(
        output,
        {"SINGLE_CHOICE": 1, "MULTIPLE_SELECT": 0, "FILL_BLANK": 0},
        {"S1": source},
        ["MEDIUM"],
        plan,
        allow_quality_warnings=True,
    )

    assert questions[0]["validationStatus"] == "WARNING"
    assert questions[0]["complexityVerified"] is False
    assert {item["code"] for item in questions[0]["validationWarnings"]} >= {
        "LEVEL_MISMATCH",
    }


def test_citation_response_contains_trusted_chunk_snapshot() -> None:
    source = _source_fixture()
    citation = SimpleNamespace(sourceId="S1", evidenceQuote="Nguồn hợp lệ")

    result = GroundedQuizService()._citations(
        [citation], {"S1": source}, 0, "QUESTION"
    )

    assert result[0]["chunkText"] == "Nguồn hợp lệ"
    assert result[0]["snapshotFingerprint"]
    assert "rawText" in result[0]


@pytest.mark.asyncio
async def test_generate_keeps_cognitive_mismatch_as_warning() -> None:
    valid = _minimal_output_question("B1Q1", "L3")
    invalid = _minimal_output_question("B1Q2", "L2")
    invalid["complexityProfile"] = {
        "conceptCount": 1,
        "reasoningStepCount": 0,
        "requiresNovelScenario": False,
        "answerDirectlyPresent": True,
        "requiresComparison": False,
        "conceptsUsed": ["A"],
        "novelScenarioSummary": None,
    }
    replacement = _minimal_output_question("B1Q2", "L3")
    router = _SequencedQuizRouter([
        [valid, invalid],
        [replacement],
    ])
    events: list[dict[str, object]] = []
    async def collect_event(event: dict[str, object]) -> None:
        events.append(event)
    request = _two_question_cognitive_request()
    source = _source_fixture()
    context = SimpleNamespace(sources=[source], text="[S1]\nNguồn hợp lệ")

    result = await GroundedQuizService().generate(
        request=request,
        context=context,
        gemini_service=None,
        trace_id="repair-trace",
        quiz_llm_router=router,
        event_sink=collect_event,
    )

    assert [question["planSlotId"] for question in result["questions"]] == [
        "B1Q1", "B1Q2",
    ]
    assert len(router.commands) == 1
    assert result["questions"][1]["validationStatus"] == "WARNING"
    assert result["questions"][1]["complexityVerified"] is False
    assert any(event["type"] == "COGNITIVE_VALIDATION_SUMMARY" for event in events)
    assert not any(event["type"] == "COGNITIVE_REPAIR_STARTED" for event in events)


@pytest.mark.asyncio
async def test_generate_emits_structured_output_checkpoint_before_quality_validation() -> None:
    router = _SequencedQuizRouter([[_minimal_output_question("B1Q1", "L3")]])
    original_request = _two_question_cognitive_request()
    request = original_request.model_copy(update={
        "questionCounts": original_request.questionCounts.model_copy(update={
            "singleChoice": 1,
        }),
        "questionPlan": original_request.questionPlan[:1],
    })
    events: list[dict[str, object]] = []

    async def collect_event(event: dict[str, object]) -> None:
        events.append(event)

    await GroundedQuizService().generate(
        request=request,
        context=SimpleNamespace(
            sources=[_source_fixture()], text="[S1]\nNguá»“n há»£p lá»‡"
        ),
        gemini_service=None,
        trace_id="checkpoint-trace",
        quiz_llm_router=router,
        event_sink=collect_event,
    )

    checkpoint_index = next(
        index for index, event in enumerate(events)
        if event["type"] == "STRUCTURED_OUTPUT_CHECKPOINT"
    )
    validation_index = next(
        index for index, event in enumerate(events)
        if event["type"] == "COGNITIVE_VALIDATION_STARTED"
    )
    checkpoint = events[checkpoint_index]
    assert checkpoint_index < validation_index
    assert len(checkpoint["acceptedQuestions"]) == 1
    assert checkpoint["model"] == "test-model"
    assert checkpoint["usage"] == {
        "inputTokens": 10,
        "outputTokens": 20,
        "totalTokens": 30,
    }


@pytest.mark.asyncio
async def test_generate_resumes_from_cognitive_checkpoint_without_regenerating_accepted_slot() -> None:
    accepted = GroundedQuizOutput.model_validate({
        "questions": [_minimal_output_question("B1Q1", "L3")]
    }).questions
    replacement = _minimal_output_question("B1Q2", "L3")
    router = _SequencedQuizRouter([[replacement]])
    request = _two_question_cognitive_request().model_copy(update={
        "acceptedQuestions": accepted,
    })
    source = _source_fixture()

    result = await GroundedQuizService().generate(
        request=request,
        context=SimpleNamespace(sources=[source], text="[S1]\nNguồn hợp lệ"),
        gemini_service=None,
        trace_id="resume-trace",
        quiz_llm_router=router,
    )

    assert len(router.commands) == 1
    assert router.commands[0].question_count == 1
    assert router.commands[0].gemini_parts[0].plan_slot_ids == ("B1Q2",)
    assert [question["planSlotId"] for question in result["questions"]] == [
        "B1Q1", "B1Q2",
    ]


class _SequencedQuizRouter:
    def __init__(self, responses: list[list[dict[str, object]]]) -> None:
        self.responses = responses
        self.commands = []

    async def generate_quiz(self, command):
        self.commands.append(command)
        questions = self.responses[len(self.commands) - 1]
        return QuizLLMResult(
            answer=GroundedQuizOutput.model_validate({"questions": questions}).model_dump_json(),
            model="test-model",
            usage=TokenUsage(10, 20, 30),
            provider="gemini_api_key",
            generated_by_provider={"gemini_api_key": len(questions)},
            providers_used=("gemini_api_key",),
        )


def _two_question_cognitive_request() -> GroundedQuizRequest:
    constraint = {
        "cognitiveLevel": "L3",
        "conceptMin": 1, "conceptMax": 2,
        "reasoningMin": 1, "reasoningMax": 2,
        "requiresNovelScenario": True,
        "answerDirectlyPresent": False,
        "requiresComparison": False,
        "scoreMin": 5, "scoreMax": 7,
    }
    return GroundedQuizRequest.model_validate({
        "documentIds": ["00000000-0000-0000-0000-000000000001"],
        "title": "Cognitive repair",
        "cognitiveMode": "L3",
        "questionCounts": {"singleChoice": 2, "multipleSelect": 0, "fillBlank": 0},
        "questionPlan": [
            {"planSlotId": "B1Q1", "questionType": "SINGLE_CHOICE", "cognitiveLevel": "L3", "constraint": constraint},
            {"planSlotId": "B1Q2", "questionType": "SINGLE_CHOICE", "cognitiveLevel": "L3", "constraint": constraint},
        ],
    })


def _source_fixture():
    return SimpleNamespace(
        source_id="S1",
        text="Nguồn hợp lệ",
        candidate=SimpleNamespace(chunk=SimpleNamespace(
            chunk_id="00000000-0000-0000-0000-000000000010",
            document_id="00000000-0000-0000-0000-000000000001",
            filename="source.txt", page_number=None, slide_number=None,
            chunk_index=0, heading=None,
        )),
    )


def test_citation_quote_is_canonicalized_back_to_an_exact_source_span() -> None:
    source = 'Embedding là “vector số” biểu diễn ý nghĩa.\nHai văn bản gần nhau.'

    quote = GroundedQuizService._canonical_quote(
        source, 'embedding là "vector số"  biểu diễn ý nghĩa'
    )

    assert quote == 'Embedding là “vector số” biểu diễn ý nghĩa'


def test_invalid_extra_citation_is_dropped_when_role_keeps_a_valid_source() -> None:
    source = _source_fixture()
    output = GroundedQuizOutput.model_validate({
        "questions": [{
            "type": "SINGLE_CHOICE",
            "difficulty": "EASY",
            "prompt": "Nguồn nào hợp lệ?",
            "explanation": "Nguồn hợp lệ giải thích đáp án.",
            "options": [
                {"text": "A", "correct": True},
                {"text": "B", "correct": False},
                {"text": "C", "correct": False},
                {"text": "D", "correct": False},
            ],
            "acceptedAnswers": [],
            "questionCitations": [
                {"sourceId": "S1", "evidenceQuote": "Nguồn hợp lệ"},
                {"sourceId": "S1", "evidenceQuote": "đoạn không tồn tại"},
            ],
            "answerCitations": [
                {"sourceId": "S1", "evidenceQuote": "Nguồn hợp lệ"},
            ],
            "explanationCitations": [
                {"sourceId": "S1", "evidenceQuote": "Nguồn hợp lệ"},
            ],
        }],
    })

    canonical, summary, invalid = GroundedQuizService()._canonicalize_citations(
        output, {"S1": source}, None
    )

    assert invalid == []
    assert len(canonical.questions[0].questionCitations) == 1
    assert summary["dropped"] == 1


def test_invalid_only_citation_is_removed_and_reported_as_quality_warning() -> None:
    source = _source_fixture()
    question = _minimal_output_question("B1Q1", "L3")
    question["questionCitations"] = [
        {"sourceId": "S1", "evidenceQuote": "Nội dung không tồn tại"}
    ]
    output = GroundedQuizOutput.model_validate({"questions": [question]})

    canonical, _, invalid = GroundedQuizService()._canonicalize_citations(
        output, {"S1": source}, None
    )

    assert canonical.questions[0].questionCitations == []
    assert invalid[0]["citationRole"] == "QUESTION"


def test_missing_citation_role_is_reported_as_quality_warning() -> None:
    source = _source_fixture()
    question = _minimal_output_question("B1Q1", "L3")
    question["answerCitations"] = []
    output = GroundedQuizOutput.model_validate({"questions": [question]})

    canonical, _, invalid = GroundedQuizService()._canonicalize_citations(
        output, {"S1": source}, None
    )

    assert canonical.questions[0].answerCitations == []
    assert any(
        item["reason"] == "MISSING_CITATION"
        and item["citationRole"] == "ANSWER"
        for item in invalid
    )


def test_semantic_citation_failure_is_exposed_as_quality_warning() -> None:
    class BrokenEmbedding:
        def encode_documents(self, texts: list[str]):
            raise RuntimeError("inference failed")

    source = _source_fixture()
    source.text = "Nguồn hợp lệ mô tả đầy đủ một khái niệm trong tài liệu học tập."
    question = _minimal_output_question("B1Q1", "L3")
    question["questionCitations"] = [{
        "sourceId": "S1",
        "evidenceQuote": "Một cách diễn đạt gần nghĩa nhưng không trùng từ vựng",
    }]
    matcher = CitationMatcher(
        mode="semantic",
        embedding_service=BrokenEmbedding(),
        lexical_min_score=0.99,
    )

    _, summary, invalid = GroundedQuizService()._canonicalize_citations(
        GroundedQuizOutput.model_validate({"questions": [question]}),
        {"S1": source},
        matcher,
    )

    assert summary["degradedErrorCode"] == "CITATION_SEMANTIC_UNAVAILABLE"
    assert any(
        item["reason"] == "CITATION_VALIDATION_DEGRADED"
        and item["questionIndex"] == 0
        for item in invalid
    )


def test_partial_usable_output_is_kept_with_count_warning() -> None:
    source = _source_fixture()
    output = GroundedQuizOutput.model_validate({
        "questions": [_minimal_output_question("B1Q1", "L3")]
    })
    plans = [
        _question_plan("B1Q1", "L3"),
        _question_plan("B1Q2", "L3"),
    ]

    questions = GroundedQuizService()._build_questions(
        output,
        {"SINGLE_CHOICE": 2, "MULTIPLE_SELECT": 0, "FILL_BLANK": 0},
        {"S1": source},
        ["MEDIUM", "MEDIUM"],
        plans,
        allow_quality_warnings=True,
    )

    assert len(questions) == 1
    assert questions[0]["validationStatus"] == "WARNING"
    assert any(
        warning["code"] == "QUESTION_COUNT_INCOMPLETE"
        for warning in questions[0]["validationWarnings"]
    )


def test_math_normalization_failure_keeps_original_text_with_warning(monkeypatch) -> None:
    def broken_normalizer(value: str):
        raise RuntimeError("normalizer failed")

    monkeypatch.setattr(
        "app.services.grounded_quiz_service.normalize_math_field",
        broken_normalizer,
    )
    source = _source_fixture()
    output = GroundedQuizOutput.model_validate({
        "questions": [_minimal_output_question("B1Q1", "L3")]
    })

    questions = GroundedQuizService()._build_questions(
        output,
        {"SINGLE_CHOICE": 1, "MULTIPLE_SELECT": 0, "FILL_BLANK": 0},
        {"S1": source},
        ["MEDIUM"],
        [_question_plan("B1Q1", "L3")],
        allow_quality_warnings=True,
    )

    assert questions[0]["prompt"] == output.questions[0].prompt
    assert any(
        warning["code"] == "MATH_FORMAT_UNVERIFIED"
        for warning in questions[0]["validationWarnings"]
    )


def test_cognitive_validation_failure_keeps_usable_question_with_warning(monkeypatch) -> None:
    def broken_validator(*args, **kwargs):
        raise RuntimeError("validator failed")

    monkeypatch.setattr(GroundedQuizService, "_evaluate_cognitive", broken_validator)
    source = _source_fixture()
    output = GroundedQuizOutput.model_validate({
        "questions": [_minimal_output_question("B1Q1", "L3")]
    })

    questions = GroundedQuizService()._build_questions(
        output,
        {"SINGLE_CHOICE": 1, "MULTIPLE_SELECT": 0, "FILL_BLANK": 0},
        {"S1": source},
        ["MEDIUM"],
        [_question_plan("B1Q1", "L3")],
        allow_quality_warnings=True,
    )

    assert questions[0]["complexityVerified"] is False
    assert any(
        warning["code"] == "COGNITIVE_VALIDATION_UNAVAILABLE"
        for warning in questions[0]["validationWarnings"]
    )
