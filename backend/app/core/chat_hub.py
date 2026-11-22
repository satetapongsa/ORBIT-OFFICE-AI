"""Real-time wake-ups for chat (ADR-062).

Every user has a version number that grows whenever something in one of their conversations
changes (a new message, a read receipt, the other person typing). Browsers hold one
``GET /chat/events?since=<version>`` request open; it answers as soon as the version differs,
so a message reaches the other person in a fraction of a second, through any HTTP proxy and
without WebSockets.

* :class:`RedisChatHub` (normal operation): the version lives in Redis (``INCR``), and one
  pub/sub subscription per API process wakes the waiting requests of that process, so it
  works with several API processes. Waiters also re-check the version every few seconds,
  so a wake-up lost during a Redis reconnect only delays delivery slightly.
* :class:`LocalChatHub` (tests): the same contract in memory for a single process.

Signals carry no message content; clients refetch what they are allowed to see.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
import uuid
from collections import defaultdict
from collections.abc import Iterable
from typing import Protocol

from redis.asyncio import Redis

from app.core.logging import get_logger

logger = get_logger(__name__)

CHANNEL = "orbit:chat:wake"
VERSION_KEY = "orbit:chat:ver:{}"
VERSION_TTL_SECONDS = 7 * 86_400
RECHECK_SECONDS = 5.0  # bound on the delay if a pub/sub wake-up is ever missed


class ChatHub(Protocol):
    async def notify(self, user_ids: Iterable[uuid.UUID]) -> None:
        """Something changed for these users (call after the database commit)."""
        ...

    async def wait(self, user_id: uuid.UUID, since: int, wait_seconds: float) -> int:
        """Returns the user's current version as soon as it differs from ``since``
        (immediately if it already does), or after ``wait_seconds``."""
        ...

    async def aclose(self) -> None: ...


class LocalChatHub:
    """In-process hub (tests, single process). Loop-agnostic: waiters poll every 50 ms."""

    def __init__(self) -> None:
        self._versions: dict[str, int] = defaultdict(int)

    async def notify(self, user_ids: Iterable[uuid.UUID]) -> None:
        for user_id in set(user_ids):
            self._versions[str(user_id)] += 1

    async def wait(self, user_id: uuid.UUID, since: int, wait_seconds: float) -> int:
        deadline = time.monotonic() + wait_seconds
        while True:
            current = self._versions[str(user_id)]
            if current != since or time.monotonic() >= deadline:
                return current
            await asyncio.sleep(0.05)

    async def aclose(self) -> None:
        return None


class RedisChatHub:
    def __init__(self, redis: Redis, subscriber: Redis) -> None:
        self._redis = redis
        self._subscriber = subscriber  # separate connection: pub/sub blocks it
        self._waiters: dict[str, set[asyncio.Event]] = defaultdict(set)
        self._listener: asyncio.Task[None] | None = None

    async def notify(self, user_ids: Iterable[uuid.UUID]) -> None:
        ids = sorted({str(u) for u in user_ids})
        if not ids:
            return
        try:
            async with self._redis.pipeline(transaction=False) as pipe:
                for user_id in ids:
                    key = VERSION_KEY.format(user_id)
                    pipe.incr(key)
                    pipe.expire(key, VERSION_TTL_SECONDS)
                pipe.publish(CHANNEL, ",".join(ids))
                await pipe.execute()
        except Exception as exc:
            # The message is already stored; clients still see it on their next check.
            logger.warning("chat_notify_failed", error_type=type(exc).__name__)

    async def _version(self, user_id: str) -> int:
        value = await self._redis.get(VERSION_KEY.format(user_id))
        return int(value or 0)

    def _ensure_listener(self) -> None:
        if self._listener is None or self._listener.done():
            self._listener = asyncio.get_running_loop().create_task(self._listen())

    async def _listen(self) -> None:
        while True:
            try:
                async with self._subscriber.pubsub() as pubsub:
                    await pubsub.subscribe(CHANNEL)
                    while True:
                        message = await pubsub.get_message(
                            ignore_subscribe_messages=True, timeout=RECHECK_SECONDS
                        )
                        if message and isinstance(message.get("data"), str):
                            for user_id in message["data"].split(","):
                                for event in self._waiters.get(user_id, ()):
                                    event.set()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("chat_listener_error", error_type=type(exc).__name__)
                await asyncio.sleep(2)

    async def wait(self, user_id: uuid.UUID, since: int, wait_seconds: float) -> int:
        key = str(user_id)
        event = asyncio.Event()
        self._waiters[key].add(event)
        deadline = time.monotonic() + wait_seconds
        try:
            self._ensure_listener()
            while True:
                # Clear before reading, so a wake-up that lands after the read is not lost.
                event.clear()
                try:
                    current = await self._version(key)
                except Exception as exc:
                    # Redis is down: behave like slow polling so clients still refresh.
                    logger.warning("chat_version_unavailable", error_type=type(exc).__name__)
                    await asyncio.sleep(min(RECHECK_SECONDS, max(wait_seconds, 0.0)))
                    return since + 1
                remaining = deadline - time.monotonic()
                if current != since or remaining <= 0:
                    return current
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(event.wait(), min(remaining, RECHECK_SECONDS))
        finally:
            self._waiters[key].discard(event)
            if not self._waiters[key]:
                self._waiters.pop(key, None)

    async def aclose(self) -> None:
        if self._listener is not None:
            self._listener.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._listener
        await self._subscriber.aclose()


def build_chat_hub(redis_url: str, *, in_memory: bool) -> ChatHub:
    if in_memory:
        return LocalChatHub()
    return RedisChatHub(
        Redis.from_url(redis_url, decode_responses=True, socket_connect_timeout=3),
        Redis.from_url(
            redis_url, decode_responses=True, socket_connect_timeout=3, health_check_interval=30
        ),
    )
