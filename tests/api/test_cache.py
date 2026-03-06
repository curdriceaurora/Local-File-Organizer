"""Tests for API cache abstraction."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.api.cache import (
    InMemoryCache,
    RedisCache,
    _is_valid_redis_url,
    build_cache_backend,
)

pytestmark = [pytest.mark.unit, pytest.mark.ci]


class TestInMemoryCache:
    """Tests for InMemoryCache."""

    def test_set_and_get(self):
        cache = InMemoryCache()
        cache.set("key1", "value1", ttl_seconds=60)
        assert cache.get("key1") == "value1"

    def test_get_nonexistent_key(self):
        cache = InMemoryCache()
        assert cache.get("missing") is None

    def test_expired_entry_returns_none(self):
        cache = InMemoryCache()
        cache.set("key1", "value1", ttl_seconds=1)
        # Manually expire the entry
        cache._entries["key1"].expires_at = time.time() - 1
        assert cache.get("key1") is None
        # Entry should be cleaned up
        assert "key1" not in cache._entries

    def test_delete_existing_key(self):
        cache = InMemoryCache()
        cache.set("key1", "value1", ttl_seconds=60)
        cache.delete("key1")
        assert cache.get("key1") is None

    def test_delete_nonexistent_key(self):
        cache = InMemoryCache()
        # Should not raise
        cache.delete("missing")

    def test_close_clears_all(self):
        cache = InMemoryCache()
        cache.set("k1", "v1", ttl_seconds=60)
        cache.set("k2", "v2", ttl_seconds=60)
        cache.close()
        assert cache.get("k1") is None
        assert cache.get("k2") is None

    def test_ttl_minimum_one_second(self):
        cache = InMemoryCache()
        cache.set("key1", "value1", ttl_seconds=0)
        # With ttl_seconds=0, max(1, 0) = 1, so it should still be valid
        assert cache.get("key1") == "value1"

    def test_overwrite_key(self):
        cache = InMemoryCache()
        cache.set("key1", "first", ttl_seconds=60)
        cache.set("key1", "second", ttl_seconds=60)
        assert cache.get("key1") == "second"


class TestRedisCache:
    """Tests for RedisCache."""

    def test_init_raises_without_redis(self):
        with patch("file_organizer.api.cache.Redis", None):
            with pytest.raises(RuntimeError, match="redis package not installed"):
                RedisCache("redis://localhost:6379")

    def test_get_returns_string_value(self):
        mock_redis = MagicMock()
        mock_redis.get.return_value = "cached_value"
        with patch("file_organizer.api.cache.Redis") as mock_cls:
            mock_cls.from_url.return_value = mock_redis
            cache = RedisCache("redis://localhost:6379")
        result = cache.get("key1")
        assert result == "cached_value"
        mock_redis.get.assert_called_once_with("key1")

    def test_get_returns_none_for_non_string(self):
        mock_redis = MagicMock()
        mock_redis.get.return_value = 42  # Not a string
        with patch("file_organizer.api.cache.Redis") as mock_cls:
            mock_cls.from_url.return_value = mock_redis
            cache = RedisCache("redis://localhost:6379")
        assert cache.get("key1") is None

    def test_get_returns_none_on_redis_error(self):
        mock_redis = MagicMock()
        from file_organizer.api.cache import RedisError

        mock_redis.get.side_effect = RedisError("connection lost")
        with patch("file_organizer.api.cache.Redis") as mock_cls:
            mock_cls.from_url.return_value = mock_redis
            cache = RedisCache("redis://localhost:6379")
        assert cache.get("key1") is None

    def test_set_calls_setex(self):
        mock_redis = MagicMock()
        with patch("file_organizer.api.cache.Redis") as mock_cls:
            mock_cls.from_url.return_value = mock_redis
            cache = RedisCache("redis://localhost:6379")
        cache.set("key1", "val1", ttl_seconds=300)
        mock_redis.setex.assert_called_once_with("key1", 300, "val1")

    def test_set_minimum_ttl(self):
        mock_redis = MagicMock()
        with patch("file_organizer.api.cache.Redis") as mock_cls:
            mock_cls.from_url.return_value = mock_redis
            cache = RedisCache("redis://localhost:6379")
        cache.set("key1", "val1", ttl_seconds=0)
        mock_redis.setex.assert_called_once_with("key1", 1, "val1")

    def test_set_handles_redis_error(self):
        mock_redis = MagicMock()
        from file_organizer.api.cache import RedisError

        mock_redis.setex.side_effect = RedisError("connection lost")
        with patch("file_organizer.api.cache.Redis") as mock_cls:
            mock_cls.from_url.return_value = mock_redis
            cache = RedisCache("redis://localhost:6379")
        # Should not raise
        cache.set("key1", "val1", ttl_seconds=60)

    def test_delete_calls_redis_delete(self):
        mock_redis = MagicMock()
        with patch("file_organizer.api.cache.Redis") as mock_cls:
            mock_cls.from_url.return_value = mock_redis
            cache = RedisCache("redis://localhost:6379")
        cache.delete("key1")
        mock_redis.delete.assert_called_once_with("key1")

    def test_delete_handles_redis_error(self):
        mock_redis = MagicMock()
        from file_organizer.api.cache import RedisError

        mock_redis.delete.side_effect = RedisError("connection lost")
        with patch("file_organizer.api.cache.Redis") as mock_cls:
            mock_cls.from_url.return_value = mock_redis
            cache = RedisCache("redis://localhost:6379")
        # Should not raise
        cache.delete("key1")

    def test_close_calls_redis_close(self):
        mock_redis = MagicMock()
        with patch("file_organizer.api.cache.Redis") as mock_cls:
            mock_cls.from_url.return_value = mock_redis
            cache = RedisCache("redis://localhost:6379")
        cache.close()
        mock_redis.close.assert_called_once()

    def test_close_handles_redis_error(self):
        mock_redis = MagicMock()
        from file_organizer.api.cache import RedisError

        mock_redis.close.side_effect = RedisError("connection lost")
        with patch("file_organizer.api.cache.Redis") as mock_cls:
            mock_cls.from_url.return_value = mock_redis
            cache = RedisCache("redis://localhost:6379")
        # Should not raise
        cache.close()

    def test_get_returns_none_for_none(self):
        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        with patch("file_organizer.api.cache.Redis") as mock_cls:
            mock_cls.from_url.return_value = mock_redis
            cache = RedisCache("redis://localhost:6379")
        assert cache.get("key1") is None


class TestIsValidRedisUrl:
    """Tests for _is_valid_redis_url."""

    def test_redis_scheme(self):
        assert _is_valid_redis_url("redis://localhost:6379") is True

    def test_rediss_scheme(self):
        assert _is_valid_redis_url("rediss://localhost:6379") is True

    def test_unix_scheme(self):
        assert _is_valid_redis_url("unix:///var/run/redis.sock") is True

    def test_http_scheme_invalid(self):
        assert _is_valid_redis_url("http://localhost:6379") is False

    def test_empty_string(self):
        assert _is_valid_redis_url("") is False

    def test_no_scheme(self):
        assert _is_valid_redis_url("localhost:6379") is False


class TestBuildCacheBackend:
    """Tests for build_cache_backend."""

    def test_none_url_returns_in_memory(self):
        backend = build_cache_backend(None)
        assert isinstance(backend, InMemoryCache)

    def test_empty_url_returns_in_memory(self):
        backend = build_cache_backend("")
        assert isinstance(backend, InMemoryCache)

    def test_invalid_scheme_returns_in_memory(self):
        backend = build_cache_backend("http://localhost:6379")
        assert isinstance(backend, InMemoryCache)

    def test_redis_connection_failure_returns_in_memory(self):
        with patch("file_organizer.api.cache.RedisCache") as mock_cls:
            mock_cls.side_effect = OSError("connection refused")
            backend = build_cache_backend("redis://localhost:6379")
        assert isinstance(backend, InMemoryCache)

    def test_redis_success_returns_redis_cache(self):
        mock_redis_cache = MagicMock(spec=RedisCache)
        with patch("file_organizer.api.cache.RedisCache", return_value=mock_redis_cache):
            backend = build_cache_backend("redis://localhost:6379")
        assert backend is mock_redis_cache
        mock_redis_cache.set.assert_called_once()

    def test_redis_runtime_error_returns_in_memory(self):
        with patch("file_organizer.api.cache.RedisCache") as mock_cls:
            mock_cls.side_effect = RuntimeError("redis not installed")
            backend = build_cache_backend("redis://localhost:6379")
        assert isinstance(backend, InMemoryCache)

    def test_redis_value_error_returns_in_memory(self):
        with patch("file_organizer.api.cache.RedisCache") as mock_cls:
            mock_cls.side_effect = ValueError("bad url")
            backend = build_cache_backend("redis://localhost:6379")
        assert isinstance(backend, InMemoryCache)
