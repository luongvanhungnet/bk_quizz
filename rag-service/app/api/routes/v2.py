import asyncio
import json
import traceback
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Literal

from fastapi import APIRouter, Depends, File, Header, Query, Request, Response, UploadFile, status
from fastapi.responses import StreamingResponse

from app.api.dependencies import require_internal_api_key, require_user_context
from app.core.contracts import (
    QUIZ_GENERATION_CAPABILITIES,
    QUIZ_GENERATION_CONTRACT,
)
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
from app.services.citation_matcher import CitationMatcher
from app.services.grounded_quiz_service import GroundedQuizService
from app.services.quiz_context_selector import QuizContextSelector
from app.utils.rag_logging import log_quiz_generation

router = APIRouter(tags=["v2-production"])


async def _stream_ndjson(
    queue: asyncio.Queue[dict[str, Any] | None],
    task: asyncio.Task[Any],
    *,
    heartbeat_seconds: float = 15.0,
) -> AsyncIterator[bytes]:
    """Keep the NDJSON connection active while CPU-bound stages are silent."""
    try:
        while True:
            try:
                event = await asyncio.wait_for(
                    queue.get(), timeout=heartbeat_seconds
                )
            except TimeoutError:
                event = {
                    "type": "HEARTBEAT",
                    "level": "INFO",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            if event is None:
                break
            yield (
                json.dumps(event, ensure_ascii=False, separators=(",", ":"))
                + "\n"
            ).encode("utf-8")
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


def _unexpected_stream_failure(
    *, request_id: str, stage: str, error_id: str
) -> dict[str, Any]:
    return {
        "type": "FAILED",
        "level": "ERROR",
        "message": "RAG gặp lỗi nội bộ khi xử lý kết quả quiz.",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "requestId": request_id,
        "errorCode": "RAG_INTERNAL_ERROR",
        "retryable": False,
        "retryAfterSeconds": None,
        "stage": stage,
        "errorId": error_id,
        "details": [{
            "reason": "UNEXPECTED_INTERNAL_ERROR",
            "stage": stage,
            "errorId": error_id,
        }],
    }


def _citation_matcher(request: Request) -> CitationMatcher:
    existing = getattr(request.app.state, "citation_matcher", None)
    if existing is not None:
        return existing
    settings = request.app.state.settings
    return CitationMatcher(
        mode=settings.citation_match_mode,
        embedding_service=request.app.state.embedding_service,
        lexical_min_score=settings.citation_lexical_min_score,
        semantic_same_source_min_score=(
            settings.citation_semantic_same_source_min_score
        ),
        semantic_cross_source_min_score=(
            settings.citation_semantic_cross_source_min_score
        ),
        uniqueness_margin=settings.citation_uniqueness_margin,
        max_window_chars=settings.citation_max_window_chars,
        max_candidates_per_source=settings.citation_max_candidates_per_source,
    )


@router.get(
    "/capabilities",
    dependencies=[Depends(require_internal_api_key)],
)
def capabilities(request: Request) -> dict[str, Any]:
    return {
        "quizGenerationContract": QUIZ_GENERATION_CONTRACT,
        "capabilities": QUIZ_GENERATION_CAPABILITIES,
        "buildRevision": request.app.state.settings.app_build_revision,
    }


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
            rawText=chunk.raw_content,
            mathEnhanced=chunk.math_enhanced,
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
            quiz_llm_router=request.app.state.quiz_llm_router,
            gemini_batch_size=request.app.state.settings.gemini_batch_size,
            ollama_max_questions=request.app.state.settings.ollama_max_questions_per_call,
            citation_matcher=_citation_matcher(request),
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
        providers_used=result.get("providersUsed", []),
        generated_by_provider=result.get("generatedByProvider", {}),
    )
    return GroundedQuizResponse(**result)


@router.post("/user-rag/generate-quiz/stream")
async def stream_grounded_quiz(
    payload: GroundedQuizRequest,
    request: Request,
    context: UserContext = Depends(require_user_context),
    service=Depends(user_rag),
) -> StreamingResponse:
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
    current_stage = {"value": "RETRIEVING"}

    async def emit(event: dict[str, Any]) -> None:
        stage = event.get("stage")
        if isinstance(stage, str) and stage:
            current_stage["value"] = stage
        await queue.put(event)

    async def run() -> None:
        try:
            await emit({
                "type": "STAGE",
                "level": "INFO",
                "message": "Đang chuẩn bị ngữ cảnh từ tài liệu đã chọn.",
                "stage": "RETRIEVING",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            corpora = await service.prepare_corpora(
                context.owner_id,
                payload.documentIds,
                False,
            )
            selection = QuizContextSelector(
                request.app.state.settings.rag_max_context_chars,
                min_useful_chars=request.app.state.settings.rag_quiz_min_useful_chars,
            ).select(payload.title, corpora)
            await emit({
                "type": "STAGE",
                "level": "INFO",
                "message": (
                    f"Đã chọn {len(selection.context.sources)} đoạn nguồn phù hợp."
                ),
                "stage": "CONTEXT_READY",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            current_stage["value"] = "GENERATING"
            result = await GroundedQuizService().generate(
                request=payload,
                context=selection.context,
                gemini_service=request.app.state.gemini_service,
                trace_id=request.state.trace_id,
                quiz_llm_router=request.app.state.quiz_llm_router,
                gemini_batch_size=request.app.state.settings.gemini_batch_size,
                ollama_max_questions=request.app.state.settings.ollama_max_questions_per_call,
                citation_matcher=_citation_matcher(request),
                event_sink=emit,
            )
            await emit({
                "type": "RESULT",
                "level": "SUCCESS",
                "message": "AI đã tạo và kiểm tra xong nhóm câu hỏi.",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "requestId": request.state.trace_id,
                "data": result,
            })
        except ServiceError as error:
            await emit({
                "type": "FAILED",
                "level": "ERROR",
                "message": error.message,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "requestId": request.state.trace_id,
                "errorCode": error.code,
                "retryable": error.retryable,
                "retryAfterSeconds": error.retry_after_seconds,
                "details": error.details,
            })
        except (TimeoutError, ConnectionError):
            await emit({
                "type": "FAILED",
                "level": "ERROR",
                "message": "RAG tạm thời không thể hoàn tất bước xử lý hiện tại.",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "requestId": request.state.trace_id,
                "errorCode": "RAG_TRANSIENT_ERROR",
                "retryable": True,
                "retryAfterSeconds": 300,
                "stage": current_stage["value"],
                "details": [{
                    "reason": "TRANSIENT_PROCESSING_FAILURE",
                    "stage": current_stage["value"],
                }],
            })
        except Exception as error:
            error_id = f"rag-{uuid.uuid4()}"
            safe_frames = [
                f"{frame.name}:{frame.lineno}"
                for frame in traceback.extract_tb(error.__traceback__)[-12:]
            ]
            request.app.state.logger.error(
                "Quiz stream internal failure trace_id=%s stage=%s error_id=%s type=%s frames=%s",
                request.state.trace_id,
                current_stage["value"],
                error_id,
                type(error).__name__,
                safe_frames,
            )
            await emit(_unexpected_stream_failure(
                request_id=request.state.trace_id,
                stage=current_stage["value"],
                error_id=error_id,
            ))
        finally:
            await queue.put(None)

    async def lines() -> AsyncIterator[bytes]:
        task = asyncio.create_task(run())
        async for chunk in _stream_ndjson(queue, task):
            yield chunk

    return StreamingResponse(
        lines(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


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
