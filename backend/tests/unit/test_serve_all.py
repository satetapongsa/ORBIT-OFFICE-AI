"""`python -m app.serve_all`: API and worker in one container (ADR-056)."""

from __future__ import annotations

import subprocess
import sys
from typing import Any

import pytest

from app import serve_all


class FakeProcess:
    def __init__(self, args: list[str], *, stops_after: int | None) -> None:
        self.args = args
        self.polls = 0
        self.stops_after = stops_after
        self.terminated = False
        self.returncode: int | None = None

    def poll(self) -> int | None:
        self.polls += 1
        if self.stops_after is not None and self.polls > self.stops_after:
            self.returncode = 1
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = -15

    def wait(self, timeout: float | None = None) -> int:
        return self.returncode or 0

    def kill(self) -> None:  # pragma: no cover - only after a timeout
        self.returncode = -9


@pytest.fixture
def started(monkeypatch: pytest.MonkeyPatch) -> list[FakeProcess]:
    processes: list[FakeProcess] = []

    def popen(args: list[str], **_: Any) -> FakeProcess:
        # The worker stops on its own after a few checks; the API keeps running.
        process = FakeProcess(args, stops_after=2 if "celery" in args else None)
        processes.append(process)
        return process

    monkeypatch.setattr(subprocess, "Popen", popen)
    monkeypatch.setattr("time.sleep", lambda _s: None)
    monkeypatch.setattr("signal.signal", lambda *_a: None)
    monkeypatch.setenv("PORT", "10000")
    return processes


def test_sets_up_then_runs_api_and_worker_and_stops_both_when_one_ends(
    started: list[FakeProcess], monkeypatch: pytest.MonkeyPatch
) -> None:
    steps: list[list[str]] = []
    monkeypatch.setattr(subprocess, "call", lambda args: steps.append(args) or 0)
    assert serve_all.main() == 1
    assert [s[2:] for s in steps] == [
        ["alembic", "upgrade", "head"],
        ["app.cli", "sync-rbac"],
        ["app.cli", "ensure-bucket"],
    ]
    api, worker = started
    assert api.args[1:4] == ["-m", "uvicorn", "app.main:app"]
    assert api.args[api.args.index("--port") + 1] == "10000"
    assert worker.args[1:5] == ["-m", "celery", "-A", "app.workers.celery_app"]
    assert "-B" in worker.args and "--pool=solo" in worker.args
    assert api.terminated  # the API is not left running without its worker


def test_nothing_starts_when_a_setup_step_fails(
    started: list[FakeProcess], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(subprocess, "call", lambda args: 1 if "sync-rbac" in args else 0)
    assert serve_all.main() == 1
    assert started == []


def test_the_supervisor_imports_only_the_standard_library() -> None:
    heavy = "{'sqlalchemy', 'fastapi', 'pydantic', 'celery'}"
    code = (
        f"import sys, app.serve_all; print([m for m in sys.modules if m.split('.')[0] in {heavy}])"
    )
    out = subprocess.run(  # noqa: S603 - fixed test command
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert out.stdout.strip() == "[]"
