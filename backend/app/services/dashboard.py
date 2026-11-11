"""Dashboard summary, assembled per user.

Every section is computed only when the user holds the permission that already guards the
equivalent detailed API, so the dashboard never reveals more than the user could see anyway:

* account, own notifications and own activity — every signed-in user;
* ``documents`` — ``documents:read``, counted through the single ACL predicate;
* ``organization`` — ``users:read`` (same data as ``GET /users`` / ``/departments``);
* ``security`` — ``audit:read`` (same data as ``GET /audit-logs``).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import UnauthenticatedError
from app.core.permissions import P
from app.core.principal import CurrentUser
from app.core.security import utcnow
from app.models.audit import AuditLog
from app.repositories import dashboard as dashboard_repo
from app.repositories import notifications as notification_repo
from app.repositories import users as user_repo
from app.schemas.dashboard import (
    AccountSummary,
    ActivityItem,
    ActorRef,
    DailyCount,
    DailySecurityCount,
    DashboardSummary,
    DepartmentHeadcount,
    DocumentSummary,
    MyActivity,
    NotificationSummary,
    OrganizationSummary,
    RecentDocument,
    SecuritySummary,
)
from app.schemas.identity import DepartmentRef, RoleRef
from app.schemas.notifications import NotificationOut
from app.services.audit import AuditAction

PERIOD_DAYS = 14
RECENT_LIMIT = 8
NOTIFICATION_PREVIEW = 5
RECENT_DOCUMENTS = 5


def _period(now: datetime, tz: str) -> tuple[list[date], datetime]:
    """Local calendar days of the period (oldest first) and the UTC instant it starts."""
    zone = ZoneInfo(tz)
    today = now.astimezone(zone).date()
    days = [today - timedelta(days=offset) for offset in range(PERIOD_DAYS - 1, -1, -1)]
    start = datetime.combine(days[0], time.min, tzinfo=zone)
    return days, start


def _activity(rows: list[tuple[AuditLog, uuid.UUID | None, str | None]]) -> list[ActivityItem]:
    items: list[ActivityItem] = []
    for log, actor_id, actor_name in rows:
        actor = (
            ActorRef(id=actor_id, display_name=actor_name)
            if actor_id is not None and actor_name is not None
            else None
        )
        items.append(
            ActivityItem(
                id=log.id,
                action=log.action,
                occurred_at=log.occurred_at,
                actor=actor,
                entity_type=log.entity_type,
            )
        )
    return items


async def build_summary(
    session: AsyncSession, settings: Settings, user: CurrentUser
) -> DashboardSummary:
    now = utcnow()
    tz = settings.app_timezone
    days, since = _period(now, tz)

    account = await user_repo.get_by_id(session, user.id)
    if account is None:  # deleted between authentication and this query
        raise UnauthenticatedError()

    login = AuditAction.LOGIN.value
    my_counts = await dashboard_repo.daily_action_counts(
        session, actions=[login], since=since, tz=tz, actor_id=user.id
    )
    latest_notifications, _ = await notification_repo.list_for_user(
        session, user.id, page=1, page_size=NOTIFICATION_PREVIEW
    )

    summary = DashboardSummary(
        generated_at=now,
        timezone=tz,
        period_days=PERIOD_DAYS,
        account=AccountSummary(
            display_name=account.display_name,
            job_title=account.job_title,
            department=(
                DepartmentRef.model_validate(account.department) if account.department else None
            ),
            roles=sorted(
                (RoleRef.model_validate(link.role) for link in account.role_links),
                key=lambda r: r.code,
            ),
            last_login_at=account.last_login_at,
            previous_login_at=await dashboard_repo.previous_login_at(session, user.id),
            password_changed_at=account.password_changed_at,
            active_sessions=await dashboard_repo.count_active_sessions(session, user.id, now),
        ),
        notifications=NotificationSummary(
            unread_count=await notification_repo.count_unread(session, user.id),
            latest=[NotificationOut.model_validate(n) for n in latest_notifications],
        ),
        my_activity=MyActivity(
            daily_sign_ins=[DailyCount(date=d, count=my_counts.get((d, login), 0)) for d in days],
            recent=_activity(
                await dashboard_repo.recent_activity(
                    session, limit=RECENT_LIMIT, about_user=user.id
                )
            ),
        ),
        documents=None,
        organization=None,
        security=None,
    )

    if user.has(P.DOCUMENTS_READ):
        owned, in_progress, broken = await dashboard_repo.my_document_counts(session, user.id)
        summary.documents = DocumentSummary(
            accessible_count=await dashboard_repo.count_accessible_documents(session, user),
            my_documents=owned,
            my_processing=in_progress,
            my_failed=broken,
            recent=[
                RecentDocument(
                    id=doc.id,
                    title=doc.title,
                    category=doc.category,
                    file_type=version.file_type if version else None,
                    processing_status=version.processing_status if version else None,
                    updated_at=doc.updated_at,
                )
                for doc, version in await dashboard_repo.recent_documents(
                    session, user, limit=RECENT_DOCUMENTS
                )
            ],
        )

    if user.has(P.USERS_READ):
        active, inactive = await dashboard_repo.user_counts(session)
        summary.organization = OrganizationSummary(
            active_users=active,
            inactive_users=inactive,
            departments=await dashboard_repo.count_departments(session),
            users_by_department=[
                DepartmentHeadcount(
                    department=DepartmentRef.model_validate(dept) if dept else None, count=n
                )
                for dept, n in await dashboard_repo.headcount_by_department(session)
            ],
        )

    if user.has(P.AUDIT_READ):
        failed = AuditAction.LOGIN_FAILED.value
        limited = AuditAction.LOGIN_RATE_LIMITED.value
        counts = await dashboard_repo.daily_action_counts(
            session, actions=[login, failed, limited], since=since, tz=tz
        )
        summary.security = SecuritySummary(
            sign_ins=sum(n for (_, action), n in counts.items() if action == login),
            failed_sign_ins=sum(n for (_, action), n in counts.items() if action == failed),
            rate_limited=sum(n for (_, action), n in counts.items() if action == limited),
            daily=[
                DailySecurityCount(
                    date=d,
                    sign_ins=counts.get((d, login), 0),
                    failed_sign_ins=counts.get((d, failed), 0),
                )
                for d in days
            ],
            recent=_activity(await dashboard_repo.recent_activity(session, limit=RECENT_LIMIT)),
        )

    return summary
