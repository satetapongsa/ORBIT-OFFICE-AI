"""RAG: document chunks with embeddings, version index status, chat citations.

The embedding dimension (1024) is fixed here; changing the embedding model to one with another
dimension needs a new migration and a full re-index (ADR-042).

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-12 05:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "document_versions",
        sa.Column("index_status", sa.String(length=20), nullable=False, server_default="PENDING"),
    )
    op.add_column("document_versions", sa.Column("index_error", sa.String(length=500)))
    op.add_column("document_versions", sa.Column("indexed_at", sa.DateTime(timezone=True)))
    op.add_column("document_versions", sa.Column("chunk_count", sa.Integer()))
    op.create_check_constraint(
        op.f("ck_document_versions_index_status"),
        "document_versions",
        "index_status IN ('PENDING', 'INDEXING', 'READY', 'FAILED', 'SKIPPED')",
    )

    op.create_table(
        "document_chunks",
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("document_version_id", sa.UUID(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("char_count", sa.Integer(), nullable=False),
        sa.Column("embedding_model", sa.String(length=200), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_document_chunks_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_version_id"],
            ["document_versions.id"],
            name=op.f("fk_document_chunks_document_version_id_document_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_chunks")),
        sa.UniqueConstraint(
            "document_version_id", "chunk_index", name="uq_document_chunks_index"
        ),
    )
    op.execute("ALTER TABLE document_chunks ADD COLUMN embedding vector(1024)")
    op.create_index("ix_document_chunks_document_id", "document_chunks", ["document_id"])
    op.execute(
        "CREATE INDEX ix_document_chunks_embedding ON document_chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )
    op.create_index(
        "ix_document_chunks_content_trgm",
        "document_chunks",
        ["content"],
        postgresql_using="gin",
        postgresql_ops={"content": "gin_trgm_ops"},
    )

    op.add_column(
        "chat_messages", sa.Column("citations", postgresql.JSONB(astext_type=sa.Text()))
    )


def downgrade() -> None:
    op.drop_column("chat_messages", "citations")
    op.drop_table("document_chunks")
    op.drop_constraint(
        op.f("ck_document_versions_index_status"), "document_versions", type_="check"
    )
    op.drop_column("document_versions", "chunk_count")
    op.drop_column("document_versions", "indexed_at")
    op.drop_column("document_versions", "index_error")
    op.drop_column("document_versions", "index_status")
