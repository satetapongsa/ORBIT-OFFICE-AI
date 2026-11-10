"""Event-loop selection for running the API natively on Windows.

psycopg 3 cannot run in async mode on Windows' default ``ProactorEventLoop``.
When running the backend directly on Windows (not in Docker), start uvicorn with::

    uvicorn app.main:app --reload --loop app.core.event_loop:selector_event_loop

Linux/macOS (including the Docker images) need nothing special.
"""

from __future__ import annotations

import asyncio
import sys


def selector_event_loop() -> asyncio.AbstractEventLoop:
    """Loop factory accepted by ``uvicorn --loop`` and anyio ``loop_factory``."""
    return asyncio.SelectorEventLoop()


def is_unsupported_windows_loop() -> bool:
    """True when running on Windows with a Proactor loop (async psycopg will fail)."""
    if sys.platform != "win32":
        return False
    proactor = getattr(asyncio, "ProactorEventLoop", None)
    return proactor is not None and isinstance(asyncio.get_running_loop(), proactor)
