"""Document Center: versions, extracted text, categories, DOCUMENT notifications.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-11 07:18:02.283887+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "document_versions",
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(length=300), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("file_type", sa.String(length=10), nullable=False),
        sa.Column("mime_type", sa.String(length=150), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("uploaded_by", sa.UUID(), nullable=True),
        sa.Column("processing_status", sa.String(length=20), nullable=False),
        sa.Column("processing_error", sa.String(length=500), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("char_count", sa.Integer(), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint(
            "file_type IN ('PDF', 'DOCX', 'XLSX', 'TXT')",
            name=op.f("ck_document_versions_file_type"),
        ),
        sa.CheckConstraint(
            "processing_status IN ('PENDING', 'PROCESSING', 'READY', 'FAILED')",
            name=op.f("ck_document_versions_processing_status"),
        ),
        sa.CheckConstraint("size_bytes >= 0", name=op.f("ck_document_versions_size_bytes")),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_document_versions_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by"],
            ["users.id"],
            name=op.f("fk_document_versions_uploaded_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_versions")),
        sa.UniqueConstraint("document_id", "version_number", name="uq_document_versions_number"),
        sa.UniqueConstraint("storage_key", name=op.f("uq_document_versions_storage_key")),
    )
    op.create_index(
        "ix_document_versions_processing_status",
        "document_versions",
        ["processing_status"],
        unique=False,
    )
    op.create_table(
        "document_version_texts",
        sa.Column("document_version_id", sa.UUID(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_version_id"],
            ["document_versions.id"],
            name=op.f("fk_document_version_texts_document_version_id_document_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("document_version_id", name=op.f("pk_document_version_texts")),
    )
    # Existing rows get OTHER; afterwards the application always sets the category.
    op.add_column(
        "documents",
        sa.Column("category", sa.String(length=20), nullable=False, server_default="OTHER"),
    )
    op.alter_column("documents", "category", server_default=None)
    op.create_check_constraint(
        op.f("ck_documents_category"),
        "documents",
        "category IN ('POLICY', 'PROCEDURE', 'FORM', 'REPORT', 'CONTRACT', 'MANUAL', 'OTHER')",
    )
    op.add_column("documents", sa.Column("current_version_id", sa.UUID(), nullable=True))
    op.create_index(
        "ix_documents_title_trgm",
        "documents",
        ["title"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"title": "gin_trgm_ops"},
    )
    op.create_index("ix_documents_updated_at", "documents", ["updated_at"], unique=False)
    op.create_foreign_key(
        op.f("fk_documents_current_version_id_document_versions"),
        "documents",
        "document_versions",
        ["current_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.drop_constraint(op.f("ck_notifications_type"), "notifications", type_="check")
    op.create_check_constraint(
        op.f("ck_notifications_type"),
        "notifications",
        "type IN ('SECURITY', 'ACCOUNT', 'SYSTEM', 'DOCUMENT')",
    )


def downgrade() -> None:
    op.execute("DELETE FROM notifications WHERE type = 'DOCUMENT'")
    op.drop_constraint(op.f("ck_notifications_type"), "notifications", type_="check")
    op.create_check_constraint(
        op.f("ck_notifications_type"),
        "notifications",
        "type IN ('SECURITY', 'ACCOUNT', 'SYSTEM')",
    )
    op.drop_constraint(
        op.f("fk_documents_current_version_id_document_versions"), "documents", type_="foreignkey"
    )
    op.drop_index("ix_documents_updated_at", table_name="documents")
    op.drop_index(
        "ix_documents_title_trgm",
        table_name="documents",
        postgresql_using="gin",
        postgresql_ops={"title": "gin_trgm_ops"},
    )
    op.drop_column("documents", "current_version_id")
    op.drop_constraint(op.f("ck_documents_category"), "documents", type_="check")
    op.drop_column("documents", "category")
    op.drop_table("document_version_texts")
    op.drop_index("ix_document_versions_processing_status", table_name="document_versions")
    op.drop_table("document_versions")
