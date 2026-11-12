"""Ticket attachments (documents and PNG/JPEG screenshots, public or internal)

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-12 01:38:13.967169+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ticket_attachments",
        sa.Column("ticket_id", sa.UUID(), nullable=False),
        sa.Column("storage_key", sa.String(length=300), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("file_type", sa.String(length=10), nullable=False),
        sa.Column("mime_type", sa.String(length=150), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("is_internal", sa.Boolean(), nullable=False),
        sa.Column("uploaded_by", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint(
            "file_type IN ('PDF', 'DOCX', 'XLSX', 'TXT', 'PNG', 'JPEG')",
            name=op.f("ck_ticket_attachments_file_type"),
        ),
        sa.CheckConstraint("size_bytes >= 0", name=op.f("ck_ticket_attachments_size_bytes")),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["tickets.id"],
            name=op.f("fk_ticket_attachments_ticket_id_tickets"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by"],
            ["users.id"],
            name=op.f("fk_ticket_attachments_uploaded_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ticket_attachments")),
        sa.UniqueConstraint("storage_key", name=op.f("uq_ticket_attachments_storage_key")),
    )
    op.create_index(
        "ix_ticket_attachments_ticket_created",
        "ticket_attachments",
        ["ticket_id", "created_at"],
        unique=False,
    )
    op.drop_constraint(op.f("ck_ticket_events_event_type"), "ticket_events", type_="check")
    op.create_check_constraint(
        op.f("ck_ticket_events_event_type"),
        "ticket_events",
        "event_type IN ('CREATED', 'STATUS_CHANGED', 'ASSIGNED', 'UNASSIGNED', 'PRIORITY_CHANGED', 'CATEGORY_CHANGED', 'COMMENTED', 'ATTACHMENT_ADDED', 'ATTACHMENT_REMOVED')",
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM ticket_events WHERE event_type IN ('ATTACHMENT_ADDED', 'ATTACHMENT_REMOVED')"
    )
    op.drop_constraint(op.f("ck_ticket_events_event_type"), "ticket_events", type_="check")
    op.create_check_constraint(
        op.f("ck_ticket_events_event_type"),
        "ticket_events",
        "event_type IN ('CREATED', 'STATUS_CHANGED', 'ASSIGNED', 'UNASSIGNED', 'PRIORITY_CHANGED', 'CATEGORY_CHANGED', 'COMMENTED')",
    )
    op.drop_index("ix_ticket_attachments_ticket_created", table_name="ticket_attachments")
    op.drop_table("ticket_attachments")
