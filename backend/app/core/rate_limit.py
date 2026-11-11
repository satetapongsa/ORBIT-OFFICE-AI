"""Fixed-window rate limiting backed by Redis.

If Redis is unavailable the limiter fails open (logs a warning) so an outage of the cache
does not lock every user out; readiness reports Redis as down in that case. Reviewed in
Phase 9 (see docs/SECURITY.md).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class RateLimitResult:
    allowed: bool
    retry_after_seconds: int = 0


class RateLimiter(Protocol):
    async def hit(self, key: str, *, limit: int, window_seconds: int) -> RateLimitResult: ...

    async def reset(self, key: str) -> None: ...


class RedisRateLimiter:
    def __init__(self, redis: Redis, prefix: str = "aura:ratelimit:") -> None:
        self._redis = redis
        self._prefix = prefix

    async def hit(self, key: str, *, limit: int, window_seconds: int) -> RateLimitResult:
        full_key = f"{self._prefix}{key}"
        try:
            async with self._redis.pipeline(transaction=True) as pipe:
                pipe.incr(full_key)
                pipe.expire(full_key, window_seconds, nx=True)
                pipe.ttl(full_key)
                count, _, ttl = await pipe.execute()
        except RedisError as exc:
            logger.warning("rate_limit_unavailable", error_type=type(exc).__name__)
            return RateLimitResult(allowed=True)
        if int(count) > limit:
            return RateLimitResult(allowed=False, retry_after_seconds=max(int(ttl), 1))
        return RateLimitResult(allowed=True)

    async def reset(self, key: str) -> None:
        try:
            await self._redis.delete(f"{self._prefix}{key}")
        except RedisError as exc:
            logger.warning("rate_limit_unavailable", error_type=type(exc).__name__)


class InMemoryRateLimiter:
    """Process-local limiter for tests."""

    def __init__(self) -> None:
        self._hits: dict[str, tuple[int, float]] = {}

    async def hit(self, key: str, *, limit: int, window_seconds: int) -> RateLimitResult:
        now = time.monotonic()
        count, started = self._hits.get(key, (0, now))
        if now - started >= window_seconds:
            count, started = 0, now
        count += 1
        self._hits[key] = (count, started)
        if count > limit:
            return RateLimitResult(False, max(int(window_seconds - (now - started)), 1))
        return RateLimitResult(True)

    async def reset(self, key: str) -> None:
        self._hits.pop(key, None)
