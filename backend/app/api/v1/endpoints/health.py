"""Liveness and readiness endpoints."""

from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Response, status

from app import __version__
from app.api.deps import get_app_settings, require_permissions
from app.core.config import Settings
from app.core.permissions import P
from app.schemas.health import ComponentStatus, LivenessResponse, ReadinessResponse
from app.services.health import readiness

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", response_model=LivenessResponse, summary="Liveness probe")
async def live(settings: Settings = Depends(get_app_settings)) -> LivenessResponse:
    """The process is running. Performs no dependency checks."""
    return LivenessResponse(
        status=ComponentStatus.OK, service=settings.app_name, version=__version__
    )


def _token_ok(settings: Settings, token: str | None) -> bool:
    expected = settings.health_check_token
    if not token or expected is None:
        return False
    return hmac.compare_digest(token.encode(), expected.get_secret_value().encode())


def _respond(response: Response, result: ReadinessResponse) -> ReadinessResponse:
    if result.status is not ComponentStatus.OK:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return result


@router.get(
    "",
    response_model=ReadinessResponse,
    summary="Readiness probe",
    responses={503: {"model": ReadinessResponse, "description": "A required dependency is down"}},
)
async def ready(
    response: Response,
    settings: Settings = Depends(get_app_settings),
    x_health_token: Annotated[str | None, Header()] = None,
) -> ReadinessResponse:
    """Checks PostgreSQL (+ pgvector), Redis and object storage; reports AI configuration.

    In production only the overall status is public; component details need
    `X-Health-Token` (monitoring) or `GET /health/details` (administrators)."""
    result = await readiness(settings)
    if not settings.health_details_visible and not _token_ok(settings, x_health_token):
        result = result.model_copy(
            update={"components": [], "environment": None, "details_hidden": True}
        )
    return _respond(response, result)


@router.get(
    "/details",
    response_model=ReadinessResponse,
    summary="Readiness with component details (system:configure)",
    dependencies=[Depends(require_permissions(P.SYSTEM_CONFIGURE))],
    responses={503: {"model": ReadinessResponse, "description": "A required dependency is down"}},
)
async def ready_details(
    response: Response, settings: Settings = Depends(get_app_settings)
) -> ReadinessResponse:
    return _respond(response, await readiness(settings))
