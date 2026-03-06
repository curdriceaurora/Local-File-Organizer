"""Thread safety tests for InMemoryCache and RedisCache close logging."""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.api.cache import InMemoryCache, RedisCache

pytestmark = pytest.mark.unit


class TestInMemoryConcurrentGetSet:
    def test_concurrent_get_set_no_crash(self) -> None:
        """10 threads reading and writing simultaneously should not corrupt state.

        This test exercises the critical path where multiple threads concurrently
        access the cache with set/get operations to ensure the locking mechanism
        prevents race conditions and data corruption.
        """
        cache = InMemoryCache()
        errors: list[Exception] = []

        def writer(thread_id: int) -> None:
            """Write entries to cache from thread."""
            try:
                for i in range(50):
                    cache.set(f"key-{thread_id}-{i}", f"val-{i}", ttl_seconds=60)
            except Exception as exc:
                errors.append(exc)

        def reader(thread_id: int) -> None:
            """Read entries from cache from thread."""
            try:
                for i in range(50):
                    cache.get(f"key-{thread_id}-{i}")
            except Exception as exc:
                errors.append(exc)

        threads = []
        for tid in range(5):
            threads.append(threading.Thread(target=writer, args=(tid,)))
            threads.append(threading.Thread(target=reader, args=(tid,)))

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        # Verify all threads actually completed
        assert all(not t.is_alive() for t in threads), "Some threads did not finish"
        assert not errors, f"Concurrent access errors: {errors}"

    def test_concurrent_expired_eviction(self) -> None:
        """Short TTL entries evicted during concurrent reads should not crash.

        This test ensures that concurrent expiration and eviction of cache
        entries doesn't cause race conditions or exceptions.
        """
        cache = InMemoryCache()
        errors: list[Exception] = []

        # Pre-populate with entries that will expire
        for i in range(20):
            cache.set(f"exp-{i}", f"val-{i}", ttl_seconds=1)
            cache._entries[f"exp-{i}"].expires_at = time.time() - 1

        def reader() -> None:
            """Read entries and trigger eviction from thread."""
            try:
                for i in range(20):
                    cache.get(f"exp-{i}")  # Should evict expired entries
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=reader) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        assert not errors, f"Concurrent eviction errors: {errors}"

    def test_concurrent_delete(self) -> None:
        """Concurrent deletes should not crash.

        This test verifies that multiple threads can safely delete cache
        entries simultaneously without corruption or exceptions.
        """
        cache = InMemoryCache()
        errors: list[Exception] = []

        for i in range(20):
            cache.set(f"del-{i}", f"val-{i}", ttl_seconds=60)

        def deleter() -> None:
            """Delete entries from cache from thread."""
            try:
                for i in range(20):
                    cache.delete(f"del-{i}")
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=deleter) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        assert not errors, f"Concurrent delete errors: {errors}"


class TestRedisCacheCloseLogsOnError:
    def test_close_logs_warning_on_error(self) -> None:
        """RedisCache.close() should log a warning when Redis raises.

        This test verifies that when the underlying Redis client fails to
        close (e.g., due to connection loss), the error is logged as a
        warning rather than silently ignored or propagated.
        """
        with patch("file_organizer.api.cache.Redis") as mock_redis_cls:
            mock_redis = MagicMock()
            mock_redis_cls.from_url.return_value = mock_redis

            cache = RedisCache("redis://localhost:6379")

            # Import the actual RedisError used by the module
            from file_organizer.api.cache import RedisError

            mock_redis.close.side_effect = RedisError("connection lost")

            with patch("file_organizer.api.cache.logger") as mock_logger:
                cache.close()
                mock_logger.warning.assert_called_once()
                call_args = mock_logger.warning.call_args
                assert "close" in call_args[0][0].lower() or "Redis" in call_args[0][0]
