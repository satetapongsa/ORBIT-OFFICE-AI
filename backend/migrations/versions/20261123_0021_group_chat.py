"""Group chats (ADR-071)

Revision ID: 0021
Revises: 0020
Create Date: 2026-11-23 17:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _ts(name: str, *, nullable: bool = True, now: bool = False) -> sa.Column:
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        server_default=sa.text("now()") if now else None,
        nullable=nullable,
    )


def upgrade() -> None:
    op.create_table(
        "chat_groups",
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        _ts("created_at", nullable=False, now=True),
        _ts("last_message_at"),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_chat_groups_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chat_groups")),
    )
    op.create_table(
        "chat_group_members",
        sa.Column("group_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.String(length=10), nullable=False),
        _ts("joined_at", nullable=False, now=True),
        _ts("last_read_at"),
        _ts("typing_at"),
        sa.CheckConstraint("role IN ('ADMIN', 'MEMBER')", name=op.f("ck_chat_group_members_role")),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["chat_groups.id"],
            name=op.f("fk_chat_group_members_group_id_chat_groups"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_chat_group_members_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("group_id", "user_id", name=op.f("pk_chat_group_members")),
    )
    op.create_index("ix_chat_group_members_user_id", "chat_group_members", ["user_id"])
    op.create_table(
        "group_messages",
        sa.Column("group_id", sa.UUID(), nullable=False),
        sa.Column("sender_id", sa.UUID(), nullable=True),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        _ts("created_at", nullable=False, now=True),
        _ts("edited_at"),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint("kind IN ('TEXT', 'SYSTEM')", name=op.f("ck_group_messages_kind")),
        sa.CheckConstraint(
            "char_length(body) BETWEEN 1 AND 4000", name=op.f("ck_group_messages_body_length")
        ),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["chat_groups.id"],
            name=op.f("fk_group_messages_group_id_chat_groups"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["sender_id"],
            ["users.id"],
            name=op.f("fk_group_messages_sender_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_group_messages")),
    )
    op.create_index(
        "ix_group_messages_group_created", "group_messages", ["group_id", "created_at"]
    )
    for table in ("chat_groups", "chat_group_members", "group_messages"):
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN "
            f"REVOKE ALL ON public.{table} FROM anon, authenticated; END IF; END $$;"
        )


def downgrade() -> None:
    op.drop_table("group_messages")
    op.drop_table("chat_group_members")
    op.drop_table("chat_groups")
