"""Typing indicator for direct messages (ADR-061)

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-23 09:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "conversations", sa.Column("low_typing_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "conversations", sa.Column("high_typing_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("conversations", "high_typing_at")
    op.drop_column("conversations", "low_typing_at")
