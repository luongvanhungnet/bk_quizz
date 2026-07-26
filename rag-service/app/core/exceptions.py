from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class ServiceError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        details: list[dict[str, Any]] | None = None,
        retryable: bool = False,
        retry_after_seconds: int | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details
        self.retryable = retryable
        self.retry_after_seconds = retry_after_seconds


def _error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    details: list[dict[str, Any]] | None = None,
    retryable: bool = False,
    retry_after_seconds: int | None = None,
) -> JSONResponse:
    if "rag/" in request.url.path or "/evaluation/" in request.url.path:
        from app.utils.rag_logging import log_rag_error

        settings = request.app.state.settings
        log_rag_error(
            request_id=getattr(request.state, "trace_id", "unknown"),
            user_id=request.headers.get("X-User-Id"),
            endpoint=request.url.path,
            error_code=code,
            secret=settings.spring_boot_internal_api_key,
        )
    trace_id = getattr(request.state, "trace_id", "unknown")
    if request.url.path.startswith("/api/v2/"):
        body: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "requestId": trace_id,
            "status": status_code,
            "code": code,
            "message": message,
            "retryable": retryable,
            "retryAfterSeconds": retry_after_seconds,
            "details": details or [],
        }
        headers = {"Retry-After": str(retry_after_seconds)} if retry_after_seconds else None
        return JSONResponse(status_code=status_code, content=body, headers=headers)
    body = {
        "status": "error",
        "code": code,
        "message": message,
        "traceId": trace_id,
    }
    if details:
        body["details"] = details
    return JSONResponse(status_code=status_code, content=body)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(
        request: Request, exception: StarletteHTTPException
    ) -> JSONResponse:
        if (
            exception.status_code == 400
            and exception.detail == "There was an error parsing the body"
        ):
            return _error_response(
                request,
                status_code=400,
                code="INVALID_JSON_BODY",
                message="Nội dung JSON phải hợp lệ và được mã hóa UTF-8.",
            )
        messages = {
            404: "Không tìm thấy endpoint được yêu cầu.",
            405: "Phương thức HTTP không được hỗ trợ.",
        }
        return _error_response(
            request,
            status_code=exception.status_code,
            code="HTTP_ERROR",
            message=messages.get(
                exception.status_code, "Yêu cầu HTTP không thể xử lý."
            ),
        )

    @app.exception_handler(ServiceError)
    async def handle_service_error(
        request: Request, exception: ServiceError
    ) -> JSONResponse:
        return _error_response(
            request,
            status_code=exception.status_code,
            code=exception.code,
            message=exception.message,
            details=exception.details,
            retryable=exception.retryable,
            retry_after_seconds=exception.retry_after_seconds,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exception: RequestValidationError
    ) -> JSONResponse:
        if any(error["type"] == "json_invalid" for error in exception.errors()):
            return _error_response(
                request,
                status_code=400,
                code="INVALID_JSON_BODY",
                message="Nội dung JSON phải hợp lệ và được mã hóa UTF-8.",
            )
        if any(
            error["type"] == "quiz_batch_too_large"
            for error in exception.errors()
        ):
            return _error_response(
                request,
                status_code=422,
                code="QUIZ_BATCH_TOO_LARGE",
                message="Mỗi lần gọi Gemini chỉ được tạo tối đa 4 câu hỏi.",
            )
        details = [
            {
                "field": ".".join(str(part) for part in error["loc"] if part != "body"),
                "message": error["msg"],
                "type": error["type"],
            }
            for error in exception.errors()
        ]
        return _error_response(
            request,
            status_code=422,
            code="VALIDATION_ERROR",
            message="Dữ liệu gửi lên không hợp lệ.",
            details=details,
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(
        request: Request, exception: Exception
    ) -> JSONResponse:
        request.app.state.logger.error(
            "Unhandled error trace_id=%s type=%s",
            getattr(request.state, "trace_id", "unknown"),
            type(exception).__name__,
        )
        return _error_response(
            request,
            status_code=500,
            code="INTERNAL_ERROR",
            message="Dịch vụ đang gặp sự cố. Vui lòng thử lại sau.",
        )
