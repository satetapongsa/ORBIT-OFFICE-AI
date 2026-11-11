"""Role and permission endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.api.deps import DbDep, MetaDep, require_permissions
from app.core.errors import NotFoundError
from app.core.permissions import P
from app.core.principal import CurrentUser
from app.repositories import roles as role_repo
from app.schemas.identity import (
    PermissionOut,
    RoleCreate,
    RoleOut,
    RolePermissionsUpdate,
    RoleUpdate,
)
from app.services import rbac

router = APIRouter(tags=["roles"])

ReadRoles = Annotated[CurrentUser, Depends(require_permissions(P.ROLES_READ))]
ManageRoles = Annotated[CurrentUser, Depends(require_permissions(P.ROLES_MANAGE))]


@router.get("/permissions", response_model=list[PermissionOut], summary="Permission catalogue")
async def list_permissions(db: DbDep, _: ReadRoles) -> list[PermissionOut]:
    return [PermissionOut.model_validate(p) for p in await role_repo.list_permissions(db)]


@router.get("/roles", response_model=list[RoleOut], summary="List roles")
async def list_roles(db: DbDep, _: ReadRoles) -> list[RoleOut]:
    return [rbac.role_out(r) for r in await role_repo.list_roles(db)]


@router.get("/roles/{role_id}", response_model=RoleOut, summary="Get a role")
async def get_role(role_id: uuid.UUID, db: DbDep, _: ReadRoles) -> RoleOut:
    role = await role_repo.get_by_id(db, role_id)
    if role is None:
        raise NotFoundError("ไม่พบบทบาทที่ต้องการ")
    return rbac.role_out(role)


@router.post(
    "/roles", response_model=RoleOut, status_code=status.HTTP_201_CREATED, summary="Create a role"
)
async def create_role(payload: RoleCreate, db: DbDep, meta: MetaDep, actor: ManageRoles) -> RoleOut:
    return await rbac.create_role(db, actor, payload, meta)


@router.patch("/roles/{role_id}", response_model=RoleOut, summary="Rename / describe a role")
async def update_role(
    role_id: uuid.UUID, payload: RoleUpdate, db: DbDep, meta: MetaDep, actor: ManageRoles
) -> RoleOut:
    return await rbac.update_role(db, actor, role_id, payload, meta)


@router.put(
    "/roles/{role_id}/permissions", response_model=RoleOut, summary="Replace role permissions"
)
async def set_role_permissions(
    role_id: uuid.UUID, payload: RolePermissionsUpdate, db: DbDep, meta: MetaDep, actor: ManageRoles
) -> RoleOut:
    return await rbac.set_role_permissions(db, actor, role_id, payload.permissions, meta)


@router.delete(
    "/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a custom role"
)
async def delete_role(role_id: uuid.UUID, db: DbDep, meta: MetaDep, actor: ManageRoles) -> Response:
    await rbac.delete_role(db, actor, role_id, meta)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
