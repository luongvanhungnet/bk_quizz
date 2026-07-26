import hashlib
import hmac
import json
import logging
from typing import Any

LOGGER = logging.getLogger("uvicorn.error")


def log_rag_request(
    *,
    request_id: str,
    user_id: str | None,
    endpoint: str,
    search: Any,
    selected_count: int,
    model: str | None,
    secret: str,
    success: bool = True,
    error_code: str | None = None,
) -> None:
    user_hash = None
    if user_id:
        user_hash = hmac.new(
            secret.encode("utf-8"), user_id.encode("utf-8"), hashlib.sha256
        ).hexdigest()[:12]
    payload = {
        "requestId": request_id,
        "userId": user_hash,
        "endpoint": endpoint,
        "vectorCandidates": len(search.retrieval.vector_candidates),
        "bm25Candidates": len(search.retrieval.bm25_candidates),
        "selectedCount": selected_count,
        "latencyMs": search.retrieval.timings_ms,
        "geminiModel": model,
        "success": success,
        "errorCode": error_code,
    }
    LOGGER.info(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


def log_rag_error(
    *, request_id: str, user_id: str | None, endpoint: str, error_code: str, secret: str
) -> None:
    user_hash = None
    if user_id:
        user_hash = hmac.new(
            secret.encode("utf-8"), user_id.encode("utf-8"), hashlib.sha256
        ).hexdigest()[:12]
    LOGGER.info(json.dumps({
        "requestId": request_id,
        "userId": user_hash,
        "endpoint": endpoint,
        "vectorCandidates": 0,
        "bm25Candidates": 0,
        "selectedCount": 0,
        "success": False,
        "errorCode": error_code,
    }, ensure_ascii=False, separators=(",", ":")))


def log_quiz_generation(
    *,
    request_id: str,
    user_id: str,
    selection: Any,
    model: str | None,
    secret: str,
    success: bool,
    error_code: str | None = None,
) -> None:
    user_hash = hmac.new(
        secret.encode("utf-8"), user_id.encode("utf-8"), hashlib.sha256
    ).hexdigest()[:12]
    LOGGER.info(json.dumps({
        "requestId": request_id,
        "userId": user_hash,
        "endpoint": "/api/v2/user-rag/generate-quiz",
        "eligibleDocuments": selection.eligible_documents,
        "eligibleChunks": selection.eligible_chunks,
        "selectedChunks": selection.selected_chunks,
        "contextChars": selection.context.character_count,
        "selectionMode": selection.mode,
        "geminiModel": model,
        "success": success,
        "errorCode": error_code,
    }, ensure_ascii=False, separators=(",", ":")))
