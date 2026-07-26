from pydantic import Field, field_validator, model_validator

from app.schemas.document import ApiModel
from app.schemas.hybrid import ConversationMessage


class RagQuestionRequest(ApiModel):
    question: str = Field(min_length=2, max_length=5000)
    top_k: int | None = Field(default=None, ge=1, le=50)
    conversation_history: list[ConversationMessage] = Field(default_factory=list, max_length=6)
    debug: bool = False

    @field_validator("question", mode="before")
    @classmethod
    def trim_question(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_history_size(self) -> "RagQuestionRequest":
        if sum(len(item.content) for item in self.conversation_history) > 12000:
            raise ValueError("Tổng nội dung lịch sử hội thoại vượt quá 12.000 ký tự.")
        return self


class SearchResultResponse(ApiModel):
    chunk_id: str
    document_id: str
    document_type: str
    filename: str
    file_hash: str
    page_number: int | None
    chunk_index: int
    heading: str | None
    text: str
    created_at: str
    score: float


class SearchResponse(ApiModel):
    question: str
    scope: str = "SYSTEM"
    top_k: int
    results: list[SearchResultResponse]
    debug: dict | None = None


class RagSourceResponse(ApiModel):
    source_id: str
    document_id: str
    filename: str
    page_number: int | None
    score: float
    chunk_id: str
    text_preview: str


class AskResponse(ApiModel):
    question: str
    answer: str
    scope: str
    sources: list[RagSourceResponse]
    insufficient_context: bool = False
    debug: dict | None = None
