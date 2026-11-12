"""Retention clean-up (`app.services.maintenance`) and backup export/import of stored files."""

from __future__ import annotations

import io
import tarfile
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, BinaryIO

import pytest
from botocore.exceptions import ClientError
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.storage import StoredObject
from app.services.backup import export_objects, import_objects
from app.services.maintenance import purge
from tests.conftest import Factory, make_settings

NOW = datetime(2026, 11, 12, 3, 0, tzinfo=UTC)


@dataclass
class FakeStorage:
    objects: dict[str, tuple[bytes, datetime]] = field(default_factory=dict)
    broken: set[str] = field(default_factory=set)
    bucket: str = "test"

    def add(self, key: str, *, age: timedelta, data: bytes = b"x") -> None:
        self.objects[key] = (data, NOW - age)

    def iter_objects(self, prefix: str = "") -> Any:
        for key, (data, modified) in list(self.objects.items()):
            yield StoredObject(key=key, size=len(data), last_modified=modified)

    def delete_object(self, key: str) -> None:
        if key in self.broken:
            raise ClientError({"Error": {"Code": "InternalError"}}, "DeleteObject")
        self.objects.pop(key, None)

    def download_to(self, key: str, fileobj: BinaryIO) -> None:
        fileobj.write(self.objects[key][0])
        fileobj.seek(0)

    def put_bytes(self, key: str, fileobj: BinaryIO, *, content_type: str) -> None:
        self.objects[key] = (fileobj.read(), NOW)


def _sql(db: Factory, sql: str, **params: Any) -> Any:
    with db.engine.begin() as conn:
        result = conn.execute(text(sql), params)
        return result.scalar() if result.returns_rows else None


def _document(db: Factory, owner: uuid.UUID, *, deleted_days: int | None, key: str) -> uuid.UUID:
    doc = _sql(
        db,
        "INSERT INTO documents (title, owner_id, visibility, status, deleted_at)"
        " VALUES ('d', :o, 'PRIVATE', 'ACTIVE',"
        " CASE WHEN CAST(:days AS int) IS NULL THEN NULL"
        "  ELSE CAST(:now AS timestamptz) - make_interval(days => CAST(:days AS int)) END)"
        " RETURNING id",
        o=owner,
        days=deleted_days,
        now=NOW,
    )
    _sql(
        db,
        "INSERT INTO document_versions (document_id, version_number, storage_key,"
        " original_filename, file_type, mime_type, size_bytes, sha256, uploaded_by,"
        " processing_status) VALUES (:d, 1, :k, 'a.txt', 'TXT', 'text/plain', 1, :h, :o, 'READY')",
        d=doc,
        k=key,
        h="0" * 64,
        o=owner,
    )
    return uuid.UUID(str(doc))


def _count(db: Factory, table: str) -> int:
    return int(db.scalar(f"SELECT count(*) FROM {table}"))


@pytest.fixture
def seeded(db: Factory) -> tuple[Factory, FakeStorage, dict[str, Any]]:
    owner = db.user("owner@example.com")
    storage = FakeStorage()
    ids = {
        "old": _document(db, owner, deleted_days=45, key="documents/old"),
        "recent": _document(db, owner, deleted_days=5, key="documents/recent"),
        "live": _document(db, owner, deleted_days=None, key="documents/live"),
    }
    for key in ("documents/old", "documents/recent", "documents/live"):
        storage.add(key, age=timedelta(days=60))
    storage.add("tasks/orphan-old", age=timedelta(hours=30))
    storage.add("tasks/orphan-new", age=timedelta(hours=2))  # an upload still in flight

    # Chats: deleted, idle for a year, active.
    for deleted, idle_days in ((True, 1), (False, 400), (False, 1)):
        _sql(
            db,
            "INSERT INTO chat_sessions (user_id, title, last_message_at, deleted_at)"
            " VALUES (:u, 'c', CAST(:now AS timestamptz) - make_interval(days => :idle),"
            " CASE WHEN :deleted THEN CAST(:now AS timestamptz) END)",
            u=owner,
            now=NOW,
            idle=idle_days,
            deleted=deleted,
        )
    # Sign-in data: one long expired session, one live; one used old reset token, one fresh.
    for days in (-60, 3):
        _sql(
            db,
            "INSERT INTO user_sessions (user_id, refresh_token_hash, family_id, expires_at,"
            " family_expires_at) VALUES (:u, :h, gen_random_uuid(),"
            " CAST(:now AS timestamptz) + make_interval(days => :d),"
            " CAST(:now AS timestamptz) + make_interval(days => :d))",
            u=owner,
            h=uuid.uuid4().hex,
            now=NOW,
            d=days,
        )
    for days in (-60, 1):
        _sql(
            db,
            "INSERT INTO password_reset_tokens (user_id, token_hash, expires_at)"
            " VALUES (:u, :h, CAST(:now AS timestamptz) + make_interval(days => :d))",
            u=owner,
            h=uuid.uuid4().hex,
            now=NOW,
            d=days,
        )
    # Notifications: old read (purged), old unread (kept), recent read (kept).
    for read, age in ((True, 400), (False, 400), (True, 10)):
        _sql(
            db,
            "INSERT INTO notifications (user_id, type, title, body, read_at, created_at)"
            " VALUES (:u, 'SYSTEM', 't', '', CASE WHEN :r THEN CAST(:now AS timestamptz) END,"
            " CAST(:now AS timestamptz) - make_interval(days => :a))",
            u=owner,
            r=read,
            now=NOW,
            a=age,
        )
    return db, storage, ids


def _run(db: Factory, storage: FakeStorage, **kwargs: Any) -> Any:
    with Session(db.engine) as session:
        return purge(session, storage, make_settings(), now=NOW, **kwargs)  # type: ignore[arg-type]


def test_dry_run_counts_without_removing(
    seeded: tuple[Factory, FakeStorage, dict[str, Any]],
) -> None:
    db, storage, _ = seeded
    report = _run(db, storage, dry_run=True)
    assert report.as_dict() == {
        "documents": 1,
        "document_objects": 1,
        "orphaned_objects": 1,
        "chat_sessions": 2,
        "auth_sessions": 1,
        "reset_tokens": 1,
        "notifications": 1,
        "errors": 0,
        "dry_run": True,
    }
    assert _count(db, "documents") == 3 and len(storage.objects) == 5
    assert _count(db, "chat_sessions") == 3


def test_purge_removes_only_expired_data(
    seeded: tuple[Factory, FakeStorage, dict[str, Any]],
) -> None:
    db, storage, ids = seeded
    report = _run(db, storage)
    assert (report.documents, report.document_objects, report.orphaned_objects) == (1, 1, 1)
    with db.engine.connect() as conn:
        remaining = {str(r) for r in conn.execute(text("SELECT id FROM documents")).scalars()}
    assert remaining == {str(ids["recent"]), str(ids["live"])}
    assert set(storage.objects) == {"documents/recent", "documents/live", "tasks/orphan-new"}
    assert _count(db, "document_versions") == 2
    assert _count(db, "chat_sessions") == 1
    assert _count(db, "user_sessions") == 1
    assert _count(db, "password_reset_tokens") == 1
    assert _count(db, "notifications") == 2
    assert _count(db, "users") == 1  # people and audit logs are never purged
    # Idempotent.
    again = _run(db, storage)
    assert (again.documents, again.orphaned_objects, again.chat_sessions) == (0, 0, 0)


def test_storage_failure_keeps_the_document_for_the_next_run(
    seeded: tuple[Factory, FakeStorage, dict[str, Any]],
) -> None:
    db, storage, ids = seeded
    storage.broken.add("documents/old")
    report = _run(db, storage)
    assert report.documents == 0 and report.errors == 1
    assert _sql(db, "SELECT count(*) FROM documents WHERE id = :i", i=ids["old"]) == 1
    storage.broken.clear()
    assert _run(db, storage).documents == 1


# --- Backups -------------------------------------------------------------------------------


def test_export_import_round_trip() -> None:
    source = FakeStorage()
    source.add("documents/a/v1.pdf", age=timedelta(days=1), data=b"%PDF-1.4 a")
    source.add("tasks/b/notes.txt", age=timedelta(days=2), data="บันทึก".encode())
    archive = io.BytesIO()
    assert export_objects(source, archive) == 2  # type: ignore[arg-type]

    archive.seek(0)
    target = FakeStorage()
    assert import_objects(target, archive) == (2, 0)  # type: ignore[arg-type]
    assert {k: v[0] for k, v in target.objects.items()} == {
        "documents/a/v1.pdf": b"%PDF-1.4 a",
        "tasks/b/notes.txt": "บันทึก".encode(),
    }


def test_import_skips_unsafe_entries() -> None:
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w") as tar:
        for name in (
            "../escape.txt",
            "documents/../../x",
            "/abs/path",
            "documents//double",
            "documents/ok.txt",
            "./documents/dot.txt",
        ):
            info = tarfile.TarInfo(name=name)
            info.size = 2
            tar.addfile(info, io.BytesIO(b"ok"))
        link = tarfile.TarInfo(name="documents/link")
        link.type = tarfile.SYMTYPE
        link.linkname = "/etc/passwd"
        tar.addfile(link)
    archive.seek(0)
    target = FakeStorage()
    restored, skipped = import_objects(target, archive)  # type: ignore[arg-type]
    assert set(target.objects) == {"documents/ok.txt", "documents/dot.txt"}
    assert (restored, skipped) == (2, 5)
