"""Leave requests, leave types and per-person quotas (ADR-068)

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-23 14:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("leave_types", "leave_quotas", "leave_requests")


def _now(name: str) -> sa.Column:
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def _id() -> sa.Column:
    return sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False)


def upgrade() -> None:
    op.create_table(
        "leave_types",
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("days_per_year", sa.Numeric(5, 1), nullable=True),
        sa.Column("color", sa.String(length=20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        _id(),
        _now("created_at"),
        _now("updated_at"),
        sa.CheckConstraint(
            "days_per_year IS NULL OR days_per_year >= 0",
            name=op.f("ck_leave_types_days_non_negative"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_leave_types")),
        sa.UniqueConstraint("code", name=op.f("uq_leave_types_code")),
    )
    op.create_table(
        "leave_quotas",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("leave_type_id", sa.UUID(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("days", sa.Numeric(5, 1), nullable=False),
        sa.CheckConstraint("days >= 0", name=op.f("ck_leave_quotas_days_non_negative")),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_leave_quotas_user_id_users"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["leave_type_id"],
            ["leave_types.id"],
            name=op.f("fk_leave_quotas_leave_type_id_leave_types"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "leave_type_id", "year", name=op.f("pk_leave_quotas")),
    )
    op.create_table(
        "leave_requests",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("leave_type_id", sa.UUID(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("half_day", sa.String(length=10), nullable=False),
        sa.Column("days", sa.Numeric(5, 1), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("decided_by", sa.UUID(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        _id(),
        _now("created_at"),
        _now("updated_at"),
        sa.CheckConstraint("end_date >= start_date", name=op.f("ck_leave_requests_date_order")),
        sa.CheckConstraint("days > 0", name=op.f("ck_leave_requests_days_positive")),
        sa.CheckConstraint(
            "status IN ('PENDING', 'APPROVED', 'REJECTED', 'CANCELLED')",
            name=op.f("ck_leave_requests_status"),
        ),
        sa.CheckConstraint(
            "half_day IN ('NONE', 'MORNING', 'AFTERNOON')", name=op.f("ck_leave_requests_half_day")
        ),
        sa.CheckConstraint(
            "half_day = 'NONE' OR start_date = end_date",
            name=op.f("ck_leave_requests_half_day_single_date"),
        ),
        sa.CheckConstraint(
            "char_length(reason) <= 2000", name=op.f("ck_leave_requests_reason_length")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_leave_requests_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["leave_type_id"],
            ["leave_types.id"],
            name=op.f("fk_leave_requests_leave_type_id_leave_types"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["decided_by"],
            ["users.id"],
            name=op.f("fk_leave_requests_decided_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_leave_requests")),
    )
    op.create_index("ix_leave_requests_user_start", "leave_requests", ["user_id", "start_date"])
    op.create_index("ix_leave_requests_status", "leave_requests", ["status"])
    op.create_index("ix_leave_requests_dates", "leave_requests", ["start_date", "end_date"])

    # Defaults follow the Thai Labour Protection Act minimums; HR can change them.
    op.execute(
        """
        INSERT INTO leave_types (code, name, days_per_year, color, is_active, sort_order) VALUES
            ('ANNUAL', 'ลาพักร้อน', 6, 'emerald', true, 1),
            ('SICK', 'ลาป่วย', 30, 'rose', true, 2),
            ('PERSONAL', 'ลากิจ', 3, 'amber', true, 3),
            ('MATERNITY', 'ลาคลอด', 98, 'violet', true, 4),
            ('UNPAID', 'ลาไม่รับค่าจ้าง', NULL, 'slate', true, 5)
        """
    )
    for table in TABLES:
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN "
            f"REVOKE ALL ON public.{table} FROM anon, authenticated; END IF; END $$;"
        )


def downgrade() -> None:
    op.drop_table("leave_requests")
    op.drop_table("leave_quotas")
    op.drop_table("leave_types")
