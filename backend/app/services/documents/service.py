"""Document Center business rules.

Access is always decided by ``app.repositories.document_access`` (one SQL predicate);
permission codes add capability checks on top:

| operation                       | requires                                                   |
| ------------------------------- | ---------------------------------------------------------- |
| list / detail / text / download | VIEW (``documents:read`` is part of the predicate)          |
| upload a new document           | ``documents:upload``                                        |
| edit metadata, archive          | EDIT                                                        |
| change visibility / department  | MANAGE                                                      |
| upload a new version            | EDIT + ``documents:upload``                                 |
| reprocess a version             | EDIT                                                        |
| delete (soft)                   | MANAGE + ``documents:delete``                               |
| read / replace the ACL          | MANAGE, or VIEW + ``documents:manage_access``               |
| history                         | MANAGE, or VIEW + ``audit:read``                            |

Unknown and inaccessible documents both answer 404, so existence is never revealed.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol

import anyio
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationFailedError,
)
from app.core.logging import get_logger
from app.core.permissions import P
from app.core.principal import CurrentUser, RequestMeta
from app.core.security import utcnow
from app.core.storage import ObjectStream
from app.models.document import (
    AccessLevel,
    Document,
    DocumentAcl,
    DocumentStatus,
    DocumentVersion,
    DocumentVisibility,
    PrincipalType,
    ProcessingStatus,
)
from app.models.identity import Department
from app.repositories import departments as department_repo
from app.repositories import documents as document_repo
from app.repositories.document_access import effective_access_level
from app.schemas.common import ErrorDetail
from app.schemas.documents import (
    AclEntryIn,
    DocumentCapabilities,
    DocumentCreate,
    DocumentUpdate,
)
from app.services import audit, notifications
from app.services.audit import AuditAction
from app.services.uploads import (
    FileStorage,
    StoredUpload,
    discard_object,
    open_object,
    receive_upload,
    store_upload,
)

logger = get_logger(__name__)

# Documents and task attachments share one private bucket and storage implementation.
DocumentStorage = FileStorage

TEXT_PREVIEW_CHARS = 50_000
LEVEL_LABELS = {
    AccessLevel.VIEW: "ดูเอกสาร",
    AccessLevel.EDIT: "แก้ไขเอกสาร",
    AccessLevel.MANAGE: "จัดการเอกสาร",
}


class DocumentProcessor(Protocol):
    async def enqueue(self, version_id: uuid.UUID, *, force: bool = False) -> None: ...


class CeleryDocumentProcessor:
    """Queues text extraction on the ``documents`` queue. A broker outage leaves the version
    PENDING (logged); users with EDIT access can retry from the UI."""

    async def enqueue(self, version_id: uuid.UUID, *, force: bool = False) -> None:
        from app.workers.celery_app import celery_app

        def _send() -> None:
            celery_app.send_task(
                "documents.extract_text",
                args=[str(version_id)],
                kwargs={"force": force},
                queue="documents",
            )

        try:
            await anyio.to_thread.run_sync(_send)
        except Exception:
            logger.warning("document_enqueue_failed", version_id=str(version_id), exc_info=True)


@dataclass(frozen=True, slots=True)
class Access:
    level: AccessLevel
    capabilities: DocumentCapabilities


NOT_FOUND = "ไม่พบเอกสาร หรือคุณไม่มีสิทธิ์เข้าถึง"


def capabilities_for(user: CurrentUser, level: AccessLevel) -> DocumentCapabilities:
    can_edit = level.rank >= AccessLevel.EDIT.rank
    can_manage = level is AccessLevel.MANAGE
    return DocumentCapabilities(
        can_edit=can_edit,
        can_manage=can_manage,
        can_delete=can_manage and user.has(P.DOCUMENTS_DELETE),
        can_manage_access=can_manage or user.has(P.DOCUMENTS_MANAGE_ACCESS),
        can_upload_version=can_edit and user.has(P.DOCUMENTS_UPLOAD),
        can_view_history=can_manage or user.has(P.AUDIT_READ),
    )


async def get_access(session: AsyncSession, user: CurrentUser, document_id: uuid.UUID) -> Access:
    level = await effective_access_level(session, user, document_id)
    if level is None:
        raise NotFoundError(NOT_FOUND)
    return Access(level=level, capabilities=capabilities_for(user, level))


def _deny(allowed: bool, message: str) -> None:
    if not allowed:
        raise PermissionDeniedError(message)


# --- Upload handling ------------------------------------------------------------------


def _version(
    *,
    version_id: uuid.UUID,
    document_id: uuid.UUID,
    number: int,
    stored: StoredUpload,
    uploader: uuid.UUID,
) -> DocumentVersion:
    return DocumentVersion(
        id=version_id,
        document_id=document_id,
        version_number=number,
        storage_key=f"documents/{document_id}/{version_id}",
        original_filename=stored.inspected.filename,
        file_type=stored.inspected.file_type.value,
        mime_type=stored.inspected.mime_type,
        size_bytes=stored.size_bytes,
        sha256=stored.sha256,
        uploaded_by=uploader,
        processing_status=ProcessingStatus.PENDING.value,
    )


async def _resolve_department(
    session: AsyncSession,
    user: CurrentUser,
    department_id: uuid.UUID | None,
    visibility: DocumentVisibility,
) -> uuid.UUID | None:
    if department_id is not None and department_id != user.department_id:
        _deny(
            user.has(P.DOCUMENTS_MANAGE),
            "กำหนดเอกสารได้เฉพาะแผนกของคุณเอง",
        )
    if department_id is not None:
        department: Department | None = await department_repo.get_by_id(session, department_id)
        if department is None:
            raise ValidationFailedError(
                details=[ErrorDetail(field="department_id", message="ไม่พบแผนกนี้")]
            )
    if visibility is DocumentVisibility.DEPARTMENT and department_id is None:
        raise ValidationFailedError(
            details=[
                ErrorDetail(
                    field="visibility",
                    message="เอกสารระดับแผนกต้องระบุแผนก (บัญชีของคุณยังไม่มีแผนก)",
                )
            ]
        )
    return department_id


# --- Commands -------------------------------------------------------------------------


async def create_document(
    session: AsyncSession,
    settings: Settings,
    storage: DocumentStorage,
    processor: DocumentProcessor,
    user: CurrentUser,
    data: DocumentCreate,
    upload: UploadFile,
    meta: RequestMeta,
) -> uuid.UUID:
    _deny(user.has(P.DOCUMENTS_UPLOAD), "คุณไม่มีสิทธิ์อัปโหลดเอกสาร")
    department_id = await _resolve_department(
        session,
        user,
        data.department_id if data.department_id is not None else user.department_id,
        data.visibility,
    )
    stored = await receive_upload(upload, settings)
    document_id, version_id = uuid.uuid4(), uuid.uuid4()
    version = _version(
        version_id=version_id, document_id=document_id, number=1, stored=stored, uploader=user.id
    )
    await store_upload(storage, version.storage_key, upload, stored)
    try:
        session.add(
            Document(
                id=document_id,
                title=data.title,
                description=data.description or None,
                owner_id=user.id,
                department_id=department_id,
                visibility=data.visibility.value,
                status=DocumentStatus.ACTIVE.value,
                category=data.category.value,
            )
        )
        await session.flush()
        session.add(version)
        await session.flush()
        document = await document_repo.get_document_for_update(session, document_id)
        assert document is not None  # noqa: S101 - inserted above
        document.current_version_id = version_id
        audit.record(
            session,
            AuditAction.DOCUMENT_UPLOADED,
            actor_id=user.id,
            meta=meta,
            entity_type="document",
            entity_id=document_id,
            details={
                "version": 1,
                "filename": stored.inspected.filename,
                "file_type": stored.inspected.file_type.value,
                "size_bytes": stored.size_bytes,
            },
        )
        await session.commit()
    except Exception:
        await session.rollback()
        await discard_object(storage, version.storage_key)
        raise
    await processor.enqueue(version_id)
    return document_id


async def add_version(
    session: AsyncSession,
    settings: Settings,
    storage: DocumentStorage,
    processor: DocumentProcessor,
    user: CurrentUser,
    document_id: uuid.UUID,
    upload: UploadFile,
    meta: RequestMeta,
) -> None:
    access = await get_access(session, user, document_id)
    _deny(access.capabilities.can_upload_version, "คุณไม่มีสิทธิ์อัปโหลดเวอร์ชันใหม่ของเอกสารนี้")
    stored = await receive_upload(upload, settings)
    version_id = uuid.uuid4()
    key = f"documents/{document_id}/{version_id}"
    await store_upload(storage, key, upload, stored)
    try:
        document = await document_repo.get_document_for_update(session, document_id)
        if document is None:
            raise NotFoundError(NOT_FOUND)
        number = await document_repo.next_version_number(session, document_id)
        session.add(
            _version(
                version_id=version_id,
                document_id=document_id,
                number=number,
                stored=stored,
                uploader=user.id,
            )
        )
        await session.flush()
        document.current_version_id = version_id
        audit.record(
            session,
            AuditAction.DOCUMENT_VERSION_UPLOADED,
            actor_id=user.id,
            meta=meta,
            entity_type="document",
            entity_id=document_id,
            details={
                "version": number,
                "filename": stored.inspected.filename,
                "file_type": stored.inspected.file_type.value,
                "size_bytes": stored.size_bytes,
            },
        )
        await session.commit()
    except Exception:
        await session.rollback()
        await discard_object(storage, key)
        raise
    await processor.enqueue(version_id)


async def update_document(
    session: AsyncSession,
    user: CurrentUser,
    document_id: uuid.UUID,
    data: DocumentUpdate,
    meta: RequestMeta,
) -> None:
    access = await get_access(session, user, document_id)
    _deny(access.capabilities.can_edit, "คุณไม่มีสิทธิ์แก้ไขเอกสารนี้")
    changes = data.model_dump(exclude_unset=True)
    if "visibility" in changes or "department_id" in changes:
        _deny(access.capabilities.can_manage, "การเปลี่ยนระดับการเข้าถึงหรือแผนกต้องมีสิทธิ์จัดการเอกสาร")
    document = await document_repo.get_document_for_update(session, document_id)
    if document is None:
        raise NotFoundError(NOT_FOUND)

    visibility = DocumentVisibility(changes.get("visibility") or document.visibility)
    department_id = changes.get("department_id", document.department_id)
    if "visibility" in changes or "department_id" in changes:
        if department_id != document.department_id:
            await _resolve_department(session, user, department_id, visibility)
        elif visibility is DocumentVisibility.DEPARTMENT and department_id is None:
            await _resolve_department(session, user, None, visibility)

    changed: list[str] = []
    for field in ("title", "description", "category", "status", "visibility"):
        if field in changes and changes[field] is not None:
            value = changes[field]
            value = value.value if hasattr(value, "value") else value
            if field == "description":
                value = value or None
            if getattr(document, field) != value:
                setattr(document, field, value)
                changed.append(field)
    if "description" in changes and changes["description"] is None and document.description:
        document.description = None
        changed.append("description")
    if "department_id" in changes and document.department_id != department_id:
        document.department_id = department_id
        changed.append("department_id")
    if not changed:
        await session.rollback()
        return
    audit.record(
        session,
        AuditAction.DOCUMENT_UPDATED,
        actor_id=user.id,
        meta=meta,
        entity_type="document",
        entity_id=document_id,
        details={"fields": sorted(changed)},
    )
    await session.commit()


async def delete_document(
    session: AsyncSession, user: CurrentUser, document_id: uuid.UUID, meta: RequestMeta
) -> None:
    access = await get_access(session, user, document_id)
    _deny(access.capabilities.can_delete, "คุณไม่มีสิทธิ์ลบเอกสารนี้")
    document = await document_repo.get_document_for_update(session, document_id)
    if document is None:
        raise NotFoundError(NOT_FOUND)
    document.deleted_at = utcnow()
    audit.record(
        session,
        AuditAction.DOCUMENT_DELETED,
        actor_id=user.id,
        meta=meta,
        entity_type="document",
        entity_id=document_id,
        details={"title": document.title},
    )
    await session.commit()


async def reprocess_version(
    session: AsyncSession,
    processor: DocumentProcessor,
    user: CurrentUser,
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    meta: RequestMeta,
) -> None:
    access = await get_access(session, user, document_id)
    _deny(access.capabilities.can_edit, "คุณไม่มีสิทธิ์สั่งประมวลผลเอกสารนี้ใหม่")
    version = await document_repo.get_version(session, document_id, version_id)
    if version is None:
        raise NotFoundError("ไม่พบเวอร์ชันนี้")
    if version.processing_status in (
        ProcessingStatus.READY.value,
        ProcessingStatus.PROCESSING.value,
    ):
        raise ConflictError("เวอร์ชันนี้ประมวลผลแล้วหรือกำลังประมวลผลอยู่")
    version.processing_status = ProcessingStatus.PENDING.value
    version.processing_error = None
    audit.record(
        session,
        AuditAction.DOCUMENT_REPROCESS_REQUESTED,
        actor_id=user.id,
        meta=meta,
        entity_type="document",
        entity_id=document_id,
        details={"version": version.version_number},
    )
    await session.commit()
    await processor.enqueue(version_id, force=True)


async def open_download(
    session: AsyncSession,
    storage: DocumentStorage,
    user: CurrentUser,
    document_id: uuid.UUID,
    version_id: uuid.UUID | None,
    meta: RequestMeta,
) -> tuple[DocumentVersion, ObjectStream]:
    row = await document_repo.get_document(session, user, document_id)
    if row is None:
        raise NotFoundError(NOT_FOUND)
    target = version_id or row.document.current_version_id
    version = await document_repo.get_version(session, document_id, target) if target else None
    if version is None:
        raise NotFoundError("ไม่พบไฟล์ของเอกสารนี้")
    stream = await open_object(storage, version.storage_key)
    audit.record(
        session,
        AuditAction.DOCUMENT_DOWNLOADED,
        actor_id=user.id,
        meta=meta,
        entity_type="document",
        entity_id=document_id,
        details={"version": version.version_number},
    )
    await session.commit()
    return version, stream


# --- ACL ------------------------------------------------------------------------------


async def _validate_principals(
    session: AsyncSession, document: Document, entries: list[AclEntryIn]
) -> None:
    seen: set[tuple[str, uuid.UUID]] = set()
    errors: list[ErrorDetail] = []
    for index, entry in enumerate(entries):
        key = (entry.principal_type.value, entry.principal_id)
        if key in seen:
            errors.append(ErrorDetail(field=f"entries.{index}", message="ระบุผู้รับสิทธิ์ซ้ำ"))
        seen.add(key)
        if entry.principal_type is PrincipalType.USER and entry.principal_id == document.owner_id:
            errors.append(ErrorDetail(field=f"entries.{index}", message="เจ้าของเอกสารมีสิทธิ์เต็มอยู่แล้ว"))
    names = await document_repo.principal_names(session, list(seen))
    for index, entry in enumerate(entries):
        if (entry.principal_type.value, entry.principal_id) not in names:
            errors.append(ErrorDetail(field=f"entries.{index}", message="ไม่พบผู้รับสิทธิ์นี้"))
    if errors:
        raise ValidationFailedError(details=errors)


async def replace_acl(
    session: AsyncSession,
    user: CurrentUser,
    document_id: uuid.UUID,
    entries: list[AclEntryIn],
    meta: RequestMeta,
) -> None:
    access = await get_access(session, user, document_id)
    _deny(access.capabilities.can_manage_access, "คุณไม่มีสิทธิ์กำหนดการเข้าถึงเอกสารนี้")
    document = await document_repo.get_document_for_update(session, document_id)
    if document is None:
        raise NotFoundError(NOT_FOUND)
    await _validate_principals(session, document, entries)

    current = {
        (a.principal_type, a.principal_id): a
        for a in await document_repo.list_acl(session, document_id)
    }
    wanted = {(e.principal_type.value, e.principal_id): e for e in entries}
    newly_shared: list[tuple[uuid.UUID, AccessLevel]] = []
    for key, stale in current.items():
        if key not in wanted:
            await session.delete(stale)
    for key, entry in wanted.items():
        row = current.get(key)
        if row is None:
            session.add(
                DocumentAcl(
                    document_id=document_id,
                    principal_type=entry.principal_type.value,
                    principal_id=entry.principal_id,
                    access_level=entry.access_level.value,
                    granted_by=user.id,
                )
            )
        elif row.access_level != entry.access_level.value:
            upgraded = entry.access_level.rank > AccessLevel(row.access_level).rank
            row.access_level = entry.access_level.value
            row.granted_by = user.id
            if not upgraded:
                continue
        else:
            continue
        if entry.principal_type is PrincipalType.USER and entry.principal_id != user.id:
            newly_shared.append((entry.principal_id, entry.access_level))

    for recipient, level in newly_shared:
        notifications.document_shared(
            session,
            recipient,
            document_id=document_id,
            title=document.title,
            level_label=LEVEL_LABELS[level],
            shared_by=user.display_name,
        )
    audit.record(
        session,
        AuditAction.DOCUMENT_ACL_CHANGED,
        actor_id=user.id,
        meta=meta,
        entity_type="document",
        entity_id=document_id,
        details={
            "entries": [
                {
                    "principal_type": e.principal_type.value,
                    "principal_id": str(e.principal_id),
                    "access_level": e.access_level.value,
                }
                for e in entries
            ],
            "removed": len([k for k in current if k not in wanted]),
        },
    )
    await session.commit()
