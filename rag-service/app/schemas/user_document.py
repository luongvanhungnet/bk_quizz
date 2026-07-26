from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_core import PydanticCustomError

from app.schemas.hybrid import ConversationMessage


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
        if total > 4:
            raise PydanticCustomError(
                "quiz_batch_too_large",
                "Mỗi batch Gemini chỉ được tạo tối đa 4 câu hỏi.",
            )
        return self


class GroundedQuizRequest(BaseModel):
    documentIds: list[str] = Field(min_length=1, max_length=10)
    title: str = Field(min_length=1, max_length=200)
    difficulty: str = Field(pattern="^(EASY|MEDIUM|HARD|MIXED)$")
    questionCounts: QuizQuestionCounts
    batchIndex: int = Field(default=0, ge=0)
    totalBatches: int = Field(default=1, ge=1, le=13)
    difficultyPlan: list[str] | None = None
    excludedPrompts: list[str] = Field(default_factory=list, max_length=50)

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
                raise ValueError("difficultyPlan phải khớp số câu trong batch.")
            if any(value not in {"EASY", "MEDIUM", "HARD"} for value in self.difficultyPlan):
                raise ValueError("difficultyPlan chỉ nhận EASY, MEDIUM hoặc HARD.")
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


class GroundedQuizQuestion(BaseModel):
    type: str
    difficulty: str
    prompt: str
    explanation: str
    options: list[dict[str, object]]
    acceptedAnswers: list[str]
    questionCitations: list[GroundedQuizCitation]
    answerCitations: list[GroundedQuizCitation]
    explanationCitations: list[GroundedQuizCitation]


class GroundedQuizResponse(BaseModel):
    questions: list[GroundedQuizQuestion]
    model: str
    usage: dict[str, int]
