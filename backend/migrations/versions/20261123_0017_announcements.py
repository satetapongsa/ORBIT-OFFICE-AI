"""Company announcements; notification types for announcements, leave and meetings (ADR-067)

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-23 13:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_TYPES = "'SECURITY', 'ACCOUNT', 'SYSTEM', 'DOCUMENT', 'TASK', 'TICKET'"
NEW_TYPES = OLD_TYPES + ", 'ANNOUNCEMENT', 'LEAVE', 'MEETING'"


def _lock(*tables: str) -> None:
    """Same lock as migration 0011 (Supabase Data API cannot reach these tables)."""
    for table in tables:
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN "
            f"REVOKE ALL ON public.{table} FROM anon, authenticated; END IF; END $$;"
        )


def upgrade() -> None:
    op.drop_constraint(op.f("ck_notifications_type"), "notifications", type_="check")
    op.create_check_constraint(op.f("ck_notifications_type"), "notifications", f"type IN ({NEW_TYPES})")

    op.create_table(
        "announcements",
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("important", sa.Boolean(), nullable=False),
        sa.Column("pinned", sa.Boolean(), nullable=False),
        sa.Column("department_id", sa.UUID(), nullable=True),
        sa.Column("author_id", sa.UUID(), nullable=True),
        sa.Column(
            "published_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "char_length(body) BETWEEN 1 AND 10000", name=op.f("ck_announcements_body_length")
        ),
        sa.CheckConstraint(
            "expires_at IS NULL OR expires_at > published_at",
            name=op.f("ck_announcements_expiry_order"),
        ),
        sa.ForeignKeyConstraint(
            ["department_id"],
            ["departments.id"],
            name=op.f("fk_announcements_department_id_departments"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["author_id"],
            ["users.id"],
            name=op.f("fk_announcements_author_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_announcements")),
    )
    op.create_index("ix_announcements_published", "announcements", ["published_at"])
    op.create_index("ix_announcements_department_id", "announcements", ["department_id"])

    op.create_table(
        "announcement_reads",
        sa.Column("announcement_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column(
            "read_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["announcement_id"],
            ["announcements.id"],
            name=op.f("fk_announcement_reads_announcement_id_announcements"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_announcement_reads_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("announcement_id", "user_id", name=op.f("pk_announcement_reads")),
    )
    op.create_index("ix_announcement_reads_user_id", "announcement_reads", ["user_id"])
    _lock("announcements", "announcement_reads")


def downgrade() -> None:
    op.drop_table("announcement_reads")
    op.drop_table("announcements")
    op.execute("DELETE FROM notifications WHERE type IN ('ANNOUNCEMENT', 'LEAVE', 'MEETING')")
    op.drop_constraint(op.f("ck_notifications_type"), "notifications", type_="check")
    op.create_check_constraint(op.f("ck_notifications_type"), "notifications", f"type IN ({OLD_TYPES})")
