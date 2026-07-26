from typing import Literal

from fastapi import APIRouter, Depends, File, Header, Query, Request, Response, UploadFile, status

from app.api.dependencies import require_user_context
from app.core.exceptions import ServiceError
from app.models.user_context import UserContext
from app.schemas.indexing_job import AsyncUploadResponse, IndexingJobDto, JobMutationResponse
from app.schemas.user_document import (
    GroundedQuizRequest,
    GroundedQuizResponse,
    PaginationDto,
    UserChunkDto,
    UserChunkListResponse,
    UserDocumentDto,
    UserDocumentListResponse,
)
from app.services.grounded_quiz_service import GroundedQuizService
from app.services.quiz_context_selector import QuizContextSelector
from app.utils.rag_logging import log_quiz_generation

router = APIRouter(tags=["v2-production"])


def async_documents(request: Request):
    return request.app.state.async_document_service


def jobs(request: Request):
    return request.app.state.indexing_job_service


def dispatcher(request: Request):
    return request.app.state.job_dispatcher


def documents(request: Request):
    return request.app.state.user_document_service


def user_rag(request: Request):
    return request.app.state.user_rag_service


def upload_rate_limit(request: Request, context: UserContext = Depends(require_user_context)) -> UserContext:
    request.app.state.rate_limiter.check("upload", context.safe_key, request.app.state.settings.upload_user_rpm)
    return context


@router.post("/user-documents", response_model=AsyncUploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    file: UploadFile = File(...),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=128),
    context: UserContext = Depends(upload_rate_limit),
    service=Depends(async_documents), job_dispatcher=Depends(dispatcher),
) -> AsyncUploadResponse:
    result = await service.upload(context, file, idempotency_key)
    if result.jobStatus == "PENDING":
        try:
            job_dispatcher.dispatch(result.jobId)
        except Exception as error:
            raise ServiceError(
                503, "JOB_QUEUE_UNAVAILABLE", "Hàng đợi lập chỉ mục tạm thời không khả dụng.",
                retryable=True, retry_after_seconds=5,
            ) from error
    return result


@router.get("/user-documents", response_model=UserDocumentListResponse)
def list_documents(
    page: int = Query(default=1, ge=1), size: int = Query(default=20, ge=1, le=100),
    status_filter: Literal["UPLOADED", "PROCESSING", "READY", "FAILED", "DELETED"] | None = Query(default=None, alias="status"),
    context: UserContext = Depends(require_user_context), service=Depends(documents),
):
    return service.list_documents(context.owner_id, page, size, status_filter)


@router.get("/user-documents/{document_id}", response_model=UserDocumentDto)
def get_document(document_id: str, context: UserContext = Depends(require_user_context), service=Depends(documents)):
    return service.get(context.owner_id, document_id)


@router.get("/user-documents/{document_id}/chunks", response_model=UserChunkListResponse)
async def list_document_chunks(
    document_id: str,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=100, ge=1, le=500),
    context: UserContext = Depends(require_user_context),
    service=Depends(user_rag),
) -> UserChunkListResponse:
    chunks = await service.document_chunks(context.owner_id, document_id)
    start = (page - 1) * size
    items = chunks[start : start + size]
    total = len(chunks)
    return UserChunkListResponse(
        items=[UserChunkDto(
            chunkId=chunk.chunk_id,
            documentId=chunk.document_id,
            filename=chunk.filename,
            pageNumber=chunk.page_number,
            slideNumber=chunk.slide_number,
            chunkIndex=chunk.chunk_index,
            heading=chunk.heading,
            text=chunk.text,
        ) for chunk in items],
        pagination=PaginationDto(
            page=page,
            size=size,
            totalItems=total,
            totalPages=(total + size - 1) // size if total else 0,
        ),
    )


@router.post("/user-rag/generate-quiz", response_model=GroundedQuizResponse)
async def generate_grounded_quiz(
    payload: GroundedQuizRequest,
    request: Request,
    context: UserContext = Depends(require_user_context),
    service=Depends(user_rag),
) -> GroundedQuizResponse:
    corpora = await service.prepare_corpora(
        context.owner_id,
        payload.documentIds,
        False,
    )
    selection = QuizContextSelector(
        request.app.state.settings.rag_max_context_chars,
        min_useful_chars=request.app.state.settings.rag_quiz_min_useful_chars,
    ).select(payload.title, corpora)
    try:
        result = await GroundedQuizService().generate(
            request=payload,
            context=selection.context,
            gemini_service=request.app.state.gemini_service,
            trace_id=request.state.trace_id,
        )
    except ServiceError as error:
        log_quiz_generation(
            request_id=request.state.trace_id,
            user_id=context.owner_id,
            selection=selection,
            model=None,
            secret=request.app.state.settings.spring_boot_internal_api_key,
            success=False,
            error_code=error.code,
        )
        raise
    log_quiz_generation(
        request_id=request.state.trace_id,
        user_id=context.owner_id,
        selection=selection,
        model=result["model"],
        secret=request.app.state.settings.spring_boot_internal_api_key,
        success=True,
    )
    return GroundedQuizResponse(**result)


@router.delete("/user-documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(document_id: str, context: UserContext = Depends(require_user_context), service=Depends(documents), job_service=Depends(jobs)) -> Response:
    job_service.cancel_for_document(context.owner_id, document_id)
    service.delete(context.owner_id, document_id)
    job_service.audit(context.owner_id, "DOCUMENT_DELETED", "DOCUMENT", document_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/indexing-jobs/{job_id}", response_model=IndexingJobDto)
def get_job(job_id: str, context: UserContext = Depends(require_user_context), service=Depends(jobs)):
    return service.get(context.owner_id, job_id)


@router.post("/indexing-jobs/{job_id}/retry", response_model=JobMutationResponse)
def retry_job(job_id: str, context: UserContext = Depends(require_user_context), service=Depends(jobs), job_dispatcher=Depends(dispatcher)):
    result = service.retry(context.owner_id, job_id, reset_attempts=True)
    job_dispatcher.dispatch(job_id)
    return JobMutationResponse(jobId=job_id, status=result.status)


@router.post("/indexing-jobs/{job_id}/cancel", response_model=JobMutationResponse)
def cancel_job(job_id: str, context: UserContext = Depends(require_user_context), service=Depends(jobs)):
    result = service.cancel(context.owner_id, job_id)
    return JobMutationResponse(jobId=job_id, status=result.status)


@router.delete("/users/{user_id}/data", status_code=status.HTTP_204_NO_CONTENT)
def delete_user_data(user_id: str, context: UserContext = Depends(require_user_context), service=Depends(async_documents)) -> Response:
    if user_id != context.owner_id:
        raise ServiceError(404, "USER_DATA_NOT_FOUND", "Không tìm thấy dữ liệu người dùng.")
    service.delete_user_data(context.owner_id, context.safe_key)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
