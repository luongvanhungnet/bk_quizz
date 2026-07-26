from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    message: str


class RetrievalHealthResponse(BaseModel):
    enabled: bool
    available: bool
    model: str
    errorCode: str | None
