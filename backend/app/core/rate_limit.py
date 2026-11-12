"""Fixed-window rate limiting backed by Redis.

When Redis is unavailable the limiter either fails open (allows the request and logs a
warning; development default) or fails closed (refuses with 503; staging/production default,
`RATE_LIMIT_FAIL_OPEN`), so an outage of the cache can never switch brute-force protection off
in production (ADR-049).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.errors import ServiceUnavailableError
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class RateLimitResult:
    allowed: bool
    retry_after_seconds: int = 0


class RateLimiter(Protocol):
    async def hit(self, key: str, *, limit: int, window_seconds: int) -> RateLimitResult: ...

    async def reset(self, key: str) -> None: ...


class RateLimiterUnavailableError(ServiceUnavailableError):
    code = "rate_limiter_unavailable"
    message = "ระบบไม่พร้อมรับคำขอนี้ชั่วคราว กรุณาลองใหม่ภายหลัง"


class RedisRateLimiter:
    def __init__(
        self, redis: Redis, prefix: str = "orbit:ratelimit:", *, fail_open: bool = True
    ) -> None:
        self._redis = redis
        self._prefix = prefix
        self._fail_open = fail_open

    async def hit(self, key: str, *, limit: int, window_seconds: int) -> RateLimitResult:
        full_key = f"{self._prefix}{key}"
        try:
            async with self._redis.pipeline(transaction=True) as pipe:
                pipe.incr(full_key)
                pipe.expire(full_key, window_seconds, nx=True)
                pipe.ttl(full_key)
                count, _, ttl = await pipe.execute()
        except RedisError as exc:
            logger.warning(
                "rate_limit_unavailable",
                error_type=type(exc).__name__,
                fail_open=self._fail_open,
            )
            if not self._fail_open:
                raise RateLimiterUnavailableError() from None
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
