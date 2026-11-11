"""User management."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationFailedError,
)
from app.core.permissions import P, SystemRole
from app.core.principal import CurrentUser, RequestMeta
from app.core.security import hash_password, utcnow
from app.models.identity import Role, User, UserRole
from app.repositories import departments as department_repo
from app.repositories import roles as role_repo
from app.repositories import sessions as session_repo
from app.repositories import users as user_repo
from app.schemas.common import ErrorDetail
from app.schemas.identity import UserCreate, UserUpdate
from app.services import audit, notifications
from app.services.audit import AuditAction
from app.services.passwords import validate_new_password
from app.services.rbac import ensure_admin_remains, ensure_can_grant

DEFAULT_ROLE = SystemRole.EMPLOYEE.value


async def get_user(session: AsyncSession, user_id: uuid.UUID, *, reload: bool = False) -> User:
    user = await user_repo.get_by_id(session, user_id, reload=reload)
    if user is None:
        raise NotFoundError("ไม่พบผู้ใช้ที่ต้องการ")
    return user


async def _check_department(session: AsyncSession, department_id: uuid.UUID | None) -> None:
    if department_id and await department_repo.get_by_id(session, department_id) is None:
        raise ValidationFailedError(
            details=[ErrorDetail(field="department_id", message="ไม่พบแผนกนี้")]
        )


async def _resolve_roles(session: AsyncSession, codes: list[str]) -> list[Role]:
    roles = await role_repo.get_by_codes(session, codes)
    missing = sorted(set(codes) - {r.code for r in roles})
    if missing:
        raise ValidationFailedError(
            details=[
                ErrorDetail(field="role_codes", message=f"ไม่พบบทบาท {code}") for code in missing
            ]
        )
    return roles


async def create_user(
    session: AsyncSession,
    settings: Settings,
    actor: CurrentUser,
    data: UserCreate,
    meta: RequestMeta,
) -> User:
    if await user_repo.email_taken(session, data.email):
        raise ConflictError("อีเมลนี้ถูกใช้แล้ว")
    if await user_repo.employee_code_taken(session, data.employee_code):
        raise ConflictError("รหัสพนักงานนี้ถูกใช้แล้ว")
    await _check_department(session, data.department_id)

    role_codes = sorted(set(data.role_codes))
    roles = await _resolve_roles(session, role_codes)
    if role_codes != [DEFAULT_ROLE]:
        if not actor.has(P.ROLES_ASSIGN):
            raise PermissionDeniedError("ต้องมีสิทธิ์กำหนดบทบาทจึงจะเลือกบทบาทอื่นได้")
        ensure_can_grant(actor, {p.code for r in roles for p in r.permissions})

    if data.password is not None:
        validate_new_password(settings, data.password, email=data.email, field="password")

    user = User(
        employee_code=data.employee_code,
        email=data.email.strip().lower(),
        password_hash=hash_password(data.password) if data.password else None,
        first_name=data.first_name,
        last_name=data.last_name,
        display_name=data.display_name or f"{data.first_name} {data.last_name}",
        department_id=data.department_id,
        job_title=data.job_title,
        phone_work=data.phone_work,
        employment_status=data.employment_status.value,
        is_active=True,
        password_changed_at=utcnow().replace(microsecond=0) if data.password else None,
    )
    user.role_links = [UserRole(role_id=r.id, assigned_by=actor.id) for r in roles]
    session.add(user)
    await session.flush()
    audit.record(
        session,
        AuditAction.USER_CREATED,
        actor_id=actor.id,
        meta=meta,
        entity_type="user",
        entity_id=user.id,
        details={"email": user.email, "roles": role_codes},
    )
    notifications.welcome(session, user.id)
    await session.commit()
    return await get_user(session, user.id, reload=True)


async def update_user(
    session: AsyncSession,
    actor: CurrentUser,
    user_id: uuid.UUID,
    data: UserUpdate,
    meta: RequestMeta,
) -> User:
    user = await get_user(session, user_id)
    changes = data.model_dump(exclude_unset=True)
    if "email" in changes and changes["email"] is not None:
        changes["email"] = changes["email"].strip().lower()
        if await user_repo.email_taken(session, changes["email"], exclude_id=user.id):
            raise ConflictError("อีเมลนี้ถูกใช้แล้ว")
    if changes.get("employee_code") and await user_repo.employee_code_taken(
        session, changes["employee_code"], exclude_id=user.id
    ):
        raise ConflictError("รหัสพนักงานนี้ถูกใช้แล้ว")
    if "department_id" in changes:
        await _check_department(session, changes["department_id"])
    for field, value in changes.items():
        if value is None and field not in {"department_id", "job_title", "phone_work"}:
            continue
        setattr(user, field, value.value if hasattr(value, "value") else value)
    audit.record(
        session,
        AuditAction.USER_UPDATED,
        actor_id=actor.id,
        meta=meta,
        entity_type="user",
        entity_id=user.id,
        details={"fields": sorted(changes)},
    )
    if user.id != actor.id:
        notifications.account_updated(session, user.id, sorted(changes))
    await session.commit()
    return await get_user(session, user.id, reload=True)


async def set_active(
    session: AsyncSession,
    actor: CurrentUser,
    user_id: uuid.UUID,
    *,
    active: bool,
    meta: RequestMeta,
) -> User:
    user = await get_user(session, user_id)
    if not active:
        if user.id == actor.id:
            raise ConflictError("ไม่สามารถระงับบัญชีของตนเองได้")
        await ensure_admin_remains(session, losing_user_id=user.id)
        user.is_active = False
        await session_repo.revoke_all_for_user(session, user.id, utcnow(), "deactivated")
    elif not user.is_active:
        user.is_active = True
        notifications.account_reactivated(session, user.id)
    audit.record(
        session,
        AuditAction.USER_ACTIVATED if active else AuditAction.USER_DEACTIVATED,
        actor_id=actor.id,
        meta=meta,
        entity_type="user",
        entity_id=user.id,
    )
    await session.commit()
    return await get_user(session, user.id, reload=True)


async def set_roles(
    session: AsyncSession,
    actor: CurrentUser,
    user_id: uuid.UUID,
    role_codes: list[str],
    meta: RequestMeta,
) -> User:
    user = await get_user(session, user_id)
    new_roles = await _resolve_roles(session, sorted(set(role_codes)))
    old_ids = {link.role_id for link in user.role_links}
    new_ids = {r.id for r in new_roles}
    added = [r for r in new_roles if r.id not in old_ids]
    removed = [link.role for link in user.role_links if link.role_id not in new_ids]

    # Granting or revoking a role requires holding all of that role's permissions.
    ensure_can_grant(actor, {p.code for r in added + removed for p in r.permissions})
    if any(r.code == SystemRole.ADMIN.value for r in removed):
        await ensure_admin_remains(session, losing_user_id=user.id)

    user.role_links = [link for link in user.role_links if link.role_id in new_ids] + [
        UserRole(role_id=r.id, assigned_by=actor.id) for r in added
    ]
    audit.record(
        session,
        AuditAction.USER_ROLES_CHANGED,
        actor_id=actor.id,
        meta=meta,
        entity_type="user",
        entity_id=user.id,
        details={
            "added": sorted(r.code for r in added),
            "removed": sorted(r.code for r in removed),
        },
    )
    notifications.roles_changed(
        session,
        user.id,
        added=[r.name for r in added],
        removed=[r.name for r in removed],
    )
    await session.commit()
    return await get_user(session, user.id, reload=True)
