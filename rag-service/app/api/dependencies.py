import secrets
from typing import Any

from fastapi import Depends, Header, Request

from app.core.exceptions import ServiceError
from app.models.user_context import UserContext, normalize_identifier, safe_user_key


async def require_internal_api_key(
    request: Request,
    x_internal_api_key: str | None = Header(default=None),
) -> None:
    settings = request.app.state.settings
    expected = settings.spring_boot_internal_api_key
    previous = settings.spring_boot_previous_internal_api_key
    provided = x_internal_api_key or ""
    current_matches = secrets.compare_digest(provided, expected)
    previous_matches = bool(previous) and secrets.compare_digest(provided, previous)
    if not (current_matches or previous_matches):
        raise ServiceError(
            401,
            "INVALID_INTERNAL_API_KEY",
            "Khóa truy cập nội bộ không hợp lệ.",
        )


async def require_user_context(
    _: None = Depends(require_internal_api_key),
    x_user_id: str | None = Header(default=None),
    x_classroom_id: str | None = Header(default=None),
) -> UserContext:
    if x_user_id is None:
        raise ServiceError(401, "USER_CONTEXT_REQUIRED", "Thiếu định danh người dùng.")
    owner_id = normalize_identifier(x_user_id, field_name="user")
    classroom_id = (
        normalize_identifier(x_classroom_id, field_name="classroom")
        if x_classroom_id is not None
        else None
    )
    return UserContext(owner_id, safe_user_key(owner_id), classroom_id)


def get_gemini_service(request: Request) -> Any:
    service = request.app.state.gemini_service
    if service is None:
        raise ServiceError(
            503,
            "GEMINI_NOT_CONFIGURED",
            "Gemini chưa được cấu hình cho dịch vụ này.",
        )
    return service


def get_system_indexing_service(request: Request) -> Any:
    return request.app.state.system_indexing_service


def get_vector_store(request: Request) -> Any:
    return request.app.state.vector_store


def get_retrieval_service(request: Request) -> Any:
    return request.app.state.retrieval_service


def get_rag_service(request: Request) -> Any:
    return request.app.state.rag_service


def get_rag_pipeline_service(request: Request) -> Any:
    return request.app.state.rag_pipeline_service


def validate_debug_access(request: Request, requested: bool) -> None:
    if not requested:
        return
    expected = request.app.state.settings.rag_debug_api_key
    provided = request.headers.get("X-Debug-RAG-Key", "")
    if not expected or not secrets.compare_digest(provided, expected):
        raise ServiceError(403, "RAG_DEBUG_FORBIDDEN", "Không có quyền xem dữ liệu debug RAG.")


def get_user_document_service(request: Request) -> Any:
    return request.app.state.user_document_service


def get_user_rag_service(request: Request) -> Any:
    return request.app.state.user_rag_service
