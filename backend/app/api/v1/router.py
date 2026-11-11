"""Aggregates all version-1 routers."""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    audit,
    auth,
    dashboard,
    departments,
    health,
    notifications,
    roles,
    users,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(departments.router)
api_router.include_router(roles.router)
api_router.include_router(audit.router)
api_router.include_router(dashboard.router)
api_router.include_router(notifications.router)
