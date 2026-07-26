from fastapi import APIRouter, Depends, Request

from app.api.dependencies import get_gemini_service, require_internal_api_key
from app.schemas.chat import ChatRequest, ChatResponse, TokenUsageResponse

SYSTEM_INSTRUCTION = (
    "Bạn là trợ lý học tập của BKQuiz. Trả lời chính xác, rõ ràng và bằng ngôn ngữ "
    "của người dùng. Nếu không đủ thông tin, hãy nói rõ thay vì suy đoán."
)

router = APIRouter(tags=["chat"], dependencies=[Depends(require_internal_api_key)])


@router.post("/chat", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    request: Request,
) -> ChatResponse:
    service = get_gemini_service(request)
    result = await service.generate(
        payload.message,
        system_instruction=SYSTEM_INSTRUCTION,
        trace_id=request.state.trace_id,
    )
    return ChatResponse(
        answer=result.answer,
        model=result.model,
        usage=TokenUsageResponse(
            input_tokens=result.usage.input_tokens,
            output_tokens=result.usage.output_tokens,
            total_tokens=result.usage.total_tokens,
        ),
    )
