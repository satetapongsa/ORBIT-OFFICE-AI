"""Documents, versions, extracted text and the document ACL.

Access to every row here is decided by the single predicate in
``app.repositories.document_access`` (see docs/SECURITY.md §3).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.identity import _in_check


class DocumentVisibility(StrEnum):
    PRIVATE = "PRIVATE"  # owner (+ explicit ACL grants) only
    DEPARTMENT = "DEPARTMENT"  # members of the owning department
    COMPANY = "COMPANY"  # every active employee
    RESTRICTED = "RESTRICTED"  # explicit ACL grants only (owner included)


class DocumentStatus(StrEnum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class DocumentCategory(StrEnum):
    POLICY = "POLICY"
    PROCEDURE = "PROCEDURE"
    FORM = "FORM"
    REPORT = "REPORT"
    CONTRACT = "CONTRACT"
    MANUAL = "MANUAL"
    OTHER = "OTHER"


class FileType(StrEnum):
    """Supported upload formats (decided by content sniffing, not by the client)."""

    PDF = "PDF"
    DOCX = "DOCX"
    XLSX = "XLSX"
    TXT = "TXT"


class ProcessingStatus(StrEnum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    READY = "READY"
    FAILED = "FAILED"


class PrincipalType(StrEnum):
    USER = "USER"
    DEPARTMENT = "DEPARTMENT"
    ROLE = "ROLE"


class AccessLevel(StrEnum):
    VIEW = "VIEW"
    EDIT = "EDIT"
    MANAGE = "MANAGE"

    @property
    def rank(self) -> int:
        return _ACCESS_RANK[self]

    def at_least(self) -> list[str]:
        """Access levels that satisfy this level (``EDIT`` → ``EDIT``, ``MANAGE``)."""
        return [lvl.value for lvl in AccessLevel if lvl.rank >= self.rank]


_ACCESS_RANK = {AccessLevel.VIEW: 1, AccessLevel.EDIT: 2, AccessLevel.MANAGE: 3}


class Document(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "documents"

    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL")
    )
    visibility: Mapped[str] = mapped_column(
        String(20), nullable=False, default=DocumentVisibility.PRIVATE.value
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=DocumentStatus.DRAFT.value
    )
    category: Mapped[str] = mapped_column(
        String(20), nullable=False, default=DocumentCategory.OTHER.value
    )
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("document_versions.id", ondelete="SET NULL", use_alter=True)
    )

    __table_args__ = (
        CheckConstraint(_in_check("visibility", DocumentVisibility), name="visibility"),
        CheckConstraint(_in_check("status", DocumentStatus), name="status"),
        CheckConstraint(_in_check("category", DocumentCategory), name="category"),
        Index("ix_documents_owner_id", "owner_id"),
        Index("ix_documents_department_id", "department_id"),
        Index("ix_documents_updated_at", "updated_at"),
        Index(
            "ix_documents_title_trgm",
            "title",
            postgresql_using="gin",
            postgresql_ops={"title": "gin_trgm_ops"},
        ),
    )


class DocumentVersion(UUIDPrimaryKeyMixin, Base):
    """One uploaded file. The object lives in storage under ``storage_key``."""

    __tablename__ = "document_versions"

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    # Server-generated (documents/{document_id}/{version_id}); never derived from user input.
    storage_key: Mapped[str] = mapped_column(String(300), nullable=False, unique=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(10), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(150), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    processing_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ProcessingStatus.PENDING.value
    )
    processing_error: Mapped[str | None] = mapped_column(String(500))
    page_count: Mapped[int | None] = mapped_column(Integer)
    char_count: Mapped[int | None] = mapped_column(Integer)
    processed_at: Mapped[datetime | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("document_id", "version_number", name="uq_document_versions_number"),
        CheckConstraint(_in_check("file_type", FileType), name="file_type"),
        CheckConstraint(_in_check("processing_status", ProcessingStatus), name="processing_status"),
        CheckConstraint("size_bytes >= 0", name="size_bytes"),
        Index("ix_document_versions_processing_status", "processing_status"),
    )


class DocumentVersionText(Base):
    """Extracted plain text of a version (kept apart so listings never load it).

    Document text is **untrusted** input: it is shown escaped and, from Phase 7, sent to the
    model only inside delimited data sections after the ACL check.
    """

    __tablename__ = "document_version_texts"

    document_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE"), primary_key=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)


class DocumentAcl(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "document_acl"

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    principal_type: Mapped[str] = mapped_column(String(20), nullable=False)
    principal_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    access_level: Mapped[str] = mapped_column(String(20), nullable=False)
    granted_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    __table_args__ = (
        UniqueConstraint(
            "document_id", "principal_type", "principal_id", name="uq_document_acl_principal"
        ),
        CheckConstraint(_in_check("principal_type", PrincipalType), name="principal_type"),
        CheckConstraint(_in_check("access_level", AccessLevel), name="access_level"),
        Index("ix_document_acl_principal", "principal_type", "principal_id"),
    )
