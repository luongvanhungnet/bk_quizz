from time import perf_counter
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from google.genai import types

from app.api.dependencies import get_gemini_service, require_internal_api_key
from app.schemas.chat import (
    GeminiHealthResponse,
    GeminiProbeOutput,
    HealthResponse,
    RetrievalHealthResponse,
)
from app.services.structured_schema import provider_json_schema

router = APIRouter(tags=["health"])


@router.get(
    "/health/llm",
    dependencies=[Depends(require_internal_api_key)],
)
async def llm_health(request: Request) -> dict[str, Any]:
    router_service = request.app.state.quiz_llm_router
    providers = await router_service.health() if router_service is not None else {}
    ollama = providers.get("ollama", {})
    return {
        "status": "ok",
        "fallbackEnabled": request.app.state.settings.llm_fallback_enabled,
        "providers": providers,
        "ollamaConfigured": bool(ollama.get("configured")),
        "ollamaReachable": bool(ollama.get("reachable")),
        "ollamaModel": ollama.get("model"),
        "ollamaModelAvailable": bool(ollama.get("modelAvailable")),
        "providerOrder": list(providers),
        "geminiBatchSize": request.app.state.settings.gemini_batch_size,
        "geminiOAuthTimeoutSeconds": (
            request.app.state.settings.gemini_oauth_timeout_seconds
        ),
        "ollamaMaxQuestionsPerCall": (
            request.app.state.settings.ollama_max_questions_per_call
        ),
        "ollamaMaxOutputTokens": (
            request.app.state.settings.ollama_max_output_tokens
        ),
    }


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
        "Trả về JSON xác nhận trạng thái kết nối.",
        system_instruction="Chỉ trả về JSON đúng schema được cung cấp với status là OK.",
        temperature=0,
        max_output_tokens=256,
        trace_id=request.state.trace_id,
        thinking_level=types.ThinkingLevel.MINIMAL,
        response_schema=provider_json_schema(GeminiProbeOutput),
    )
    GeminiProbeOutput.model_validate_json(result.answer)
    return GeminiHealthResponse(
        status="ok",
        model=result.model,
        latency_ms=round((perf_counter() - started_at) * 1000),
        credential_source=request.app.state.gemini_credential_source,
        message="Kết nối Gemini hoạt động bình thường.",
    )
