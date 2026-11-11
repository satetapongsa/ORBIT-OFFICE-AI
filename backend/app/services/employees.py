"""Employee Center: directory, profiles and the sensitive HR record.

| data                                   | who                                              |
| -------------------------------------- | ------------------------------------------------ |
| directory (name, title, department,    | ``employees:read_directory``; inactive accounts   |
| work e-mail/phone) of active employees | only with ``users:read``                         |
| account (status, roles, last sign-in)  | ``users:read``                                   |
| HR record                              | the employee themself, or                        |
|                                        | ``employees:read_sensitive`` (every view by      |
|                                        | someone else is audit-logged)                    |
| edit HR record                         | ``employees:manage`` + ``employees:read_sensitive`` |
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, PermissionDeniedError
from app.core.permissions import P
from app.core.principal import CurrentUser, RequestMeta
from app.models.employee import EmployeeHrProfile
from app.models.identity import EmploymentStatus, User
from app.repositories import employees as employee_repo
from app.repositories.documents import user_names
from app.schemas.documents import UserRef
from app.schemas.employees import (
    EmergencyContact,
    EmployeeAccount,
    EmployeeCapabilities,
    EmployeeListItem,
    EmployeePage,
    EmployeeProfile,
    HrProfileIn,
    HrProfileOut,
)
from app.schemas.identity import DepartmentRef, RoleRef
from app.services import audit
from app.services.audit import AuditAction

NOT_FOUND = "ไม่พบพนักงานที่ต้องการ"
_HR_FIELDS = tuple(HrProfileIn.model_fields)


def _item(user: User) -> EmployeeListItem:
    return EmployeeListItem(
        id=user.id,
        employee_code=user.employee_code,
        display_name=user.display_name,
        first_name=user.first_name,
        last_name=user.last_name,
        job_title=user.job_title,
        department=DepartmentRef.model_validate(user.department) if user.department else None,
        email=user.email,
        phone_work=user.phone_work,
        is_active=user.is_active,
    )


async def list_directory(
    session: AsyncSession,
    actor: CurrentUser,
    *,
    q: str | None,
    department_id: uuid.UUID | None,
    include_inactive: bool,
    page: int,
    page_size: int,
) -> EmployeePage:
    if include_inactive and not actor.has(P.USERS_READ):
        raise PermissionDeniedError("ต้องมีสิทธิ์ดูบัญชีผู้ใช้จึงจะดูพนักงานที่ถูกระงับได้")
    users, total = await employee_repo.list_directory(
        session,
        q=q,
        department_id=department_id,
        include_inactive=include_inactive,
        page=page,
        page_size=page_size,
    )
    return EmployeePage(
        items=[_item(u) for u in users], total=total, page=page, page_size=page_size
    )


async def _visible_employee(session: AsyncSession, actor: CurrentUser, user_id: uuid.UUID) -> User:
    user = await employee_repo.get_employee(session, user_id)
    if user is None or (not user.is_active and not actor.has(P.USERS_READ)):
        raise NotFoundError(NOT_FOUND)
    return user


def capabilities_for(actor: CurrentUser, user: User) -> EmployeeCapabilities:
    is_self = actor.id == user.id
    return EmployeeCapabilities(
        can_edit_account=actor.has(P.USERS_UPDATE),
        can_manage_roles=actor.has_all((P.ROLES_ASSIGN, P.ROLES_READ)),
        can_change_active=actor.has(P.USERS_DEACTIVATE) and not is_self,
        can_view_hr=is_self or actor.has(P.EMPLOYEES_READ_SENSITIVE),
        can_edit_hr=actor.has_all((P.EMPLOYEES_MANAGE, P.EMPLOYEES_READ_SENSITIVE)),
    )


async def get_profile(
    session: AsyncSession, actor: CurrentUser, user_id: uuid.UUID
) -> EmployeeProfile:
    user = await _visible_employee(session, actor, user_id)
    manager = await employee_repo.department_manager(session, user.department_id)
    account = (
        EmployeeAccount(
            employment_status=EmploymentStatus(user.employment_status),
            roles=[RoleRef.model_validate(r) for r in user.roles],
            last_login_at=user.last_login_at,
            created_at=user.created_at,
        )
        if actor.has(P.USERS_READ)
        else None
    )
    return EmployeeProfile(
        **_item(user).model_dump(),
        department_manager=UserRef(id=manager[0], display_name=manager[1])
        if manager and manager[0] != user.id
        else None,
        account=account,
        capabilities=capabilities_for(actor, user),
    )


async def _hr_out(
    session: AsyncSession, user_id: uuid.UUID, profile: EmployeeHrProfile | None
) -> HrProfileOut:
    if profile is None:
        return HrProfileOut(user_id=user_id, exists=False, updated_at=None, updated_by=None)
    names = await user_names(session, {profile.updated_by} if profile.updated_by else set())
    return HrProfileOut(
        user_id=user_id,
        exists=True,
        date_of_birth=profile.date_of_birth,
        national_id_last4=profile.national_id_last4,
        personal_phone=profile.personal_phone,
        personal_email=profile.personal_email,
        address=profile.address,
        hire_date=profile.hire_date,
        employment_type=profile.employment_type,
        emergency_contact=EmergencyContact.model_validate(profile.emergency_contact)
        if profile.emergency_contact
        else None,
        updated_at=profile.updated_at,
        updated_by=UserRef(id=profile.updated_by, display_name=names.get(profile.updated_by, ""))
        if profile.updated_by
        else None,
    )


async def get_hr_profile(
    session: AsyncSession, actor: CurrentUser, user_id: uuid.UUID, meta: RequestMeta
) -> HrProfileOut:
    user = await _visible_employee(session, actor, user_id)
    if not capabilities_for(actor, user).can_view_hr:
        raise PermissionDeniedError("คุณไม่มีสิทธิ์ดูข้อมูลบุคคลของพนักงานคนนี้")
    profile = await employee_repo.get_hr_profile(session, user.id)
    if actor.id != user.id:
        # Reads of someone else's sensitive data are always traceable.
        audit.record(
            session,
            AuditAction.EMPLOYEE_HR_PROFILE_VIEWED,
            actor_id=actor.id,
            meta=meta,
            entity_type="user",
            entity_id=user.id,
        )
        await session.commit()
    return await _hr_out(session, user.id, profile)


async def replace_hr_profile(
    session: AsyncSession,
    actor: CurrentUser,
    user_id: uuid.UUID,
    data: HrProfileIn,
    meta: RequestMeta,
) -> HrProfileOut:
    user = await _visible_employee(session, actor, user_id)
    if not capabilities_for(actor, user).can_edit_hr:
        raise PermissionDeniedError("คุณไม่มีสิทธิ์แก้ไขข้อมูลบุคคลของพนักงาน")
    profile = await employee_repo.get_hr_profile(session, user.id)
    # Nested models become plain dicts (JSONB); the enum is stored by value.
    values = data.model_dump()
    if data.employment_type is not None:
        values["employment_type"] = data.employment_type.value

    if profile is None:
        profile = EmployeeHrProfile(user_id=user.id)
        session.add(profile)
        changed = [f for f in _HR_FIELDS if values[f] is not None]
    else:
        changed = [f for f in _HR_FIELDS if getattr(profile, f) != values[f]]
    for name in _HR_FIELDS:
        setattr(profile, name, values[name])
    profile.updated_by = actor.id
    # Field names only — values are sensitive and never written to the audit log.
    audit.record(
        session,
        AuditAction.EMPLOYEE_HR_PROFILE_UPDATED,
        actor_id=actor.id,
        meta=meta,
        entity_type="user",
        entity_id=user.id,
        details={"fields": sorted(changed)},
    )
    await session.commit()
    return await _hr_out(session, user.id, await employee_repo.get_hr_profile(session, user.id))
