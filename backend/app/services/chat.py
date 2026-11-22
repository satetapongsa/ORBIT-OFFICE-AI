"""Direct messages between two users (ADR-060).

Only the two participants can see a conversation: everyone else, administrators included,
gets 404. Read state is one timestamp per participant, taken from the database clock (the
newest message's ``created_at``) so it never disagrees with message times.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import and_, func, or_, select, text, tuple_
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.core.errors import ConflictError, NotFoundError, ValidationFailedError
from app.core.permissions import P
from app.core.principal import CurrentUser
from app.models.identity import User
from app.models.messaging import Conversation, DirectMessage
from app.repositories import users as user_repo
from app.schemas.common import ErrorDetail
from app.schemas.messaging import (
    ChatPerson,
    ConversationList,
    ConversationOut,
    MessageOut,
    MessagePage,
)

NOT_FOUND = "ไม่พบบทสนทนานี้"
# A typing signal counts for this long; the client repeats it every few seconds while typing.
TYPING_FRESH_SECONDS = 6


def _pair(a: uuid.UUID, b: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    return (a, b) if a < b else (b, a)


def _mine(user_id: uuid.UUID) -> ColumnElement[bool]:
    return or_(Conversation.user_low_id == user_id, Conversation.user_high_id == user_id)


def _unread_condition(user_id: uuid.UUID) -> ColumnElement[bool]:
    """Messages from the other person that arrived after my last read time."""
    return and_(
        DirectMessage.sender_id != user_id,
        or_(
            and_(
                Conversation.user_low_id == user_id,
                or_(
                    Conversation.low_last_read_at.is_(None),
                    DirectMessage.created_at > Conversation.low_last_read_at,
                ),
            ),
            and_(
                Conversation.user_high_id == user_id,
                or_(
                    Conversation.high_last_read_at.is_(None),
                    DirectMessage.created_at > Conversation.high_last_read_at,
                ),
            ),
        ),
    )


def _person(user: User) -> ChatPerson:
    return ChatPerson(
        id=user.id,
        display_name=user.display_name,
        job_title=user.job_title,
        department_name=user.department.name if user.department else None,
        is_active=user.is_active and user.deleted_at is None,
    )


async def _get_mine(
    session: AsyncSession, user: CurrentUser, conversation_id: uuid.UUID
) -> Conversation:
    conversation = await session.scalar(
        select(Conversation).where(Conversation.id == conversation_id, _mine(user.id))
    )
    if conversation is None:
        raise NotFoundError(NOT_FOUND)
    return conversation


async def _typing_cutoff(session: AsyncSession) -> datetime:
    """Database time minus the freshness window, so client and server clocks never matter."""
    cutoff = await session.scalar(
        select(func.now() - text(f"interval '{TYPING_FRESH_SECONDS} seconds'"))
    )
    if not isinstance(cutoff, datetime):  # pragma: no cover - now() always returns a time
        raise TypeError("database did not return a timestamp")
    return cutoff


def _other_typing(conversation: Conversation, user_id: uuid.UUID, cutoff: datetime) -> bool:
    at = conversation.typing_at(conversation.other_user_id(user_id))
    return at is not None and at > cutoff


async def _summaries(
    session: AsyncSession, user: CurrentUser, conversations: Sequence[Conversation]
) -> list[ConversationOut]:
    if not conversations:
        return []
    ids = [c.id for c in conversations]
    unread = dict(
        (
            await session.execute(
                select(DirectMessage.conversation_id, func.count())
                .join(Conversation, Conversation.id == DirectMessage.conversation_id)
                .where(DirectMessage.conversation_id.in_(ids), _unread_condition(user.id))
                .group_by(DirectMessage.conversation_id)
            )
        ).all()
    )
    last_rows = (
        await session.scalars(
            select(DirectMessage)
            .where(DirectMessage.conversation_id.in_(ids))
            .order_by(
                DirectMessage.conversation_id,
                DirectMessage.created_at.desc(),
                DirectMessage.id.desc(),
            )
            .ext(distinct_on(DirectMessage.conversation_id))
        )
    ).all()
    last = {m.conversation_id: m for m in last_rows}
    others = {
        u.id: u
        for u in (
            await session.scalars(
                select(User).where(User.id.in_([c.other_user_id(user.id) for c in conversations]))
            )
        ).unique()
    }
    cutoff = await _typing_cutoff(session)
    out = []
    for c in conversations:
        other = others.get(c.other_user_id(user.id))
        if other is None:  # pragma: no cover - users are never hard-deleted
            continue
        message = last.get(c.id)
        out.append(
            ConversationOut(
                id=c.id,
                other=_person(other),
                last_message=MessageOut.model_validate(message) if message else None,
                last_message_at=c.last_message_at,
                unread_count=int(unread.get(c.id, 0)),
                other_last_read_at=c.last_read_at(c.other_user_id(user.id)),
                other_typing=_other_typing(c, user.id, cutoff),
            )
        )
    return out


async def unread_total(session: AsyncSession, user: CurrentUser) -> int:
    count = await session.scalar(
        select(func.count())
        .select_from(DirectMessage)
        .join(Conversation, Conversation.id == DirectMessage.conversation_id)
        .where(_mine(user.id), _unread_condition(user.id))
    )
    return int(count or 0)


async def list_conversations(session: AsyncSession, user: CurrentUser) -> ConversationList:
    conversations = (
        await session.scalars(
            select(Conversation)
            .where(_mine(user.id))
            .order_by(
                Conversation.last_message_at.desc().nulls_last(), Conversation.created_at.desc()
            )
            .limit(200)
        )
    ).all()
    return ConversationList(
        items=await _summaries(session, user, conversations),
        unread_total=await unread_total(session, user),
    )


async def start_conversation(
    session: AsyncSession, user: CurrentUser, other_id: uuid.UUID
) -> ConversationOut:
    if other_id == user.id:
        raise ValidationFailedError(
            details=[ErrorDetail(field="user_id", message="ไม่สามารถแชทกับตัวเองได้")]
        )
    other = await user_repo.get_by_id(session, other_id)
    if other is None:
        raise NotFoundError("ไม่พบพนักงานคนนี้")
    low, high = _pair(user.id, other_id)
    conversation = await session.scalar(
        select(Conversation).where(
            Conversation.user_low_id == low, Conversation.user_high_id == high
        )
    )
    if conversation is None:
        # A new thread needs someone who can actually read it; an existing one stays open.
        if not other.is_active:
            raise ConflictError("บัญชีของพนักงานคนนี้ถูกระงับอยู่")
        if P.CHAT_USE not in await user_repo.permissions_for_user(session, other_id):
            raise ConflictError("พนักงานคนนี้ไม่มีสิทธิ์ใช้งานแชท")
        conversation = Conversation(user_low_id=low, user_high_id=high)
        session.add(conversation)
        await session.commit()
        await session.refresh(conversation)
    return (await _summaries(session, user, [conversation]))[0]


async def get_conversation(
    session: AsyncSession, user: CurrentUser, conversation_id: uuid.UUID
) -> ConversationOut:
    conversation = await _get_mine(session, user, conversation_id)
    return (await _summaries(session, user, [conversation]))[0]


async def list_messages(
    session: AsyncSession,
    user: CurrentUser,
    conversation_id: uuid.UUID,
    *,
    before: uuid.UUID | None,
    limit: int,
) -> MessagePage:
    conversation = await _get_mine(session, user, conversation_id)
    stmt = select(DirectMessage).where(DirectMessage.conversation_id == conversation_id)
    if before is not None:
        anchor = await session.scalar(
            select(DirectMessage).where(
                DirectMessage.id == before, DirectMessage.conversation_id == conversation_id
            )
        )
        if anchor is None:
            raise NotFoundError("ไม่พบข้อความอ้างอิง")
        stmt = stmt.where(
            tuple_(DirectMessage.created_at, DirectMessage.id)
            < tuple_(anchor.created_at, anchor.id)
        )
    rows = (
        await session.scalars(
            stmt.order_by(DirectMessage.created_at.desc(), DirectMessage.id.desc()).limit(limit + 1)
        )
    ).all()
    has_more = len(rows) > limit
    page = list(reversed(rows[:limit]))
    return MessagePage(
        items=[MessageOut.model_validate(m) for m in page],
        has_more=has_more,
        other_last_read_at=conversation.last_read_at(conversation.other_user_id(user.id)),
        other_typing=_other_typing(conversation, user.id, await _typing_cutoff(session)),
    )


async def send_message(
    session: AsyncSession, user: CurrentUser, conversation_id: uuid.UUID, body: str
) -> MessageOut:
    conversation = await _get_mine(session, user, conversation_id)
    other = await user_repo.get_by_id(session, conversation.other_user_id(user.id))
    if other is None or not other.is_active:
        raise ConflictError("บัญชีของพนักงานคนนี้ถูกระงับอยู่ จึงส่งข้อความไม่ได้")
    message = DirectMessage(conversation_id=conversation.id, sender_id=user.id, body=body)
    session.add(message)
    await session.flush()
    await session.refresh(message)
    conversation.last_message_at = message.created_at
    conversation.mark_read(user.id, message.created_at)  # my own message is read
    conversation.set_typing(user.id, None)  # sending ends "typing"
    await session.commit()
    return MessageOut.model_validate(message)


async def mark_read(session: AsyncSession, user: CurrentUser, conversation_id: uuid.UUID) -> int:
    """Marks everything up to the newest message as read; returns the remaining total."""
    conversation = await _get_mine(session, user, conversation_id)
    newest = await session.scalar(
        select(func.max(DirectMessage.created_at)).where(
            DirectMessage.conversation_id == conversation.id
        )
    )
    current = conversation.last_read_at(user.id)
    if newest is not None and (current is None or newest > current):
        conversation.mark_read(user.id, newest)
        await session.commit()
    return await unread_total(session, user)


async def set_typing(session: AsyncSession, user: CurrentUser, conversation_id: uuid.UUID) -> None:
    """Records that the user is typing right now (database time)."""
    conversation = await _get_mine(session, user, conversation_id)
    conversation.set_typing(user.id, func.now())
    await session.commit()
