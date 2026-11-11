"""Document Center schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.models.document import (
    AccessLevel,
    DocumentCategory,
    DocumentStatus,
    DocumentVisibility,
    FileType,
    IndexStatus,
    PrincipalType,
    ProcessingStatus,
)
from app.schemas.identity import DepartmentRef

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000)]


class UserRef(BaseModel):
    id: uuid.UUID
    display_name: str


class DocumentCreate(BaseModel):
    """Metadata sent with the first upload (multipart form fields)."""

    title: Title
    description: Description | None = None
    category: DocumentCategory = DocumentCategory.OTHER
    visibility: DocumentVisibility = DocumentVisibility.PRIVATE
    department_id: uuid.UUID | None = None


class DocumentUpdate(BaseModel):
    title: Title | None = None
    description: Description | None = None
    category: DocumentCategory | None = None
    status: DocumentStatus | None = None
    visibility: DocumentVisibility | None = None
    department_id: uuid.UUID | None = None


class VersionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    version_number: int
    original_filename: str
    file_type: FileType
    size_bytes: int
    processing_status: ProcessingStatus
    index_status: IndexStatus


class VersionOut(VersionSummary):
    mime_type: str
    sha256: str
    uploaded_by: UserRef | None
    processing_error: str | None
    page_count: int | None
    char_count: int | None
    processed_at: datetime | None
    index_error: str | None
    chunk_count: int | None
    indexed_at: datetime | None
    created_at: datetime


class DocumentListItem(BaseModel):
    id: uuid.UUID
    title: str
    description: str | None
    category: DocumentCategory
    visibility: DocumentVisibility
    status: DocumentStatus
    owner: UserRef
    department: DepartmentRef | None
    current_version: VersionSummary | None
    created_at: datetime
    updated_at: datetime


class DocumentCapabilities(BaseModel):
    can_edit: bool
    can_manage: bool
    can_delete: bool
    can_manage_access: bool
    can_upload_version: bool
    can_view_history: bool


class DocumentDetail(DocumentListItem):
    access_level: AccessLevel
    capabilities: DocumentCapabilities
    versions: list[VersionOut]


class DocumentPage(BaseModel):
    items: list[DocumentListItem]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)


class AclEntryIn(BaseModel):
    principal_type: PrincipalType
    principal_id: uuid.UUID
    access_level: AccessLevel


class AclReplace(BaseModel):
    entries: list[AclEntryIn] = Field(max_length=200)


class AclEntryOut(BaseModel):
    id: uuid.UUID
    principal_type: PrincipalType
    principal_id: uuid.UUID
    principal_name: str
    access_level: AccessLevel
    granted_by: UserRef | None
    created_at: datetime


class AclOut(BaseModel):
    visibility: DocumentVisibility
    owner: UserRef
    entries: list[AclEntryOut]


class DocumentText(BaseModel):
    version_id: uuid.UUID
    version_number: int
    content: str
    char_count: int
    truncated: bool = Field(description="True when only the beginning is returned (preview).")


class DocumentHistoryItem(BaseModel):
    id: uuid.UUID
    action: str
    occurred_at: datetime
    actor: UserRef | None
    details: dict[str, Any]


class DirectoryUser(BaseModel):
    """Directory-safe fields only (no e-mail, phone or HR data)."""

    id: uuid.UUID
    display_name: str
    job_title: str | None
    department: DepartmentRef | None


class ContentSearchHit(BaseModel):
    document_id: uuid.UUID
    title: str
    category: DocumentCategory
    version_number: int
    page: int | None
    snippet: str = Field(description="The best matching passage (plain text, untrusted).")
    score: float


class ContentSearchResult(BaseModel):
    query: str
    mode: Literal["hybrid", "keyword"]
    degraded: bool = Field(description="Semantic search is configured but was unavailable.")
    results: list[ContentSearchHit]
