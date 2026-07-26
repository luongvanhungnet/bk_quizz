from datetime import datetime

from pydantic import BaseModel


class AsyncUploadResponse(BaseModel):
    documentId: str
    jobId: str
    documentStatus: str
    jobStatus: str


class IndexingJobDto(BaseModel):
    id: str
    documentId: str
    status: str
    progress: int
    step: str
    attempts: int
    maxAttempts: int
    errorCode: str | None
    errorMessage: str | None
    createdAt: datetime
    updatedAt: datetime
    startedAt: datetime | None
    heartbeatAt: datetime | None
    finishedAt: datetime | None


class JobMutationResponse(BaseModel):
    jobId: str
    status: str

