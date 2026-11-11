"""Shared FastAPI dependencies: settings, request metadata, authentication and permissions."""

from __future__ import annotations

import ipaddress
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.db import get_db
from app.core.errors import AppError, PermissionDeniedError, UnauthenticatedError
from app.core.notifications import PasswordResetNotifier
from app.core.principal import CurrentUser, RequestMeta
from app.core.rate_limit import RateLimiter
from app.core.request_context import get_request_id
from app.core.security import (
    ACCESS_COOKIE,
    CSRF_COOKIE,
    CSRF_HEADER,
    InvalidTokenError,
    decode_access_token,
    tokens_match,
    utcnow,
)
from app.repositories import sessions as session_repo
from app.repositories import users as user_repo
from app.services.documents.service import DocumentProcessor, DocumentStorage

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


class CsrfFailedError(AppError):
    status_code = 403
    code = "csrf_failed"
    message = "คำขอไม่ผ่านการตรวจสอบความปลอดภัย กรุณารีเฟรชหน้าแล้วลองใหม่"


def get_app_settings(request: Request) -> Settings:
    """Settings the running app was created with (lets tests inject their own settings)."""
    settings: Settings = request.app.state.settings
    return settings


def get_rate_limiter(request: Request) -> RateLimiter:
    limiter: RateLimiter = request.app.state.rate_limiter
    return limiter


def get_reset_notifier(request: Request) -> PasswordResetNotifier:
    notifier: PasswordResetNotifier = request.app.state.reset_notifier
    return notifier


def _client_ip(request: Request) -> str | None:
    host = request.client.host if request.client else None
    try:
        return str(ipaddress.ip_address(host)) if host else None
    except ValueError:
        return None  # e.g. the TestClient's "testclient" host


def get_document_storage(request: Request) -> DocumentStorage:
    storage: DocumentStorage = request.app.state.document_storage
    return storage


def get_document_processor(request: Request) -> DocumentProcessor:
    processor: DocumentProcessor = request.app.state.document_processor
    return processor


def get_request_meta(request: Request) -> RequestMeta:
    return RequestMeta(
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_id=get_request_id(),
    )


def verify_csrf(request: Request) -> None:
    """Double-submit check for cookie-authenticated, state-changing requests."""
    if request.method in SAFE_METHODS:
        return
    if not tokens_match(request.cookies.get(CSRF_COOKIE), request.headers.get(CSRF_HEADER)):
        raise CsrfFailedError()


SettingsDep = Annotated[Settings, Depends(get_app_settings)]
DbDep = Annotated[AsyncSession, Depends(get_db)]
MetaDep = Annotated[RequestMeta, Depends(get_request_meta)]


async def get_current_user(request: Request, session: DbDep, settings: SettingsDep) -> CurrentUser:
    token: str | None = None
    via_cookie = False
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
    elif ACCESS_COOKIE in request.cookies:
        token = request.cookies[ACCESS_COOKIE]
        via_cookie = True
    if not token:
        raise UnauthenticatedError()

    try:
        claims = decode_access_token(settings, token)
    except InvalidTokenError:
        raise UnauthenticatedError("เซสชันหมดอายุ กรุณาเข้าสู่ระบบใหม่") from None

    user = await user_repo.get_by_id(session, claims.user_id)
    if user is None or not user.is_active:
        raise UnauthenticatedError()
    if user.password_changed_at and claims.issued_at < user.password_changed_at.replace(
        microsecond=0
    ):
        raise UnauthenticatedError("เซสชันหมดอายุ กรุณาเข้าสู่ระบบใหม่")
    if not await session_repo.family_is_active(session, claims.session_family_id, utcnow()):
        raise UnauthenticatedError("เซสชันหมดอายุ กรุณาเข้าสู่ระบบใหม่")

    if via_cookie:
        verify_csrf(request)

    permissions = await user_repo.permissions_for_user(session, user.id)
    return CurrentUser(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        department_id=user.department_id,
        role_ids=frozenset(link.role_id for link in user.role_links),
        role_codes=frozenset(link.role.code for link in user.role_links),
        permissions=frozenset(permissions),
        session_family_id=claims.session_family_id,
    )


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]


def require_permissions(*codes: str) -> Callable[[CurrentUser], Awaitable[CurrentUser]]:
    """Route guard: the user must hold **all** listed permissions."""

    async def dependency(user: CurrentUserDep) -> CurrentUser:
        if not user.has_all(codes):
            raise PermissionDeniedError()
        return user

    return dependency
