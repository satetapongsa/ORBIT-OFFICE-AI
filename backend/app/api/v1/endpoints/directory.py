"""Employee directory lookups for pickers (e.g. sharing a document with a colleague).

Directory-safe fields only; the full Employee Center arrives in Phase 5.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import DbDep, require_permissions
from app.core.permissions import P
from app.core.principal import CurrentUser
from app.repositories import documents as document_repo
from app.schemas.documents import DirectoryUser
from app.schemas.identity import DepartmentRef

router = APIRouter(prefix="/directory", tags=["directory"])


@router.get("/users", response_model=list[DirectoryUser], summary="Search active colleagues")
async def search_users(
    db: DbDep,
    _: Annotated[CurrentUser, Depends(require_permissions(P.EMPLOYEES_READ_DIRECTORY))],
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> list[DirectoryUser]:
    users = await document_repo.search_directory(db, q, limit=limit)
    return [
        DirectoryUser(
            id=u.id,
            display_name=u.display_name,
            job_title=u.job_title,
            department=DepartmentRef.model_validate(u.department) if u.department else None,
        )
        for u in users
    ]
