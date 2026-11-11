"""Helpdesk tickets, notification e-mail preferences and delivery status, TICKET notifications

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-11 17:56:57.310244+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE ticket_number_seq")
    op.create_table(
        "notification_preferences",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("email_enabled", sa.Boolean(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "type IN ('SECURITY', 'ACCOUNT', 'SYSTEM', 'DOCUMENT', 'TASK', 'TICKET')",
            name=op.f("ck_notification_preferences_type"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_notification_preferences_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "type", name=op.f("pk_notification_preferences")),
    )
    op.create_table(
        "tickets",
        sa.Column("ticket_number", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=30), nullable=False),
        sa.Column("priority", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("requester_id", sa.UUID(), nullable=False),
        sa.Column("assignee_id", sa.UUID(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "category IN ('COMPUTER', 'NETWORK', 'PRINTER', 'SOFTWARE', 'ACCOUNT_ACCESS', 'OTHER')",
            name=op.f("ck_tickets_category"),
        ),
        sa.CheckConstraint(
            "priority IN ('LOW', 'MEDIUM', 'HIGH', 'URGENT')", name=op.f("ck_tickets_priority")
        ),
        sa.CheckConstraint(
            "status IN ('OPEN', 'IN_PROGRESS', 'WAITING_FOR_USER', 'RESOLVED', 'CLOSED', 'CANCELLED')",
            name=op.f("ck_tickets_status"),
        ),
        sa.ForeignKeyConstraint(
            ["assignee_id"],
            ["users.id"],
            name=op.f("fk_tickets_assignee_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["requester_id"],
            ["users.id"],
            name=op.f("fk_tickets_requester_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tickets")),
        sa.UniqueConstraint("ticket_number", name=op.f("uq_tickets_ticket_number")),
    )
    op.create_index(
        "ix_tickets_assignee_status", "tickets", ["assignee_id", "status"], unique=False
    )
    op.create_index("ix_tickets_requester_id", "tickets", ["requester_id"], unique=False)
    op.create_index("ix_tickets_status_created", "tickets", ["status", "created_at"], unique=False)
    op.create_index(
        "ix_tickets_title_trgm",
        "tickets",
        ["title"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"title": "gin_trgm_ops"},
    )
    op.create_table(
        "ticket_comments",
        sa.Column("ticket_id", sa.UUID(), nullable=False),
        sa.Column("author_id", sa.UUID(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("is_internal", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint(
            "char_length(body) BETWEEN 1 AND 5000", name=op.f("ck_ticket_comments_body_length")
        ),
        sa.ForeignKeyConstraint(
            ["author_id"],
            ["users.id"],
            name=op.f("fk_ticket_comments_author_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["tickets.id"],
            name=op.f("fk_ticket_comments_ticket_id_tickets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ticket_comments")),
    )
    op.create_index(
        "ix_ticket_comments_ticket_created",
        "ticket_comments",
        ["ticket_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "ticket_events",
        sa.Column("ticket_id", sa.UUID(), nullable=False),
        sa.Column("actor_id", sa.UUID(), nullable=True),
        sa.Column("event_type", sa.String(length=30), nullable=False),
        sa.Column("from_value", sa.String(length=300), nullable=True),
        sa.Column("to_value", sa.String(length=300), nullable=True),
        sa.Column("is_internal", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint(
            "event_type IN ('CREATED', 'STATUS_CHANGED', 'ASSIGNED', 'UNASSIGNED', 'PRIORITY_CHANGED', 'CATEGORY_CHANGED', 'COMMENTED')",
            name=op.f("ck_ticket_events_event_type"),
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name=op.f("fk_ticket_events_actor_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["tickets.id"],
            name=op.f("fk_ticket_events_ticket_id_tickets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ticket_events")),
    )
    op.create_index(
        "ix_ticket_events_ticket_created",
        "ticket_events",
        ["ticket_id", "created_at"],
        unique=False,
    )
    op.add_column("notifications", sa.Column("email_status", sa.String(length=20), nullable=True))
    op.add_column(
        "notifications", sa.Column("emailed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_check_constraint(
        op.f("ck_notifications_email_status"),
        "notifications",
        "email_status IS NULL OR email_status IN ('PENDING', 'SENT', 'SKIPPED', 'FAILED')",
    )
    op.drop_constraint(op.f("ck_notifications_type"), "notifications", type_="check")
    op.create_check_constraint(
        op.f("ck_notifications_type"),
        "notifications",
        "type IN ('SECURITY', 'ACCOUNT', 'SYSTEM', 'DOCUMENT', 'TASK', 'TICKET')",
    )


def downgrade() -> None:
    op.execute("DELETE FROM notifications WHERE type = 'TICKET'")
    op.drop_constraint(op.f("ck_notifications_email_status"), "notifications", type_="check")
    op.drop_constraint(op.f("ck_notifications_type"), "notifications", type_="check")
    op.create_check_constraint(
        op.f("ck_notifications_type"),
        "notifications",
        "type IN ('SECURITY', 'ACCOUNT', 'SYSTEM', 'DOCUMENT', 'TASK')",
    )
    op.drop_column("notifications", "emailed_at")
    op.drop_column("notifications", "email_status")
    op.drop_index("ix_ticket_events_ticket_created", table_name="ticket_events")
    op.drop_table("ticket_events")
    op.drop_index("ix_ticket_comments_ticket_created", table_name="ticket_comments")
    op.drop_table("ticket_comments")
    op.drop_index(
        "ix_tickets_title_trgm",
        table_name="tickets",
        postgresql_using="gin",
        postgresql_ops={"title": "gin_trgm_ops"},
    )
    op.drop_index("ix_tickets_status_created", table_name="tickets")
    op.drop_index("ix_tickets_requester_id", table_name="tickets")
    op.drop_index("ix_tickets_assignee_status", table_name="tickets")
    op.drop_table("tickets")
    op.drop_table("notification_preferences")
    op.execute("DROP SEQUENCE ticket_number_seq")
