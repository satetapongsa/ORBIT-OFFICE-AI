"""Health-check response schemas."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class ComponentStatus(StrEnum):
    OK = "ok"
    ERROR = "error"
    CONFIGURED = "configured"  # settings present; connectivity is not probed
    NOT_CONFIGURED = "not_configured"


class ComponentHealth(BaseModel):
    name: str
    status: ComponentStatus
    required: bool
    latency_ms: float | None = None
    detail: str | None = None


class LivenessResponse(BaseModel):
    status: ComponentStatus
    service: str
    version: str


class ReadinessResponse(BaseModel):
    status: ComponentStatus
    service: str
    version: str
    environment: str | None
    checked_at: datetime
    components: list[ComponentHealth]
    # True when component details are withheld (public endpoint in production).
    details_hidden: bool = False
