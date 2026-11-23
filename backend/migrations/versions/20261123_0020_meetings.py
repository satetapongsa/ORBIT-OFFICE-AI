"""Calendar meetings and invitations (ADR-070)

Revision ID: 0020
Revises: 0019
Create Date: 2026-11-23 16:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0020"
down_revision: str | None = "0019"
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
        "meetings",
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("location", sa.String(length=200), nullable=True),
        sa.Column("online_url", sa.String(length=500), nullable=True),
        _ts("start_at", nullable=False),
        _ts("end_at", nullable=False),
        sa.Column("organizer_id", sa.UUID(), nullable=True),
        sa.Column("reminder_minutes", sa.Integer(), nullable=False),
        _ts("reminder_sent_at"),
        _ts("cancelled_at"),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        _ts("created_at", nullable=False, now=True),
        _ts("updated_at", nullable=False, now=True),
        sa.CheckConstraint("end_at > start_at", name=op.f("ck_meetings_time_order")),
        sa.CheckConstraint(
            "char_length(description) <= 5000", name=op.f("ck_meetings_description_length")
        ),
        sa.CheckConstraint(
            "reminder_minutes BETWEEN 0 AND 1440", name=op.f("ck_meetings_reminder_range")
        ),
        sa.CheckConstraint(
            "online_url IS NULL OR online_url LIKE 'https://%'",
            name=op.f("ck_meetings_online_url_https"),
        ),
        sa.ForeignKeyConstraint(
            ["organizer_id"],
            ["users.id"],
            name=op.f("fk_meetings_organizer_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_meetings")),
    )
    op.create_index("ix_meetings_start_at", "meetings", ["start_at"])
    op.create_table(
        "meeting_attendees",
        sa.Column("meeting_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("response", sa.String(length=10), nullable=False),
        _ts("responded_at"),
        sa.CheckConstraint(
            "response IN ('PENDING', 'ACCEPTED', 'TENTATIVE', 'DECLINED')",
            name=op.f("ck_meeting_attendees_response"),
        ),
        sa.ForeignKeyConstraint(
            ["meeting_id"],
            ["meetings.id"],
            name=op.f("fk_meeting_attendees_meeting_id_meetings"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_meeting_attendees_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("meeting_id", "user_id", name=op.f("pk_meeting_attendees")),
    )
    op.create_index("ix_meeting_attendees_user_id", "meeting_attendees", ["user_id"])
    for table in ("meetings", "meeting_attendees"):
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN "
            f"REVOKE ALL ON public.{table} FROM anon, authenticated; END IF; END $$;"
        )


def downgrade() -> None:
    op.drop_table("meeting_attendees")
    op.drop_table("meetings")
