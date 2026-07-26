from typing import Literal

from fastapi import APIRouter, Depends, Query, Request

from app.api.dependencies import require_user_context, validate_debug_access
from app.core.exceptions import ServiceError
from app.models.user_context import UserContext
from app.schemas.evaluation import RetrievalEvaluationItem, RetrievalMetrics

router = APIRouter(prefix="/evaluation", tags=["evaluation"])


@router.post("/retrieval", response_model=RetrievalMetrics)
async def evaluate_retrieval(
    payload: list[RetrievalEvaluationItem],
    request: Request,
    k: int = Query(default=5, ge=1, le=50),
    mode: Literal["baseline", "hybrid"] = Query(default="hybrid"),
    context: UserContext = Depends(require_user_context),
) -> RetrievalMetrics:
    validate_debug_access(request, True)
    if k > request.app.state.settings.rag_max_top_k:
        raise ServiceError(422, "RAG_TOP_K_EXCEEDED", f"k không được lớn hơn {request.app.state.settings.rag_max_top_k}.")
    result = await request.app.state.evaluation_service.evaluate(
        context.owner_id,
        payload,
        k,
        mode,
        trace_id=request.state.trace_id,
    )
    return RetrievalMetrics(**result)
