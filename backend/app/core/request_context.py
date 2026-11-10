"""Per-request context (request ID) shared by middleware, logging and error handlers."""

from __future__ import annotations

import re
import secrets
from contextvars import ContextVar

REQUEST_ID_HEADER = "X-Request-ID"
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{8,64}$")

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


def new_request_id() -> str:
    return secrets.token_hex(8)


def sanitize_request_id(candidate: str | None) -> str:
    """Accept a client-supplied request ID only if it is well-formed; otherwise generate one."""
    if candidate and _REQUEST_ID_PATTERN.fullmatch(candidate):
        return candidate
    return new_request_id()


def set_request_id(value: str) -> None:
    _request_id.set(value)


def get_request_id() -> str | None:
    return _request_id.get()
