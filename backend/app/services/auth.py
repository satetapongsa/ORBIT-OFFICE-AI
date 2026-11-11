"""Authentication: login, refresh-token rotation, logout, password change and reset."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError, RateLimitedError, UnauthenticatedError
from app.core.logging import get_logger
from app.core.notifications import PasswordResetNotifier
from app.core.principal import CurrentUser, RequestMeta
from app.core.rate_limit import RateLimiter
from app.core.security import (
    create_access_token,
    hash_password,
    hash_token,
    new_opaque_token,
    password_needs_rehash,
    utcnow,
    verify_password,
)
from app.models.auth import PasswordResetToken, UserSession
from app.models.identity import User
from app.repositories import sessions as session_repo
from app.repositories import users as user_repo
from app.services import audit, notifications
from app.services.audit import AuditAction
from app.services.passwords import validate_new_password

logger = get_logger(__name__)

INVALID_CREDENTIALS = "อีเมลหรือรหัสผ่านไม่ถูกต้อง"
SESSION_EXPIRED = "เซสชันหมดอายุ กรุณาเข้าสู่ระบบใหม่"


class SessionRefreshConflictError(AppError):
    """A just-rotated refresh token was re-sent (e.g. two tabs refreshing at once)."""

    status_code = 401
    code = "session_refresh_conflict"
    message = "เซสชันถูกต่ออายุแล้วจากหน้าต่างอื่น กรุณาลองใหม่"


class InvalidResetTokenError(AppError):
    status_code = 400
    code = "invalid_reset_token"
    message = "ลิงก์ตั้งรหัสผ่านใหม่ไม่ถูกต้องหรือหมดอายุแล้ว"


@dataclass(frozen=True, slots=True)
class IssuedTokens:
    access_token: str
    access_expires_at: datetime
    refresh_token: str
    refresh_expires_at: datetime
    csrf_token: str


@dataclass(frozen=True, slots=True)
class LoginResult:
    user: User
    tokens: IssuedTokens


def _email_key(email: str) -> str:
    return hashlib.sha256(email.strip().lower().encode()).hexdigest()[:32]


def _issue_tokens(
    session: AsyncSession,
    settings: Settings,
    *,
    user: User,
    family_id: uuid.UUID,
    family_expires_at: datetime,
    meta: RequestMeta,
    now: datetime,
) -> IssuedTokens:
    refresh_token = new_opaque_token()
    refresh_expires_at = min(
        now + timedelta(days=settings.refresh_token_ttl_days), family_expires_at
    )
    session.add(
        UserSession(
            user_id=user.id,
            family_id=family_id,
            refresh_token_hash=hash_token(refresh_token),
            expires_at=refresh_expires_at,
            family_expires_at=family_expires_at,
            user_agent=(meta.user_agent or "")[:500] or None,
            ip_address=meta.ip_address,
        )
    )
    access_token, access_expires_at = create_access_token(
        settings, user_id=user.id, session_family_id=family_id
    )
    return IssuedTokens(
        access_token=access_token,
        access_expires_at=access_expires_at,
        refresh_token=refresh_token,
        refresh_expires_at=refresh_expires_at,
        csrf_token=new_opaque_token(),
    )


async def login(
    session: AsyncSession,
    settings: Settings,
    limiter: RateLimiter,
    *,
    email: str,
    password: str,
    meta: RequestMeta,
) -> LoginResult:
    window = settings.login_rate_limit_window_seconds
    limit = settings.login_rate_limit_attempts
    email_key = f"login:email:{_email_key(email)}"
    checks = [await limiter.hit(email_key, limit=limit, window_seconds=window)]
    if meta.ip_address:
        # The per-IP budget is larger: several employees may share one office IP.
        checks.append(
            await limiter.hit(f"login:ip:{meta.ip_address}", limit=limit * 5, window_seconds=window)
        )
    blocked = [c for c in checks if not c.allowed]
    if blocked:
        audit.record(
            session,
            AuditAction.LOGIN_RATE_LIMITED,
            actor_id=None,
            meta=meta,
            details={"email_hash": _email_key(email)},
        )
        await session.commit()
        retry = max(c.retry_after_seconds for c in blocked)
        raise RateLimitedError(headers={"Retry-After": str(retry)})

    user = await user_repo.get_by_email(session, email)
    password_ok = verify_password(password, user.password_hash if user else None)
    if user is None or not password_ok or not user.is_active:
        reason = (
            "unknown_email" if user is None else ("bad_password" if not password_ok else "inactive")
        )
        audit.record(
            session,
            AuditAction.LOGIN_FAILED,
            actor_id=user.id if user else None,
            meta=meta,
            entity_type="user" if user else None,
            entity_id=user.id if user else None,
            details={"reason": reason, "email_hash": _email_key(email)},
        )
        await session.commit()
        raise UnauthenticatedError(INVALID_CREDENTIALS)

    now = utcnow()
    if user.password_hash and password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    user.last_login_at = now
    tokens = _issue_tokens(
        session,
        settings,
        user=user,
        family_id=uuid.uuid4(),
        family_expires_at=now + timedelta(days=settings.refresh_token_absolute_days),
        meta=meta,
        now=now,
    )
    audit.record(
        session,
        AuditAction.LOGIN,
        actor_id=user.id,
        meta=meta,
        entity_type="user",
        entity_id=user.id,
    )
    await session.commit()
    await limiter.reset(email_key)
    return LoginResult(user=user, tokens=tokens)


async def refresh(
    session: AsyncSession, settings: Settings, *, refresh_token: str, meta: RequestMeta
) -> LoginResult:
    now = utcnow()
    current = await session_repo.get_by_token_hash_for_update(session, hash_token(refresh_token))
    if current is None or current.revoked_at is not None:
        raise UnauthenticatedError(SESSION_EXPIRED)

    if current.rotated_at is not None:
        age = (now - current.rotated_at).total_seconds()
        if age <= settings.refresh_reuse_grace_seconds:
            raise SessionRefreshConflictError()
        # A long-rotated token came back: treat as theft and kill the whole login.
        await session_repo.revoke_family(session, current.family_id, now, "refresh_reuse")
        audit.record(
            session,
            AuditAction.REFRESH_REUSE_DETECTED,
            actor_id=current.user_id,
            meta=meta,
            entity_type="user",
            entity_id=current.user_id,
            details={"family_id": str(current.family_id)},
        )
        notifications.suspicious_session(session, current.user_id)
        await session.commit()
        logger.warning("refresh_token_reuse_detected", user_id=str(current.user_id))
        raise UnauthenticatedError(SESSION_EXPIRED)

    if current.expires_at <= now or current.family_expires_at <= now:
        await session_repo.revoke_family(session, current.family_id, now, "expired")
        await session.commit()
        raise UnauthenticatedError(SESSION_EXPIRED)

    user = await user_repo.get_by_id(session, current.user_id)
    if user is None or not user.is_active:
        await session_repo.revoke_family(session, current.family_id, now, "user_inactive")
        await session.commit()
        raise UnauthenticatedError(SESSION_EXPIRED)

    current.rotated_at = now
    tokens = _issue_tokens(
        session,
        settings,
        user=user,
        family_id=current.family_id,
        family_expires_at=current.family_expires_at,
        meta=meta,
        now=now,
    )
    await session.commit()
    return LoginResult(user=user, tokens=tokens)


async def logout(
    session: AsyncSession,
    *,
    refresh_token: str | None,
    family_id: uuid.UUID | None,
    actor_id: uuid.UUID | None,
    meta: RequestMeta,
) -> None:
    now = utcnow()
    target_family = family_id
    target_user = actor_id
    if refresh_token:
        row = await session_repo.get_by_token_hash_for_update(session, hash_token(refresh_token))
        if row is not None:
            target_family = row.family_id
            target_user = row.user_id
    if target_family is not None:
        await session_repo.revoke_family(session, target_family, now, "logout")
    if target_user is not None:
        audit.record(
            session,
            AuditAction.LOGOUT,
            actor_id=target_user,
            meta=meta,
            entity_type="user",
            entity_id=target_user,
        )
    await session.commit()


async def change_password(
    session: AsyncSession,
    settings: Settings,
    *,
    principal: CurrentUser,
    current_password: str,
    new_password: str,
    meta: RequestMeta,
) -> LoginResult:
    user = await user_repo.get_by_id(session, principal.id)
    if user is None or not verify_password(current_password, user.password_hash):
        raise UnauthenticatedError("รหัสผ่านปัจจุบันไม่ถูกต้อง")
    validate_new_password(settings, new_password, email=user.email, field="new_password")
    now = utcnow()
    user.password_hash = hash_password(new_password)
    user.password_changed_at = now.replace(microsecond=0)
    # Sign out every other device; keep (and re-issue tokens for) the current login.
    await session_repo.revoke_all_for_user(
        session, user.id, now, "password_changed", except_family=principal.session_family_id
    )
    family_id = principal.session_family_id or uuid.uuid4()
    await session_repo.revoke_family(session, family_id, now, "password_changed")
    tokens = _issue_tokens(
        session,
        settings,
        user=user,
        family_id=family_id,
        family_expires_at=now + timedelta(days=settings.refresh_token_absolute_days),
        meta=meta,
        now=now,
    )
    audit.record(
        session,
        AuditAction.PASSWORD_CHANGED,
        actor_id=user.id,
        meta=meta,
        entity_type="user",
        entity_id=user.id,
    )
    notifications.password_changed(session, user.id, via_reset=False)
    await session.commit()
    return LoginResult(user=user, tokens=tokens)


async def request_password_reset(
    session: AsyncSession,
    settings: Settings,
    notifier: PasswordResetNotifier,
    limiter: RateLimiter,
    *,
    email: str,
    meta: RequestMeta,
) -> None:
    """Always succeeds from the caller's point of view (no account enumeration)."""
    check = await limiter.hit(
        f"reset:email:{_email_key(email)}",
        limit=5,
        window_seconds=settings.login_rate_limit_window_seconds,
    )
    user = await user_repo.get_by_email(session, email)
    if not check.allowed or user is None or not user.is_active:
        return
    now = utcnow()
    await session_repo.invalidate_reset_tokens(session, user.id, now)
    token = new_opaque_token()
    session.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=hash_token(token),
            expires_at=now + timedelta(minutes=settings.password_reset_ttl_minutes),
        )
    )
    audit.record(
        session,
        AuditAction.PASSWORD_RESET_REQUESTED,
        actor_id=user.id,
        meta=meta,
        entity_type="user",
        entity_id=user.id,
    )
    await session.commit()
    reset_url = f"{settings.frontend_base_url.rstrip('/')}/reset-password?token={token}"
    await notifier.send_password_reset(
        email=user.email, display_name=user.display_name, reset_url=reset_url
    )


async def confirm_password_reset(
    session: AsyncSession,
    settings: Settings,
    *,
    token: str,
    new_password: str,
    meta: RequestMeta,
) -> None:
    now = utcnow()
    row = await session_repo.get_reset_token_for_update(session, hash_token(token))
    if row is None or row.used_at is not None or row.expires_at <= now:
        raise InvalidResetTokenError()
    user = await user_repo.get_by_id(session, row.user_id)
    if user is None or not user.is_active:
        raise InvalidResetTokenError()
    validate_new_password(settings, new_password, email=user.email, field="new_password")
    user.password_hash = hash_password(new_password)
    user.password_changed_at = now.replace(microsecond=0)
    row.used_at = now
    await session_repo.invalidate_reset_tokens(session, user.id, now)
    await session_repo.revoke_all_for_user(session, user.id, now, "password_reset")
    audit.record(
        session,
        AuditAction.PASSWORD_RESET_COMPLETED,
        actor_id=user.id,
        meta=meta,
        entity_type="user",
        entity_id=user.id,
    )
    notifications.password_changed(session, user.id, via_reset=True)
    await session.commit()
