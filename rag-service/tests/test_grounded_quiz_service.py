import pytest
from pydantic import ValidationError

from app.schemas.user_document import GroundedQuizRequest
from app.services.grounded_quiz_service import GroundedQuizService


def test_grounded_quiz_request_rejects_more_than_four_questions() -> None:
    with pytest.raises(ValidationError):
        GroundedQuizRequest.model_validate({
            "documentIds": ["00000000-0000-0000-0000-000000000001"],
            "title": "Batch too large",
            "difficulty": "MIXED",
            "questionCounts": {
                "singleChoice": 5,
                "multipleSelect": 0,
                "fillBlank": 0,
            },
        })


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


def test_citation_quote_is_canonicalized_back_to_an_exact_source_span() -> None:
    source = 'Embedding là “vector số” biểu diễn ý nghĩa.\nHai văn bản gần nhau.'

    quote = GroundedQuizService._canonical_quote(
        source, 'embedding là "vector số"  biểu diễn ý nghĩa'
    )

    assert quote == 'Embedding là “vector số” biểu diễn ý nghĩa'
