"""Self-service sign-up: pending registrations awaiting e-mail confirmation

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-19 09:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pending_registrations",
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pending_registrations")),
    )
    op.create_index(
        "uq_pending_registrations_token_hash",
        "pending_registrations",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        "uq_pending_registrations_email", "pending_registrations", ["email"], unique=True
    )


def downgrade() -> None:
    op.drop_index("uq_pending_registrations_email", table_name="pending_registrations")
    op.drop_index("uq_pending_registrations_token_hash", table_name="pending_registrations")
    op.drop_table("pending_registrations")
