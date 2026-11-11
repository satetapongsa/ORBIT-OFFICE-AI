"""Document queries.

Every query that returns documents (or anything derived from them) filters with
:func:`accessible_documents_condition` — never re-implement access rules here.
Version/ACL/history helpers take a ``document_id`` that the caller has already authorised.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.principal import CurrentUser
from app.models.audit import AuditLog
from app.models.document import (
    AccessLevel,
    Document,
    DocumentAcl,
    DocumentVersion,
    DocumentVersionText,
    PrincipalType,
)
from app.models.identity import Department, Role, User
from app.repositories.document_access import accessible_documents_condition

SortKey = Literal["updated", "created", "title"]


@dataclass(frozen=True, slots=True)
class DocumentRow:
    document: Document
    current_version: DocumentVersion | None
    owner_name: str
    department: Department | None


@dataclass(frozen=True, slots=True)
class DocumentFilters:
    q: str | None = None
    category: str | None = None
    visibility: str | None = None
    status: str | None = None
    processing_status: str | None = None
    department_id: uuid.UUID | None = None
    owner_id: uuid.UUID | None = None


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _base(
    user: CurrentUser, level: AccessLevel = AccessLevel.VIEW
) -> Select[Document, DocumentVersion, str, Department]:
    current = aliased(DocumentVersion)
    owner = aliased(User)
    return (
        select(Document, current, owner.display_name, Department)
        .join(owner, owner.id == Document.owner_id)
        .outerjoin(current, current.id == Document.current_version_id)
        .outerjoin(Department, Department.id == Document.department_id)
        .where(accessible_documents_condition(user, level))
    )


def _row(row: Sequence[object]) -> DocumentRow:
    document, current, owner_name, department = row
    assert isinstance(document, Document)  # noqa: S101 - narrowing for mypy
    return DocumentRow(
        document=document,
        current_version=current if isinstance(current, DocumentVersion) else None,
        owner_name=str(owner_name),
        department=department if isinstance(department, Department) else None,
    )


async def list_documents(
    session: AsyncSession,
    user: CurrentUser,
    filters: DocumentFilters,
    *,
    sort: SortKey,
    page: int,
    page_size: int,
) -> tuple[list[DocumentRow], int]:
    stmt = _base(user)
    if filters.q:
        pattern = f"%{_escape_like(filters.q.strip())}%"
        stmt = stmt.where(
            or_(
                Document.title.ilike(pattern, escape="\\"),
                Document.description.ilike(pattern, escape="\\"),
            )
        )
    if filters.category:
        stmt = stmt.where(Document.category == filters.category)
    if filters.visibility:
        stmt = stmt.where(Document.visibility == filters.visibility)
    if filters.status:
        stmt = stmt.where(Document.status == filters.status)
    if filters.department_id:
        stmt = stmt.where(Document.department_id == filters.department_id)
    if filters.owner_id:
        stmt = stmt.where(Document.owner_id == filters.owner_id)
    if filters.processing_status:
        stmt = stmt.where(
            Document.current_version_id.in_(
                select(DocumentVersion.id).where(
                    DocumentVersion.processing_status == filters.processing_status
                )
            )
        )

    total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    order: tuple[Any, Any] = {
        "updated": (Document.updated_at.desc(), Document.id.desc()),
        "created": (Document.created_at.desc(), Document.id.desc()),
        "title": (Document.title.asc(), Document.id.asc()),
    }[sort]
    rows = await session.execute(
        stmt.order_by(*order).offset((page - 1) * page_size).limit(page_size)
    )
    return [_row(r) for r in rows], total


async def get_document(
    session: AsyncSession,
    user: CurrentUser,
    document_id: uuid.UUID,
    level: AccessLevel = AccessLevel.VIEW,
) -> DocumentRow | None:
    row = (await session.execute(_base(user, level).where(Document.id == document_id))).first()
    return _row(row) if row else None


async def get_document_for_update(session: AsyncSession, document_id: uuid.UUID) -> Document | None:
    """Lock a live document row; call only after an access check."""
    stmt = (
        select(Document)
        .where(Document.id == document_id, Document.deleted_at.is_(None))
        .with_for_update()
    )
    return await session.scalar(stmt)


async def list_versions(
    session: AsyncSession, document_id: uuid.UUID
) -> list[tuple[DocumentVersion, uuid.UUID | None, str | None]]:
    stmt = (
        select(DocumentVersion, User.id, User.display_name)
        .outerjoin(User, User.id == DocumentVersion.uploaded_by)
        .where(DocumentVersion.document_id == document_id)
        .order_by(DocumentVersion.version_number.desc())
    )
    return [(r[0], r[1], r[2]) for r in await session.execute(stmt)]


async def get_version(
    session: AsyncSession, document_id: uuid.UUID, version_id: uuid.UUID
) -> DocumentVersion | None:
    stmt = select(DocumentVersion).where(
        DocumentVersion.id == version_id, DocumentVersion.document_id == document_id
    )
    return await session.scalar(stmt)


async def next_version_number(session: AsyncSession, document_id: uuid.UUID) -> int:
    stmt = select(func.coalesce(func.max(DocumentVersion.version_number), 0)).where(
        DocumentVersion.document_id == document_id
    )
    return int(await session.scalar(stmt) or 0) + 1


async def get_text(session: AsyncSession, version_id: uuid.UUID) -> str | None:
    return await session.scalar(
        select(DocumentVersionText.content).where(
            DocumentVersionText.document_version_id == version_id
        )
    )


async def list_acl(session: AsyncSession, document_id: uuid.UUID) -> Sequence[DocumentAcl]:
    stmt = (
        select(DocumentAcl)
        .where(DocumentAcl.document_id == document_id)
        .order_by(DocumentAcl.created_at, DocumentAcl.id)
    )
    return (await session.scalars(stmt)).all()


async def principal_names(
    session: AsyncSession, entries: Sequence[tuple[str, uuid.UUID]]
) -> dict[tuple[str, uuid.UUID], str]:
    """Display names for ACL principals; missing (deleted) principals are absent."""
    by_type: dict[str, set[uuid.UUID]] = {}
    for kind, pid in entries:
        by_type.setdefault(kind, set()).add(pid)
    names: dict[tuple[str, uuid.UUID], str] = {}
    if ids := by_type.get(PrincipalType.USER.value):
        for uid, name in await session.execute(
            select(User.id, User.display_name).where(User.id.in_(ids), User.deleted_at.is_(None))
        ):
            names[(PrincipalType.USER.value, uid)] = name
    if ids := by_type.get(PrincipalType.DEPARTMENT.value):
        for did, name in await session.execute(
            select(Department.id, Department.name).where(
                Department.id.in_(ids), Department.deleted_at.is_(None)
            )
        ):
            names[(PrincipalType.DEPARTMENT.value, did)] = name
    if ids := by_type.get(PrincipalType.ROLE.value):
        for rid, name in await session.execute(select(Role.id, Role.name).where(Role.id.in_(ids))):
            names[(PrincipalType.ROLE.value, rid)] = name
    return names


async def user_names(session: AsyncSession, ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not ids:
        return {}
    rows = await session.execute(select(User.id, User.display_name).where(User.id.in_(ids)))
    return {r[0]: r[1] for r in rows}


async def history(
    session: AsyncSession, document_id: uuid.UUID, *, limit: int
) -> list[tuple[AuditLog, uuid.UUID | None, str | None]]:
    actor = aliased(User)
    stmt = (
        select(AuditLog, actor.id, actor.display_name)
        .outerjoin(actor, actor.id == AuditLog.actor_id)
        .where(AuditLog.entity_type == "document", AuditLog.entity_id == document_id)
        .order_by(AuditLog.occurred_at.desc(), AuditLog.id.desc())
        .limit(limit)
    )
    return [(r[0], r[1], r[2]) for r in await session.execute(stmt)]


async def search_directory(session: AsyncSession, q: str | None, *, limit: int) -> Sequence[User]:
    """Active, live users for pickers (directory-safe; callers expose limited fields only)."""
    stmt = select(User).where(User.deleted_at.is_(None), User.is_active.is_(True))
    if q and q.strip():
        pattern = f"%{_escape_like(q.strip())}%"
        stmt = stmt.where(
            or_(
                User.display_name.ilike(pattern, escape="\\"),
                User.job_title.ilike(pattern, escape="\\"),
            )
        )
    return (await session.scalars(stmt.order_by(User.display_name).limit(limit))).all()
