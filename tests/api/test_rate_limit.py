"""Tests for API rate limiting."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.api.rate_limit import (
    InMemoryRateLimiter,
    RateLimitResult,
    RedisRateLimiter,
    build_rate_limiter,
)


class TestRateLimitResult:
    """Tests for RateLimitResult dataclass."""

    def test_creation(self):
        result = RateLimitResult(allowed=True, remaining=9, reset_at=1000)
        assert result.allowed is True
        assert result.remaining == 9
        assert result.reset_at == 1000

    def test_frozen(self):
        result = RateLimitResult(allowed=True, remaining=9, reset_at=1000)
        with pytest.raises(AttributeError):
            result.allowed = False  # type: ignore[misc]


class TestInMemoryRateLimiter:
    """Tests for InMemoryRateLimiter."""

    def test_first_request_allowed(self):
        limiter = InMemoryRateLimiter()
        result = limiter.check("test-key", limit=10, window_seconds=60)
        assert result.allowed is True
        assert result.remaining == 9

    def test_within_limit_allowed(self):
        limiter = InMemoryRateLimiter()
        for _ in range(5):
            result = limiter.check("test-key", limit=10, window_seconds=60)
        assert result.allowed is True
        assert result.remaining == 5

    def test_at_limit_allowed(self):
        limiter = InMemoryRateLimiter()
        for _ in range(10):
            result = limiter.check("test-key", limit=10, window_seconds=60)
        assert result.allowed is True
        assert result.remaining == 0

    def test_over_limit_denied(self):
        limiter = InMemoryRateLimiter()
        for _ in range(11):
            result = limiter.check("test-key", limit=10, window_seconds=60)
        assert result.allowed is False
        assert result.remaining == 0

    def test_different_keys_independent(self):
        limiter = InMemoryRateLimiter()
        for _ in range(10):
            limiter.check("key-a", limit=10, window_seconds=60)
        result = limiter.check("key-b", limit=10, window_seconds=60)
        assert result.allowed is True
        assert result.remaining == 9

    def test_expired_window_resets(self):
        limiter = InMemoryRateLimiter()
        # Use up the limit
        for _ in range(10):
            limiter.check("test-key", limit=10, window_seconds=60)
        # Expire the window
        limiter._state["test-key"].reset_at = int(time.time()) - 1
        result = limiter.check("test-key", limit=10, window_seconds=60)
        assert result.allowed is True
        assert result.remaining == 9

    def test_sweep_on_interval(self):
        limiter = InMemoryRateLimiter(sweep_interval_seconds=0)
        limiter.check("key1", limit=10, window_seconds=1)
        # Expire the entry
        limiter._state["key1"].reset_at = int(time.time()) - 1
        # Next check triggers sweep (sweep_interval_seconds=0 means always sweep)
        limiter.check("key2", limit=10, window_seconds=60)
        assert "key1" not in limiter._state

    def test_sweep_on_max_entries(self):
        limiter = InMemoryRateLimiter(max_entries=2, sweep_interval_seconds=9999)
        limiter.check("key1", limit=10, window_seconds=1)
        limiter.check("key2", limit=10, window_seconds=1)
        # Expire one key
        limiter._state["key1"].reset_at = int(time.time()) - 1
        # Third check exceeds max_entries, triggers sweep
        limiter.check("key3", limit=10, window_seconds=60)
        assert "key1" not in limiter._state

    def test_remaining_never_negative(self):
        limiter = InMemoryRateLimiter()
        for _ in range(20):
            result = limiter.check("test-key", limit=5, window_seconds=60)
        assert result.remaining == 0


class TestRedisRateLimiter:
    """Tests for RedisRateLimiter."""

    def _make_limiter(self):
        mock_redis = MagicMock()
        limiter = RedisRateLimiter(mock_redis, prefix="test:")
        return limiter, mock_redis

    def test_key_prefix(self):
        limiter, mock_redis = self._make_limiter()
        assert limiter._key("user:123") == "test:user:123"

    def test_allowed_when_under_limit(self):
        limiter, mock_redis = self._make_limiter()
        mock_redis.eval.return_value = (1, 60)
        result = limiter.check("user:123", limit=10, window_seconds=60)
        assert result.allowed is True
        assert result.remaining == 9

    def test_denied_when_over_limit(self):
        limiter, mock_redis = self._make_limiter()
        mock_redis.eval.return_value = (11, 30)
        result = limiter.check("user:123", limit=10, window_seconds=60)
        assert result.allowed is False
        assert result.remaining == 0

    def test_ttl_none_uses_window(self):
        limiter, mock_redis = self._make_limiter()
        mock_redis.eval.return_value = (1, None)
        result = limiter.check("user:123", limit=10, window_seconds=60)
        assert result.allowed is True
        # reset_at should be now + window_seconds

    def test_ttl_negative_uses_window(self):
        limiter, mock_redis = self._make_limiter()
        mock_redis.eval.return_value = (1, -1)
        result = limiter.check("user:123", limit=10, window_seconds=60)
        assert result.allowed is True

    def test_exact_limit_allowed(self):
        limiter, mock_redis = self._make_limiter()
        mock_redis.eval.return_value = (10, 30)
        result = limiter.check("user:123", limit=10, window_seconds=60)
        assert result.allowed is True
        assert result.remaining == 0

    def test_script_called_with_correct_args(self):
        limiter, mock_redis = self._make_limiter()
        mock_redis.eval.return_value = (1, 60)
        limiter.check("user:123", limit=10, window_seconds=120)
        call_args = mock_redis.eval.call_args
        assert call_args[0][1] == 1  # number of keys
        assert call_args[0][2] == "test:user:123"
        assert call_args[0][3] == 120  # window_seconds


class TestBuildRateLimiter:
    """Tests for build_rate_limiter."""

    def test_no_url_returns_in_memory(self):
        limiter = build_rate_limiter(None)
        assert isinstance(limiter, InMemoryRateLimiter)

    def test_empty_url_returns_in_memory(self):
        limiter = build_rate_limiter("")
        assert isinstance(limiter, InMemoryRateLimiter)

    def test_redis_failure_returns_in_memory(self):
        with patch("file_organizer.api.rate_limit.Redis") as mock_redis_cls:
            mock_client = MagicMock()
            mock_client.ping.side_effect = ConnectionError("refused")
            mock_redis_cls.from_url.return_value = mock_client
            limiter = build_rate_limiter("redis://localhost:6379")
        assert isinstance(limiter, InMemoryRateLimiter)

    def test_redis_success_returns_redis_limiter(self):
        with patch("file_organizer.api.rate_limit.Redis") as mock_redis_cls:
            mock_client = MagicMock()
            mock_client.ping.return_value = True
            mock_redis_cls.from_url.return_value = mock_client
            limiter = build_rate_limiter("redis://localhost:6379")
        assert isinstance(limiter, RedisRateLimiter)
