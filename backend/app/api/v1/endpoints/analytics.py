"""Analytics and report exports (HTTP only — rules live in ``app.services.analytics``)."""

from __future__ import annotations

import asyncio
import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.api.deps import (
    CurrentUserDep,
    DbDep,
    MetaDep,
    SettingsDep,
    get_chat_provider,
    require_permissions,
)
from app.api.v1.endpoints.documents import content_disposition
from app.core.permissions import P
from app.schemas.analytics import (
    AnalyticsOverview,
    AnalyticsScope,
    AnalyticsSummary,
    SummaryRequest,
)
from app.services import analytics
from app.services.ai.providers.base import ChatProvider
from app.services.audit import AuditAction
from app.services.audit import record as audit_record
from app.services.reports import export

router = APIRouter(tags=["analytics"])

ProviderDep = Annotated[ChatProvider | None, Depends(get_chat_provider)]

XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get(
    "/analytics/overview",
    response_model=AnalyticsOverview,
    summary="Task, ticket and document statistics for a scope I may analyse",
)
async def overview(
    db: DbDep,
    settings: SettingsDep,
    user: CurrentUserDep,
    scope: AnalyticsScope = "own",
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
) -> AnalyticsOverview:
    return await analytics.overview(db, settings, user, scope, date_from, date_to)


@router.post(
    "/analytics/summary",
    response_model=AnalyticsSummary,
    summary="AI-written summary of the statistics (needs ai:chat and a configured model)",
)
async def summary(
    body: SummaryRequest,
    db: DbDep,
    settings: SettingsDep,
    user: CurrentUserDep,
    provider: ProviderDep,
) -> AnalyticsSummary:
    return await analytics.ai_summary(
        db, settings, provider, user, body.scope, body.date_from, body.date_to
    )


async def _export(
    fmt: str,
    db: DbDep,
    settings: SettingsDep,
    user: CurrentUserDep,
    meta: MetaDep,
    scope: AnalyticsScope,
    date_from: dt.date | None,
    date_to: dt.date | None,
) -> Response:
    report = await export.collect(db, settings, user, scope, date_from, date_to)
    o = report.overview
    builder = export.to_xlsx if fmt == "xlsx" else export.to_pdf
    content = await asyncio.to_thread(builder, report)
    audit_record(
        db,
        AuditAction.REPORT_EXPORTED,
        actor_id=user.id,
        meta=meta,
        entity_type="report",
        details={
            "format": fmt,
            "scope": o.scope,
            "date_from": o.date_from.isoformat(),
            "date_to": o.date_to.isoformat(),
            "tasks": len(report.tasks),
            "tickets": len(report.tickets),
        },
    )
    await db.commit()
    return Response(
        content=content,
        media_type=XLSX_TYPE if fmt == "xlsx" else "application/pdf",
        headers={
            "Content-Disposition": content_disposition(export.filename(o, fmt)),
            "Cache-Control": "no-store",
        },
    )


@router.get(
    "/reports/overview.xlsx",
    summary="Export the overview as Excel (reports:export; audited)",
    dependencies=[Depends(require_permissions(P.REPORTS_EXPORT))],
    response_class=Response,
)
async def export_xlsx(
    db: DbDep,
    settings: SettingsDep,
    user: CurrentUserDep,
    meta: MetaDep,
    scope: AnalyticsScope = "own",
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
) -> Response:
    return await _export("xlsx", db, settings, user, meta, scope, date_from, date_to)


@router.get(
    "/reports/overview.pdf",
    summary="Export the overview as PDF (reports:export; audited)",
    dependencies=[Depends(require_permissions(P.REPORTS_EXPORT))],
    response_class=Response,
)
async def export_pdf(
    db: DbDep,
    settings: SettingsDep,
    user: CurrentUserDep,
    meta: MetaDep,
    scope: AnalyticsScope = "own",
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
) -> Response:
    return await _export("pdf", db, settings, user, meta, scope, date_from, date_to)
