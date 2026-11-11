"""Dashboard summary. Optional sections are ``null`` when the user lacks the permission."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from app.schemas.identity import DepartmentRef, RoleRef
from app.schemas.notifications import NotificationOut


class DailyCount(BaseModel):
    date: date
    count: int = Field(ge=0)


class ActorRef(BaseModel):
    id: uuid.UUID
    display_name: str


class ActivityItem(BaseModel):
    """An audit event, reduced to what a dashboard may show (no IP, user agent or metadata)."""

    id: uuid.UUID
    action: str
    occurred_at: datetime
    actor: ActorRef | None
    entity_type: str | None


class AccountSummary(BaseModel):
    display_name: str
    job_title: str | None
    department: DepartmentRef | None
    roles: list[RoleRef]
    last_login_at: datetime | None
    previous_login_at: datetime | None = Field(
        description="The sign-in before the current one (helps users spot unknown access)."
    )
    password_changed_at: datetime | None
    active_sessions: int = Field(ge=0)


class NotificationSummary(BaseModel):
    unread_count: int = Field(ge=0)
    latest: list[NotificationOut]


class MyActivity(BaseModel):
    daily_sign_ins: list[DailyCount]
    recent: list[ActivityItem]


class RecentDocument(BaseModel):
    id: uuid.UUID
    title: str
    category: str
    file_type: str | None
    processing_status: str | None
    updated_at: datetime


class DocumentSummary(BaseModel):
    accessible_count: int = Field(ge=0, description="Documents this user may view (ACL-filtered).")
    my_documents: int = Field(ge=0, description="Live documents the user owns.")
    my_processing: int = Field(
        ge=0, description="My documents whose current file is queued/processing."
    )
    my_failed: int = Field(ge=0, description="My documents whose current file failed processing.")
    recent: list[RecentDocument] = Field(description="Latest updated documents the user may view.")


class UpcomingTask(BaseModel):
    id: uuid.UUID
    title: str
    status: str
    priority: str
    due_at: datetime | None
    is_overdue: bool


class TaskSummary(BaseModel):
    open_assigned: int = Field(ge=0, description="Open tasks assigned to me.")
    overdue: int = Field(ge=0, description="Of those, past their due time.")
    due_soon: int = Field(ge=0, description="Of those, due within the next 7 days.")
    upcoming: list[UpcomingTask] = Field(description="My open tasks, earliest due first.")


class DepartmentHeadcount(BaseModel):
    department: DepartmentRef | None  # None = users without a department
    count: int = Field(ge=0)


class OrganizationSummary(BaseModel):
    active_users: int = Field(ge=0)
    inactive_users: int = Field(ge=0)
    departments: int = Field(ge=0)
    users_by_department: list[DepartmentHeadcount]


class DailySecurityCount(BaseModel):
    date: date
    sign_ins: int = Field(ge=0)
    failed_sign_ins: int = Field(ge=0)


class SecuritySummary(BaseModel):
    sign_ins: int = Field(ge=0)
    failed_sign_ins: int = Field(ge=0)
    rate_limited: int = Field(ge=0)
    daily: list[DailySecurityCount]
    recent: list[ActivityItem]


class DashboardSummary(BaseModel):
    generated_at: datetime
    timezone: str
    period_days: int
    account: AccountSummary
    notifications: NotificationSummary
    my_activity: MyActivity
    documents: DocumentSummary | None = Field(description="Requires `documents:read`.")
    tasks: TaskSummary | None = Field(default=None, description="Requires `tasks:read_own`.")
    organization: OrganizationSummary | None = Field(description="Requires `users:read`.")
    security: SecuritySummary | None = Field(description="Requires `audit:read`.")
