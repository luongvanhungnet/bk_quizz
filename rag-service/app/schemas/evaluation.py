from pydantic import BaseModel, Field


class RetrievalEvaluationItem(BaseModel):
    question: str = Field(min_length=2, max_length=5000)
    expectedDocumentIds: list[str] = Field(min_length=1, max_length=100)
    expectedPageNumbers: list[int] = Field(default_factory=list, max_length=100)


class RetrievalMetrics(BaseModel):
    mode: str
    k: int
    queryCount: int
    hitRate: float
    recall: float
    mrr: float
    meanLatencyMs: float
    p50LatencyMs: float
    p95LatencyMs: float
