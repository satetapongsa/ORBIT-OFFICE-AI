"""Direct messages between employees (ADR-060). Participants only; others get 404."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile, status
from fastapi.responses import StreamingResponse

from app.api.deps import (
    DbDep,
    SettingsDep,
    get_document_storage,
    limit_uploads,
    per_user_rate_limit,
    require_permissions,
)
from app.api.v1.endpoints.documents import content_disposition
from app.core.chat_hub import ChatHub
from app.core.permissions import P
from app.core.principal import CurrentUser
from app.schemas.messaging import (
    ChatEvents,
    ChatUnread,
    ConversationList,
    ConversationOut,
    GroupAddMembers,
    GroupCreate,
    GroupDetail,
    GroupMessageOut,
    GroupMessagePage,
    GroupRename,
    GroupSummary,
    MessageOut,
    MessagePage,
    SendMessage,
    StartConversation,
)
from app.services import chat as chat_service
from app.services import chat_files
from app.services import chat_groups as group_service
from app.services.uploads import FileStorage

router = APIRouter(prefix="/chat", tags=["chat"])


def get_chat_hub(request: Request) -> ChatHub:
    hub: ChatHub = request.app.state.chat_hub
    return hub


HubDep = Annotated[ChatHub, Depends(get_chat_hub)]
StorageDep = Annotated[FileStorage, Depends(get_document_storage)]
FileField = Annotated[UploadFile, File(description="PDF, DOCX, XLSX, TXT, PNG or JPG")]
CaptionField = Annotated[str | None, Form(max_length=4000)]

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
    conversation_id: uuid.UUID, body: SendMessage, db: DbDep, user: ChatUser, hub: HubDep
) -> MessageOut:
    return await chat_service.send_message(db, user, conversation_id, body.body, hub)


@router.post(
    "/conversations/{conversation_id}/read",
    response_model=ChatUnread,
    summary="Mark the conversation as read",
)
async def mark_read(
    conversation_id: uuid.UUID, db: DbDep, user: ChatUser, hub: HubDep
) -> ChatUnread:
    return ChatUnread(unread_total=await chat_service.mark_read(db, user, conversation_id, hub))


@router.post(
    "/conversations/{conversation_id}/typing",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Signal that I am typing (shown to the other person for a few seconds)",
    dependencies=[Depends(limit_typing)],
)
async def typing(conversation_id: uuid.UUID, db: DbDep, user: ChatUser, hub: HubDep) -> Response:
    await chat_service.set_typing(db, user, conversation_id, hub)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/events",
    response_model=ChatEvents,
    summary="Long poll: answers as soon as anything changes in my conversations",
)
async def events(
    db: DbDep,
    user: ChatUser,
    hub: HubDep,
    since: int = -1,
    wait: Annotated[int, Query(ge=0, le=30)] = 25,
) -> ChatEvents:
    # Give the database connection back before waiting: nothing below touches the database,
    # and a held connection per open browser tab would exhaust the small pool.
    await db.close()
    return ChatEvents(version=await hub.wait(user.id, since, float(wait)))


@router.patch(
    "/conversations/{conversation_id}/messages/{message_id}",
    response_model=MessageOut,
    summary="Edit one of my messages",
    dependencies=[Depends(limit_messages)],
)
async def edit_message(
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    body: SendMessage,
    db: DbDep,
    user: ChatUser,
    hub: HubDep,
) -> MessageOut:
    return await chat_service.edit_message(db, user, conversation_id, message_id, body.body, hub)


# --- Group chats (ADR-071) ------------------------------------------------------------------


@router.get("/groups", response_model=list[GroupSummary], summary="My group chats")
async def list_groups(db: DbDep, user: ChatUser) -> list[GroupSummary]:
    return await group_service.list_groups(db, user)


@router.post(
    "/groups",
    response_model=GroupDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Create a group chat",
)
async def create_group(body: GroupCreate, db: DbDep, user: ChatUser, hub: HubDep) -> GroupDetail:
    return await group_service.create_group(db, user, body, hub)


@router.get("/groups/{group_id}", response_model=GroupDetail, summary="Group with its members")
async def get_group(group_id: uuid.UUID, db: DbDep, user: ChatUser) -> GroupDetail:
    return await group_service.get_group(db, user, group_id)


@router.patch("/groups/{group_id}", response_model=GroupDetail, summary="Rename (admin)")
async def rename_group(
    group_id: uuid.UUID, body: GroupRename, db: DbDep, user: ChatUser, hub: HubDep
) -> GroupDetail:
    return await group_service.rename_group(db, user, group_id, body.name, hub)


@router.post("/groups/{group_id}/members", response_model=GroupDetail, summary="Add (admin)")
async def add_members(
    group_id: uuid.UUID, body: GroupAddMembers, db: DbDep, user: ChatUser, hub: HubDep
) -> GroupDetail:
    return await group_service.add_members(db, user, group_id, body.user_ids, hub)


@router.delete(
    "/groups/{group_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a member (admin) or leave (yourself)",
)
async def remove_member(
    group_id: uuid.UUID, user_id: uuid.UUID, db: DbDep, user: ChatUser, hub: HubDep
) -> Response:
    await group_service.remove_member(db, user, group_id, user_id, hub)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/groups/{group_id}/messages", response_model=GroupMessagePage, summary="Group messages"
)
async def group_messages(
    group_id: uuid.UUID,
    db: DbDep,
    user: ChatUser,
    before: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> GroupMessagePage:
    return await group_service.list_messages(db, user, group_id, before=before, limit=limit)


@router.post(
    "/groups/{group_id}/messages",
    response_model=GroupMessageOut,
    status_code=status.HTTP_201_CREATED,
    summary="Send to the group",
    dependencies=[Depends(limit_messages)],
)
async def send_group_message(
    group_id: uuid.UUID, body: SendMessage, db: DbDep, user: ChatUser, hub: HubDep
) -> GroupMessageOut:
    return await group_service.send_message(db, user, group_id, body.body, hub)


@router.patch(
    "/groups/{group_id}/messages/{message_id}",
    response_model=GroupMessageOut,
    summary="Edit my group message",
    dependencies=[Depends(limit_messages)],
)
async def edit_group_message(
    group_id: uuid.UUID,
    message_id: uuid.UUID,
    body: SendMessage,
    db: DbDep,
    user: ChatUser,
    hub: HubDep,
) -> GroupMessageOut:
    return await group_service.edit_message(db, user, group_id, message_id, body.body, hub)


@router.post("/groups/{group_id}/read", response_model=ChatUnread, summary="Mark as read")
async def mark_group_read(
    group_id: uuid.UUID, db: DbDep, user: ChatUser, hub: HubDep
) -> ChatUnread:
    await group_service.mark_read(db, user, group_id, hub)
    return ChatUnread(unread_total=await chat_service.unread_total(db, user))


@router.post(
    "/groups/{group_id}/typing",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="I am typing in the group",
    dependencies=[Depends(limit_typing)],
)
async def group_typing(group_id: uuid.UUID, db: DbDep, user: ChatUser, hub: HubDep) -> Response:
    await group_service.set_typing(db, user, group_id, hub)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Files and images (ADR-072) ---------------------------------------------------------


@router.post(
    "/conversations/{conversation_id}/files",
    response_model=MessageOut,
    status_code=status.HTTP_201_CREATED,
    summary="Send a file or image (optional caption)",
    dependencies=[Depends(limit_uploads)],
)
async def send_direct_file(
    conversation_id: uuid.UUID,
    db: DbDep,
    settings: SettingsDep,
    user: ChatUser,
    hub: HubDep,
    storage: StorageDep,
    file: FileField,
    body: CaptionField = None,
) -> MessageOut:
    return await chat_files.send_direct_file(
        db, settings, storage, user, conversation_id, file, body, hub
    )


@router.post(
    "/groups/{group_id}/files",
    response_model=GroupMessageOut,
    status_code=status.HTTP_201_CREATED,
    summary="Send a file or image to a group (optional caption)",
    dependencies=[Depends(limit_uploads)],
)
async def send_group_file(
    group_id: uuid.UUID,
    db: DbDep,
    settings: SettingsDep,
    user: ChatUser,
    hub: HubDep,
    storage: StorageDep,
    file: FileField,
    body: CaptionField = None,
) -> GroupMessageOut:
    return await chat_files.send_group_file(db, settings, storage, user, group_id, file, body, hub)


@router.get(
    "/attachments/{attachment_id}",
    response_class=StreamingResponse,
    summary="Download a chat file (people in that chat only)",
)
async def download_attachment(
    attachment_id: uuid.UUID, db: DbDep, user: ChatUser, storage: StorageDep
) -> StreamingResponse:
    attachment, stream = await chat_files.open_file(db, storage, user, attachment_id)
    return StreamingResponse(
        iter(stream),
        media_type=attachment.mime_type,
        headers={
            # Always a download; the app shows images from a blob, never as a page.
            "Content-Disposition": content_disposition(attachment.original_filename),
            "Content-Length": str(attachment.size_bytes),
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
            "Cache-Control": "private, max-age=3600",
        },
    )
