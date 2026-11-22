"""Direct messages between employees (ADR-060). Participants only; others get 404."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.deps import DbDep, per_user_rate_limit, require_permissions
from app.core.permissions import P
from app.core.principal import CurrentUser
from app.schemas.messaging import (
    ChatUnread,
    ConversationList,
    ConversationOut,
    MessageOut,
    MessagePage,
    SendMessage,
    StartConversation,
)
from app.services import chat as chat_service

router = APIRouter(prefix="/chat", tags=["chat"])

ChatUser = Annotated[CurrentUser, Depends(require_permissions(P.CHAT_USE))]
limit_messages = per_user_rate_limit("chat-send", lambda _s: 60, lambda _s: 60)
# The client sends at most one typing signal every 3 seconds per open thread.
limit_typing = per_user_rate_limit("chat-typing", lambda _s: 60, lambda _s: 60)


@router.get("/conversations", response_model=ConversationList, summary="My conversations")
async def list_conversations(db: DbDep, user: ChatUser) -> ConversationList:
    return await chat_service.list_conversations(db, user)


@router.get("/unread-count", response_model=ChatUnread, summary="Unread messages for the badge")
async def unread_count(db: DbDep, user: ChatUser) -> ChatUnread:
    return ChatUnread(unread_total=await chat_service.unread_total(db, user))


@router.post(
    "/conversations",
    response_model=ConversationOut,
    summary="Open (or create) the conversation with another user",
)
async def start_conversation(body: StartConversation, db: DbDep, user: ChatUser) -> ConversationOut:
    return await chat_service.start_conversation(db, user, body.user_id)


@router.get(
    "/conversations/{conversation_id}", response_model=ConversationOut, summary="One conversation"
)
async def get_conversation(
    conversation_id: uuid.UUID, db: DbDep, user: ChatUser
) -> ConversationOut:
    return await chat_service.get_conversation(db, user, conversation_id)


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=MessagePage,
    summary="Messages, oldest first (newest page unless `before` is given)",
)
async def list_messages(
    conversation_id: uuid.UUID,
    db: DbDep,
    user: ChatUser,
    before: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> MessagePage:
    return await chat_service.list_messages(db, user, conversation_id, before=before, limit=limit)


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=MessageOut,
    status_code=status.HTTP_201_CREATED,
    summary="Send a message",
    dependencies=[Depends(limit_messages)],
)
async def send_message(
    conversation_id: uuid.UUID, body: SendMessage, db: DbDep, user: ChatUser
) -> MessageOut:
    return await chat_service.send_message(db, user, conversation_id, body.body)


@router.post(
    "/conversations/{conversation_id}/read",
    response_model=ChatUnread,
    summary="Mark the conversation as read",
)
async def mark_read(conversation_id: uuid.UUID, db: DbDep, user: ChatUser) -> ChatUnread:
    return ChatUnread(unread_total=await chat_service.mark_read(db, user, conversation_id))


@router.post(
    "/conversations/{conversation_id}/typing",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Signal that I am typing (shown to the other person for a few seconds)",
    dependencies=[Depends(limit_typing)],
)
async def typing(conversation_id: uuid.UUID, db: DbDep, user: ChatUser) -> Response:
    await chat_service.set_typing(db, user, conversation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
