from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_core import PydanticCustomError

from app.schemas.hybrid import ConversationMessage, GroundedQuizQuestionOutput


class UserDocumentDto(BaseModel):
    id: str
    classroomId: str | None
    filename: str
    mimeType: str
    size: int
    hash: str
    status: str
    pageCount: int | None
    chunkCount: int
    error: str | None
    createdAt: datetime
    updatedAt: datetime
    indexedAt: datetime | None
    mathExtractionStatus: str = "NOT_DETECTED"
    mathFormulaCount: int = 0
    mathWarningCount: int = 0


class PaginationDto(BaseModel):
    page: int
    size: int
    totalItems: int
    totalPages: int


class UserDocumentListResponse(BaseModel):
    items: list[UserDocumentDto]
    pagination: PaginationDto


class UserRagRequest(BaseModel):
    question: str = Field(min_length=2, max_length=5000)
    topK: int | None = Field(default=None, ge=1, le=50)
    documentIds: list[str] | None = Field(default=None, max_length=100)
    conversationHistory: list[ConversationMessage] = Field(default_factory=list, max_length=6)
    debug: bool = False

    @field_validator("question")
    @classmethod
    def normalize_question(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise ValueError("Câu hỏi phải có ít nhất 2 ký tự.")
        return value

    @model_validator(mode="after")
    def validate_history_size(self) -> "UserRagRequest":
        if sum(len(item.content) for item in self.conversationHistory) > 12000:
            raise ValueError("Tổng nội dung lịch sử hội thoại vượt quá 12.000 ký tự.")
        return self


class UserRagAskRequest(UserRagRequest):
    includeSystemDocuments: bool = False


class UserRagResult(BaseModel):
    chunkId: str
    documentId: str
    filename: str
    sourceType: str
    pageNumber: int | None
    slideNumber: int | None
    chunkIndex: int
    heading: str | None
    text: str
    score: float


class UserRagSearchResponse(BaseModel):
    question: str
    topK: int
    results: list[UserRagResult]
    debug: dict | None = None


class UserRagSource(BaseModel):
    sourceId: str
    documentId: str
    filename: str
    sourceType: str
    pageNumber: int | None
    slideNumber: int | None
    chunkIndex: int
    heading: str | None
    score: float
    textPreview: str


class UserRagAskResponse(BaseModel):
    answer: str
    model: str | None
    usage: dict[str, int]
    sources: list[UserRagSource]
    insufficientContext: bool = False
    debug: dict | None = None


class UserChunkDto(BaseModel):
    chunkId: str
    documentId: str
    filename: str
    pageNumber: int | None
    slideNumber: int | None
    chunkIndex: int
    heading: str | None
    text: str
    rawText: str | None = None
    mathEnhanced: bool = False


class UserChunkListResponse(BaseModel):
    items: list[UserChunkDto]
    pagination: PaginationDto


class QuizQuestionCounts(BaseModel):
    singleChoice: int = Field(ge=0, le=50)
    multipleSelect: int = Field(ge=0, le=50)
    fillBlank: int = Field(ge=0, le=50)

    @model_validator(mode="after")
    def validate_total(self) -> "QuizQuestionCounts":
        total = self.singleChoice + self.multipleSelect + self.fillBlank
        if total < 1:
            raise ValueError("Tổng số câu hỏi phải có ít nhất một câu.")
        if total > 20:
            raise PydanticCustomError(
                "quiz_batch_too_large",
                "Mỗi batch Gemini chỉ được tạo tối đa 20 câu hỏi.",
            )
        return self


class CognitiveConstraintPlan(BaseModel):
    cognitiveLevel: Literal["L1", "L2", "L3", "L4", "L5"]
    conceptMin: int = Field(ge=1, le=6)
    conceptMax: int = Field(ge=1, le=6)
    reasoningMin: int = Field(ge=0, le=5)
    reasoningMax: int = Field(ge=0, le=5)
    requiresNovelScenario: bool
    answerDirectlyPresent: bool
    requiresComparison: bool
    scoreMin: int = Field(ge=1)
    scoreMax: int | None = Field(default=None, ge=1)


class CognitiveQuestionPlan(BaseModel):
    planSlotId: str = Field(min_length=1, max_length=50)
    questionType: Literal["SINGLE_CHOICE", "MULTIPLE_SELECT", "FILL_BLANK"]
    cognitiveLevel: Literal["L1", "L2", "L3", "L4", "L5"]
    constraint: CognitiveConstraintPlan


_COGNITIVE_POLICIES: dict[str, dict[str, object]] = {
    "L1": {
        "conceptMin": 1, "conceptMax": 1, "reasoningMin": 0, "reasoningMax": 0,
        "requiresNovelScenario": False, "answerDirectlyPresent": True,
        "requiresComparison": False, "scoreMin": 1, "scoreMax": 2,
    },
    "L2": {
        "conceptMin": 1, "conceptMax": 2, "reasoningMin": 1, "reasoningMax": 1,
        "requiresNovelScenario": False, "answerDirectlyPresent": False,
        "requiresComparison": False, "scoreMin": 3, "scoreMax": 4,
    },
    "L3": {
        "conceptMin": 1, "conceptMax": 2, "reasoningMin": 1, "reasoningMax": 2,
        "requiresNovelScenario": True, "answerDirectlyPresent": False,
        "requiresComparison": False, "scoreMin": 5, "scoreMax": 7,
    },
    "L4": {
        "conceptMin": 2, "conceptMax": 4, "reasoningMin": 2, "reasoningMax": 3,
        "requiresNovelScenario": True, "answerDirectlyPresent": False,
        "requiresComparison": True, "scoreMin": 8, "scoreMax": 10,
    },
    "L5": {
        "conceptMin": 3, "conceptMax": 6, "reasoningMin": 3, "reasoningMax": 5,
        "requiresNovelScenario": True, "answerDirectlyPresent": False,
        "requiresComparison": True, "scoreMin": 11, "scoreMax": None,
    },
}

_LEGACY_DIFFICULTY_BY_LEVEL = {
    "L1": "EASY", "L2": "MEDIUM", "L3": "MEDIUM", "L4": "HARD", "L5": "HARD",
}


class GroundedQuizRequest(BaseModel):
    documentIds: list[str] = Field(min_length=1, max_length=10)
    title: str = Field(min_length=1, max_length=200)
    difficulty: str | None = Field(default=None, pattern="^(EASY|MEDIUM|HARD|MIXED)$")
    cognitiveMode: str | None = Field(default=None, pattern="^(L1|L2|L3|L4|L5|BALANCED)$")
    questionCounts: QuizQuestionCounts
    batchIndex: int = Field(default=0, ge=0)
    totalBatches: int = Field(default=1, ge=1, le=13)
    difficultyPlan: list[str] | None = None
    questionPlan: list[CognitiveQuestionPlan] | None = None
    excludedPrompts: list[str] = Field(default_factory=list, max_length=50)
    acceptedQuestions: list[GroundedQuizQuestionOutput] = Field(
        default_factory=list, max_length=20
    )

    @field_validator("acceptedQuestions", mode="before")
    @classmethod
    def normalize_empty_cognitive_checkpoint(cls, value: object) -> object:
        return [] if value is None else value

    @model_validator(mode="after")
    def validate_batch_contract(self) -> "GroundedQuizRequest":
        if self.batchIndex >= self.totalBatches:
            raise ValueError("batchIndex phải nhỏ hơn totalBatches.")
        total = (
            self.questionCounts.singleChoice
            + self.questionCounts.multipleSelect
            + self.questionCounts.fillBlank
        )
        if self.difficultyPlan is not None:
            if len(self.difficultyPlan) != total:
                raise PydanticCustomError(
                    "cognitive_plan_invalid",
                    "difficultyPlan phải khớp số câu trong batch.",
                )
            if any(value not in {"EASY", "MEDIUM", "HARD"} for value in self.difficultyPlan):
                raise PydanticCustomError(
                    "cognitive_plan_invalid",
                    "difficultyPlan chỉ nhận EASY, MEDIUM hoặc HARD.",
                )
        if self.cognitiveMode is None and self.difficulty is None:
            raise ValueError("cognitiveMode là bắt buộc.")
        if self.questionPlan is not None:
            if len(self.questionPlan) != total:
                raise PydanticCustomError(
                    "cognitive_plan_invalid",
                    "questionPlan phải khớp số câu trong batch.",
                )
            if len({item.planSlotId for item in self.questionPlan}) != total:
                raise PydanticCustomError(
                    "cognitive_plan_invalid",
                    "planSlotId trong questionPlan phải là duy nhất.",
                )
            expected_types = {
                "SINGLE_CHOICE": self.questionCounts.singleChoice,
                "MULTIPLE_SELECT": self.questionCounts.multipleSelect,
                "FILL_BLANK": self.questionCounts.fillBlank,
            }
            actual_types = {
                name: sum(item.questionType == name for item in self.questionPlan)
                for name in expected_types
            }
            if actual_types != expected_types:
                raise PydanticCustomError(
                    "cognitive_plan_invalid",
                    "Loại câu trong questionPlan không khớp questionCounts.",
                )
            for item in self.questionPlan:
                constraint = item.constraint.model_dump(exclude={"cognitiveLevel"})
                if (item.constraint.cognitiveLevel != item.cognitiveLevel
                        or constraint != _COGNITIVE_POLICIES[item.cognitiveLevel]):
                    raise PydanticCustomError(
                        "cognitive_plan_invalid",
                        "Constraint trong questionPlan không khớp Cognitive Level.",
                    )
            if self.cognitiveMode not in (None, "BALANCED") and any(
                item.cognitiveLevel != self.cognitiveMode for item in self.questionPlan
            ):
                raise PydanticCustomError(
                    "cognitive_plan_invalid",
                    "questionPlan không khớp cognitiveMode đã chọn.",
                )
            if self.difficultyPlan is not None:
                mapped = [
                    _LEGACY_DIFFICULTY_BY_LEVEL[item.cognitiveLevel]
                    for item in self.questionPlan
                ]
                if mapped != self.difficultyPlan:
                    raise PydanticCustomError(
                        "cognitive_plan_invalid",
                        "difficultyPlan không tương thích với questionPlan.",
                    )
            accepted_slots = [item.planSlotId for item in self.acceptedQuestions]
            planned_slots = {item.planSlotId for item in self.questionPlan}
            if len(set(accepted_slots)) != len(accepted_slots) or any(
                slot is None or slot not in planned_slots for slot in accepted_slots
            ):
                raise PydanticCustomError(
                    "cognitive_checkpoint_invalid",
                    "Câu hỏi checkpoint không khớp questionPlan.",
                )
        elif self.acceptedQuestions:
            raise PydanticCustomError(
                "cognitive_checkpoint_invalid",
                "Checkpoint Cognitive yêu cầu questionPlan.",
            )
        if sum(len(value) for value in self.excludedPrompts) > 25000:
            raise ValueError("excludedPrompts vượt quá giới hạn 25000 ký tự.")
        return self


class GroundedQuizCitation(BaseModel):
    chunkId: str
    documentId: str
    filename: str
    pageNumber: int | None
    slideNumber: int | None
    chunkIndex: int
    heading: str | None
    evidenceQuote: str
    chunkText: str
    rawText: str | None = None
    mathEnhanced: bool = False
    snapshotFingerprint: str


class GroundedQuizQuestion(BaseModel):
    type: str
    difficulty: str | None = None
    planSlotId: str | None = None
    cognitiveLevel: str | None = None
    complexityProfile: dict[str, object] | None = None
    prompt: str
    explanation: str
    options: list[dict[str, object]]
    acceptedAnswers: list[str]
    questionCitations: list[GroundedQuizCitation]
    answerCitations: list[GroundedQuizCitation]
    explanationCitations: list[GroundedQuizCitation]
    validationStatus: Literal["VERIFIED", "WARNING"] = "VERIFIED"
    validationWarnings: list[dict[str, object]] = Field(default_factory=list)
    complexityVerified: bool = True


class GroundedQuizResponse(BaseModel):
    questions: list[GroundedQuizQuestion]
    model: str
    usage: dict[str, int]
    validationStatus: Literal["VERIFIED", "WARNING"] = "VERIFIED"
    validationWarnings: list[dict[str, object]] = Field(default_factory=list)
    requestedCount: int = 0
    savedCount: int = 0
    warningCount: int = 0
