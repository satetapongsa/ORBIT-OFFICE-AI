"""Files and images in chat (ADR-072)

Revision ID: 0022
Revises: 0021
Create Date: 2026-11-23 07:02:12.039757+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MAX = 4000
NEW_CHECK = f"char_length(body) <= {MAX} AND (char_length(body) >= 1 OR attachment_id IS NOT NULL)"
OLD_CHECK = f"char_length(body) BETWEEN 1 AND {MAX}"


def upgrade() -> None:
    op.create_table(
        "chat_attachments",
        sa.Column("conversation_id", sa.UUID(), nullable=True),
        sa.Column("group_id", sa.UUID(), nullable=True),
        sa.Column("uploaded_by", sa.UUID(), nullable=True),
        sa.Column("storage_key", sa.String(length=300), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("file_type", sa.String(length=10), nullable=False),
        sa.Column("mime_type", sa.String(length=150), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint(
            "num_nonnulls(conversation_id, group_id) = 1", name=op.f("ck_chat_attachments_one_chat")
        ),
        sa.CheckConstraint("size_bytes >= 0", name=op.f("ck_chat_attachments_size_bytes")),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name=op.f("fk_chat_attachments_conversation_id_conversations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["chat_groups.id"],
            name=op.f("fk_chat_attachments_group_id_chat_groups"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by"],
            ["users.id"],
            name=op.f("fk_chat_attachments_uploaded_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chat_attachments")),
        sa.UniqueConstraint("storage_key", name=op.f("uq_chat_attachments_storage_key")),
    )
    op.create_index(
        op.f("ix_chat_attachments_conversation_id"),
        "chat_attachments",
        ["conversation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_chat_attachments_group_id"), "chat_attachments", ["group_id"], unique=False
    )
    op.add_column("direct_messages", sa.Column("attachment_id", sa.UUID(), nullable=True))
    op.create_unique_constraint(
        op.f("uq_direct_messages_attachment_id"), "direct_messages", ["attachment_id"]
    )
    op.create_foreign_key(
        op.f("fk_direct_messages_attachment_id_chat_attachments"),
        "direct_messages",
        "chat_attachments",
        ["attachment_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.add_column("group_messages", sa.Column("attachment_id", sa.UUID(), nullable=True))
    op.create_unique_constraint(
        op.f("uq_group_messages_attachment_id"), "group_messages", ["attachment_id"]
    )
    op.create_foreign_key(
        op.f("fk_group_messages_attachment_id_chat_attachments"),
        "group_messages",
        "chat_attachments",
        ["attachment_id"],
        ["id"],
        ondelete="CASCADE",
    )
    # A message with a file may have an empty caption.
    for table in ("direct_messages", "group_messages"):
        op.drop_constraint(op.f(f"ck_{table}_body_length"), table, type_="check")
        op.create_check_constraint(op.f(f"ck_{table}_body_length"), table, NEW_CHECK)
    op.execute("ALTER TABLE public.chat_attachments ENABLE ROW LEVEL SECURITY")
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN "
        "REVOKE ALL ON public.chat_attachments FROM anon, authenticated; END IF; END $$;"
    )


def downgrade() -> None:
    for table in ("direct_messages", "group_messages"):
        op.execute(f"DELETE FROM {table} WHERE char_length(body) = 0")
        op.drop_constraint(op.f(f"ck_{table}_body_length"), table, type_="check")
        op.create_check_constraint(op.f(f"ck_{table}_body_length"), table, OLD_CHECK)
    op.drop_constraint(
        op.f("fk_group_messages_attachment_id_chat_attachments"),
        "group_messages",
        type_="foreignkey",
    )
    op.drop_constraint(op.f("uq_group_messages_attachment_id"), "group_messages", type_="unique")
    op.drop_column("group_messages", "attachment_id")
    op.drop_constraint(
        op.f("fk_direct_messages_attachment_id_chat_attachments"),
        "direct_messages",
        type_="foreignkey",
    )
    op.drop_constraint(op.f("uq_direct_messages_attachment_id"), "direct_messages", type_="unique")
    op.drop_column("direct_messages", "attachment_id")
    op.drop_index(op.f("ix_chat_attachments_group_id"), table_name="chat_attachments")
    op.drop_index(op.f("ix_chat_attachments_conversation_id"), table_name="chat_attachments")
    op.drop_table("chat_attachments")
