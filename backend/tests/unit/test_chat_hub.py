"""Real-time chat wake-ups (ADR-062): local hub and the Redis hub across processes."""

from __future__ import annotations

import asyncio
import os
import time
import uuid

import pytest
from redis.asyncio import Redis

from app.core.chat_hub import LocalChatHub, RedisChatHub, build_chat_hub
from tests.conftest import run

REDIS_URL = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")


def test_local_hub_answers_on_change_or_timeout() -> None:
    async def scenario() -> None:
        hub = LocalChatHub()
        me, other = uuid.uuid4(), uuid.uuid4()
        assert await hub.wait(me, -1, 5) == 0  # first call: current version at once
        started = time.monotonic()
        assert await hub.wait(me, 0, 0.2) == 0  # nothing happened: waits, then answers
        assert time.monotonic() - started >= 0.2

        async def later() -> None:
            await asyncio.sleep(0.1)
            await hub.notify([me, me])

        task = asyncio.create_task(later())
        started = time.monotonic()
        assert await hub.wait(me, 0, 5) == 1  # duplicates count once
        assert time.monotonic() - started < 1
        await task
        assert await hub.wait(other, 0, 0) == 0  # others are not woken

    run(scenario())


def _redis_available() -> bool:
    async def ping() -> bool:
        client = Redis.from_url(REDIS_URL, socket_connect_timeout=1)
        try:
            return bool(await client.ping())
        except Exception:
            return False
        finally:
            await client.aclose()

    return bool(run(ping()))


@pytest.mark.skipif(not _redis_available(), reason="Redis is not running")
def test_redis_hub_wakes_a_waiter_in_another_process_within_a_fraction_of_a_second() -> None:
    async def scenario() -> None:
        # Two hubs on one Redis behave like two API processes.
        api_a = build_chat_hub(REDIS_URL, in_memory=False)
        api_b = build_chat_hub(REDIS_URL, in_memory=False)
        assert isinstance(api_a, RedisChatHub)
        alice = uuid.uuid4()
        try:
            version = await api_a.wait(alice, -1, 5)
            waiter = asyncio.create_task(api_a.wait(alice, version, 20))
            await asyncio.sleep(0.5)  # let the subscription settle
            sent = time.monotonic()
            await api_b.notify([alice])
            assert await waiter == version + 1
            delay = time.monotonic() - sent
            assert delay < 0.5, f"wake-up took {delay:.3f}s"
            # An unchanged version waits, then answers with the same value.
            assert await api_a.wait(alice, version + 1, 0.3) == version + 1
        finally:
            await api_a.aclose()
            await api_b.aclose()

    run(scenario())
