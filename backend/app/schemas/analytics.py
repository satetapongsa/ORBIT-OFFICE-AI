"""Analytics and report schemas."""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.documents import UserRef
from app.schemas.identity import DepartmentRef

AnalyticsScope = Literal["own", "department", "all"]


class CountByKey(BaseModel):
    key: str
    count: int = Field(ge=0)


class DailyPair(BaseModel):
    date: dt.date
    opened: int = Field(ge=0, description="Created (tasks) / opened (tickets) that day")
    closed: int = Field(ge=0, description="Completed (tasks) / resolved (tickets) that day")


class WorkloadRow(BaseModel):
    user: UserRef
    open: int = Field(ge=0)
    overdue: int = Field(ge=0)
    completed: int = Field(ge=0, description="Completed in the period")


class TaskAnalytics(BaseModel):
    open: int
    overdue: int
    created: int
    completed: int
    completion_rate: float | None = Field(description="completed / created in the period")
    avg_completion_hours: float | None
    by_status: list[CountByKey]
    open_by_priority: list[CountByKey]
    daily: list[DailyPair]
    workload: list[WorkloadRow] = Field(description="Empty for the 'own' scope")


class TicketAnalytics(BaseModel):
    open: int
    opened: int
    resolved: int
    avg_resolution_hours: float | None
    by_status: list[CountByKey]
    by_category: list[CountByKey]
    daily: list[DailyPair]


class DocumentAnalytics(BaseModel):
    total: int
    uploaded: int
    by_category: list[CountByKey]


class AnalyticsOverview(BaseModel):
    scope: AnalyticsScope
    department: DepartmentRef | None
    date_from: dt.date
    date_to: dt.date
    timezone: str
    generated_at: dt.datetime
    available_scopes: list[AnalyticsScope]
    can_export: bool
    tasks: TaskAnalytics
    tickets: TicketAnalytics
    documents: DocumentAnalytics


class SummaryRequest(BaseModel):
    scope: AnalyticsScope = "own"
    date_from: dt.date | None = None
    date_to: dt.date | None = None


class AnalyticsSummary(BaseModel):
    summary: str
    model: str
    generated_at: dt.datetime
