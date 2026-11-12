"""Operational commands.

python -m app.cli sync-rbac                 # permissions + system roles (safe everywhere)
python -m app.cli seed-dev                  # development departments and accounts (dev only)
python -m app.cli reindex-documents [--all] # queue search indexing
python -m app.cli ensure-bucket             # create the storage bucket (deploy step)
python -m app.cli create-admin EMAIL FIRST LAST  # first administrator; password from stdin
python -m app.cli purge [--dry-run]         # retention clean-up (also run daily by beat)
python -m app.cli storage-export > files.tar  # all stored files as a tar stream (backups)
python -m app.cli storage-import < files.tar  # restore stored files (backups)
"""

from __future__ import annotations

import argparse
import sys

from app.core.config import Environment, get_settings
from app.core.db import sync_session_scope


def _sync_rbac() -> int:
    from app.services.rbac_sync import sync_rbac

    with sync_session_scope() as session:
        report = sync_rbac(session)
    print(
        f"sync-rbac: permissions created={len(report.permissions_created)} "
        f"roles created={report.roles_created or '-'} updated={report.roles_updated or '-'}"
    )
    return 0


def _seed_dev() -> int:
    from app.services.rbac_sync import DEV_USERS, seed_dev

    settings = get_settings()
    if settings.environment is not Environment.DEVELOPMENT:
        print("seed-dev refused: ENVIRONMENT must be 'development'", file=sys.stderr)
        return 2
    if settings.seed_dev_password is None:
        print("seed-dev refused: set SEED_DEV_PASSWORD in .env (see .env.example)", file=sys.stderr)
        return 2
    with sync_session_scope() as session:
        created = seed_dev(session, settings.seed_dev_password.get_secret_value())
    print(
        f"seed-dev: created {len(created)} account(s); dev accounts: "
        + ", ".join(u[1] for u in DEV_USERS)
    )
    print("seed-dev: password = SEED_DEV_PASSWORD from your .env")
    return 0


def _reindex(include_ready: bool) -> int:
    """Queue search indexing for current document versions (after enabling or changing the
    embedding provider, or to backfill documents uploaded before Phase 7)."""
    from app.core.db import sync_session_scope
    from app.services.documents.indexing import versions_to_index
    from app.workers.celery_app import celery_app

    with sync_session_scope() as session:
        ids = versions_to_index(session, include_ready=include_ready)
    for version_id in ids:
        celery_app.send_task(
            "documents.index_version",
            args=[str(version_id)],
            kwargs={"force": True},
            queue="documents",
        )
    print(f"reindex-documents: queued {len(ids)} version(s)")
    return 0


def _purge(dry_run: bool) -> int:
    from app.core.storage import get_storage
    from app.services.maintenance import purge

    with sync_session_scope() as session:
        report = purge(session, get_storage(), get_settings(), dry_run=dry_run)
    label = "would remove" if dry_run else "removed"
    print(f"purge: {label} " + ", ".join(f"{k}={v}" for k, v in report.as_dict().items()))
    return 1 if report.errors else 0


def _storage_export() -> int:
    from app.core.storage import get_storage
    from app.services.backup import export_objects

    count = export_objects(get_storage(), sys.stdout.buffer)
    sys.stdout.buffer.flush()
    print(f"storage-export: {count} object(s)", file=sys.stderr)
    return 0


def _storage_import() -> int:
    from app.core.storage import get_storage
    from app.services.backup import import_objects

    storage = get_storage()
    storage.ensure_bucket(create=True)
    restored, skipped = import_objects(storage, sys.stdin.buffer)
    print(f"storage-import: restored {restored}, skipped {skipped}", file=sys.stderr)
    return 0


def _ensure_bucket() -> int:
    from app.core.storage import get_storage

    storage = get_storage()
    storage.ensure_bucket(create=True)
    print(f"ensure-bucket: '{storage.bucket}' is ready")
    return 0


def _read_password() -> str:
    """Hidden prompt on a terminal, otherwise the first line of stdin (scripts)."""
    import getpass

    if sys.stdin.isatty():
        first = getpass.getpass("Password: ")
        if first != getpass.getpass("Repeat password: "):
            raise SystemExit("create-admin: passwords do not match")
        return first
    return sys.stdin.readline().rstrip("\r\n")


def _create_admin(values: list[str], employee_code: str) -> int:
    from app.core.errors import ValidationFailedError
    from app.services.bootstrap import BootstrapError, create_admin

    if len(values) != 3:
        print("usage: python -m app.cli create-admin EMAIL FIRST_NAME LAST_NAME", file=sys.stderr)
        return 2
    email, first, last = values
    password = _read_password()
    try:
        with sync_session_scope() as session:
            user = create_admin(
                session,
                get_settings(),
                email=email,
                first_name=first,
                last_name=last,
                employee_code=employee_code,
                password=password,
            )
            created = user.email
    except BootstrapError as exc:
        print(f"create-admin refused: {exc}", file=sys.stderr)
        return 2
    except ValidationFailedError as exc:
        reasons = "; ".join(d.message for d in exc.details)
        print(f"create-admin refused: {reasons}", file=sys.stderr)
        return 2
    print(f"create-admin: {created} created with roles ADMIN and EMPLOYEE")
    return 0


COMMANDS = [
    "create-admin",
    "ensure-bucket",
    "sync-rbac",
    "seed-dev",
    "reindex-documents",
    "purge",
    "storage-export",
    "storage-import",
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    parser.add_argument("command", choices=COMMANDS)
    parser.add_argument(
        "--all", action="store_true", help="reindex-documents: also rebuild READY indexes"
    )
    parser.add_argument("--dry-run", action="store_true", help="purge: only count")
    parser.add_argument("values", nargs="*", help="create-admin: EMAIL FIRST_NAME LAST_NAME")
    parser.add_argument("--employee-code", default="ADM-0001", help="create-admin: employee code")
    args = parser.parse_args(argv)
    match args.command:
        case "reindex-documents":
            return _reindex(include_ready=args.all)
        case "purge":
            return _purge(dry_run=args.dry_run)
        case "storage-export":
            return _storage_export()
        case "storage-import":
            return _storage_import()
        case "sync-rbac":
            return _sync_rbac()
        case "ensure-bucket":
            return _ensure_bucket()
        case "create-admin":
            return _create_admin(args.values, args.employee_code)
        case _:
            return _seed_dev()


if __name__ == "__main__":
    raise SystemExit(main())
