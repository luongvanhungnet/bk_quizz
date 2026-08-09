import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.core.config import get_settings
from app.schemas.hybrid import GroundedQuizOutput
from app.services.gemini_quiz_providers import GeminiApiKeyProvider, GeminiOAuthProvider
from app.services.gemini_service import GeminiService
from app.services.grounded_quiz_service import GroundedQuizService
from app.services.ollama_qwen_provider import OllamaQwenProvider
from app.services.quiz_llm_provider import (
    LLMErrorCategory,
    LLMProviderError,
    QuizLLMCommand,
    QuizLLMPart,
    QuizLLMRouter,
)

SOURCE_TEXT = (
    "Retrieval-Augmented Generation kết hợp truy xuất tài liệu với mô hình ngôn ngữ. "
    "FAISS tìm kiếm theo vector, còn BM25 tìm kiếm theo từ khóa. "
    "Câu trả lời phải dựa trên context và kèm nguồn trích dẫn."
)


class FailingProvider:
    def __init__(self, name: str) -> None:
        self.name = name
        self.model = "simulated"

    async def generate_quiz(self, command: QuizLLMCommand) -> Any:
        raise LLMProviderError(
            LLMErrorCategory.UNAVAILABLE,
            "Simulated provider failure",
            fallback_eligible=True,
        )

    async def close(self) -> None:
        return None

    async def health(self) -> dict[str, Any]:
        return {"configured": True, "simulatedFailure": True}


def command() -> QuizLLMCommand:
    slots = [
        {
            "planSlotId": f"manual-{index + 1}",
            "questionType": "SINGLE_CHOICE",
            "cognitiveLevel": "L1",
            "focusHint": ("RAG", "FAISS", "BM25", "trích dẫn nguồn")[index],
            "constraint": {
                "cognitiveLevel": "L1",
                "conceptMin": 1,
                "conceptMax": 1,
                "reasoningMin": 0,
                "reasoningMax": 0,
                "requiresNovelScenario": False,
                "answerDirectlyPresent": True,
                "requiresComparison": False,
                "scoreMin": 1,
                "scoreMax": 2,
            },
        }
        for index in range(4)
    ]
    message = (
        "Tạo chính xác 4 câu SINGLE_CHOICE bằng tiếng Việt theo questionPlan sau. "
        "Mỗi câu có đúng 4 options và đúng 1 đáp án. "
        f"questionPlan={json.dumps(slots, ensure_ascii=False)}\n"
        "Mọi citation dùng sourceId S1 và evidenceQuote phải sao chép từ nguồn.\n"
        f"<context>\n[S1]\nNội dung:\n{SOURCE_TEXT}\n</context>"
    )
    return QuizLLMCommand(
        message=message,
        system_instruction="Bạn là hệ thống tạo quiz có kiểm chứng nguồn của BKQuiz.",
        response_schema=GroundedQuizOutput,
        question_count=4,
        batch_index=0,
        trace_id="manual-llm-fallback-test",
        gemini_parts=(
            QuizLLMPart(
                message,
                4,
                tuple(item["planSlotId"] for item in slots),
                tuple(slots),
            ),
        ),
        ollama_parts=tuple(
            QuizLLMPart(
                message,
                2,
                tuple(
                    item["planSlotId"] for item in slots[offset:offset + 2]
                ),
                tuple(slots[offset:offset + 2]),
            )
            for offset in range(0, len(slots), 2)
        ),
        allowed_source_ids=frozenset({"S1"}),
    )


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--provider",
        choices=("chain", "gemini-api-key", "gemini-oauth", "ollama"),
        default="chain",
    )
    parser.add_argument("--simulate-gemini-failure", action="store_true")
    args = parser.parse_args()
    settings = get_settings()

    print(json.dumps({
        "geminiApiKeyConfigured": bool(settings.gemini_api_key),
        "geminiModel": settings.gemini_model,
        "oauthEnabled": settings.gemini_oauth_enabled,
        "oauthQuotaProjectConfigured": bool(settings.gemini_oauth_quota_project),
        "geminiBatchSize": settings.gemini_batch_size,
        "geminiOAuthTimeoutSeconds": settings.gemini_oauth_timeout_seconds,
        "ollamaEnabled": settings.ollama_enabled,
        "ollamaBaseUrl": settings.ollama_base_url,
        "ollamaModel": settings.ollama_model,
        "ollamaMaxQuestionsPerCall": settings.ollama_max_questions_per_call,
        "ollamaMaxOutputTokens": settings.ollama_max_output_tokens,
    }, ensure_ascii=False, indent=2))

    providers: list[Any] = []
    owned_gemini: GeminiService | None = None
    if args.provider == "ollama":
        providers.append(OllamaQwenProvider(settings))
    elif args.provider == "gemini-api-key":
        if not settings.gemini_api_key:
            raise SystemExit("GEMINI_API_KEY chưa được cấu hình.")
        owned_gemini = GeminiService(settings)
        providers.append(GeminiApiKeyProvider(owned_gemini, settings.gemini_model))
    elif args.provider == "gemini-oauth":
        providers.append(GeminiOAuthProvider(settings))
    elif args.simulate_gemini_failure:
        providers.extend([
            FailingProvider("gemini_api_key"),
            FailingProvider("gemini_oauth"),
            OllamaQwenProvider(settings),
        ])
    else:
        if settings.gemini_api_key:
            owned_gemini = GeminiService(settings)
            providers.append(GeminiApiKeyProvider(owned_gemini, settings.gemini_model))
        if settings.gemini_oauth_enabled:
            providers.append(GeminiOAuthProvider(settings))
        if settings.ollama_enabled:
            providers.append(OllamaQwenProvider(settings))
    router = QuizLLMRouter(
        providers,
        failure_threshold=settings.llm_circuit_breaker_failure_threshold,
        cooldown_seconds=settings.llm_circuit_breaker_cooldown_seconds,
    )
    try:
        print(json.dumps(await router.health(), ensure_ascii=False, indent=2))
        result = await router.generate_quiz(command())
        output = GroundedQuizOutput.model_validate_json(result.answer)
        for question in output.questions:
            if len(question.options) != 4 or sum(option.correct for option in question.options) != 1:
                raise ValueError("Câu SINGLE_CHOICE không có đúng bốn lựa chọn và một đáp án.")
            citations = (
                question.questionCitations
                + question.answerCitations
                + question.explanationCitations
            )
            if any(
                citation.sourceId != "S1"
                or GroundedQuizService._canonical_quote(
                    SOURCE_TEXT, citation.evidenceQuote
                ) is None
                for citation in citations
            ):
                raise ValueError("Citation Qwen không khớp context tin cậy.")
        print(json.dumps({
            "provider": result.provider,
            "model": result.model,
            "questions": len(output.questions),
            "usage": {
                "inputTokens": result.usage.input_tokens,
                "outputTokens": result.usage.output_tokens,
                "totalTokens": result.usage.total_tokens,
            },
        }, ensure_ascii=False, indent=2))
        return 0
    finally:
        await router.close()
        if owned_gemini is not None:
            await owned_gemini.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
