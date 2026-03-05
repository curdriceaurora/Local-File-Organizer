"""Thread safety tests for API cache implementations."""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.api.cache import InMemoryCache, RedisCache

pytestmark = pytest.mark.unit


class TestInMemoryCacheThreadSafety:
    """Verify InMemoryCache is thread-safe."""

    def test_has_lock(self):
        cache = InMemoryCache()
        assert hasattr(cache, "_lock")
        assert isinstance(cache._lock, type(threading.Lock()))

    def test_concurrent_get_set(self):
        """10 threads read/write simultaneously without crash."""
        cache = InMemoryCache()
        errors: list[Exception] = []

        def writer(tid: int):
            try:
                for i in range(50):
                    cache.set(f"key-{tid}-{i}", f"val-{tid}-{i}", ttl_seconds=60)
            except Exception as exc:
                errors.append(exc)

        def reader(tid: int):
            try:
                for i in range(50):
                    cache.get(f"key-{tid}-{i}")
            except Exception as exc:
                errors.append(exc)

        threads = []
        for tid in range(5):
            threads.append(threading.Thread(target=writer, args=(tid,)))
            threads.append(threading.Thread(target=reader, args=(tid,)))

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors, f"Thread safety errors: {errors}"

    def test_concurrent_expired_eviction(self):
        """Concurrent reads trigger eviction of expired entries safely."""
        cache = InMemoryCache()
        errors: list[Exception] = []

        # Pre-populate with short-TTL entries
        for i in range(20):
            cache.set(f"k{i}", f"v{i}", ttl_seconds=1)

        # Immediately expire them
        with cache._lock:
            for entry in cache._entries.values():
                entry.expires_at = time.time() - 1

        def reader():
            try:
                for i in range(20):
                    cache.get(f"k{i}")
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=reader) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors, f"Eviction race errors: {errors}"

    def test_concurrent_delete(self):
        """Concurrent deletes do not crash."""
        cache = InMemoryCache()
        for i in range(20):
            cache.set(f"k{i}", f"v{i}", ttl_seconds=60)

        errors: list[Exception] = []

        def deleter(start: int):
            try:
                for i in range(start, start + 10):
                    cache.delete(f"k{i}")
            except Exception as exc:
                errors.append(exc)

        t1 = threading.Thread(target=deleter, args=(0,))
        t2 = threading.Thread(target=deleter, args=(10,))
        t1.start()
        t2.start()
        t1.join(timeout=5)
        t2.join(timeout=5)

        assert not errors


class TestRedisCacheCloseLogging:
    """Verify RedisCache.close() logs on error instead of silently swallowing."""

    def test_close_logs_warning_on_error(self):
        from file_organizer.api.cache import RedisError

        mock_redis = MagicMock()
        mock_redis.close.side_effect = RedisError("connection lost")
        with patch("file_organizer.api.cache.Redis") as mock_cls:
            mock_cls.from_url.return_value = mock_redis
            cache = RedisCache("redis://localhost:6379")

        with patch("file_organizer.api.cache.logger") as mock_logger:
            cache.close()
            mock_logger.warning.assert_called_once()
            call_args = str(mock_logger.warning.call_args)
            assert "close failed" in call_args
