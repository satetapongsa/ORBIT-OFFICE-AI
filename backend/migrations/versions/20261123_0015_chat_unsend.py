"""Unsend chat messages; editing without a time limit (ADR-064)

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-23 11:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "direct_messages", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.drop_constraint(op.f("ck_direct_messages_body_length"), "direct_messages", type_="check")
    op.create_check_constraint(
        op.f("ck_direct_messages_body_length"),
        "direct_messages",
        "(deleted_at IS NULL AND char_length(body) BETWEEN 1 AND 4000)"
        " OR (deleted_at IS NOT NULL AND body = '')",
    )


def downgrade() -> None:
    # Unsent rows have no text left; keep them valid under the old rule with a placeholder.
    op.execute(
        "UPDATE direct_messages SET body = '(ยกเลิกข้อความแล้ว)' WHERE deleted_at IS NOT NULL"
    )
    op.drop_constraint(op.f("ck_direct_messages_body_length"), "direct_messages", type_="check")
    op.create_check_constraint(
        op.f("ck_direct_messages_body_length"),
        "direct_messages",
        "char_length(body) BETWEEN 1 AND 4000",
    )
    op.drop_column("direct_messages", "deleted_at")
