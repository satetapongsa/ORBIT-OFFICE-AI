"""Read models for the Document Center API (all access-checked)."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError, PermissionDeniedError
from app.core.principal import CurrentUser
from app.models.document import ProcessingStatus
from app.repositories import documents as document_repo
from app.repositories.documents import DocumentFilters, DocumentRow, SortKey
from app.schemas.documents import (
    AclEntryOut,
    AclOut,
    DocumentDetail,
    DocumentHistoryItem,
    DocumentListItem,
    DocumentPage,
    DocumentText,
    UserRef,
    VersionOut,
    VersionSummary,
)
from app.schemas.identity import DepartmentRef
from app.services.documents.service import NOT_FOUND, TEXT_PREVIEW_CHARS, get_access

HISTORY_LIMIT = 100


def _list_item(row: DocumentRow) -> DocumentListItem:
    doc = row.document
    return DocumentListItem(
        id=doc.id,
        title=doc.title,
        description=doc.description,
        category=doc.category,
        visibility=doc.visibility,
        status=doc.status,
        owner=UserRef(id=doc.owner_id, display_name=row.owner_name),
        department=DepartmentRef.model_validate(row.department) if row.department else None,
        current_version=(
            VersionSummary.model_validate(row.current_version) if row.current_version else None
        ),
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


async def list_documents(
    session: AsyncSession,
    user: CurrentUser,
    filters: DocumentFilters,
    *,
    sort: SortKey,
    page: int,
    page_size: int,
) -> DocumentPage:
    rows, total = await document_repo.list_documents(
        session, user, filters, sort=sort, page=page, page_size=page_size
    )
    return DocumentPage(
        items=[_list_item(r) for r in rows], total=total, page=page, page_size=page_size
    )


async def get_detail(
    session: AsyncSession, user: CurrentUser, document_id: uuid.UUID
) -> DocumentDetail:
    access = await get_access(session, user, document_id)
    row = await document_repo.get_document(session, user, document_id)
    if row is None:
        raise NotFoundError(NOT_FOUND)
    versions = [
        VersionOut.model_validate(
            {
                **{c: getattr(v, c) for c in VersionOut.model_fields if c != "uploaded_by"},
                "uploaded_by": UserRef(id=uid, display_name=name) if uid and name else None,
            }
        )
        for v, uid, name in await document_repo.list_versions(session, document_id)
    ]
    return DocumentDetail(
        **_list_item(row).model_dump(),
        access_level=access.level,
        capabilities=access.capabilities,
        versions=versions,
    )


async def get_text(
    session: AsyncSession, user: CurrentUser, document_id: uuid.UUID, version_id: uuid.UUID | None
) -> DocumentText:
    row = await document_repo.get_document(session, user, document_id)
    if row is None:
        raise NotFoundError(NOT_FOUND)
    target = version_id or row.document.current_version_id
    version = await document_repo.get_version(session, document_id, target) if target else None
    if version is None:
        raise NotFoundError("ไม่พบไฟล์ของเอกสารนี้")
    if version.processing_status != ProcessingStatus.READY.value:
        raise ConflictError("ยังไม่มีข้อความของเวอร์ชันนี้ (ยังประมวลผลไม่เสร็จหรือประมวลผลไม่สำเร็จ)")
    content = await document_repo.get_text(session, version.id) or ""
    return DocumentText(
        version_id=version.id,
        version_number=version.version_number,
        content=content[:TEXT_PREVIEW_CHARS],
        char_count=len(content),
        truncated=len(content) > TEXT_PREVIEW_CHARS,
    )


async def get_acl(session: AsyncSession, user: CurrentUser, document_id: uuid.UUID) -> AclOut:
    access = await get_access(session, user, document_id)
    if not access.capabilities.can_manage_access:
        raise PermissionDeniedError("คุณไม่มีสิทธิ์ดูการกำหนดสิทธิ์ของเอกสารนี้")
    row = await document_repo.get_document(session, user, document_id)
    if row is None:
        raise NotFoundError(NOT_FOUND)
    acl = await document_repo.list_acl(session, document_id)
    names = await document_repo.principal_names(
        session, [(a.principal_type, a.principal_id) for a in acl]
    )
    granters = await document_repo.user_names(
        session, {a.granted_by for a in acl if a.granted_by is not None}
    )
    entries = [
        AclEntryOut(
            id=a.id,
            principal_type=a.principal_type,
            principal_id=a.principal_id,
            principal_name=names.get((a.principal_type, a.principal_id), "(ถูกลบแล้ว)"),
            access_level=a.access_level,
            granted_by=(
                UserRef(id=a.granted_by, display_name=granters[a.granted_by])
                if a.granted_by in granters
                else None
            ),
            created_at=a.created_at,
        )
        for a in acl
    ]
    return AclOut(
        visibility=row.document.visibility,
        owner=UserRef(id=row.document.owner_id, display_name=row.owner_name),
        entries=entries,
    )


async def get_history(
    session: AsyncSession, user: CurrentUser, document_id: uuid.UUID
) -> list[DocumentHistoryItem]:
    access = await get_access(session, user, document_id)
    if not access.capabilities.can_view_history:
        raise PermissionDeniedError("คุณไม่มีสิทธิ์ดูประวัติของเอกสารนี้")
    return [
        DocumentHistoryItem(
            id=log.id,
            action=log.action,
            occurred_at=log.occurred_at,
            actor=UserRef(id=actor_id, display_name=name) if actor_id and name else None,
            details=log.details,
        )
        for log, actor_id, name in await document_repo.history(
            session, document_id, limit=HISTORY_LIMIT
        )
    ]
