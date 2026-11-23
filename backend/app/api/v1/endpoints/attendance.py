"""Attendance check-in / check-out (ADR-069)."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from app.api.deps import CurrentUserDep, DbDep, MetaDep, SettingsDep, require_permissions
from app.core.permissions import P
from app.core.principal import CurrentUser
from app.schemas.attendance import CheckIn, CheckOut, MonthlyReport, MyMonth, TeamDay, TodayOut
from app.services import attendance as service

router = APIRouter(prefix="/attendance", tags=["attendance"])

Worker = Annotated[CurrentUser, Depends(require_permissions(P.ATTENDANCE_CHECKIN))]
Month = Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}$")]


@router.get("/today", response_model=TodayOut, summary="My attendance today and working hours")
async def today(db: DbDep, settings: SettingsDep, user: Worker) -> TodayOut:
    return await service.today(db, user, settings)


@router.post("/check-in", response_model=TodayOut, summary="Check in now (server time)")
async def check_in(
    body: CheckIn, db: DbDep, settings: SettingsDep, user: Worker, meta: MetaDep
) -> TodayOut:
    return await service.check_in(db, user, settings, body, meta)


@router.post("/check-out", response_model=TodayOut, summary="Check out now (server time)")
async def check_out(
    body: CheckOut, db: DbDep, settings: SettingsDep, user: Worker, meta: MetaDep
) -> TodayOut:
    return await service.check_out(db, user, settings, body, meta)


@router.get("/me", response_model=MyMonth, summary="My records and summary for a month")
async def my_month(db: DbDep, settings: SettingsDep, user: Worker, month: Month = None) -> MyMonth:
    return await service.my_month(db, user, settings, month)


@router.get("/team", response_model=TeamDay, summary="Daily board (department or everyone)")
async def team(
    db: DbDep,
    settings: SettingsDep,
    user: CurrentUserDep,
    day: Annotated[date | None, Query(alias="date")] = None,
    department_id: uuid.UUID | None = None,
) -> TeamDay:
    return await service.team_day(db, user, settings, day, department_id)


@router.get("/report", response_model=MonthlyReport, summary="Monthly summary per person")
async def report(
    db: DbDep,
    settings: SettingsDep,
    user: CurrentUserDep,
    month: Month = None,
    department_id: uuid.UUID | None = None,
) -> MonthlyReport:
    return await service.monthly_report(db, user, settings, month, department_id)


@router.get("/report.csv", summary="Monthly summary as CSV (opens in Excel)")
async def report_csv(
    db: DbDep,
    settings: SettingsDep,
    user: CurrentUserDep,
    month: Month = None,
    department_id: uuid.UUID | None = None,
) -> Response:
    data = await service.monthly_report(db, user, settings, month, department_id)
    return Response(
        content=service.report_csv(data).encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="attendance-{data.month}.csv"'},
    )
