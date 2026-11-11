"""User management endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import DbDep, MetaDep, SettingsDep, require_permissions
from app.core.permissions import P
from app.core.principal import CurrentUser
from app.repositories import users as user_repo
from app.schemas.common import Page
from app.schemas.identity import UserCreate, UserOut, UserRolesUpdate, UserUpdate
from app.services import users as user_service

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=Page[UserOut], summary="List users")
async def list_users(
    db: DbDep,
    _: Annotated[CurrentUser, Depends(require_permissions(P.USERS_READ))],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    q: Annotated[str | None, Query(max_length=100)] = None,
    department_id: uuid.UUID | None = None,
    is_active: bool | None = None,
    role: Annotated[str | None, Query(max_length=50)] = None,
) -> Page[UserOut]:
    rows, total = await user_repo.list_users(
        db,
        page=page,
        page_size=page_size,
        q=q,
        department_id=department_id,
        is_active=is_active,
        role_code=role,
    )
    return Page[UserOut](
        items=[UserOut.model_validate(u) for u in rows], total=total, page=page, page_size=page_size
    )


@router.post(
    "", response_model=UserOut, status_code=status.HTTP_201_CREATED, summary="Create a user"
)
async def create_user(
    payload: UserCreate,
    db: DbDep,
    settings: SettingsDep,
    meta: MetaDep,
    actor: Annotated[CurrentUser, Depends(require_permissions(P.USERS_CREATE))],
) -> UserOut:
    return UserOut.model_validate(
        await user_service.create_user(db, settings, actor, payload, meta)
    )


@router.get("/{user_id}", response_model=UserOut, summary="Get a user")
async def get_user(
    user_id: uuid.UUID,
    db: DbDep,
    _: Annotated[CurrentUser, Depends(require_permissions(P.USERS_READ))],
) -> UserOut:
    return UserOut.model_validate(await user_service.get_user(db, user_id))


@router.patch("/{user_id}", response_model=UserOut, summary="Update a user")
async def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    db: DbDep,
    meta: MetaDep,
    actor: Annotated[CurrentUser, Depends(require_permissions(P.USERS_UPDATE))],
) -> UserOut:
    return UserOut.model_validate(await user_service.update_user(db, actor, user_id, payload, meta))


@router.post("/{user_id}/deactivate", response_model=UserOut, summary="Deactivate a user")
async def deactivate_user(
    user_id: uuid.UUID,
    db: DbDep,
    meta: MetaDep,
    actor: Annotated[CurrentUser, Depends(require_permissions(P.USERS_DEACTIVATE))],
) -> UserOut:
    return UserOut.model_validate(
        await user_service.set_active(db, actor, user_id, active=False, meta=meta)
    )


@router.post("/{user_id}/activate", response_model=UserOut, summary="Re-activate a user")
async def activate_user(
    user_id: uuid.UUID,
    db: DbDep,
    meta: MetaDep,
    actor: Annotated[CurrentUser, Depends(require_permissions(P.USERS_DEACTIVATE))],
) -> UserOut:
    return UserOut.model_validate(
        await user_service.set_active(db, actor, user_id, active=True, meta=meta)
    )


@router.put("/{user_id}/roles", response_model=UserOut, summary="Replace a user's roles")
async def set_user_roles(
    user_id: uuid.UUID,
    payload: UserRolesUpdate,
    db: DbDep,
    meta: MetaDep,
    actor: Annotated[CurrentUser, Depends(require_permissions(P.ROLES_ASSIGN))],
) -> UserOut:
    return UserOut.model_validate(
        await user_service.set_roles(db, actor, user_id, payload.role_codes, meta)
    )
