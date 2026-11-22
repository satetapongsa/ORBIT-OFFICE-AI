"""Direct messages between users and private notes (ADR-060)

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-22 10:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_TABLES = ("conversations", "direct_messages", "notes")


def _id() -> sa.Column:
    return sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False)


def _now(name: str) -> sa.Column:
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("user_low_id", sa.UUID(), nullable=False),
        sa.Column("user_high_id", sa.UUID(), nullable=False),
        _now("created_at"),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("low_last_read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("high_last_read_at", sa.DateTime(timezone=True), nullable=True),
        _id(),
        sa.CheckConstraint(
            "user_low_id < user_high_id", name=op.f("ck_conversations_ordered_pair")
        ),
        sa.ForeignKeyConstraint(
            ["user_low_id"],
            ["users.id"],
            name=op.f("fk_conversations_user_low_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_high_id"],
            ["users.id"],
            name=op.f("fk_conversations_user_high_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_conversations")),
    )
    op.create_index(
        "uq_conversations_pair", "conversations", ["user_low_id", "user_high_id"], unique=True
    )
    op.create_index("ix_conversations_user_high_id", "conversations", ["user_high_id"])

    op.create_table(
        "direct_messages",
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column("sender_id", sa.UUID(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        _now("created_at"),
        _id(),
        sa.CheckConstraint(
            "char_length(body) BETWEEN 1 AND 4000", name=op.f("ck_direct_messages_body_length")
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name=op.f("fk_direct_messages_conversation_id_conversations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["sender_id"],
            ["users.id"],
            name=op.f("fk_direct_messages_sender_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_direct_messages")),
    )
    op.create_index(
        "ix_direct_messages_conversation_created",
        "direct_messages",
        ["conversation_id", "created_at"],
    )

    op.create_table(
        "notes",
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        _now("content_updated_at"),
        sa.Column("ai_summary", sa.Text(), nullable=True),
        sa.Column("ai_summary_at", sa.DateTime(timezone=True), nullable=True),
        _now("created_at"),
        _now("updated_at"),
        _id(),
        sa.CheckConstraint(
            "char_length(content) <= 20000", name=op.f("ck_notes_content_length")
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], name=op.f("fk_notes_owner_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notes")),
    )
    op.create_index("ix_notes_owner_content_updated", "notes", ["owner_id", "content_updated_at"])

    # Same lock as migration 0011: hosted data APIs (Supabase) must not reach these tables.
    for table in NEW_TABLES:
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
                REVOKE ALL ON public.conversations, public.direct_messages, public.notes
                    FROM anon, authenticated;
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.drop_table("notes")
    op.drop_table("direct_messages")
    op.drop_table("conversations")
