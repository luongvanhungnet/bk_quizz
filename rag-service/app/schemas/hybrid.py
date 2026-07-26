from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class ConversationMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2000)

    @field_validator("content")
    @classmethod
    def trim_content(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Nội dung hội thoại không được để trống.")
        return value


class HybridOptions(BaseModel):
    conversationHistory: list[ConversationMessage] = Field(default_factory=list, max_length=6)
    debug: bool = False

    @model_validator(mode="after")
    def validate_history_size(self) -> "HybridOptions":
        if sum(len(item.content) for item in self.conversationHistory) > 12000:
            raise ValueError("Tổng nội dung lịch sử hội thoại vượt quá 12.000 ký tự.")
        return self


class QueryRewriteOutput(BaseModel):
    standaloneQuestion: str = Field(min_length=2, max_length=5000)
    rewritten: bool


class GroundedAnswerOutput(BaseModel):
    answer: str
    usedSourceIds: list[str]
    insufficientContext: bool


class QuizCitationOutput(BaseModel):
    sourceId: str
    evidenceQuote: str = Field(min_length=1, max_length=1000)


class QuizOptionOutput(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    correct: bool


class GroundedQuizQuestionOutput(BaseModel):
    type: Literal["SINGLE_CHOICE", "MULTIPLE_SELECT", "FILL_BLANK"]
    difficulty: Literal["EASY", "MEDIUM", "HARD"] | None = None
    prompt: str = Field(min_length=1, max_length=10000)
    explanation: str = Field(min_length=1, max_length=10000)
    options: list[QuizOptionOutput] = Field(default_factory=list)
    acceptedAnswers: list[str] = Field(default_factory=list)
    questionCitations: list[QuizCitationOutput] = Field(min_length=1)
    answerCitations: list[QuizCitationOutput] = Field(min_length=1)
    explanationCitations: list[QuizCitationOutput] = Field(min_length=1)


class GroundedQuizOutput(BaseModel):
    questions: list[GroundedQuizQuestionOutput]
