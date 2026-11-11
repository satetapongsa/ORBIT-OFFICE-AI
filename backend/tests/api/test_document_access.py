"""The single document-access predicate, evaluated by PostgreSQL.

These tests are the foundation for the Phase 4/7 guarantees (listing, download, search and
RAG retrieval all reuse ``accessible_documents_condition``).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.core.permissions import SYSTEM_ROLES, P, SystemRole
from app.core.principal import CurrentUser
from app.models.document import AccessLevel, Document
from app.repositories.document_access import accessible_documents_condition, can_access_document
from tests.conftest import TEST_DATABASE_URL, Factory, run

EMPLOYEE_PERMS = frozenset(p.value for p in SYSTEM_ROLES[SystemRole.EMPLOYEE][2])


@dataclass
class World:
    sales: uuid.UUID
    hr: uuid.UUID
    owner: CurrentUser
    colleague: CurrentUser  # same department as the owner (SALES)
    outsider: CurrentUser  # HR department
    docs: dict[str, uuid.UUID]


def _principal(
    db: Factory, email: str, dept: uuid.UUID, roles: list[str], perms: frozenset[str]
) -> CurrentUser:
    uid = db.user(email, roles, department_id=dept)
    return CurrentUser(
        id=uid,
        email=email,
        display_name=email,
        department_id=dept,
        role_ids=frozenset(db.role_id(r) for r in roles),
        role_codes=frozenset(roles),
        permissions=perms,
    )


def _doc(
    db: Factory,
    title: str,
    owner: uuid.UUID,
    dept: uuid.UUID | None,
    visibility: str,
    deleted: bool = False,
) -> uuid.UUID:
    with db.engine.begin() as conn:
        return uuid.UUID(
            str(
                conn.scalar(
                    text(
                        "INSERT INTO documents (title, owner_id, department_id, visibility, status, deleted_at)"
                        " VALUES (:t, :o, :d, :v, 'ACTIVE', CASE WHEN :del THEN now() END) RETURNING id"
                    ),
                    {"t": title, "o": owner, "d": dept, "v": visibility, "del": deleted},
                )
            )
        )


def _grant(db: Factory, doc: uuid.UUID, ptype: str, pid: uuid.UUID, level: str) -> None:
    with db.engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO document_acl (document_id, principal_type, principal_id, access_level)"
                " VALUES (:d, :t, :p, :l)"
            ),
            {"d": doc, "t": ptype, "p": pid, "l": level},
        )


@pytest.fixture
def world(db: Factory) -> World:
    sales, hr = db.department("SALES"), db.department("HR")
    owner = _principal(db, "owner@example.com", sales, ["EMPLOYEE"], EMPLOYEE_PERMS)
    colleague = _principal(db, "colleague@example.com", sales, ["EMPLOYEE"], EMPLOYEE_PERMS)
    outsider = _principal(db, "outsider@example.com", hr, ["EMPLOYEE", "HR"], EMPLOYEE_PERMS)
    docs = {
        "private": _doc(db, "private", owner.id, sales, "PRIVATE"),
        "department": _doc(db, "department", owner.id, sales, "DEPARTMENT"),
        "company": _doc(db, "company", owner.id, sales, "COMPANY"),
        "restricted": _doc(db, "restricted", owner.id, sales, "RESTRICTED"),
        "deleted_company": _doc(db, "deleted", owner.id, sales, "COMPANY", deleted=True),
        "acl_user": _doc(db, "acl user", owner.id, sales, "RESTRICTED"),
        "acl_dept": _doc(db, "acl dept", owner.id, sales, "RESTRICTED"),
        "acl_role": _doc(db, "acl role", owner.id, sales, "RESTRICTED"),
        "acl_edit": _doc(db, "acl edit", owner.id, sales, "RESTRICTED"),
    }
    _grant(db, docs["acl_user"], "USER", outsider.id, "VIEW")
    _grant(db, docs["acl_dept"], "DEPARTMENT", hr, "VIEW")
    _grant(db, docs["acl_role"], "ROLE", db.role_id("HR"), "VIEW")
    _grant(db, docs["acl_edit"], "USER", outsider.id, "EDIT")
    return World(sales, hr, owner, colleague, outsider, docs)


def _visible(user: CurrentUser, level: AccessLevel = AccessLevel.VIEW) -> set[uuid.UUID]:
    async def query() -> set[uuid.UUID]:
        engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
        async with engine.connect() as conn:
            rows = await conn.execute(
                select(Document.id).where(accessible_documents_condition(user, level))
            )
            result = {r[0] for r in rows}
        await engine.dispose()
        return result

    return run(query())


def _names(world: World, ids: set[uuid.UUID]) -> set[str]:
    return {name for name, doc_id in world.docs.items() if doc_id in ids}


def test_owner_sees_all_own_live_documents(world: World) -> None:
    assert _names(world, _visible(world.owner)) == set(world.docs) - {"deleted_company"}


def test_department_member_sees_department_and_company_documents_only(world: World) -> None:
    assert _names(world, _visible(world.colleague)) == {"department", "company"}


def test_outsider_sees_company_documents_and_explicit_grants(world: World) -> None:
    assert _names(world, _visible(world.outsider)) == {
        "company",
        "acl_user",
        "acl_dept",
        "acl_role",
        "acl_edit",
    }


def test_edit_level_requires_an_edit_or_manage_grant(world: World) -> None:
    assert _names(world, _visible(world.outsider, AccessLevel.EDIT)) == {"acl_edit"}
    # COMPANY/DEPARTMENT visibility never implies edit rights.
    assert _names(world, _visible(world.colleague, AccessLevel.EDIT)) == set()


def test_documents_manage_is_an_override_but_still_excludes_deleted(world: World) -> None:
    admin = CurrentUser(
        id=uuid.uuid4(),
        email="a@example.com",
        display_name="a",
        department_id=None,
        role_ids=frozenset(),
        role_codes=frozenset({"ADMIN"}),
        permissions=frozenset({P.DOCUMENTS_MANAGE.value}),
    )
    assert _names(world, _visible(admin)) == set(world.docs) - {"deleted_company"}


def test_without_documents_read_nothing_is_visible(world: World) -> None:
    no_read = CurrentUser(
        id=world.colleague.id,
        email="c@example.com",
        display_name="c",
        department_id=world.sales,
        role_ids=world.colleague.role_ids,
        role_codes=world.colleague.role_codes,
        permissions=frozenset(),
    )
    assert _visible(no_read) == set()


def test_can_access_document_matches_the_listing_predicate(world: World) -> None:
    async def check() -> tuple[bool, bool]:
        from sqlalchemy.ext.asyncio import AsyncSession

        engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
        async with AsyncSession(engine) as session:
            allowed = await can_access_document(session, world.outsider, world.docs["acl_user"])
            denied = await can_access_document(session, world.colleague, world.docs["private"])
        await engine.dispose()
        return allowed, denied

    allowed, denied = run(check())
    assert allowed is True
    assert denied is False
