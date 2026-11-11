"""ASGI middleware: request context/access logging and baseline security headers."""

from __future__ import annotations

import time

import structlog
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging import get_logger
from app.core.request_context import REQUEST_ID_HEADER, sanitize_request_id, set_request_id

logger = get_logger("app.request")

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Cross-Origin-Opener-Policy": "same-origin",
}

# Health probes are polled frequently; keep them out of the access log at INFO.
_QUIET_PATHS = frozenset({"/api/v1/health/live"})


class RequestContextMiddleware:
    """Assigns a request ID, binds it to every log line, and writes one access-log entry."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = None
        for key, value in scope.get("headers", []):
            if key == b"x-request-id":
                incoming = value.decode("latin-1")
                break
        request_id = sanitize_request_id(incoming)
        set_request_id(request_id)
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        start = time.perf_counter()
        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = MutableHeaders(scope=message)
                if REQUEST_ID_HEADER not in headers:
                    headers.append(REQUEST_ID_HEADER, request_id)
                for name, value in _SECURITY_HEADERS.items():
                    if name not in headers:
                        headers.append(name, value)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            path = scope.get("path", "")
            log = logger.debug if path in _QUIET_PATHS else logger.info
            log(
                "http_request",
                method=scope.get("method"),
                path=path,
                status_code=status_code,
                duration_ms=duration_ms,
            )


class UploadSizeLimitMiddleware:
    """Rejects oversized uploads from the ``Content-Length`` header, before the multipart body
    is read and spooled. Upload routes also re-check the real size while hashing; Nginx adds
    ``client_max_body_size`` in front (docs/SECURITY.md §4)."""

    # Multipart framing and form fields on top of the file itself.
    OVERHEAD_BYTES = 1024 * 1024

    def __init__(self, app: ASGIApp, *, max_bytes: int, path_prefix: str) -> None:
        self.app = app
        self.limit = max_bytes + self.OVERHEAD_BYTES
        self.path_prefix = path_prefix

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] == "http"
            and scope["method"] in {"POST", "PUT"}
            and scope["path"].startswith(self.path_prefix)
        ):
            from app.core.errors import AppError, error_response

            headers = dict(scope["headers"])
            raw_length = headers.get(b"content-length")
            error: AppError | None = None
            if raw_length is None:
                if headers.get(b"transfer-encoding"):
                    error = AppError("ต้องระบุขนาดของไฟล์ที่อัปโหลด")
                    error.status_code = 411
                    error.code = "length_required"
            elif not raw_length.isdigit() or int(raw_length) > self.limit:
                error = AppError(
                    f"ไฟล์มีขนาดใหญ่เกิน {(self.limit - self.OVERHEAD_BYTES) // (1024 * 1024)} MB"
                )
                error.status_code = 413
                error.code = "file_too_large"
            if error is not None:
                await error_response(error)(scope, receive, send)
                return
        await self.app(scope, receive, send)
