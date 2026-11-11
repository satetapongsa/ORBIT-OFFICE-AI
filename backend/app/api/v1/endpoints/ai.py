"""AI assistant endpoints (HTTP only — rules live in ``app.services.ai``)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import StreamingResponse

from app.api.deps import (
    DbDep,
    EmbeddingDep,
    MetaDep,
    SettingsDep,
    get_chat_provider,
    get_rate_limiter,
    require_permissions,
)
from app.core.db import get_async_session_factory
from app.core.permissions import P
from app.core.principal import CurrentUser
from app.core.rate_limit import RateLimiter
from app.schemas.ai import (
    ActionOut,
    AiStatus,
    ChatSessionCreate,
    ChatSessionDetail,
    ChatSessionOut,
    ChatSessionPage,
    ChatSessionUpdate,
    SendMessage,
)
from app.services.ai import chat
from app.services.ai.providers.base import ChatProvider

router = APIRouter(prefix="/ai", tags=["ai"])

ChatUser = Annotated[CurrentUser, Depends(require_permissions(P.AI_CHAT))]
ProviderDep = Annotated[ChatProvider | None, Depends(get_chat_provider)]
LimiterDep = Annotated[RateLimiter, Depends(get_rate_limiter)]


@router.get("/status", response_model=AiStatus, summary="Is the assistant available?")
async def ai_status(user: ChatUser, provider: ProviderDep) -> AiStatus:
    return chat.status(provider, user)


@router.get("/sessions", response_model=ChatSessionPage, summary="My conversations")
async def list_sessions(
    db: DbDep,
    user: ChatUser,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 30,
) -> ChatSessionPage:
    return await chat.list_sessions(db, user, page=page, page_size=page_size)


@router.post(
    "/sessions",
    response_model=ChatSessionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Start a conversation",
)
async def create_session(body: ChatSessionCreate, db: DbDep, user: ChatUser) -> ChatSessionOut:
    return await chat.create_session(db, user, body.title)


@router.get("/sessions/{session_id}", response_model=ChatSessionDetail, summary="Messages")
async def get_session(session_id: uuid.UUID, db: DbDep, user: ChatUser) -> ChatSessionDetail:
    return await chat.get_session_detail(db, user, session_id)


@router.patch("/sessions/{session_id}", response_model=ChatSessionOut, summary="Rename")
async def rename_session(
    session_id: uuid.UUID, body: ChatSessionUpdate, db: DbDep, user: ChatUser
) -> ChatSessionOut:
    return await chat.rename_session(db, user, session_id, body.title)


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete")
async def delete_session(session_id: uuid.UUID, db: DbDep, user: ChatUser) -> Response:
    await chat.delete_session(db, user, session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/sessions/{session_id}/messages",
    response_class=StreamingResponse,
    summary="Send a message; the answer streams as server-sent events",
)
async def send_message(
    session_id: uuid.UUID,
    body: SendMessage,
    db: DbDep,
    settings: SettingsDep,
    meta: MetaDep,
    user: ChatUser,
    provider: ProviderDep,
    limiter: LimiterDep,
    embedder: EmbeddingDep,
) -> StreamingResponse:
    await chat.precheck_send(db, user, settings, provider, limiter, session_id)
    assert provider is not None  # noqa: S101 - checked by precheck_send
    return StreamingResponse(
        chat.stream_reply(
            get_async_session_factory(),
            settings,
            provider,
            user,
            meta,
            session_id,
            body.content,
            embedder=embedder,
        ),
        media_type="text/event-stream",
        # no-transform stops proxies (Next.js, Nginx) from compressing and buffering the stream.
        headers={"Cache-Control": "no-store, no-transform", "X-Accel-Buffering": "no"},
    )


@router.post("/actions/{action_id}/confirm", response_model=ActionOut, summary="Run it")
async def confirm_action(
    action_id: uuid.UUID, db: DbDep, settings: SettingsDep, meta: MetaDep, user: ChatUser
) -> ActionOut:
    return await chat.confirm_action(db, settings, user, action_id, meta)


@router.post("/actions/{action_id}/reject", response_model=ActionOut, summary="Discard it")
async def reject_action(
    action_id: uuid.UUID, db: DbDep, meta: MetaDep, user: ChatUser
) -> ActionOut:
    return await chat.reject_action(db, user, action_id, meta)
