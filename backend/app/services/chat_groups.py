"""Group chats (ADR-071).

* Only current members see a group; former members lose access (404).
* The creator is an admin. Admins rename the group, add people and remove members; anyone may
  leave. When the last admin leaves, the longest-standing member becomes admin; the group is
  deleted when nobody is left.
* Membership changes are posted in the group as system messages.
* Read state, typing and real-time wake-ups work as in direct messages (ADR-061/062).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from datetime import datetime

from sqlalchemy import and_, delete, func, or_, select, text, tuple_, update
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.chat_hub import ChatHub
from app.core.errors import NotFoundError, PermissionDeniedError, ValidationFailedError
from app.core.permissions import P
from app.core.principal import CurrentUser
from app.models.chat_group import (
    GROUP_MAX_MEMBERS,
    ChatGroup,
    ChatGroupMember,
    GroupMessage,
    GroupMessageKind,
    GroupRole,
)
from app.models.identity import User
from app.repositories import users as user_repo
from app.schemas.common import ErrorDetail
from app.schemas.messaging import (
    GroupCreate,
    GroupDetail,
    GroupMember,
    GroupMessageOut,
    GroupMessagePage,
    GroupSummary,
)
from app.services.chat import TYPING_FRESH_SECONDS

NOT_FOUND = "ไม่พบกลุ่มแชทนี้"


def _fail(field: str, message: str) -> ValidationFailedError:
    return ValidationFailedError(details=[ErrorDetail(field=field, message=message)])


async def _cutoff(session: AsyncSession) -> datetime:
    value = await session.scalar(
        select(func.now() - text(f"interval '{TYPING_FRESH_SECONDS} seconds'"))
    )
    if not isinstance(value, datetime):  # pragma: no cover
        raise TypeError("database did not return a timestamp")
    return value


async def _membership(
    session: AsyncSession, user: CurrentUser, group_id: uuid.UUID, *, lock: bool = False
) -> tuple[ChatGroup, ChatGroupMember]:
    stmt = select(ChatGroupMember).where(
        ChatGroupMember.group_id == group_id, ChatGroupMember.user_id == user.id
    )
    member = await session.scalar(stmt.with_for_update() if lock else stmt)
    group = await session.get(ChatGroup, group_id) if member else None
    if member is None or group is None:
        raise NotFoundError(NOT_FOUND)
    return group, member


def _admin(member: ChatGroupMember) -> None:
    if member.role != GroupRole.ADMIN.value:
        raise PermissionDeniedError("ต้องเป็นผู้ดูแลกลุ่ม")


async def _member_ids(session: AsyncSession, group_id: uuid.UUID) -> list[uuid.UUID]:
    return list(
        (
            await session.scalars(
                select(ChatGroupMember.user_id).where(ChatGroupMember.group_id == group_id)
            )
        ).all()
    )


async def _eligible(session: AsyncSession, ids: Iterable[uuid.UUID]) -> list[User]:
    """Active users who may use chat (others could not read the group)."""
    wanted = set(ids)
    if not wanted:
        return []
    users = (
        (
            await session.scalars(
                select(User).where(
                    User.id.in_(wanted), User.is_active.is_(True), User.deleted_at.is_(None)
                )
            )
        )
        .unique()
        .all()
    )
    if len(users) != len(wanted):
        raise _fail("member_ids", "มีสมาชิกที่ไม่พบหรือบัญชีถูกระงับ")
    for u in users:
        if P.CHAT_USE not in await user_repo.permissions_for_user(session, u.id):
            raise _fail("member_ids", f"{u.display_name} ไม่มีสิทธิ์ใช้งานแชท")
    return list(users)


async def _system(
    session: AsyncSession, group: ChatGroup, body: str, actor_id: uuid.UUID | None = None
) -> None:
    """Add a notice ("X added Y"); the person who caused it has already "read" it."""
    message = GroupMessage(group_id=group.id, kind=GroupMessageKind.SYSTEM.value, body=body[:4000])
    session.add(message)
    await session.flush()
    await session.refresh(message)
    group.last_message_at = message.created_at
    if actor_id is not None:
        await session.execute(
            update(ChatGroupMember)
            .where(ChatGroupMember.group_id == group.id, ChatGroupMember.user_id == actor_id)
            .values(last_read_at=message.created_at)
        )


def _msg_out(m: GroupMessage, names: dict[uuid.UUID, str]) -> GroupMessageOut:
    return GroupMessageOut(
        id=m.id,
        group_id=m.group_id,
        sender_id=m.sender_id,
        sender_name=names.get(m.sender_id) if m.sender_id else None,
        kind=m.kind,
        body=m.body,
        created_at=m.created_at,
        edited_at=m.edited_at,
    )


async def _names(session: AsyncSession, ids: Iterable[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    wanted = {i for i in ids if i}
    if not wanted:
        return {}
    return dict(
        (await session.execute(select(User.id, User.display_name).where(User.id.in_(wanted)))).all()
    )


def _unread_condition(user_id: uuid.UUID) -> object:
    return and_(
        or_(GroupMessage.sender_id.is_(None), GroupMessage.sender_id != user_id),
        or_(
            ChatGroupMember.last_read_at.is_(None),
            GroupMessage.created_at > ChatGroupMember.last_read_at,
        ),
        GroupMessage.created_at >= ChatGroupMember.joined_at,
    )


async def unread_total(session: AsyncSession, user: CurrentUser) -> int:
    count = await session.scalar(
        select(func.count())
        .select_from(GroupMessage)
        .join(
            ChatGroupMember,
            and_(
                ChatGroupMember.group_id == GroupMessage.group_id,
                ChatGroupMember.user_id == user.id,
            ),
        )
        .where(_unread_condition(user.id))  # type: ignore[arg-type]
    )
    return int(count or 0)


async def _summaries(
    session: AsyncSession, user: CurrentUser, groups: Sequence[ChatGroup]
) -> list[GroupSummary]:
    if not groups:
        return []
    ids = [g.id for g in groups]
    members = (
        await session.scalars(select(ChatGroupMember).where(ChatGroupMember.group_id.in_(ids)))
    ).all()
    by_group: dict[uuid.UUID, list[ChatGroupMember]] = {}
    for m in members:
        by_group.setdefault(m.group_id, []).append(m)
    unread = dict(
        (
            await session.execute(
                select(GroupMessage.group_id, func.count())
                .join(
                    ChatGroupMember,
                    and_(
                        ChatGroupMember.group_id == GroupMessage.group_id,
                        ChatGroupMember.user_id == user.id,
                    ),
                )
                .where(GroupMessage.group_id.in_(ids), _unread_condition(user.id))  # type: ignore[arg-type]
                .group_by(GroupMessage.group_id)
            )
        ).all()
    )
    last_rows = (
        await session.scalars(
            select(GroupMessage)
            .where(GroupMessage.group_id.in_(ids))
            .order_by(GroupMessage.group_id, GroupMessage.created_at.desc(), GroupMessage.id.desc())
            .ext(distinct_on(GroupMessage.group_id))
        )
    ).all()
    last = {m.group_id: m for m in last_rows}
    cutoff = await _cutoff(session)
    typers = {
        m.user_id
        for m in members
        if m.user_id != user.id and m.typing_at is not None and m.typing_at > cutoff
    }
    names = await _names(session, [m.sender_id for m in last_rows] + list(typers))
    out = []
    for g in groups:
        group_members = by_group.get(g.id, [])
        me = next((m for m in group_members if m.user_id == user.id), None)
        message = last.get(g.id)
        out.append(
            GroupSummary(
                id=g.id,
                name=g.name,
                member_count=len(group_members),
                my_role=me.role if me else "MEMBER",
                last_message=_msg_out(message, names) if message else None,
                last_message_at=g.last_message_at,
                unread_count=int(unread.get(g.id, 0)),
                typing_names=sorted(
                    names.get(m.user_id, "") for m in group_members if m.user_id in typers
                ),
            )
        )
    return out


async def list_groups(session: AsyncSession, user: CurrentUser) -> list[GroupSummary]:
    mine = select(ChatGroupMember.group_id).where(ChatGroupMember.user_id == user.id)
    groups = (
        await session.scalars(
            select(ChatGroup)
            .where(ChatGroup.id.in_(mine))
            .order_by(ChatGroup.last_message_at.desc().nulls_last(), ChatGroup.created_at.desc())
            .limit(200)
        )
    ).all()
    return await _summaries(session, user, groups)


async def _members_out(session: AsyncSession, group_id: uuid.UUID) -> list[GroupMember]:
    rows = (
        (
            await session.execute(
                select(ChatGroupMember, User)
                .join(User, User.id == ChatGroupMember.user_id)
                .where(ChatGroupMember.group_id == group_id)
                .order_by(ChatGroupMember.role, User.display_name)
            )
        )
        .unique()
        .all()
    )
    return [
        GroupMember(
            id=u.id,
            display_name=u.display_name,
            department_name=u.department.name if u.department else None,
            role=m.role,
            last_read_at=m.last_read_at,
        )
        for m, u in rows
    ]


async def get_group(session: AsyncSession, user: CurrentUser, group_id: uuid.UUID) -> GroupDetail:
    group, _ = await _membership(session, user, group_id)
    summary = (await _summaries(session, user, [group]))[0]
    return GroupDetail(**summary.model_dump(), members=await _members_out(session, group.id))


async def create_group(
    session: AsyncSession, user: CurrentUser, data: GroupCreate, hub: ChatHub
) -> GroupDetail:
    ids = {i for i in data.member_ids if i != user.id}
    if data.include_department_id is not None:
        if data.include_department_id != user.department_id and not user.has(P.USERS_READ):
            raise PermissionDeniedError("เพิ่มทั้งแผนกได้เฉพาะแผนกของคุณ")
        ids |= set(
            (
                await session.scalars(
                    select(User.id).where(
                        User.department_id == data.include_department_id,
                        User.is_active.is_(True),
                        User.deleted_at.is_(None),
                        User.id != user.id,
                    )
                )
            ).all()
        )
    if not ids:
        raise _fail("member_ids", "เลือกสมาชิกอย่างน้อย 1 คน")
    if len(ids) + 1 > GROUP_MAX_MEMBERS:
        raise _fail("member_ids", f"กลุ่มมีสมาชิกได้ไม่เกิน {GROUP_MAX_MEMBERS} คน")
    members = await _eligible(session, ids)
    group = ChatGroup(name=data.name, created_by=user.id)
    session.add(group)
    await session.flush()
    session.add(ChatGroupMember(group_id=group.id, user_id=user.id, role=GroupRole.ADMIN.value))
    for m in members:
        session.add(ChatGroupMember(group_id=group.id, user_id=m.id))
    await session.flush()
    await _system(session, group, f"{user.display_name} สร้างกลุ่ม “{data.name}”", user.id)
    await session.commit()
    await hub.notify([user.id, *ids])
    return await get_group(session, user, group.id)


async def rename_group(
    session: AsyncSession, user: CurrentUser, group_id: uuid.UUID, name: str, hub: ChatHub
) -> GroupDetail:
    group, member = await _membership(session, user, group_id)
    _admin(member)
    if name != group.name:
        group.name = name
        await _system(session, group, f"{user.display_name} เปลี่ยนชื่อกลุ่มเป็น “{name}”", user.id)
        ids = await _member_ids(session, group.id)
        await session.commit()
        await hub.notify(ids)
    return await get_group(session, user, group.id)


async def add_members(
    session: AsyncSession,
    user: CurrentUser,
    group_id: uuid.UUID,
    user_ids: Sequence[uuid.UUID],
    hub: ChatHub,
) -> GroupDetail:
    group, member = await _membership(session, user, group_id)
    _admin(member)
    current = set(await _member_ids(session, group.id))
    new = set(user_ids) - current
    if not new:
        return await get_group(session, user, group.id)
    if len(current) + len(new) > GROUP_MAX_MEMBERS:
        raise _fail("user_ids", f"กลุ่มมีสมาชิกได้ไม่เกิน {GROUP_MAX_MEMBERS} คน")
    people = await _eligible(session, new)
    for p in people:
        session.add(ChatGroupMember(group_id=group.id, user_id=p.id))
    await session.flush()
    await _system(
        session,
        group,
        f"{user.display_name} เพิ่ม {', '.join(p.display_name for p in people)} เข้ากลุ่ม",
        user.id,
    )
    await session.commit()
    await hub.notify(current | new)
    return await get_group(session, user, group.id)


async def _ensure_admin_left(session: AsyncSession, group: ChatGroup) -> None:
    has_admin = await session.scalar(
        select(func.count())
        .select_from(ChatGroupMember)
        .where(ChatGroupMember.group_id == group.id, ChatGroupMember.role == GroupRole.ADMIN.value)
    )
    if not has_admin:
        oldest = await session.scalar(
            select(ChatGroupMember)
            .where(ChatGroupMember.group_id == group.id)
            .order_by(ChatGroupMember.joined_at)
            .limit(1)
        )
        if oldest is not None:
            oldest.role = GroupRole.ADMIN.value


async def remove_member(
    session: AsyncSession,
    user: CurrentUser,
    group_id: uuid.UUID,
    target_id: uuid.UUID,
    hub: ChatHub,
) -> GroupDetail | None:
    """An admin removes someone, or anyone removes themselves (= leave). ``None`` when the
    caller is no longer a member."""
    group, member = await _membership(session, user, group_id)
    leaving = target_id == user.id
    if not leaving:
        _admin(member)
    target = await session.get(ChatGroupMember, (group.id, target_id))
    if target is None:
        raise NotFoundError("บุคคลนี้ไม่ได้อยู่ในกลุ่ม")
    before = set(await _member_ids(session, group.id))
    names = await _names(session, [target_id])
    await session.execute(
        delete(ChatGroupMember).where(
            ChatGroupMember.group_id == group.id, ChatGroupMember.user_id == target_id
        )
    )
    await session.flush()
    remaining = before - {target_id}
    if not remaining:
        await session.delete(group)
        await session.commit()
        await hub.notify(before)
        return None
    await _ensure_admin_left(session, group)
    await _system(
        session,
        group,
        f"{names.get(target_id, '')} ออกจากกลุ่ม"
        if leaving
        else f"{user.display_name} นำ {names.get(target_id, '')} ออกจากกลุ่ม",
        None if leaving else user.id,
    )
    await session.commit()
    await hub.notify(before)
    return None if leaving else await get_group(session, user, group.id)


async def list_messages(
    session: AsyncSession,
    user: CurrentUser,
    group_id: uuid.UUID,
    *,
    before: uuid.UUID | None,
    limit: int,
) -> GroupMessagePage:
    group, _me = await _membership(session, user, group_id)
    stmt = select(GroupMessage).where(GroupMessage.group_id == group.id)
    if before is not None:
        anchor = await session.scalar(
            select(GroupMessage).where(GroupMessage.id == before, GroupMessage.group_id == group.id)
        )
        if anchor is None:
            raise NotFoundError("ไม่พบข้อความอ้างอิง")
        stmt = stmt.where(
            tuple_(GroupMessage.created_at, GroupMessage.id) < tuple_(anchor.created_at, anchor.id)
        )
    rows = (
        await session.scalars(
            stmt.order_by(GroupMessage.created_at.desc(), GroupMessage.id.desc()).limit(limit + 1)
        )
    ).all()
    page = list(reversed(rows[:limit]))
    members = await _members_out(session, group.id)
    cutoff = await _cutoff(session)
    typing_ids = set(
        (
            await session.scalars(
                select(ChatGroupMember.user_id).where(
                    ChatGroupMember.group_id == group.id,
                    ChatGroupMember.user_id != user.id,
                    ChatGroupMember.typing_at > cutoff,
                )
            )
        ).all()
    )
    names = {m.id: m.display_name for m in members}
    names |= await _names(session, {m.sender_id for m in page if m.sender_id not in names})
    return GroupMessagePage(
        items=[_msg_out(m, names) for m in page],
        has_more=len(rows) > limit,
        reads=[m for m in members if m.id != user.id],
        typing_names=sorted(names[i] for i in typing_ids if i in names),
    )


async def send_message(
    session: AsyncSession, user: CurrentUser, group_id: uuid.UUID, body: str, hub: ChatHub
) -> GroupMessageOut:
    group, me = await _membership(session, user, group_id, lock=True)
    message = GroupMessage(group_id=group.id, sender_id=user.id, body=body)
    session.add(message)
    await session.flush()
    await session.refresh(message)
    group.last_message_at = message.created_at
    me.last_read_at = message.created_at
    me.typing_at = None
    ids = await _member_ids(session, group.id)
    await session.commit()
    await hub.notify(ids)
    return _msg_out(message, {user.id: user.display_name})


async def edit_message(
    session: AsyncSession,
    user: CurrentUser,
    group_id: uuid.UUID,
    message_id: uuid.UUID,
    body: str,
    hub: ChatHub,
) -> GroupMessageOut:
    group, _ = await _membership(session, user, group_id)
    message = await session.scalar(
        select(GroupMessage)
        .where(GroupMessage.id == message_id, GroupMessage.group_id == group.id)
        .with_for_update()
    )
    if message is None:
        raise NotFoundError("ไม่พบข้อความนี้")
    if message.sender_id != user.id or message.kind != GroupMessageKind.TEXT.value:
        raise PermissionDeniedError("แก้ไขได้เฉพาะข้อความของคุณเอง")
    if body != message.body:
        message.body = body
        message.edited_at = func.now()
        ids = await _member_ids(session, group.id)
        await session.commit()
        await session.refresh(message)
        await hub.notify(ids)
    return _msg_out(message, {user.id: user.display_name})


async def mark_read(
    session: AsyncSession, user: CurrentUser, group_id: uuid.UUID, hub: ChatHub
) -> None:
    group, me = await _membership(session, user, group_id, lock=True)
    newest = await session.scalar(
        select(func.max(GroupMessage.created_at)).where(GroupMessage.group_id == group.id)
    )
    if newest is not None and (me.last_read_at is None or newest > me.last_read_at):
        me.last_read_at = newest
        ids = await _member_ids(session, group.id)
        await session.commit()
        await hub.notify(ids)  # read counts and my badge on other devices


async def set_typing(
    session: AsyncSession, user: CurrentUser, group_id: uuid.UUID, hub: ChatHub
) -> None:
    group, me = await _membership(session, user, group_id)
    me.typing_at = func.now()
    others = [i for i in await _member_ids(session, group.id) if i != user.id]
    await session.commit()
    await hub.notify(others)
