"""Whitelisted AI tools (docs/SECURITY.md §5).

Every tool runs **as the signed-in user** through the same services and visibility predicates
as the HTTP API, so the assistant can never see or change more than the user could by hand.

* Read-only tools return data immediately.
* Mutating tools never run when the model calls them: the chat service stores the validated
  arguments as an ``ai_action_requests`` row and the user confirms or rejects it in the UI.
  :meth:`AiTool.precheck` catches obvious problems early; :meth:`AiTool.execute` repeats every
  check at confirmation time (permissions may have changed).

There is no SQL, shell, file or network tool, and tools accept only the arguments below.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Annotated, Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import PermissionDeniedError
from app.core.permissions import P
from app.core.principal import CurrentUser, RequestMeta
from app.core.security import utcnow
from app.models.task import TaskPriority, TaskStatus
from app.repositories import tasks as task_repo
from app.repositories.tasks import TaskFilters
from app.schemas.tasks import TaskCreate
from app.services.ai.providers.base import ToolSpec
from app.services.tasks import queries as task_queries
from app.services.tasks import service as task_service
from app.services.tasks.service import STATUS_LABELS

PRIORITY_LABELS = {
    TaskPriority.LOW: "ต่ำ",
    TaskPriority.MEDIUM: "ปานกลาง",
    TaskPriority.HIGH: "สูง",
    TaskPriority.URGENT: "ด่วนที่สุด",
}
DESCRIPTION_LIMIT = 2000


@dataclass(frozen=True, slots=True)
class ToolContext:
    session: AsyncSession
    user: CurrentUser
    settings: Settings
    meta: RequestMeta


class StrictArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- Argument models (validated before anything runs) ------------------------------------


class GetMyTasksArgs(StrictArgs):
    scope: Literal["assigned", "created", "all"] = "assigned"
    include_completed: bool = False
    query: Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)] | None = None
    limit: int = Field(default=10, ge=1, le=20)


class TaskIdArgs(StrictArgs):
    task_id: uuid.UUID


class FindColleaguesArgs(StrictArgs):
    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class CreateTaskArgs(StrictArgs):
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
    description: (
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=DESCRIPTION_LIMIT)]
        | None
    ) = None
    priority: TaskPriority = TaskPriority.MEDIUM
    due_date: date | None = None
    assignee_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)


class UpdateTaskStatusArgs(StrictArgs):
    task_id: uuid.UUID
    status: TaskStatus


# --- Helpers ---------------------------------------------------------------------------


def _local(value: datetime | None, tz: str) -> str | None:
    return value.astimezone(ZoneInfo(tz)).strftime("%Y-%m-%d %H:%M") if value else None


def due_at_from_date(day: date, tz: str) -> datetime:
    """A due *day* means the end of that business day (same rule as the web UI, ADR-036)."""
    return datetime.combine(day, time(23, 59), tzinfo=ZoneInfo(tz))


def _require(user: CurrentUser, *permissions: str) -> None:
    if not user.has_all(permissions):
        raise PermissionDeniedError("คุณไม่มีสิทธิ์ใช้ความสามารถนี้")


# --- Tool implementations --------------------------------------------------------------


async def _get_my_tasks(ctx: ToolContext, args: BaseModel) -> dict[str, Any]:
    assert isinstance(args, GetMyTasksArgs)  # noqa: S101 - registry guarantees the type
    rows, total = await task_repo.list_tasks(
        ctx.session,
        ctx.user,
        TaskFilters(scope=args.scope, q=args.query, open_only=not args.include_completed),
        now=utcnow(),
        sort="due",
        page=1,
        page_size=args.limit,
    )
    now = utcnow()
    return {
        "total": total,
        "tasks": [
            {
                "id": str(r.task.id),
                "title": r.task.title,
                "status": r.task.status,
                "status_label": STATUS_LABELS[TaskStatus(r.task.status)],
                "priority": r.task.priority,
                "due_at": _local(r.task.due_at, ctx.settings.app_timezone),
                "is_overdue": task_queries.is_overdue(r.task.due_at, r.task.status, now),
                "assignees": [name for _, name in r.assignees],
                "created_by": r.creator_name,
                "link": f"/tasks/{r.task.id}",
            }
            for r in rows
        ],
    }


async def _get_task_details(ctx: ToolContext, args: BaseModel) -> dict[str, Any]:
    assert isinstance(args, TaskIdArgs)  # noqa: S101
    detail = await task_queries.get_detail(ctx.session, ctx.user, args.task_id)
    description = detail.description or ""
    return {
        "id": str(detail.id),
        "title": detail.title,
        "description": description[:DESCRIPTION_LIMIT],
        "status": detail.status.value,
        "status_label": STATUS_LABELS[detail.status],
        "priority": detail.priority.value,
        "due_at": _local(detail.due_at, ctx.settings.app_timezone),
        "is_overdue": detail.is_overdue,
        "department": detail.department.name if detail.department else None,
        "created_by": detail.created_by.display_name,
        "assignees": [a.display_name for a in detail.assignees],
        "comment_count": detail.comment_count,
        "attachment_count": detail.attachment_count,
        "what_you_can_do": {
            "change_status": detail.capabilities.can_change_status,
            "cancel": detail.capabilities.can_cancel,
            "edit": detail.capabilities.can_edit,
        },
        "link": f"/tasks/{detail.id}",
    }


async def _find_colleagues(ctx: ToolContext, args: BaseModel) -> dict[str, Any]:
    assert isinstance(args, FindColleaguesArgs)  # noqa: S101
    people = await task_queries.assignable_users(ctx.session, ctx.user, args.query, limit=10)
    return {
        "people": [
            {
                "id": str(p.id),
                "display_name": p.display_name,
                "job_title": p.job_title,
                "department": p.department.name if p.department else None,
            }
            for p in people
        ],
        "note": "Only people this user may assign tasks to are listed.",
    }


async def _precheck_create(ctx: ToolContext, args: BaseModel) -> str:
    assert isinstance(args, CreateTaskArgs)  # noqa: S101
    _require(ctx.user, P.TASKS_CREATE)
    requested = args.assignee_ids or [ctx.user.id]
    if any(uid != ctx.user.id for uid in requested):
        _require(ctx.user, P.TASKS_ASSIGN)
    people = await task_service.validate_assignees(
        ctx.session, ctx.user, ctx.user.department_id, requested
    )
    names = ", ".join("คุณเอง" if uid == ctx.user.id else name for uid, name in people)
    parts = [f"สร้างงาน “{args.title}”", f"ความสำคัญ{PRIORITY_LABELS[args.priority]}"]
    if args.due_date:
        parts.append(f"กำหนดส่ง {args.due_date.isoformat()}")
    parts.append(f"ผู้รับผิดชอบ: {names}")
    return " · ".join(parts)


async def _execute_create(ctx: ToolContext, args: BaseModel) -> dict[str, Any]:
    assert isinstance(args, CreateTaskArgs)  # noqa: S101
    task_id = await task_service.create_task(
        ctx.session,
        ctx.user,
        TaskCreate(
            title=args.title,
            description=args.description,
            priority=args.priority,
            due_at=due_at_from_date(args.due_date, ctx.settings.app_timezone)
            if args.due_date
            else None,
            assignee_ids=args.assignee_ids,
        ),
        ctx.meta,
    )
    return {"task_id": str(task_id), "link": f"/tasks/{task_id}"}


async def _precheck_status(ctx: ToolContext, args: BaseModel) -> str:
    assert isinstance(args, UpdateTaskStatusArgs)  # noqa: S101
    access = await task_service.get_access(ctx.session, ctx.user, args.task_id)
    if not access.capabilities.can_change_status:
        raise PermissionDeniedError("คุณไม่มีสิทธิ์เปลี่ยนสถานะงานนี้")
    if args.status is TaskStatus.CANCELLED and not access.capabilities.can_cancel:
        raise PermissionDeniedError("เฉพาะผู้สร้างงานหรือผู้จัดการเท่านั้นที่ยกเลิกงานได้")
    current = TaskStatus(access.task.status)
    return (
        f"เปลี่ยนสถานะงาน “{access.task.title}” จาก{STATUS_LABELS[current]}"
        f" เป็น{STATUS_LABELS[args.status]}"
    )


async def _execute_status(ctx: ToolContext, args: BaseModel) -> dict[str, Any]:
    assert isinstance(args, UpdateTaskStatusArgs)  # noqa: S101
    await task_service.change_status(ctx.session, ctx.user, args.task_id, args.status, ctx.meta)
    return {
        "task_id": str(args.task_id),
        "status": args.status.value,
        "link": f"/tasks/{args.task_id}",
    }


# --- Registry ----------------------------------------------------------------------------

Handler = Callable[[ToolContext, BaseModel], Awaitable[dict[str, Any]]]
Precheck = Callable[[ToolContext, BaseModel], Awaitable[str]]


@dataclass(frozen=True, slots=True)
class AiTool:
    name: str
    label: str  # Thai, shown in the chat while the tool runs
    description: str
    input_schema: dict[str, Any]
    args_model: type[BaseModel]
    permissions: tuple[str, ...]
    run: Handler | None = None  # read-only tools
    precheck: Precheck | None = None  # mutating tools: validate + Thai summary
    execute: Handler | None = None  # mutating tools: runs only after confirmation

    @property
    def mutating(self) -> bool:
        return self.execute is not None

    def spec(self) -> ToolSpec:
        return ToolSpec(self.name, self.description, self.input_schema)


def _object(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


_TASK_ID = {"type": "string", "format": "uuid", "description": "Task id from get_my_tasks."}

TOOLS: dict[str, AiTool] = {
    tool.name: tool
    for tool in (
        AiTool(
            name="get_my_tasks",
            label="ค้นหางานของคุณ",
            description=(
                "List tasks the user can see, earliest due first. scope: 'assigned' = assigned "
                "to the user (default), 'created' = created by the user, 'all' = everything the "
                "user may see. Completed/cancelled tasks are excluded unless include_completed."
            ),
            input_schema=_object(
                {
                    "scope": {"type": "string", "enum": ["assigned", "created", "all"]},
                    "include_completed": {"type": "boolean"},
                    "query": {"type": "string", "description": "Optional words in the title."},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                },
                [],
            ),
            args_model=GetMyTasksArgs,
            permissions=(P.TASKS_READ_OWN,),
            run=_get_my_tasks,
        ),
        AiTool(
            name="get_task_details",
            label="เปิดดูรายละเอียดงาน",
            description="Details of one task the user can see (description, people, status).",
            input_schema=_object({"task_id": _TASK_ID}, ["task_id"]),
            args_model=TaskIdArgs,
            permissions=(P.TASKS_READ_OWN,),
            run=_get_task_details,
        ),
        AiTool(
            name="find_colleagues",
            label="ค้นหาเพื่อนร่วมงาน",
            description=(
                "Find people the user may assign tasks to, by name or job title. Use the "
                "returned id for create_task.assignee_ids."
            ),
            input_schema=_object({"query": {"type": "string"}}, ["query"]),
            args_model=FindColleaguesArgs,
            permissions=(P.TASKS_READ_OWN,),
            run=_find_colleagues,
        ),
        AiTool(
            name="create_task",
            label="เตรียมสร้างงาน",
            description=(
                "PROPOSE a new task. Nothing is created until the user confirms in the app. "
                "Empty assignee_ids = assign to the user. due_date is a calendar date "
                "(YYYY-MM-DD) in the company time zone."
            ),
            input_schema=_object(
                {
                    "title": {"type": "string", "maxLength": 300},
                    "description": {"type": "string", "maxLength": DESCRIPTION_LIMIT},
                    "priority": {"type": "string", "enum": [p.value for p in TaskPriority]},
                    "due_date": {"type": "string", "format": "date"},
                    "assignee_ids": {
                        "type": "array",
                        "items": {"type": "string", "format": "uuid"},
                        "maxItems": 20,
                    },
                },
                ["title"],
            ),
            args_model=CreateTaskArgs,
            permissions=(P.TASKS_CREATE,),
            precheck=_precheck_create,
            execute=_execute_create,
        ),
        AiTool(
            name="update_task_status",
            label="เตรียมเปลี่ยนสถานะงาน",
            description=(
                "PROPOSE changing a task's status. Nothing changes until the user confirms in "
                "the app."
            ),
            input_schema=_object(
                {
                    "task_id": _TASK_ID,
                    "status": {"type": "string", "enum": [s.value for s in TaskStatus]},
                },
                ["task_id", "status"],
            ),
            args_model=UpdateTaskStatusArgs,
            permissions=(P.TASKS_READ_OWN,),
            precheck=_precheck_status,
            execute=_execute_status,
        ),
    )
}


def tools_for(user: CurrentUser) -> list[AiTool]:
    """Tools offered to this user: ``ai:use_tools`` plus each tool's own permissions."""
    if not user.has(P.AI_USE_TOOLS):
        return []
    return [t for t in TOOLS.values() if user.has_all(t.permissions)]
