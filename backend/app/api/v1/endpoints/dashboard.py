"""Dashboard summary for the signed-in user."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUserDep, DbDep, SettingsDep
from app.schemas.dashboard import DashboardSummary
from app.services import dashboard as dashboard_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get(
    "/summary",
    response_model=DashboardSummary,
    summary="Dashboard metrics scoped to the caller's permissions",
)
async def dashboard_summary(
    db: DbDep, settings: SettingsDep, user: CurrentUserDep
) -> DashboardSummary:
    return await dashboard_service.build_summary(db, settings, user)
