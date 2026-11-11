"""Document ACL foundation (Phase 2).

Phase 2 creates the core ``documents`` row and ``document_acl`` so the single access
predicate (``app.repositories.document_access``) can be built and tested now. Versions,
storage, categories and processing columns are added by the Phase 4 migration.
"""

from __future__ import annotations

import uuid
from enum import StrEnum

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint
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

    __table_args__ = (
        CheckConstraint(_in_check("visibility", DocumentVisibility), name="visibility"),
        CheckConstraint(_in_check("status", DocumentStatus), name="status"),
        Index("ix_documents_owner_id", "owner_id"),
        Index("ix_documents_department_id", "department_id"),
    )


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
