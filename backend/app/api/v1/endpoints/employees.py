"""Employee Center endpoints (directory, profiles, HR record).

Account administration (create/edit/deactivate/roles) uses the existing ``/users`` API.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import CurrentUserDep, DbDep, MetaDep, require_permissions
from app.core.permissions import P
from app.core.principal import CurrentUser
from app.schemas.employees import EmployeePage, EmployeeProfile, HrProfileIn, HrProfileOut
from app.services import employees as employee_service

router = APIRouter(prefix="/employees", tags=["employees"])

DirectoryReader = Annotated[CurrentUser, Depends(require_permissions(P.EMPLOYEES_READ_DIRECTORY))]


@router.get("", response_model=EmployeePage, summary="Employee directory")
async def list_employees(
    db: DbDep,
    actor: DirectoryReader,
    q: Annotated[str | None, Query(max_length=100)] = None,
    department_id: uuid.UUID | None = None,
    include_inactive: bool = False,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 24,
) -> EmployeePage:
    return await employee_service.list_directory(
        db,
        actor,
        q=q,
        department_id=department_id,
        include_inactive=include_inactive,
        page=page,
        page_size=page_size,
    )


@router.get("/{user_id}", response_model=EmployeeProfile, summary="Employee profile")
async def get_employee(user_id: uuid.UUID, db: DbDep, actor: DirectoryReader) -> EmployeeProfile:
    return await employee_service.get_profile(db, actor, user_id)


@router.get(
    "/{user_id}/hr",
    response_model=HrProfileOut,
    summary="Sensitive HR record (self or employees:read_sensitive; audited)",
)
async def get_hr_profile(
    user_id: uuid.UUID, db: DbDep, actor: CurrentUserDep, meta: MetaDep
) -> HrProfileOut:
    return await employee_service.get_hr_profile(db, actor, user_id, meta)


@router.put(
    "/{user_id}/hr",
    response_model=HrProfileOut,
    summary="Replace the HR record (employees:manage + employees:read_sensitive)",
)
async def replace_hr_profile(
    user_id: uuid.UUID,
    body: HrProfileIn,
    db: DbDep,
    meta: MetaDep,
    actor: Annotated[
        CurrentUser,
        Depends(require_permissions(P.EMPLOYEES_MANAGE, P.EMPLOYEES_READ_SENSITIVE)),
    ],
) -> HrProfileOut:
    return await employee_service.replace_hr_profile(db, actor, user_id, body, meta)
