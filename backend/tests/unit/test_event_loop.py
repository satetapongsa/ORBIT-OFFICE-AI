from __future__ import annotations

import asyncio
import sys

import pytest

from app.core.event_loop import is_unsupported_windows_loop, selector_event_loop


def test_selector_event_loop_factory_returns_selector_loop() -> None:
    loop = selector_event_loop()
    try:
        assert isinstance(loop, asyncio.SelectorEventLoop)
    finally:
        loop.close()


def test_selector_loop_is_supported() -> None:
    async def check() -> bool:
        return is_unsupported_windows_loop()

    with asyncio.Runner(loop_factory=selector_event_loop) as runner:
        assert runner.run(check()) is False


@pytest.mark.skipif(sys.platform != "win32", reason="Proactor loop exists only on Windows")
def test_proactor_loop_is_detected_on_windows() -> None:
    async def check() -> bool:
        return is_unsupported_windows_loop()

    proactor = asyncio.ProactorEventLoop  # type: ignore[attr-defined,unused-ignore]
    with asyncio.Runner(loop_factory=proactor) as runner:
        assert runner.run(check()) is True
