"""Single-container mode for small hosts such as Render's free plan (ADR-056).

    python -m app.serve_all

Applies migrations, synchronises permissions and checks the storage bucket, then runs the API
and the Celery worker with the daily schedule (``-B``) side by side. As soon as either process
stops, the other is stopped too and the command exits non-zero, so the platform restarts the
container instead of leaving it half alive.

Only the standard library is imported here: this supervisor stays resident next to the API and
the worker, and the free plan has 512 MB for all of them.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from types import FrameType

PYTHON = sys.executable  # same interpreter and packages; every argument below is fixed

SETUP_STEPS = (
    ("alembic", "upgrade", "head"),
    ("app.cli", "sync-rbac"),
    ("app.cli", "ensure-bucket"),
)


def api_command(port: str) -> list[str]:
    return [
        PYTHON, "-m", "uvicorn", "app.main:app",
        "--host", "0.0.0.0", "--port", port,  # noqa: S104 - the container's published port
        "--proxy-headers", "--forwarded-allow-ips", "*",
    ]  # fmt: skip


def worker_command() -> list[str]:
    return [
        PYTHON, "-m", "celery", "-A", "app.workers.celery_app", "worker",
        "-B", "--pool=solo", "--loglevel=INFO", "-Q", "default,documents",
    ]  # fmt: skip


def _stop(_signum: int, _frame: FrameType | None) -> None:
    raise SystemExit(0)


def main() -> int:
    for step in SETUP_STEPS:
        if subprocess.call([PYTHON, "-m", *step]) != 0:  # noqa: S603
            print(f"serve-all: '{' '.join(step)}' failed", file=sys.stderr)
            return 1

    signal.signal(signal.SIGTERM, _stop)
    port = str(int(os.environ.get("PORT", "8000")))
    processes = [
        subprocess.Popen(api_command(port)),  # noqa: S603
        subprocess.Popen(worker_command()),  # noqa: S603
    ]
    try:
        while all(p.poll() is None for p in processes):
            time.sleep(1)
        print("serve-all: a process stopped; shutting down", file=sys.stderr)
        return 1
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    raise SystemExit(main())
