"""Role/permission management with privilege-escalation guards."""

from __future__ import annotations

import uuid
from collections.abc import Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationFailedError,
)
from app.core.permissions import ALL_PERMISSIONS, LOCKED_ROLES, SystemRole
from app.core.principal import CurrentUser, RequestMeta
from app.models.identity import Role
from app.repositories import roles as role_repo
from app.repositories import users as user_repo
from app.schemas.common import ErrorDetail
from app.schemas.identity import RoleCreate, RoleOut, RoleUpdate
from app.services import audit
from app.services.audit import AuditAction

KNOWN_PERMISSIONS = frozenset(p.value for p in ALL_PERMISSIONS)


def role_out(role: Role) -> RoleOut:
    return RoleOut(
        id=role.id,
        code=role.code,
        name=role.name,
        description=role.description,
        is_system=role.is_system,
        is_locked=role.code in LOCKED_ROLES,
        permissions=[p.code for p in role.permissions],
        created_at=role.created_at,
        updated_at=role.updated_at,
    )


def ensure_can_grant(actor: CurrentUser, permissions: Iterable[str]) -> None:
    """Nobody can grant (or take away) permissions they do not hold themselves."""
    missing = sorted(set(permissions) - actor.permissions)
    if missing:
        raise PermissionDeniedError(
            "ไม่สามารถกำหนดสิทธิ์ที่คุณเองไม่มีได้",
            details=[ErrorDetail(field="permissions", message=code) for code in missing],
        )


def _validate_codes(codes: Iterable[str]) -> set[str]:
    wanted = set(codes)
    unknown = sorted(wanted - KNOWN_PERMISSIONS)
    if unknown:
        raise ValidationFailedError(
            "ไม่รู้จักสิทธิ์บางรายการ",
            details=[ErrorDetail(field="permissions", message=code) for code in unknown],
        )
    return wanted


async def _get_role(session: AsyncSession, role_id: uuid.UUID) -> Role:
    role = await role_repo.get_by_id(session, role_id)
    if role is None:
        raise NotFoundError("ไม่พบบทบาทที่ต้องการ")
    return role


async def create_role(
    session: AsyncSession, actor: CurrentUser, data: RoleCreate, meta: RequestMeta
) -> RoleOut:
    if await role_repo.get_by_code(session, data.code):
        raise ConflictError("มีรหัสบทบาทนี้อยู่แล้ว")
    codes = _validate_codes(data.permissions)
    ensure_can_grant(actor, codes)
    role = Role(
        code=data.code,
        name=data.name,
        description=data.description,
        is_system=False,
        permissions=await role_repo.get_permissions_by_codes(session, codes),
    )
    session.add(role)
    await session.flush()
    audit.record(
        session,
        AuditAction.ROLE_CREATED,
        actor_id=actor.id,
        meta=meta,
        entity_type="role",
        entity_id=role.id,
        details={"code": role.code, "permissions": sorted(codes)},
    )
    await session.commit()
    await session.refresh(role)
    return role_out(role)


async def update_role(
    session: AsyncSession,
    actor: CurrentUser,
    role_id: uuid.UUID,
    data: RoleUpdate,
    meta: RequestMeta,
) -> RoleOut:
    role = await _get_role(session, role_id)
    changes = data.model_dump(exclude_unset=True)
    for field, value in changes.items():
        if value is not None:
            setattr(role, field, value)
    audit.record(
        session,
        AuditAction.ROLE_UPDATED,
        actor_id=actor.id,
        meta=meta,
        entity_type="role",
        entity_id=role.id,
        details={"fields": sorted(changes)},
    )
    await session.commit()
    await session.refresh(role)
    return role_out(role)


async def set_role_permissions(
    session: AsyncSession,
    actor: CurrentUser,
    role_id: uuid.UUID,
    permissions: list[str],
    meta: RequestMeta,
) -> RoleOut:
    role = await _get_role(session, role_id)
    if role.code in LOCKED_ROLES:
        raise PermissionDeniedError("ไม่สามารถแก้ไขสิทธิ์ของบทบาทนี้ได้")
    new_codes = _validate_codes(permissions)
    old_codes = {p.code for p in role.permissions}
    added, removed = new_codes - old_codes, old_codes - new_codes
    ensure_can_grant(actor, added | removed)
    role.permissions = await role_repo.get_permissions_by_codes(session, new_codes)
    audit.record(
        session,
        AuditAction.ROLE_PERMISSIONS_CHANGED,
        actor_id=actor.id,
        meta=meta,
        entity_type="role",
        entity_id=role.id,
        details={"code": role.code, "added": sorted(added), "removed": sorted(removed)},
    )
    await session.commit()
    await session.refresh(role)
    return role_out(role)


async def delete_role(
    session: AsyncSession, actor: CurrentUser, role_id: uuid.UUID, meta: RequestMeta
) -> None:
    role = await _get_role(session, role_id)
    if role.is_system:
        raise ConflictError("ไม่สามารถลบบทบาทของระบบได้")
    if await role_repo.count_users_with_role(session, role.id):
        raise ConflictError("ยังมีผู้ใช้ที่ได้รับบทบาทนี้อยู่ กรุณาถอดบทบาทออกก่อน")
    audit.record(
        session,
        AuditAction.ROLE_DELETED,
        actor_id=actor.id,
        meta=meta,
        entity_type="role",
        entity_id=role.id,
        details={"code": role.code},
    )
    await session.delete(role)
    await session.commit()


async def ensure_admin_remains(session: AsyncSession, *, losing_user_id: uuid.UUID) -> None:
    """Refuse a change that would leave no active user holding the ADMIN role."""
    admin = await role_repo.get_by_code(session, SystemRole.ADMIN.value)
    if admin is None:
        return
    user = await user_repo.get_by_id(session, losing_user_id)
    holds_admin = user is not None and any(link.role_id == admin.id for link in user.role_links)
    if (
        holds_admin
        and user is not None
        and user.is_active
        and await user_repo.count_active_holders_of_role(session, admin.id) <= 1
    ):
        raise ConflictError("ต้องมีผู้ดูแลระบบที่ใช้งานอยู่อย่างน้อยหนึ่งคน")
