"""Application error types and the global error-envelope handlers.

Every error response has the shape documented in docs/API_CONVENTIONS.md::

    {"error": {"code": "...", "message": "...", "details": [...], "request_id": "..."}}
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger
from app.core.request_context import REQUEST_ID_HEADER, get_request_id
from app.schemas.common import ErrorBody, ErrorDetail, ErrorResponse

logger = get_logger(__name__)


class AppError(Exception):
    """Base class for expected, user-presentable errors."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "bad_request"
    message: str = "คำขอไม่ถูกต้อง"

    def __init__(
        self,
        message: str | None = None,
        *,
        details: list[ErrorDetail] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.message = message or self.message
        self.details = details or []
        self.headers = headers
        super().__init__(self.message)


class UnauthenticatedError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "unauthenticated"
    message = "กรุณาเข้าสู่ระบบ"


class PermissionDeniedError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "permission_denied"
    message = "คุณไม่มีสิทธิ์ดำเนินการนี้"


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"
    message = "ไม่พบข้อมูลที่ต้องการ"


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"
    message = "ข้อมูลขัดแย้งกับข้อมูลที่มีอยู่"


class ValidationFailedError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "validation_error"
    message = "ข้อมูลไม่ถูกต้อง"


class RateLimitedError(AppError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "rate_limited"
    message = "มีคำขอมากเกินไป กรุณาลองใหม่ภายหลัง"


class ServiceUnavailableError(AppError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "service_unavailable"
    message = "บริการไม่พร้อมใช้งานชั่วคราว"


class AINotConfiguredError(ServiceUnavailableError):
    code = "ai_not_configured"
    message = "ยังไม่ได้ตั้งค่าผู้ให้บริการ AI กรุณาติดต่อผู้ดูแลระบบ"


_HTTP_STATUS_CODES: dict[int, tuple[str, str]] = {
    400: ("bad_request", "คำขอไม่ถูกต้อง"),
    401: ("unauthenticated", "กรุณาเข้าสู่ระบบ"),
    403: ("permission_denied", "คุณไม่มีสิทธิ์ดำเนินการนี้"),
    404: ("not_found", "ไม่พบข้อมูลที่ต้องการ"),
    405: ("method_not_allowed", "ไม่รองรับวิธีการเรียกนี้"),
    409: ("conflict", "ข้อมูลขัดแย้งกับข้อมูลที่มีอยู่"),
    413: ("payload_too_large", "ไฟล์หรือข้อมูลมีขนาดใหญ่เกินกำหนด"),
    415: ("unsupported_media_type", "ไม่รองรับประเภทไฟล์นี้"),
    429: ("rate_limited", "มีคำขอมากเกินไป กรุณาลองใหม่ภายหลัง"),
}


def _envelope(
    status_code: int,
    code: str,
    message: str,
    details: list[ErrorDetail] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    request_id = get_request_id()
    body = ErrorResponse(
        error=ErrorBody(
            code=code,
            message=message,
            details=details or [],
            request_id=request_id,
        )
    )
    response_headers = dict(headers or {})
    if request_id:
        # Also set here because 500 responses bypass the request-context middleware.
        response_headers.setdefault(REQUEST_ID_HEADER, request_id)
    return JSONResponse(
        status_code=status_code, content=body.model_dump(), headers=response_headers
    )


def _field_path(loc: tuple[Any, ...] | list[Any]) -> str:
    # Drop the leading "body"/"query"/"path" marker for readability.
    parts = [str(p) for p in loc]
    if parts and parts[0] in {"body", "query", "path", "header", "cookie"}:
        parts = parts[1:]
    return ".".join(parts)


def error_response(exc: AppError) -> JSONResponse:
    """Render an ``AppError`` as the standard envelope (for handlers that add headers/cookies)."""
    return _envelope(exc.status_code, exc.code, exc.message, exc.details, exc.headers)


async def _app_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)  # noqa: S101 - narrowed by registration
    return error_response(exc)


async def _validation_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)  # noqa: S101
    details = [
        ErrorDetail(field=_field_path(err.get("loc", ())), message=str(err.get("msg", "")))
        for err in exc.errors()
    ]
    return _envelope(
        status.HTTP_422_UNPROCESSABLE_CONTENT, "validation_error", "ข้อมูลไม่ถูกต้อง", details
    )


async def _http_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)  # noqa: S101
    code, message = _HTTP_STATUS_CODES.get(exc.status_code, ("error", "เกิดข้อผิดพลาด"))
    return _envelope(exc.status_code, code, message, headers=getattr(exc, "headers", None))


async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(
        "unhandled_exception",
        path=request.url.path,
        method=request.method,
        error_type=type(exc).__name__,
    )
    return _envelope(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "internal_error",
        "เกิดข้อผิดพลาดภายในระบบ กรุณาลองใหม่อีกครั้ง",
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(Exception, _unhandled_exception_handler)
