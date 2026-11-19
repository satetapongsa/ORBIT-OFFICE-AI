"""Self-service sign-up with e-mail confirmation (ADR-057).

1. ``register`` validates the company domain and password, stores a *pending* registration
   (password already hashed, token stored only as SHA-256) and e-mails a single-use link.
   No ``users`` row exists yet, so an unconfirmed sign-up cannot block the real owner of the
   address, and the answer is the same whether or not the address already has an account.
2. ``verify_email`` consumes the link, creates the account with the EMPLOYEE role only and
   signs the user in.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError, RateLimitedError, ValidationFailedError
from app.core.notifications import PasswordResetNotifier
from app.core.permissions import SystemRole
from app.core.principal import RequestMeta
from app.core.rate_limit import RateLimiter
from app.core.security import hash_password, hash_token, new_opaque_token, utcnow
from app.models.auth import PendingRegistration
from app.models.identity import EmploymentStatus, User, UserRole
from app.repositories import roles as role_repo
from app.repositories import users as user_repo
from app.schemas.common import ErrorDetail
from app.services import audit, notifications
from app.services.audit import AuditAction
from app.services.auth import LoginResult, _email_key, _issue_tokens
from app.services.passwords import validate_new_password

REGISTER_ACCEPTED = (
    "หากอีเมลนี้สมัครได้ เราได้ส่งลิงก์ยืนยันไปที่อีเมลแล้ว กรุณาเปิดอีเมลเพื่อยืนยันภายในเวลาที่กำหนด "
    "(หากมีบัญชีอยู่แล้ว ให้เข้าสู่ระบบหรือใช้เมนูลืมรหัสผ่าน)"
)


class RegistrationDisabledError(AppError):
    status_code = 403
    code = "registration_disabled"
    message = "ระบบยังไม่เปิดให้สมัครสมาชิกเอง กรุณาติดต่อฝ่ายบุคคลหรือผู้ดูแลระบบ"


class InvalidVerificationTokenError(AppError):
    status_code = 400
    code = "invalid_verification_token"
    message = "ลิงก์ยืนยันอีเมลไม่ถูกต้อง ถูกใช้ไปแล้ว หรือหมดอายุ กรุณาสมัครใหม่อีกครั้ง"


def _domain_allowed(settings: Settings, email: str) -> bool:
    domain = email.rsplit("@", 1)[-1].lower()
    return domain in settings.self_registration_domains


async def _new_employee_code(session: AsyncSession) -> str:
    for _ in range(10):
        code = f"SU-{secrets.token_hex(4).upper()}"
        if not await user_repo.employee_code_taken(session, code):
            return code
    raise RuntimeError("could not allocate a unique employee code")  # pragma: no cover


async def register(
    session: AsyncSession,
    settings: Settings,
    notifier: PasswordResetNotifier,
    limiter: RateLimiter,
    *,
    email: str,
    first_name: str,
    last_name: str,
    password: str,
    meta: RequestMeta,
) -> None:
    if not settings.self_registration_enabled:
        raise RegistrationDisabledError()
    email = email.strip().lower()
    if not _domain_allowed(settings, email):
        domains = ", ".join(f"@{d}" for d in settings.self_registration_domains)
        raise ValidationFailedError(
            details=[ErrorDetail(field="email", message=f"ต้องใช้อีเมลบริษัท ({domains})")]
        )
    validate_new_password(settings, password, email=email, field="password")

    window = settings.login_rate_limit_window_seconds
    email_key = f"register:email:{_email_key(email)}"
    checks = [await limiter.hit(email_key, limit=5, window_seconds=window)]
    if meta.ip_address:
        checks.append(
            await limiter.hit(f"register:ip:{meta.ip_address}", limit=20, window_seconds=window)
        )
    blocked = [c for c in checks if not c.allowed]
    if blocked:
        retry = max(c.retry_after_seconds for c in blocked)
        raise RateLimitedError(headers={"Retry-After": str(retry)})

    # Hash first so existing and new addresses take the same time (no timing enumeration).
    password_hash = hash_password(password)
    # Same answer for existing accounts: nothing is created or sent (no enumeration).
    if await user_repo.email_taken(session, email):
        return

    now = utcnow()
    token = new_opaque_token()
    await session.execute(delete(PendingRegistration).where(PendingRegistration.email == email))
    session.add(
        PendingRegistration(
            email=email,
            first_name=first_name,
            last_name=last_name,
            password_hash=password_hash,
            token_hash=hash_token(token),
            expires_at=now + timedelta(hours=settings.email_verification_ttl_hours),
        )
    )
    audit.record(
        session,
        AuditAction.REGISTRATION_REQUESTED,
        actor_id=None,
        meta=meta,
        details={"email_hash": _email_key(email)},
    )
    await session.commit()
    verify_url = f"{settings.frontend_base_url.rstrip('/')}/verify-email?token={token}"
    await notifier.send_email_verification(
        email=email, display_name=f"{first_name} {last_name}", verify_url=verify_url
    )


async def verify_email(
    session: AsyncSession, settings: Settings, *, token: str, meta: RequestMeta
) -> LoginResult:
    if not settings.self_registration_enabled:
        raise RegistrationDisabledError()
    now = utcnow()
    pending = await session.scalar(
        select(PendingRegistration)
        .where(PendingRegistration.token_hash == hash_token(token))
        .with_for_update()
    )
    if pending is None or pending.expires_at <= now:
        raise InvalidVerificationTokenError()
    email = pending.email
    if not _domain_allowed(settings, email) or await user_repo.email_taken(session, email):
        # The domain was removed meanwhile, or HR created the account in the meantime.
        await session.delete(pending)
        await session.commit()
        raise InvalidVerificationTokenError()

    role = (await role_repo.get_by_codes(session, [SystemRole.EMPLOYEE.value]))[0]
    user = User(
        employee_code=await _new_employee_code(session),
        email=email,
        password_hash=pending.password_hash,
        first_name=pending.first_name,
        last_name=pending.last_name,
        display_name=f"{pending.first_name} {pending.last_name}",
        employment_status=EmploymentStatus.ACTIVE.value,
        is_active=True,
        password_changed_at=now.replace(microsecond=0),
        last_login_at=now,
    )
    user.role_links = [UserRole(role_id=role.id, assigned_by=None)]
    session.add(user)
    await session.delete(pending)
    await session.flush()
    audit.record(
        session,
        AuditAction.USER_REGISTERED,
        actor_id=user.id,
        meta=meta,
        entity_type="user",
        entity_id=user.id,
        details={"email": email, "roles": [SystemRole.EMPLOYEE.value]},
    )
    audit.record(
        session,
        AuditAction.LOGIN,
        actor_id=user.id,
        meta=meta,
        entity_type="user",
        entity_id=user.id,
    )
    notifications.welcome(session, user.id)
    tokens = _issue_tokens(
        session,
        settings,
        user=user,
        family_id=uuid.uuid4(),
        family_expires_at=now + timedelta(days=settings.refresh_token_absolute_days),
        meta=meta,
        now=now,
    )
    await session.commit()
    return LoginResult(user=user, tokens=tokens)
