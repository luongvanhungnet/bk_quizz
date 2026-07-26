from time import perf_counter
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from google.genai import types

from app.api.dependencies import get_gemini_service, require_internal_api_key
from app.schemas.chat import GeminiHealthResponse, HealthResponse, RetrievalHealthResponse

router = APIRouter(tags=["health"])


@router.get(
    "/health/retrieval",
    response_model=RetrievalHealthResponse,
    dependencies=[Depends(require_internal_api_key)],
)
async def retrieval_health(request: Request) -> RetrievalHealthResponse:
    service = request.app.state.reranker_service
    return RetrievalHealthResponse(
        enabled=service.enabled,
        available=service.available,
        model=service.model_name,
        errorCode=service.error_code,
    )


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    settings = request.app.state.settings
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        environment=settings.app_env,
        gemini_configured=bool(settings.gemini_api_key),
    )


@router.get(
    "/health/gemini",
    response_model=GeminiHealthResponse,
    dependencies=[Depends(require_internal_api_key)],
)
async def gemini_health(
    request: Request,
    service: Annotated[Any, Depends(get_gemini_service)],
) -> GeminiHealthResponse:
    started_at = perf_counter()
    result = await service.generate(
        "Chỉ trả lời đúng một từ: OK",
        system_instruction="Bạn là kiểm tra kết nối. Chỉ trả lời đúng yêu cầu.",
        temperature=0,
        max_output_tokens=64,
        trace_id=request.state.trace_id,
        thinking_level=types.ThinkingLevel.MINIMAL,
    )
    return GeminiHealthResponse(
        status="ok",
        model=result.model,
        latency_ms=round((perf_counter() - started_at) * 1000),
        message="Kết nối Gemini hoạt động bình thường.",
    )
