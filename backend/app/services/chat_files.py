"""Files and images in chat (ADR-072).

A file is sent as a message with an optional caption. It goes through the same upload checks as
ticket attachments (size limit, type sniffed from the content: PDF, DOCX, XLSX, TXT, PNG, JPG)
and is stored under a server-generated key. Only the people in that chat can open it: the two
participants of a direct message, or the current members of a group (someone who left or was
removed loses access). Others get 404.
"""

from __future__ import annotations

import uuid

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.chat_hub import ChatHub
from app.core.config import Settings
from app.core.errors import ConflictError, NotFoundError, ValidationFailedError
from app.core.principal import CurrentUser
from app.core.storage import ObjectStream
from app.models.chat_attachment import ChatAttachment
from app.models.chat_group import ChatGroupMember
from app.models.messaging import MESSAGE_MAX_CHARS, Conversation
from app.repositories import users as user_repo
from app.schemas.common import ErrorDetail
from app.schemas.messaging import GroupMessageOut, MessageOut
from app.services import chat as chat_service
from app.services import chat_groups as group_service
from app.services.documents.files import inspect_attachment
from app.services.uploads import (
    FileStorage,
    discard_object,
    open_object,
    receive_upload,
    store_upload,
)

NOT_FOUND = "ไม่พบไฟล์นี้"


def _caption(text: str | None) -> str:
    caption = (text or "").strip()
    if len(caption) > MESSAGE_MAX_CHARS:
        raise ValidationFailedError(
            details=[
                ErrorDetail(field="body", message=f"ข้อความยาวได้ไม่เกิน {MESSAGE_MAX_CHARS} ตัวอักษร")
            ]
        )
    return caption


async def _store(
    session: AsyncSession,
    settings: Settings,
    storage: FileStorage,
    user: CurrentUser,
    upload: UploadFile,
    *,
    conversation_id: uuid.UUID | None = None,
    group_id: uuid.UUID | None = None,
) -> tuple[ChatAttachment, str]:
    stored = await receive_upload(upload, settings, inspect_attachment)
    attachment_id = uuid.uuid4()
    scope = f"dm/{conversation_id}" if conversation_id else f"groups/{group_id}"
    key = f"chat/{scope}/{attachment_id}"
    await store_upload(storage, key, upload, stored)
    attachment = ChatAttachment(
        id=attachment_id,
        conversation_id=conversation_id,
        group_id=group_id,
        uploaded_by=user.id,
        storage_key=key,
        original_filename=stored.inspected.filename,
        file_type=stored.inspected.file_type.value,
        mime_type=stored.inspected.mime_type,
        size_bytes=stored.size_bytes,
        sha256=stored.sha256,
    )
    session.add(attachment)
    return attachment, key


async def _cleanup_if_unsaved(
    session: AsyncSession, storage: FileStorage, attachment_id: uuid.UUID, key: str
) -> None:
    """After a failure: remove the stored object unless its row was committed after all."""
    await session.rollback()
    saved = await session.scalar(
        select(ChatAttachment.id).where(ChatAttachment.id == attachment_id)
    )
    if saved is None:
        await discard_object(storage, key)


async def send_direct_file(
    session: AsyncSession,
    settings: Settings,
    storage: FileStorage,
    user: CurrentUser,
    conversation_id: uuid.UUID,
    upload: UploadFile,
    caption: str | None,
    hub: ChatHub,
) -> MessageOut:
    body = _caption(caption)
    # Check access before reading the file.
    conversation = await session.scalar(
        select(Conversation).where(Conversation.id == conversation_id, chat_service._mine(user.id))
    )
    if conversation is None:
        raise NotFoundError(chat_service.NOT_FOUND)
    other = await user_repo.get_by_id(session, conversation.other_user_id(user.id))
    if other is None or not other.is_active:
        raise ConflictError("บัญชีของพนักงานคนนี้ถูกระงับอยู่ จึงส่งข้อความไม่ได้")
    attachment, key = await _store(
        session, settings, storage, user, upload, conversation_id=conversation_id
    )
    try:
        return await chat_service.send_message(
            session, user, conversation_id, body, hub, attachment=attachment
        )
    except Exception:
        await _cleanup_if_unsaved(session, storage, attachment.id, key)
        raise


async def send_group_file(
    session: AsyncSession,
    settings: Settings,
    storage: FileStorage,
    user: CurrentUser,
    group_id: uuid.UUID,
    upload: UploadFile,
    caption: str | None,
    hub: ChatHub,
) -> GroupMessageOut:
    body = _caption(caption)
    await group_service._membership(session, user, group_id)
    attachment, key = await _store(session, settings, storage, user, upload, group_id=group_id)
    try:
        return await group_service.send_message(
            session, user, group_id, body, hub, attachment=attachment
        )
    except Exception:
        await _cleanup_if_unsaved(session, storage, attachment.id, key)
        raise


async def open_file(
    session: AsyncSession, storage: FileStorage, user: CurrentUser, attachment_id: uuid.UUID
) -> tuple[ChatAttachment, ObjectStream]:
    attachment = await session.get(ChatAttachment, attachment_id)
    if attachment is None:
        raise NotFoundError(NOT_FOUND)
    if attachment.conversation_id is not None:
        allowed = await session.scalar(
            select(Conversation.id).where(
                Conversation.id == attachment.conversation_id, chat_service._mine(user.id)
            )
        )
    else:
        allowed = await session.scalar(
            select(ChatGroupMember.user_id).where(
                ChatGroupMember.group_id == attachment.group_id,
                ChatGroupMember.user_id == user.id,
            )
        )
    if allowed is None:
        raise NotFoundError(NOT_FOUND)
    return attachment, await open_object(storage, attachment.storage_key)
