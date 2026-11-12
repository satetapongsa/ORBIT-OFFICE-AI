"""ASGI middleware: request context/access logging and baseline security headers."""

from __future__ import annotations

import hmac
import ipaddress
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
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
}
# API responses are data, never pages: nothing may load, run or frame them. The interactive
# API docs (development only) load Swagger UI from a CDN, so they are left out.
_API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
_DOCS_PREFIXES = ("/api/docs", "/api/redoc", "/api/openapi.json")

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
                path = scope.get("path", "")
                if "Content-Security-Policy" not in headers and not path.startswith(_DOCS_PREFIXES):
                    headers.append("Content-Security-Policy", _API_CSP)
                # API data is per user: no shared cache (CDN, proxy) may keep a copy.
                if "Cache-Control" not in headers:
                    headers.append("Cache-Control", "no-store")
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


PROXY_SECRET_HEADER = b"x-orbit-proxy-secret"
# Set by Vercel's edge to the visitor's IP; clients cannot supply their own (ADR-055).
_PROXY_CLIENT_IP_HEADER = b"x-vercel-forwarded-for"
_PROXY_EXEMPT_PATHS = frozenset({"/api/v1/health/live"})  # the host platform's probe


class TrustedProxyMiddleware:
    """Accepts API requests only through the front end's proxy (ADR-055).

    The proxy adds a shared secret header; requests without it get 403, so the API cannot be
    called directly to dodge the per-IP login limit with a forged ``X-Forwarded-For``. On
    accepted requests the secret is removed from the headers (it never reaches handlers or
    logs) and the client address becomes the visitor IP reported by the proxy."""

    def __init__(self, app: ASGIApp, *, secret: str) -> None:
        self.app = app
        self.secret = secret.encode()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path", "") in _PROXY_EXEMPT_PATHS:
            await self.app(scope, receive, send)
            return

        supplied = b""
        client_ip: str | None = None
        kept: list[tuple[bytes, bytes]] = []
        for key, value in scope.get("headers", []):
            if key == PROXY_SECRET_HEADER:
                supplied = value
                continue
            if key == _PROXY_CLIENT_IP_HEADER and client_ip is None:
                client_ip = _first_ip(value)
            kept.append((key, value))

        if not hmac.compare_digest(supplied, self.secret):
            from app.core.errors import AppError, error_response

            error = AppError("กรุณาใช้งานผ่านหน้าเว็บของระบบ")
            error.status_code = 403
            error.code = "proxy_required"
            await error_response(error)(scope, receive, send)
            return

        scope = dict(scope)
        scope["headers"] = kept
        if client_ip is not None:
            port = scope["client"][1] if scope.get("client") else 0
            scope["client"] = (client_ip, port)
        await self.app(scope, receive, send)


def _first_ip(value: bytes) -> str | None:
    first = value.decode("latin-1").split(",")[0].strip()
    try:
        return str(ipaddress.ip_address(first))
    except ValueError:
        return None


class UploadSizeLimitMiddleware:
    """Rejects oversized uploads from the ``Content-Length`` header, before the multipart body
    is read and spooled. Upload routes also re-check the real size while hashing; Nginx adds
    ``client_max_body_size`` in front (docs/SECURITY.md §4)."""

    # Multipart framing and form fields on top of the file itself.
    OVERHEAD_BYTES = 1024 * 1024

    def __init__(self, app: ASGIApp, *, max_bytes: int, path_prefixes: tuple[str, ...]) -> None:
        self.app = app
        self.limit = max_bytes + self.OVERHEAD_BYTES
        self.path_prefixes = path_prefixes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] == "http"
            and scope["method"] in {"POST", "PUT"}
            and scope["path"].startswith(self.path_prefixes)
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
