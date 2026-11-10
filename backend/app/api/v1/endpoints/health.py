"""Liveness and readiness endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from app import __version__
from app.api.deps import get_app_settings
from app.core.config import Settings
from app.schemas.health import ComponentStatus, LivenessResponse, ReadinessResponse
from app.services.health import readiness

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", response_model=LivenessResponse, summary="Liveness probe")
async def live(settings: Settings = Depends(get_app_settings)) -> LivenessResponse:
    """The process is running. Performs no dependency checks."""
    return LivenessResponse(
        status=ComponentStatus.OK, service=settings.app_name, version=__version__
    )


@router.get(
    "",
    response_model=ReadinessResponse,
    summary="Readiness probe",
    responses={503: {"model": ReadinessResponse, "description": "A required dependency is down"}},
)
async def ready(
    response: Response, settings: Settings = Depends(get_app_settings)
) -> ReadinessResponse:
    """Checks PostgreSQL (+ pgvector), Redis and object storage; reports AI configuration."""
    result = await readiness(settings)
    if result.status is not ComponentStatus.OK:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return result
