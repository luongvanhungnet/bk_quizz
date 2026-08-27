from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ChatRequest(BaseModel):
    message: str = Field(min_length=2, max_length=5000)

    @field_validator("message", mode="before")
    @classmethod
    def trim_message(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class TokenUsageResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    input_tokens: int = Field(alias="inputTokens", ge=0)
    output_tokens: int = Field(alias="outputTokens", ge=0)
    total_tokens: int = Field(alias="totalTokens", ge=0)


class ChatResponse(BaseModel):
    answer: str
    model: str
    usage: TokenUsageResponse


class HealthResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    status: str
    service: str
    environment: str
    gemini_configured: bool = Field(alias="geminiConfigured")


class GeminiHealthResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    status: str
    model: str
    latency_ms: int = Field(alias="latencyMs", ge=0)
    credential_source: str = Field(alias="credentialSource")
    message: str


class GeminiProbeOutput(BaseModel):
    status: Literal["OK"]


class TutorConversationMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=5000)


class TutorSource(BaseModel):
    sourceId: str = Field(min_length=1, max_length=80)
    sourceChunkId: str | None = Field(default=None, max_length=80)
    sourceDocumentId: str | None = Field(default=None, max_length=80)
    filename: str = Field(min_length=1, max_length=255)
    pageNumber: int | None = Field(default=None, ge=1)
    slideNumber: int | None = Field(default=None, ge=1)
    chunkIndex: int = Field(ge=0)
    heading: str | None = Field(default=None, max_length=500)
    evidenceQuote: str = Field(min_length=1, max_length=5000)


class AttemptTutorRequest(BaseModel):
    questionNumber: int = Field(ge=1)
    questionType: str = Field(min_length=1, max_length=40)
    prompt: str = Field(min_length=1, max_length=10000)
    options: list[str] = Field(default_factory=list, max_length=20)
    learnerAnswer: str | None = Field(default=None, max_length=10000)
    correctAnswer: str = Field(min_length=1, max_length=10000)
    explanation: str | None = Field(default=None, max_length=10000)
    sources: list[TutorSource] = Field(default_factory=list, max_length=20)
    conversationHistory: list[TutorConversationMessage] = Field(default_factory=list, max_length=12)
    message: str = Field(min_length=2, max_length=4000)

    @model_validator(mode="after")
    def validate_total_size(self) -> "AttemptTutorRequest":
        history_size = sum(len(item.content) for item in self.conversationHistory)
        source_size = sum(len(item.evidenceQuote) for item in self.sources)
        if history_size > 12000:
            raise ValueError("Lịch sử hội thoại vượt quá 12.000 ký tự.")
        if source_size > 30000:
            raise ValueError("Nguồn tham chiếu vượt quá 30.000 ký tự.")
        return self


class RetrievalHealthResponse(BaseModel):
    enabled: bool
    available: bool
    model: str
    errorCode: str | None
