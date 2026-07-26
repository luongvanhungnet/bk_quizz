import json
import re
from dataclasses import dataclass
from typing import Any

from app.schemas.hybrid import ConversationMessage, QueryRewriteOutput
from app.services.hybrid_retrieval import normalize_query

DEPENDENT_QUERY = re.compile(
    r"\b(nó|đó|này|họ|chúng|điều đó|cái này|như vậy|tại sao vậy)\b",
    re.IGNORECASE,
)
REWRITE_INSTRUCTION = """Viết lại câu hỏi phụ thuộc hội thoại thành một câu hỏi độc lập bằng đúng ngôn ngữ người dùng.
Không dịch, không thêm sự kiện, tên riêng hoặc ý định mới. Nếu câu hỏi đã độc lập, giữ nguyên.
Chỉ trả JSON theo schema được cung cấp."""


@dataclass(frozen=True)
class RewriteResult:
    original: str
    rewritten: str
    changed: bool
    attempted: bool


class QueryRewriteService:
    def __init__(self, enabled: bool) -> None:
        self._enabled = enabled

    async def rewrite(
        self,
        question: str,
        history: list[ConversationMessage],
        gemini_service: Any | None,
        *,
        trace_id: str,
    ) -> RewriteResult:
        original = normalize_query(question)
        if (
            not self._enabled
            or not history
            or gemini_service is None
            or not self._needs_rewrite(original)
        ):
            return RewriteResult(original, original, False, False)
        conversation = [item.model_dump() for item in history]
        message = json.dumps(
            {"conversationHistory": conversation, "question": original},
            ensure_ascii=False,
        )
        try:
            result = await gemini_service.generate(
                message,
                system_instruction=REWRITE_INSTRUCTION,
                temperature=0,
                max_output_tokens=512,
                trace_id=trace_id,
                response_schema=QueryRewriteOutput,
            )
            parsed = QueryRewriteOutput.model_validate_json(result.answer)
            rewritten = normalize_query(parsed.standaloneQuestion)
            if len(rewritten) < 2 or len(rewritten) > 5000:
                raise ValueError("invalid rewritten question")
            return RewriteResult(original, rewritten, parsed.rewritten and rewritten != original, True)
        except Exception:
            return RewriteResult(original, original, False, True)

    @staticmethod
    def _needs_rewrite(question: str) -> bool:
        return bool(DEPENDENT_QUERY.search(question)) or (
            len(question) < 40 and question.casefold().startswith(("tại sao", "vì sao", "thế nào"))
        )
