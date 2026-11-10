"""Shared FastAPI dependencies.

Authentication (``get_current_user``) and permission guards (``require_permissions``)
are added here in Phase 2.
"""

from __future__ import annotations

from fastapi import Request

from app.core.config import Settings


def get_app_settings(request: Request) -> Settings:
    """Settings the running app was created with (lets tests inject their own settings)."""
    settings: Settings = request.app.state.settings
    return settings
