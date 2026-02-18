"""Tests for API cache backends."""

from __future__ import annotations

import json
from typing import cast

import pytest

import file_organizer.api.cache as cache_mod
from file_organizer.api.cache import InMemoryCache, build_cache_backend


def test_in_memory_cache_set_get_delete() -> None:
    cache = InMemoryCache()
    cache.set("k1", "v1", ttl_seconds=60)
    assert cache.get("k1") == "v1"
    cache.delete("k1")
    assert cache.get("k1") is None


def test_in_memory_cache_expiry(monkeypatch: pytest.MonkeyPatch) -> None:
    cache = InMemoryCache()
    now = 1_000.0

    monkeypatch.setattr(cache_mod.time, "time", lambda: now)
    cache.set("exp", "value", ttl_seconds=10)
    assert cache.get("exp") == "value"

    monkeypatch.setattr(cache_mod.time, "time", lambda: now + 11.0)
    assert cache.get("exp") is None


def test_build_cache_backend_without_url_returns_memory() -> None:
    backend = build_cache_backend(None)
    assert isinstance(backend, InMemoryCache)


def test_build_cache_backend_invalid_url_falls_back_to_memory() -> None:
    backend = build_cache_backend("http://not-redis")
    assert isinstance(backend, InMemoryCache)


def test_build_cache_backend_fallback_when_redis_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BrokenRedisCache:
        def __init__(self, _url: str) -> None:
            raise RuntimeError("no redis")

    monkeypatch.setattr(cache_mod, "RedisCache", BrokenRedisCache)
    backend = build_cache_backend("redis://localhost:6379/0")
    assert isinstance(backend, InMemoryCache)


def test_build_cache_backend_redis_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeRedisCache:
        def __init__(self, _url: str) -> None:
            self.values: dict[str, str] = {}

        def get(self, key: str) -> str | None:
            return self.values.get(key)

        def set(self, key: str, value: str, *, ttl_seconds: int) -> None:
            assert ttl_seconds > 0
            self.values[key] = value

        def delete(self, key: str) -> None:
            self.values.pop(key, None)

        def close(self) -> None:
            pass

    monkeypatch.setattr(cache_mod, "RedisCache", FakeRedisCache)
    backend = cast(FakeRedisCache, build_cache_backend("redis://localhost:6379/0"))
    backend.set("payload", json.dumps({"ok": True}), ttl_seconds=10)
    assert backend.get("payload") == json.dumps({"ok": True})
