"""Operational commands.

python -m app.cli sync-rbac      # permissions + system roles (safe in every environment)
python -m app.cli seed-dev       # development departments and accounts (development only)
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    parser.add_argument("command", choices=["sync-rbac", "seed-dev", "reindex-documents"])
    parser.add_argument(
        "--all", action="store_true", help="reindex-documents: also rebuild READY indexes"
    )
    args = parser.parse_args(argv)
    if args.command == "reindex-documents":
        return _reindex(include_ready=args.all)
    return _sync_rbac() if args.command == "sync-rbac" else _seed_dev()


if __name__ == "__main__":
    raise SystemExit(main())
