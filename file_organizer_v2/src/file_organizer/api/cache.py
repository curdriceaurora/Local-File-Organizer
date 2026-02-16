"""Cache abstraction for API persistence layers.

Provides a small key/value interface with an in-memory implementation and an
optional Redis backend.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Optional, Protocol
from urllib.parse import urlparse

from loguru import logger

try:
    from redis import Redis
    from redis.exceptions import RedisError
except (ImportError, ModuleNotFoundError):  # pragma: no cover - optional dependency runtime fallback
    Redis = None  # type: ignore[assignment]

    class RedisError(Exception):
        """Fallback Redis exception type when redis package is unavailable."""


class CacheBackend(Protocol):
    """Minimal cache backend contract."""

    def get(self, key: str) -> Optional[str]:
        """Return cached value for *key*, or None when absent/expired."""

    def set(self, key: str, value: str, *, ttl_seconds: int) -> None:
        """Store *value* for *key* with TTL."""

    def delete(self, key: str) -> None:
        """Delete *key* if present."""

    def close(self) -> None:
        """Release any backend resources."""


@dataclass
class _MemoryEntry:
    value: str
    expires_at: float


class InMemoryCache:
    """In-process TTL cache implementation."""

    def __init__(self) -> None:
        self._entries: dict[str, _MemoryEntry] = {}

    def get(self, key: str) -> Optional[str]:
        entry = self._entries.get(key)
        if entry is None:
            return None
        if entry.expires_at < time.time():
            self._entries.pop(key, None)
            return None
        return entry.value

    def set(self, key: str, value: str, *, ttl_seconds: int) -> None:
        expires_at = time.time() + max(1, ttl_seconds)
        self._entries[key] = _MemoryEntry(value=value, expires_at=expires_at)

    def delete(self, key: str) -> None:
        self._entries.pop(key, None)

    def close(self) -> None:
        self._entries.clear()


class RedisCache:
    """Redis-backed cache implementation."""

    def __init__(self, redis_url: str) -> None:
        if Redis is None:
            raise RuntimeError("redis package not installed")
        self._redis = Redis.from_url(redis_url, decode_responses=True)

    def get(self, key: str) -> Optional[str]:
        try:
            value = self._redis.get(key)
        except RedisError as exc:
            logger.warning("Redis cache get failed for {}: {}", key, exc)
            return None
        return value if isinstance(value, str) else None

    def set(self, key: str, value: str, *, ttl_seconds: int) -> None:
        try:
            self._redis.setex(key, max(1, ttl_seconds), value)
        except RedisError as exc:
            logger.warning("Redis cache set failed for {}: {}", key, exc)

    def delete(self, key: str) -> None:
        try:
            self._redis.delete(key)
        except RedisError as exc:
            logger.warning("Redis cache delete failed for {}: {}", key, exc)

    def close(self) -> None:
        try:
            self._redis.close()
        except RedisError:
            pass


def _is_valid_redis_url(redis_url: str) -> bool:
    parsed = urlparse(redis_url)
    return parsed.scheme in {"redis", "rediss", "unix"}


def build_cache_backend(redis_url: Optional[str]) -> CacheBackend:
    """Build a cache backend from configuration.

    Falls back to in-memory cache when Redis is unavailable or connection
    validation fails.
    """
    if not redis_url:
        return InMemoryCache()
    if not _is_valid_redis_url(redis_url):
        logger.warning("Invalid Redis URL scheme; falling back to in-memory cache")
        return InMemoryCache()

    try:
        backend = RedisCache(redis_url)
        backend.set("__fo_cache_health__", json.dumps({"ok": True}), ttl_seconds=5)
        return backend
    except (RedisError, RuntimeError, ValueError, OSError) as exc:
        logger.warning(
            "Falling back to in-memory cache (redis unavailable: {}): {}",
            type(exc).__name__,
            exc,
        )
        return InMemoryCache()
