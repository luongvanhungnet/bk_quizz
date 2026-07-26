from fastapi import APIRouter, Depends, Request

from app.api.dependencies import get_user_rag_service, require_user_context, validate_debug_access
from app.models.user_context import UserContext
from app.schemas.user_document import (
    UserRagAskRequest,
    UserRagAskResponse,
    UserRagRequest,
    UserRagResult,
    UserRagSearchResponse,
    UserRagSource,
)
from app.utils.rag_logging import log_rag_request

router = APIRouter(tags=["user-rag"])


@router.post("/user-rag/search", response_model=UserRagSearchResponse)
async def search_user_documents(
    payload: UserRagRequest,
    request: Request,
    context: UserContext = Depends(require_user_context),
    service=Depends(get_user_rag_service),
) -> UserRagSearchResponse:
    top_k = payload.topK or request.app.state.settings.rag_default_top_k
    top_k = min(top_k, request.app.state.settings.rag_max_top_k)
    validate_debug_access(request, payload.debug)
    result, _ = await service.search(
        owner_id=context.owner_id,
        question=payload.question,
        top_k=top_k,
        document_ids=payload.documentIds,
        include_system=False,
        history=payload.conversationHistory,
        gemini_service=request.app.state.gemini_service,
        trace_id=request.state.trace_id,
    )
    response = UserRagSearchResponse(
        question=payload.question,
        topK=top_k,
        results=[UserRagResult(
            chunkId=item.chunk.chunk_id,
            documentId=item.chunk.document_id,
            filename=item.chunk.filename,
            sourceType=item.chunk.source_type or item.chunk.document_type,
            pageNumber=item.chunk.page_number,
            slideNumber=item.chunk.slide_number,
            chunkIndex=item.chunk.chunk_index,
            heading=item.chunk.heading,
            text=item.chunk.text,
            score=round(item.final_score, 6),
        ) for item in result.retrieval.candidates],
        debug=request.app.state.rag_pipeline_service.debug_payload(result) if payload.debug else None,
    )
    log_rag_request(
        request_id=request.state.trace_id, user_id=context.owner_id,
        endpoint="/api/v1/user-rag/search", search=result,
        selected_count=len(result.retrieval.candidates), model=None,
        secret=request.app.state.settings.spring_boot_internal_api_key,
    )
    return response


@router.post("/user-rag/ask", response_model=UserRagAskResponse)
async def ask_user_documents(
    payload: UserRagAskRequest,
    request: Request,
    context: UserContext = Depends(require_user_context),
    service=Depends(get_user_rag_service),
) -> UserRagAskResponse:
    top_k = payload.topK or request.app.state.settings.rag_default_top_k
    top_k = min(top_k, request.app.state.settings.rag_max_top_k)
    validate_debug_access(request, payload.debug)
    search, corpora = await service.search(
        owner_id=context.owner_id,
        question=payload.question,
        top_k=top_k,
        document_ids=payload.documentIds,
        include_system=payload.includeSystemDocuments,
        history=payload.conversationHistory,
        gemini_service=request.app.state.gemini_service,
        trace_id=request.state.trace_id,
    )
    result, debug = await service.ask(
        search=search,
        corpora=corpora,
        top_k=top_k,
        gemini_service=request.app.state.gemini_service,
        trace_id=request.state.trace_id,
    )
    response = UserRagAskResponse(
        answer=result["answer"],
        model=result["model"],
        usage=result["usage"],
        sources=[UserRagSource(**source) for source in result["sources"]],
        insufficientContext=result["insufficientContext"],
        debug=debug if payload.debug else None,
    )
    log_rag_request(
        request_id=request.state.trace_id, user_id=context.owner_id,
        endpoint="/api/v1/user-rag/ask", search=search,
        selected_count=len(result["sources"]), model=result["model"],
        secret=request.app.state.settings.spring_boot_internal_api_key,
    )
    return response
