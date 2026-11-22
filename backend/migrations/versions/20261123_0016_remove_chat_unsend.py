"""Remove "unsend" from chat again (ADR-065)

Messages already unsent had their text erased (migration 0015), so they are removed here:
there is nothing left to show.

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-23 12:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DELETE FROM direct_messages WHERE deleted_at IS NOT NULL")
    op.drop_constraint(op.f("ck_direct_messages_body_length"), "direct_messages", type_="check")
    op.create_check_constraint(
        op.f("ck_direct_messages_body_length"),
        "direct_messages",
        "char_length(body) BETWEEN 1 AND 4000",
    )
    op.drop_column("direct_messages", "deleted_at")


def downgrade() -> None:
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
