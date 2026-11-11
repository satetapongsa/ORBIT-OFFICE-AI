"""Document Center endpoints (HTTP only — rules live in ``app.services.documents``)."""

from __future__ import annotations

import uuid
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status
from fastapi.responses import StreamingResponse

from app.api.deps import (
    CurrentUserDep,
    DbDep,
    EmbeddingDep,
    MetaDep,
    SettingsDep,
    get_document_processor,
    get_document_storage,
    require_permissions,
)
from app.core.permissions import P
from app.core.principal import CurrentUser
from app.models.document import (
    DocumentCategory,
    DocumentStatus,
    DocumentVisibility,
    ProcessingStatus,
)
from app.repositories.documents import DocumentFilters, SortKey
from app.schemas.documents import (
    AclOut,
    AclReplace,
    ContentSearchHit,
    ContentSearchResult,
    DocumentCreate,
    DocumentDetail,
    DocumentHistoryItem,
    DocumentPage,
    DocumentText,
    DocumentUpdate,
)
from app.services.documents import queries
from app.services.documents import service as document_service
from app.services.documents.service import DocumentProcessor, DocumentStorage
from app.services.rag import search as rag

router = APIRouter(prefix="/documents", tags=["documents"])

SNIPPET_CHARS = 400

StorageDep = Annotated[DocumentStorage, Depends(get_document_storage)]
ProcessorDep = Annotated[DocumentProcessor, Depends(get_document_processor)]


def content_disposition(filename: str) -> str:
    """RFC 6266 / 5987: ASCII fallback plus the UTF-8 (Thai) name."""
    ascii_name = filename.encode("ascii", "ignore").decode() or "document"
    ascii_name = ascii_name.replace('"', "").replace("\\", "")
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"


@router.get("", response_model=DocumentPage, summary="List documents I can access")
async def list_documents(
    db: DbDep,
    user: CurrentUserDep,
    q: Annotated[str | None, Query(max_length=200)] = None,
    category: DocumentCategory | None = None,
    visibility: DocumentVisibility | None = None,
    status_: Annotated[DocumentStatus | None, Query(alias="status")] = None,
    processing_status: ProcessingStatus | None = None,
    department_id: uuid.UUID | None = None,
    mine: bool = False,
    sort: SortKey = "updated",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> DocumentPage:
    filters = DocumentFilters(
        q=q,
        category=category.value if category else None,
        visibility=visibility.value if visibility else None,
        status=status_.value if status_ else None,
        processing_status=processing_status.value if processing_status else None,
        department_id=department_id,
        owner_id=user.id if mine else None,
    )
    return await queries.list_documents(
        db, user, filters, sort=sort, page=page, page_size=page_size
    )


@router.get(
    "/search",
    response_model=ContentSearchResult,
    summary="Search inside the documents I can access (semantic + keyword)",
)
async def search_content(
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permissions(P.DOCUMENTS_READ))],
    embedder: EmbeddingDep,
    q: Annotated[str, Query(min_length=1, max_length=500)],
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> ContentSearchResult:
    result = await rag.search(db, user, q, limit=limit * 3, embedder=embedder)
    return ContentSearchResult(
        query=q.strip(),
        mode=result.mode,
        degraded=result.degraded,
        results=[
            ContentSearchHit(
                document_id=h.document_id,
                title=h.title,
                category=DocumentCategory(h.category),
                version_number=h.version_number,
                page=h.page,
                snippet=h.content[:SNIPPET_CHARS],
                score=round(h.score, 4),
            )
            for h in rag.best_per_document(result.hits, limit=limit)
        ],
    )


@router.post(
    "",
    response_model=DocumentDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a new document (multipart: file + metadata)",
)
async def upload_document(
    db: DbDep,
    settings: SettingsDep,
    user: CurrentUserDep,
    meta: MetaDep,
    storage: StorageDep,
    processor: ProcessorDep,
    data: Annotated[DocumentCreate, Form()],
    file: Annotated[UploadFile, File(description="PDF, DOCX, XLSX or TXT")],
) -> DocumentDetail:
    document_id = await document_service.create_document(
        db, settings, storage, processor, user, data, file, meta
    )
    return await queries.get_detail(db, user, document_id)


@router.get("/{document_id}", response_model=DocumentDetail, summary="Document details")
async def get_document(document_id: uuid.UUID, db: DbDep, user: CurrentUserDep) -> DocumentDetail:
    return await queries.get_detail(db, user, document_id)


@router.patch("/{document_id}", response_model=DocumentDetail, summary="Update metadata")
async def update_document(
    document_id: uuid.UUID, body: DocumentUpdate, db: DbDep, user: CurrentUserDep, meta: MetaDep
) -> DocumentDetail:
    await document_service.update_document(db, user, document_id, body, meta)
    return await queries.get_detail(db, user, document_id)


@router.delete(
    "/{document_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete (soft) a document"
)
async def delete_document(
    document_id: uuid.UUID, db: DbDep, user: CurrentUserDep, meta: MetaDep
) -> Response:
    await document_service.delete_document(db, user, document_id, meta)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{document_id}/versions",
    response_model=DocumentDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a new version (becomes current)",
)
async def upload_version(
    document_id: uuid.UUID,
    db: DbDep,
    settings: SettingsDep,
    user: CurrentUserDep,
    meta: MetaDep,
    storage: StorageDep,
    processor: ProcessorDep,
    file: Annotated[UploadFile, File(description="PDF, DOCX, XLSX or TXT")],
) -> DocumentDetail:
    await document_service.add_version(
        db, settings, storage, processor, user, document_id, file, meta
    )
    return await queries.get_detail(db, user, document_id)


@router.post(
    "/{document_id}/versions/{version_id}/reprocess",
    response_model=DocumentDetail,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue text extraction again for a failed or stuck version",
)
async def reprocess_version(
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    db: DbDep,
    user: CurrentUserDep,
    meta: MetaDep,
    processor: ProcessorDep,
) -> DocumentDetail:
    await document_service.reprocess_version(db, processor, user, document_id, version_id, meta)
    return await queries.get_detail(db, user, document_id)


@router.get(
    "/{document_id}/download",
    summary="Download the current (or a given) version",
    response_class=StreamingResponse,
)
async def download_document(
    document_id: uuid.UUID,
    db: DbDep,
    user: CurrentUserDep,
    meta: MetaDep,
    storage: StorageDep,
    version_id: uuid.UUID | None = None,
) -> StreamingResponse:
    version, stream = await document_service.open_download(
        db, storage, user, document_id, version_id, meta
    )
    return StreamingResponse(
        iter(stream),
        media_type=version.mime_type,
        headers={
            "Content-Disposition": content_disposition(version.original_filename),
            "Content-Length": str(version.size_bytes),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@router.get("/{document_id}/text", response_model=DocumentText, summary="Extracted text preview")
async def get_text(
    document_id: uuid.UUID, db: DbDep, user: CurrentUserDep, version_id: uuid.UUID | None = None
) -> DocumentText:
    return await queries.get_text(db, user, document_id, version_id)


@router.get("/{document_id}/acl", response_model=AclOut, summary="Who else can access")
async def get_acl(document_id: uuid.UUID, db: DbDep, user: CurrentUserDep) -> AclOut:
    return await queries.get_acl(db, user, document_id)


@router.put("/{document_id}/acl", response_model=AclOut, summary="Replace explicit grants")
async def replace_acl(
    document_id: uuid.UUID, body: AclReplace, db: DbDep, user: CurrentUserDep, meta: MetaDep
) -> AclOut:
    await document_service.replace_acl(db, user, document_id, body.entries, meta)
    return await queries.get_acl(db, user, document_id)


@router.get(
    "/{document_id}/history",
    response_model=list[DocumentHistoryItem],
    summary="Audit history of this document",
)
async def get_history(
    document_id: uuid.UUID, db: DbDep, user: CurrentUserDep
) -> list[DocumentHistoryItem]:
    return await queries.get_history(db, user, document_id)
