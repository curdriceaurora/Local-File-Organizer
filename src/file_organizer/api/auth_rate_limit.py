"""Login rate limiting helpers."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Protocol

from loguru import logger
from redis import Redis


class LoginRateLimiter(Protocol):
    """Protocol for login rate limiting backends."""

    def is_blocked(self, key: str) -> tuple[bool, int]:
        """Return (blocked, retry_after_seconds)."""

    def record_failure(self, key: str) -> tuple[bool, int]:
        """Record a failed attempt and return (blocked, retry_after_seconds)."""

    def reset(self, key: str) -> None:
        """Clear rate limit state for a key."""


@dataclass
class RateLimitState:
    """Track rate limit count and expiry for a key."""

    count: int
    expires_at: float

    def remaining(self, now: float) -> int:
        """Return remaining seconds until window expiry."""
        return max(0, int(self.expires_at - now))


@dataclass
class InMemoryLoginRateLimiter:
    """In-memory fixed-window rate limiter for login attempts."""

    max_attempts: int
    window_seconds: int
    _state: dict[str, RateLimitState] = field(default_factory=dict)

    def _get_state(self, key: str, now: float) -> RateLimitState | None:
        state = self._state.get(key)
        if state is None:
            return None
        if state.expires_at <= now:
            self._state.pop(key, None)
            return None
        return state

    def is_blocked(self, key: str) -> tuple[bool, int]:
        """Return whether the key is currently blocked and retry-after seconds."""
        now = time.time()
        state = self._get_state(key, now)
        if state is None:
            return False, 0
        if state.count >= self.max_attempts:
            return True, state.remaining(now)
        return False, 0

    def record_failure(self, key: str) -> tuple[bool, int]:
        """Record a failed attempt and return blocked status and retry-after seconds."""
        now = time.time()
        state = self._get_state(key, now)
        if state is None:
            state = RateLimitState(count=1, expires_at=now + self.window_seconds)
            self._state[key] = state
        else:
            state.count += 1
        blocked = state.count >= self.max_attempts
        return blocked, state.remaining(now)

    def reset(self, key: str) -> None:
        """Clear rate limit state for the given key."""
        self._state.pop(key, None)


@dataclass(frozen=True)
class RedisLoginRateLimiter:
    """Redis-backed fixed-window login rate limiter."""

    redis: Redis
    max_attempts: int
    window_seconds: int
    prefix: str = "auth:login:"

    def _key(self, key: str) -> str:
        return f"{self.prefix}{key}"

    def _ttl(self, key: str) -> int:
        ttl = self.redis.ttl(key)
        if ttl is None or int(ttl) < 0:
            return self.window_seconds
        return int(ttl)

    def is_blocked(self, key: str) -> tuple[bool, int]:
        """Return whether the key is currently blocked and retry-after seconds."""
        redis_key = self._key(key)
        value = self.redis.get(redis_key)
        if value is None:
            return False, 0
        try:
            count = int(value)
        except ValueError:
            self.redis.delete(redis_key)
            return False, 0
        if count >= self.max_attempts:
            return True, self._ttl(redis_key)
        return False, 0

    def record_failure(self, key: str) -> tuple[bool, int]:
        """Record a failed attempt and return blocked status and retry-after seconds."""
        redis_key = self._key(key)
        pipe = self.redis.pipeline()
        pipe.incr(redis_key)
        pipe.ttl(redis_key)
        count, ttl = pipe.execute()
        if ttl is None or int(ttl) < 0:
            self.redis.expire(redis_key, self.window_seconds)
            ttl = self.window_seconds
        blocked = int(count) >= self.max_attempts
        return blocked, int(ttl)

    def reset(self, key: str) -> None:
        """Clear rate limit state for the given key."""
        self.redis.delete(self._key(key))


def build_login_rate_limiter(
    redis_url: str | None,
    max_attempts: int,
    window_seconds: int,
) -> LoginRateLimiter:
    """Create a login rate limiter, preferring Redis when configured."""
    if not redis_url:
        return InMemoryLoginRateLimiter(max_attempts=max_attempts, window_seconds=window_seconds)
    try:
        client = Redis.from_url(redis_url, decode_responses=True)
        client.ping()
        return RedisLoginRateLimiter(
            redis=client,
            max_attempts=max_attempts,
            window_seconds=window_seconds,
        )
    except Exception as exc:
        logger.warning("Auth redis unavailable, using in-memory rate limiter: {}", exc)
        return InMemoryLoginRateLimiter(max_attempts=max_attempts, window_seconds=window_seconds)
