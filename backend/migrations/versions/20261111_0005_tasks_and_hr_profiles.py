"""Task management, employee HR profiles, TASK notifications, directory name search.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-11 12:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _id() -> sa.Column[sa.UUID]:
    return sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False)


def _created() -> sa.Column[sa.DateTime]:
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def _updated() -> sa.Column[sa.DateTime]:
    return sa.Column(
        "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "tasks",
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("priority", sa.String(length=20), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column("department_id", sa.UUID(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        _id(),
        _created(),
        _updated(),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('TODO', 'IN_PROGRESS', 'REVIEW', 'COMPLETED', 'CANCELLED')",
            name=op.f("ck_tasks_status"),
        ),
        sa.CheckConstraint(
            "priority IN ('LOW', 'MEDIUM', 'HIGH', 'URGENT')", name=op.f("ck_tasks_priority")
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_tasks_created_by_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["department_id"],
            ["departments.id"],
            name=op.f("fk_tasks_department_id_departments"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tasks")),
    )
    op.create_index("ix_tasks_status_due_at", "tasks", ["status", "due_at"])
    op.create_index("ix_tasks_department_id", "tasks", ["department_id"])
    op.create_index("ix_tasks_created_by", "tasks", ["created_by"])
    op.create_index("ix_tasks_updated_at", "tasks", ["updated_at"])
    op.create_index(
        "ix_tasks_title_trgm",
        "tasks",
        ["title"],
        postgresql_using="gin",
        postgresql_ops={"title": "gin_trgm_ops"},
    )

    op.create_table(
        "task_assignees",
        sa.Column("task_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("assigned_by", sa.UUID(), nullable=True),
        _created(),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["tasks.id"],
            name=op.f("fk_task_assignees_task_id_tasks"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_task_assignees_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["assigned_by"],
            ["users.id"],
            name=op.f("fk_task_assignees_assigned_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("task_id", "user_id", name=op.f("pk_task_assignees")),
    )
    op.create_index("ix_task_assignees_user_id", "task_assignees", ["user_id"])

    op.create_table(
        "task_comments",
        sa.Column("task_id", sa.UUID(), nullable=False),
        sa.Column("author_id", sa.UUID(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
        _id(),
        _created(),
        _updated(),
        sa.CheckConstraint(
            "char_length(body) BETWEEN 1 AND 5000", name=op.f("ck_task_comments_body_length")
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["tasks.id"],
            name=op.f("fk_task_comments_task_id_tasks"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["author_id"],
            ["users.id"],
            name=op.f("fk_task_comments_author_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_task_comments")),
    )
    op.create_index("ix_task_comments_task_created", "task_comments", ["task_id", "created_at"])

    op.create_table(
        "task_attachments",
        sa.Column("task_id", sa.UUID(), nullable=False),
        sa.Column("storage_key", sa.String(length=300), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("file_type", sa.String(length=10), nullable=False),
        sa.Column("mime_type", sa.String(length=150), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("uploaded_by", sa.UUID(), nullable=True),
        _created(),
        _id(),
        sa.CheckConstraint(
            "file_type IN ('PDF', 'DOCX', 'XLSX', 'TXT')",
            name=op.f("ck_task_attachments_file_type"),
        ),
        sa.CheckConstraint("size_bytes >= 0", name=op.f("ck_task_attachments_size_bytes")),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["tasks.id"],
            name=op.f("fk_task_attachments_task_id_tasks"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by"],
            ["users.id"],
            name=op.f("fk_task_attachments_uploaded_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_task_attachments")),
        sa.UniqueConstraint("storage_key", name=op.f("uq_task_attachments_storage_key")),
    )
    op.create_index("ix_task_attachments_task_id", "task_attachments", ["task_id"])

    op.create_table(
        "task_events",
        sa.Column("task_id", sa.UUID(), nullable=False),
        sa.Column("actor_id", sa.UUID(), nullable=True),
        sa.Column("event_type", sa.String(length=30), nullable=False),
        sa.Column("from_value", sa.String(length=300), nullable=True),
        sa.Column("to_value", sa.String(length=300), nullable=True),
        _created(),
        _id(),
        sa.CheckConstraint(
            "event_type IN ('CREATED', 'UPDATED', 'STATUS_CHANGED', 'ASSIGNED', 'UNASSIGNED',"
            " 'COMMENTED', 'ATTACHMENT_ADDED', 'ATTACHMENT_REMOVED')",
            name=op.f("ck_task_events_event_type"),
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["tasks.id"],
            name=op.f("fk_task_events_task_id_tasks"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name=op.f("fk_task_events_actor_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_task_events")),
    )
    op.create_index("ix_task_events_task_created", "task_events", ["task_id", "created_at"])

    op.create_table(
        "employee_hr_profiles",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column("national_id_last4", sa.String(length=4), nullable=True),
        sa.Column("personal_phone", sa.String(length=50), nullable=True),
        sa.Column("personal_email", sa.String(length=320), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("hire_date", sa.Date(), nullable=True),
        sa.Column("employment_type", sa.String(length=20), nullable=True),
        sa.Column("emergency_contact", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        _created(),
        _updated(),
        sa.CheckConstraint(
            "national_id_last4 IS NULL OR national_id_last4 ~ '^[0-9]{4}$'",
            name=op.f("ck_employee_hr_profiles_national_id_last4"),
        ),
        sa.CheckConstraint(
            "employment_type IS NULL OR employment_type IN "
            "('FULL_TIME', 'PART_TIME', 'CONTRACT', 'INTERN')",
            name=op.f("ck_employee_hr_profiles_employment_type"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_employee_hr_profiles_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["users.id"],
            name=op.f("fk_employee_hr_profiles_updated_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_employee_hr_profiles")),
    )

    op.create_index(
        "ix_users_display_name_trgm",
        "users",
        ["display_name"],
        postgresql_using="gin",
        postgresql_ops={"display_name": "gin_trgm_ops"},
    )
    op.drop_constraint(op.f("ck_notifications_type"), "notifications", type_="check")
    op.create_check_constraint(
        op.f("ck_notifications_type"),
        "notifications",
        "type IN ('SECURITY', 'ACCOUNT', 'SYSTEM', 'DOCUMENT', 'TASK')",
    )


def downgrade() -> None:
    op.execute("DELETE FROM notifications WHERE type = 'TASK'")
    op.drop_constraint(op.f("ck_notifications_type"), "notifications", type_="check")
    op.create_check_constraint(
        op.f("ck_notifications_type"),
        "notifications",
        "type IN ('SECURITY', 'ACCOUNT', 'SYSTEM', 'DOCUMENT')",
    )
    op.drop_index(
        "ix_users_display_name_trgm",
        table_name="users",
        postgresql_using="gin",
        postgresql_ops={"display_name": "gin_trgm_ops"},
    )
    op.drop_table("employee_hr_profiles")
    op.drop_index("ix_task_events_task_created", table_name="task_events")
    op.drop_table("task_events")
    op.drop_index("ix_task_attachments_task_id", table_name="task_attachments")
    op.drop_table("task_attachments")
    op.drop_index("ix_task_comments_task_created", table_name="task_comments")
    op.drop_table("task_comments")
    op.drop_index("ix_task_assignees_user_id", table_name="task_assignees")
    op.drop_table("task_assignees")
    op.drop_index(
        "ix_tasks_title_trgm",
        table_name="tasks",
        postgresql_using="gin",
        postgresql_ops={"title": "gin_trgm_ops"},
    )
    op.drop_index("ix_tasks_updated_at", table_name="tasks")
    op.drop_index("ix_tasks_created_by", table_name="tasks")
    op.drop_index("ix_tasks_department_id", table_name="tasks")
    op.drop_index("ix_tasks_status_due_at", table_name="tasks")
    op.drop_table("tasks")
