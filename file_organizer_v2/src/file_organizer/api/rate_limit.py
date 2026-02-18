"""Rate limiting helpers for API requests."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional, Protocol

from loguru import logger
from redis import Redis


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    remaining: int
    reset_at: int


class RateLimiter(Protocol):
    """Protocol for rate limit backends."""

    def check(self, key: str, limit: int, window_seconds: int) -> RateLimitResult:
        """Check rate limit for a key and return the remaining quota."""


@dataclass
class RateLimitState:
    count: int
    reset_at: int


class InMemoryRateLimiter:
    """Simple in-memory fixed-window rate limiter."""

    def __init__(
        self,
        max_entries: int = 10000,
        sweep_interval_seconds: int = 60,
    ) -> None:
        self._state: dict[str, RateLimitState] = {}
        self._last_sweep: int = 0
        self._max_entries = max_entries
        self._sweep_interval_seconds = sweep_interval_seconds

    def _sweep(self, now: int) -> None:
        expired = [key for key, state in self._state.items() if state.reset_at <= now]
        for key in expired:
            self._state.pop(key, None)
        self._last_sweep = now

    def check(self, key: str, limit: int, window_seconds: int) -> RateLimitResult:
        now = int(time.time())
        if now - self._last_sweep >= self._sweep_interval_seconds:
            self._sweep(now)
        elif len(self._state) >= self._max_entries:
            self._sweep(now)
        state = self._state.get(key)
        if state is None or state.reset_at <= now:
            reset_at = now + window_seconds
            self._state[key] = RateLimitState(count=1, reset_at=reset_at)
            remaining = max(limit - 1, 0)
            return RateLimitResult(allowed=True, remaining=remaining, reset_at=reset_at)

        state.count += 1
        allowed = state.count <= limit
        remaining = max(limit - state.count, 0)
        return RateLimitResult(allowed=allowed, remaining=remaining, reset_at=state.reset_at)


class RedisRateLimiter:
    """Redis-backed fixed-window rate limiter."""

    def __init__(self, redis: Redis, prefix: str = "ratelimit:") -> None:
        self._redis = redis
        self._prefix = prefix

    def _key(self, key: str) -> str:
        return f"{self._prefix}{key}"

    def check(self, key: str, limit: int, window_seconds: int) -> RateLimitResult:
        now = int(time.time())
        redis_key = self._key(key)
        script = """
        local current = redis.call("INCR", KEYS[1])
        if current == 1 then
          redis.call("EXPIRE", KEYS[1], ARGV[1])
        end
        local ttl = redis.call("TTL", KEYS[1])
        return {current, ttl}
        """
        count, ttl = self._redis.eval(script, 1, redis_key, window_seconds)
        if ttl is None or int(ttl) < 0:
            ttl = window_seconds
        reset_at = now + int(ttl)
        allowed = int(count) <= limit
        remaining = max(limit - int(count), 0)
        return RateLimitResult(allowed=allowed, remaining=remaining, reset_at=reset_at)


def build_rate_limiter(redis_url: Optional[str]) -> RateLimiter:
    """Create a rate limiter instance."""
    if not redis_url:
        return InMemoryRateLimiter()
    try:
        client = Redis.from_url(redis_url, decode_responses=True)
        client.ping()
        return RedisRateLimiter(client)
    except Exception as exc:
        logger.warning("Rate limiter Redis unavailable, using in-memory limiter: {}", exc)
        return InMemoryRateLimiter()
