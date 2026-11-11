"""The single document access predicate.

Every code path that reads documents — listing, preview, download, search, RAG retrieval,
summarisation and reports — must filter with :func:`accessible_documents_condition`
(or :func:`can_access_document`) so permission rules exist in exactly one place.
The condition is pure SQL, so it can be combined with vector search in Phase 7 and applied
*before* any document content leaves the database.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ColumnElement, and_, exists, false, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import P
from app.core.principal import CurrentUser
from app.models.document import (
    AccessLevel,
    Document,
    DocumentAcl,
    DocumentVisibility,
    PrincipalType,
)


def _acl_grant(user: CurrentUser, levels: list[str]) -> ColumnElement[bool]:
    principals: list[ColumnElement[bool]] = [
        and_(
            DocumentAcl.principal_type == PrincipalType.USER.value,
            DocumentAcl.principal_id == user.id,
        )
    ]
    if user.department_id is not None:
        principals.append(
            and_(
                DocumentAcl.principal_type == PrincipalType.DEPARTMENT.value,
                DocumentAcl.principal_id == user.department_id,
            )
        )
    if user.role_ids:
        principals.append(
            and_(
                DocumentAcl.principal_type == PrincipalType.ROLE.value,
                DocumentAcl.principal_id.in_(user.role_ids),
            )
        )
    return exists(
        select(DocumentAcl.id).where(
            DocumentAcl.document_id == Document.id,
            DocumentAcl.access_level.in_(levels),
            or_(*principals),
        )
    )


def accessible_documents_condition(
    user: CurrentUser, level: AccessLevel = AccessLevel.VIEW
) -> ColumnElement[bool]:
    """SQL condition on ``Document`` that is true only for documents ``user`` may access.

    Rules (see docs/SECURITY.md §3), soft-deleted documents always excluded:
    1. ``documents:manage`` — administrative override (all documents);
    2. owner — full access;
    3. ``COMPANY`` visibility — VIEW for everyone with ``documents:read``;
    4. ``DEPARTMENT`` visibility — VIEW for members of the owning department;
    5. explicit ACL grant (user, department or role) with a sufficient access level.
    """
    not_deleted = Document.deleted_at.is_(None)
    if user.has(P.DOCUMENTS_MANAGE):
        return not_deleted
    if not user.has(P.DOCUMENTS_READ):
        return false()

    rules: list[ColumnElement[bool]] = [
        Document.owner_id == user.id,
        _acl_grant(user, level.at_least()),
    ]
    if level is AccessLevel.VIEW:
        rules.append(Document.visibility == DocumentVisibility.COMPANY.value)
        if user.department_id is not None:
            rules.append(
                and_(
                    Document.visibility == DocumentVisibility.DEPARTMENT.value,
                    Document.department_id == user.department_id,
                )
            )
    return and_(not_deleted, or_(*rules))


async def can_access_document(
    session: AsyncSession,
    user: CurrentUser,
    document_id: uuid.UUID,
    level: AccessLevel = AccessLevel.VIEW,
) -> bool:
    stmt = select(
        exists(
            select(Document.id).where(
                Document.id == document_id, accessible_documents_condition(user, level)
            )
        )
    )
    return bool(await session.scalar(stmt))
