"""Aggregates all version-1 routers."""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    ai,
    analytics,
    audit,
    auth,
    dashboard,
    departments,
    directory,
    documents,
    employees,
    health,
    notifications,
    roles,
    tasks,
    tickets,
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
api_router.include_router(documents.router)
api_router.include_router(directory.router)
api_router.include_router(tasks.router)
api_router.include_router(employees.router)
api_router.include_router(ai.router)
api_router.include_router(tickets.router)
api_router.include_router(analytics.router)
