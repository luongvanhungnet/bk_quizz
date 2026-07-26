from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request

from app.api.dependencies import get_rag_pipeline_service, require_internal_api_key, validate_debug_access
from app.core.exceptions import ServiceError
from app.schemas.rag import (
    AskResponse,
    RagQuestionRequest,
    SearchResponse,
    SearchResultResponse,
)
from app.services.hybrid_retrieval import CorpusView
from app.utils.rag_logging import log_rag_request

router = APIRouter(
    prefix="/rag",
    tags=["rag"],
    dependencies=[Depends(require_internal_api_key)],
)


def resolve_top_k(request: Request, requested: int | None) -> int:
    settings = request.app.state.settings
    top_k = requested or settings.rag_default_top_k
    if top_k > settings.rag_max_top_k:
        raise ServiceError(
            422,
            "RAG_TOP_K_EXCEEDED",
            f"topK không được lớn hơn {settings.rag_max_top_k}.",
        )
    return top_k


@router.post("/search", response_model=SearchResponse)
async def search_system_documents(
    payload: RagQuestionRequest,
    request: Request,
    service: Annotated[Any, Depends(get_rag_pipeline_service)],
) -> SearchResponse:
    top_k = resolve_top_k(request, payload.top_k)
    validate_debug_access(request, payload.debug)
    snapshot = request.app.state.vector_store.require_snapshot()
    result = await service.search(
        payload.question,
        payload.conversation_history,
        request.app.state.gemini_service,
        [CorpusView("system", snapshot)],
        top_k,
        namespace="system",
        trace_id=request.state.trace_id,
    )
    response = SearchResponse(
        question=payload.question,
        top_k=top_k,
        results=[
            SearchResultResponse(
                chunk_id=item.chunk.chunk_id,
                document_id=item.chunk.document_id,
                document_type=item.chunk.document_type,
                filename=item.chunk.filename,
                file_hash=item.chunk.file_hash,
                page_number=item.chunk.page_number,
                chunk_index=item.chunk.chunk_index,
                heading=item.chunk.heading,
                text=item.chunk.text,
                created_at=item.chunk.created_at,
                score=round(item.final_score, 6),
            )
            for item in result.retrieval.candidates
        ],
        debug=service.debug_payload(result) if payload.debug else None,
    )
    log_rag_request(
        request_id=request.state.trace_id, user_id=None, endpoint="/api/v1/rag/search",
        search=result, selected_count=len(result.retrieval.candidates), model=None,
        secret=request.app.state.settings.spring_boot_internal_api_key,
    )
    return response


@router.post("/ask", response_model=AskResponse)
async def ask_system_documents(
    payload: RagQuestionRequest,
    request: Request,
    service: Annotated[Any, Depends(get_rag_pipeline_service)],
) -> AskResponse:
    top_k = resolve_top_k(request, payload.top_k)
    validate_debug_access(request, payload.debug)
    snapshot = request.app.state.vector_store.require_snapshot()
    corpora = [CorpusView("system", snapshot)]
    search = await service.search(
        payload.question,
        payload.conversation_history,
        request.app.state.gemini_service,
        corpora,
        top_k,
        namespace="system",
        trace_id=request.state.trace_id,
    )
    answer, debug = await service.ask(
        search, corpora, top_k, request.app.state.gemini_service,
        trace_id=request.state.trace_id,
    )
    response = AskResponse(
        question=payload.question,
        answer=answer["answer"],
        scope="SYSTEM",
        sources=answer["sources"],
        insufficient_context=answer["insufficientContext"],
        debug=debug if payload.debug else None,
    )
    log_rag_request(
        request_id=request.state.trace_id, user_id=None, endpoint="/api/v1/rag/ask",
        search=search, selected_count=len(answer["sources"]), model=answer["model"],
        secret=request.app.state.settings.spring_boot_internal_api_key,
    )
    return response
