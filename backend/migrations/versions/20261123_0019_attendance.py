"""Attendance check-in / check-out (ADR-069)

Revision ID: 0019
Revises: 0018
Create Date: 2026-11-23 15:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "attendance_records",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("check_in_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("check_out_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("work_mode", sa.String(length=10), nullable=False),
        sa.Column("late", sa.Boolean(), nullable=False),
        sa.Column("check_in_note", sa.String(length=300), nullable=True),
        sa.Column("check_out_note", sa.String(length=300), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "work_mode IN ('OFFICE', 'WFH', 'ONSITE')", name=op.f("ck_attendance_records_work_mode")
        ),
        sa.CheckConstraint(
            "check_out_at IS NULL OR check_out_at >= check_in_at",
            name=op.f("ck_attendance_records_time_order"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_attendance_records_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_attendance_records")),
    )
    op.create_index(
        "uq_attendance_user_date", "attendance_records", ["user_id", "work_date"], unique=True
    )
    op.create_index("ix_attendance_work_date", "attendance_records", ["work_date"])
    op.execute("ALTER TABLE public.attendance_records ENABLE ROW LEVEL SECURITY")
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN "
        "REVOKE ALL ON public.attendance_records FROM anon, authenticated; END IF; END $$;"
    )


def downgrade() -> None:
    op.drop_table("attendance_records")
