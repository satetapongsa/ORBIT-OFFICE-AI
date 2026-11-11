"""Department management."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError, ValidationFailedError
from app.core.principal import CurrentUser, RequestMeta
from app.core.security import utcnow
from app.models.identity import Department
from app.repositories import departments as department_repo
from app.repositories import users as user_repo
from app.schemas.common import ErrorDetail
from app.schemas.identity import DepartmentCreate, DepartmentOut, DepartmentUpdate
from app.services import audit
from app.services.audit import AuditAction


def department_out(dept: Department, member_count: int = 0) -> DepartmentOut:
    return DepartmentOut(
        id=dept.id,
        code=dept.code,
        name=dept.name,
        description=dept.description,
        parent_id=dept.parent_id,
        manager_id=dept.manager_id,
        member_count=member_count,
        created_at=dept.created_at,
        updated_at=dept.updated_at,
    )


async def _get(session: AsyncSession, department_id: uuid.UUID) -> Department:
    dept = await department_repo.get_by_id(session, department_id)
    if dept is None:
        raise NotFoundError("ไม่พบแผนกที่ต้องการ")
    return dept


async def _validate_refs(
    session: AsyncSession,
    *,
    parent_id: uuid.UUID | None,
    manager_id: uuid.UUID | None,
    self_id: uuid.UUID | None = None,
) -> None:
    details: list[ErrorDetail] = []
    if parent_id is not None:
        if parent_id == self_id:
            details.append(
                ErrorDetail(field="parent_id", message="แผนกไม่สามารถเป็นแผนกแม่ของตนเองได้")
            )
        elif await department_repo.get_by_id(session, parent_id) is None:
            details.append(ErrorDetail(field="parent_id", message="ไม่พบแผนกแม่"))
    if manager_id is not None and await user_repo.get_by_id(session, manager_id) is None:
        details.append(ErrorDetail(field="manager_id", message="ไม่พบผู้ใช้ที่เป็นผู้จัดการ"))
    if details:
        raise ValidationFailedError(details=details)


async def create_department(
    session: AsyncSession, actor: CurrentUser, data: DepartmentCreate, meta: RequestMeta
) -> DepartmentOut:
    code = data.code.upper()
    if await department_repo.code_taken(session, code):
        raise ConflictError("มีรหัสแผนกนี้อยู่แล้ว")
    await _validate_refs(session, parent_id=data.parent_id, manager_id=data.manager_id)
    dept = Department(
        code=code,
        name=data.name,
        description=data.description,
        parent_id=data.parent_id,
        manager_id=data.manager_id,
    )
    session.add(dept)
    await session.flush()
    audit.record(
        session,
        AuditAction.DEPARTMENT_CREATED,
        actor_id=actor.id,
        meta=meta,
        entity_type="department",
        entity_id=dept.id,
        details={"code": code},
    )
    await session.commit()
    await session.refresh(dept)
    return department_out(dept)


async def update_department(
    session: AsyncSession,
    actor: CurrentUser,
    department_id: uuid.UUID,
    data: DepartmentUpdate,
    meta: RequestMeta,
) -> DepartmentOut:
    dept = await _get(session, department_id)
    changes = data.model_dump(exclude_unset=True)
    if changes.get("code"):
        changes["code"] = changes["code"].upper()
        if await department_repo.code_taken(session, changes["code"], exclude_id=dept.id):
            raise ConflictError("มีรหัสแผนกนี้อยู่แล้ว")
    await _validate_refs(
        session,
        parent_id=changes.get("parent_id"),
        manager_id=changes.get("manager_id"),
        self_id=dept.id,
    )
    for field, value in changes.items():
        if value is None and field in {"code", "name"}:
            continue
        setattr(dept, field, value)
    audit.record(
        session,
        AuditAction.DEPARTMENT_UPDATED,
        actor_id=actor.id,
        meta=meta,
        entity_type="department",
        entity_id=dept.id,
        details={"fields": sorted(changes)},
    )
    await session.commit()
    await session.refresh(dept)
    return department_out(dept, await department_repo.count_members(session, dept.id))


async def delete_department(
    session: AsyncSession, actor: CurrentUser, department_id: uuid.UUID, meta: RequestMeta
) -> None:
    dept = await _get(session, department_id)
    if await department_repo.count_members(session, dept.id):
        raise ConflictError("ยังมีพนักงานอยู่ในแผนกนี้ กรุณาย้ายพนักงานออกก่อน")
    dept.deleted_at = utcnow()
    audit.record(
        session,
        AuditAction.DEPARTMENT_DELETED,
        actor_id=actor.id,
        meta=meta,
        entity_type="department",
        entity_id=dept.id,
        details={"code": dept.code},
    )
    await session.commit()
