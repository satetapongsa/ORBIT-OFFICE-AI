"""Department endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.api.deps import DbDep, MetaDep, require_permissions
from app.core.errors import NotFoundError
from app.core.permissions import P
from app.core.principal import CurrentUser
from app.repositories import departments as department_repo
from app.schemas.identity import DepartmentCreate, DepartmentOut, DepartmentUpdate
from app.services import departments as department_service

router = APIRouter(prefix="/departments", tags=["departments"])

ReadDepartments = Annotated[CurrentUser, Depends(require_permissions(P.DEPARTMENTS_READ))]
ManageDepartments = Annotated[CurrentUser, Depends(require_permissions(P.DEPARTMENTS_MANAGE))]


@router.get("", response_model=list[DepartmentOut], summary="List departments")
async def list_departments(db: DbDep, _: ReadDepartments) -> list[DepartmentOut]:
    counts = await department_repo.member_counts(db)
    return [
        department_service.department_out(d, counts.get(d.id, 0))
        for d in await department_repo.list_departments(db)
    ]


@router.get("/{department_id}", response_model=DepartmentOut, summary="Get a department")
async def get_department(department_id: uuid.UUID, db: DbDep, _: ReadDepartments) -> DepartmentOut:
    dept = await department_repo.get_by_id(db, department_id)
    if dept is None:
        raise NotFoundError("ไม่พบแผนกที่ต้องการ")
    return department_service.department_out(dept, await department_repo.count_members(db, dept.id))


@router.post(
    "",
    response_model=DepartmentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a department",
)
async def create_department(
    payload: DepartmentCreate, db: DbDep, meta: MetaDep, actor: ManageDepartments
) -> DepartmentOut:
    return await department_service.create_department(db, actor, payload, meta)


@router.patch("/{department_id}", response_model=DepartmentOut, summary="Update a department")
async def update_department(
    department_id: uuid.UUID,
    payload: DepartmentUpdate,
    db: DbDep,
    meta: MetaDep,
    actor: ManageDepartments,
) -> DepartmentOut:
    return await department_service.update_department(db, actor, department_id, payload, meta)


@router.delete(
    "/{department_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a department"
)
async def delete_department(
    department_id: uuid.UUID, db: DbDep, meta: MetaDep, actor: ManageDepartments
) -> Response:
    await department_service.delete_department(db, actor, department_id, meta)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
