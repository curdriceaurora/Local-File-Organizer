"""Tests for login rate limiting (auth_rate_limit.py)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from file_organizer.api.auth_rate_limit import (
    InMemoryLoginRateLimiter,
    RateLimitState,
    RedisLoginRateLimiter,
    build_login_rate_limiter,
)


@pytest.mark.unit
class TestRateLimitState:
    """Tests for RateLimitState helper."""

    def test_remaining_positive(self):
        import time
        state = RateLimitState(count=1, expires_at=time.time() + 60)
        assert state.remaining(time.time()) > 0

    def test_remaining_clamps_to_zero(self):
        state = RateLimitState(count=1, expires_at=0.0)
        assert state.remaining(1000.0) == 0


@pytest.mark.unit
class TestInMemoryLoginRateLimiter:
    """Tests for InMemoryLoginRateLimiter."""

    def test_not_blocked_initially(self):
        limiter = InMemoryLoginRateLimiter(max_attempts=3, window_seconds=60)
        blocked, _ = limiter.is_blocked("user@example.com")
        assert blocked is False

    def test_record_failure_increments_count(self):
        limiter = InMemoryLoginRateLimiter(max_attempts=5, window_seconds=60)
        blocked, _ = limiter.record_failure("user@example.com")
        assert blocked is False

    def test_blocked_after_max_attempts(self):
        limiter = InMemoryLoginRateLimiter(max_attempts=2, window_seconds=60)
        limiter.record_failure("user@example.com")
        blocked, retry_after = limiter.record_failure("user@example.com")
        assert blocked is True
        assert retry_after > 0

    def test_is_blocked_reflects_state(self):
        limiter = InMemoryLoginRateLimiter(max_attempts=2, window_seconds=60)
        limiter.record_failure("user@example.com")
        limiter.record_failure("user@example.com")
        blocked, _ = limiter.is_blocked("user@example.com")
        assert blocked is True

    def test_reset_clears_state(self):
        limiter = InMemoryLoginRateLimiter(max_attempts=2, window_seconds=60)
        limiter.record_failure("user@example.com")
        limiter.record_failure("user@example.com")
        limiter.reset("user@example.com")
        blocked, _ = limiter.is_blocked("user@example.com")
        assert blocked is False

    def test_different_keys_independent(self):
        limiter = InMemoryLoginRateLimiter(max_attempts=2, window_seconds=60)
        limiter.record_failure("alice@example.com")
        limiter.record_failure("alice@example.com")
        blocked, _ = limiter.is_blocked("bob@example.com")
        assert blocked is False

    def test_expire_all_helper_unblocks(self):
        # S-1: use _expire_all helper instead of reaching into _state directly
        limiter = InMemoryLoginRateLimiter(max_attempts=2, window_seconds=60)
        limiter.record_failure("user@example.com")
        limiter.record_failure("user@example.com")
        assert limiter.is_blocked("user@example.com")[0] is True

        limiter._expire_all()
        blocked, _ = limiter.is_blocked("user@example.com")
        assert blocked is False

    def test_advance_time_helper_triggers_expiry(self):
        # S-1: use _advance_time helper to simulate window expiry
        limiter = InMemoryLoginRateLimiter(max_attempts=2, window_seconds=60)
        limiter.record_failure("user@example.com")
        limiter.record_failure("user@example.com")
        assert limiter.is_blocked("user@example.com")[0] is True

        limiter._advance_time(61)
        blocked, _ = limiter.is_blocked("user@example.com")
        assert blocked is False

    def test_retry_after_is_reasonable(self):
        limiter = InMemoryLoginRateLimiter(max_attempts=1, window_seconds=60)
        _, retry_after = limiter.record_failure("user@example.com")
        assert 0 < retry_after <= 60


@pytest.mark.unit
class TestRedisLoginRateLimiter:
    """Tests for RedisLoginRateLimiter."""

    def _make_limiter(self, max_attempts: int = 5, window: int = 60):
        mock_redis = MagicMock()
        limiter = RedisLoginRateLimiter(
            redis=mock_redis,
            max_attempts=max_attempts,
            window_seconds=window,
        )
        return limiter, mock_redis

    def test_key_prefix(self):
        limiter, _ = self._make_limiter()
        assert limiter._key("test@example.com") == "auth:login:test@example.com"

    def test_custom_prefix(self):
        mock_redis = MagicMock()
        limiter = RedisLoginRateLimiter(
            redis=mock_redis,
            max_attempts=3,
            window_seconds=60,
            prefix="custom:",
        )
        assert limiter._key("x") == "custom:x"

    def test_not_blocked_when_key_absent(self):
        limiter, mock_redis = self._make_limiter()
        mock_redis.get.return_value = None
        blocked, _ = limiter.is_blocked("user@example.com")
        assert blocked is False

    def test_not_blocked_below_max(self):
        limiter, mock_redis = self._make_limiter(max_attempts=5)
        mock_redis.get.return_value = "3"
        blocked, _ = limiter.is_blocked("user@example.com")
        assert blocked is False

    def test_blocked_at_max(self):
        limiter, mock_redis = self._make_limiter(max_attempts=5)
        mock_redis.get.return_value = "5"
        mock_redis.ttl.return_value = 30
        blocked, retry_after = limiter.is_blocked("user@example.com")
        assert blocked is True
        assert retry_after == 30

    def test_record_failure_increments(self):
        limiter, mock_redis = self._make_limiter(max_attempts=5)
        mock_redis.pipeline.return_value.__enter__ = MagicMock(return_value=mock_redis.pipeline.return_value)
        mock_redis.pipeline.return_value.__exit__ = MagicMock(return_value=False)
        mock_redis.pipeline.return_value.execute.return_value = (1, 60)
        blocked, _ = limiter.record_failure("user@example.com")
        assert blocked is False

    def test_reset_deletes_key(self):
        limiter, mock_redis = self._make_limiter()
        limiter.reset("user@example.com")
        mock_redis.delete.assert_called_once()

    def test_invalid_redis_value_cleared(self):
        limiter, mock_redis = self._make_limiter()
        mock_redis.get.return_value = "not-a-number"
        blocked, _ = limiter.is_blocked("user@example.com")
        assert blocked is False
        mock_redis.delete.assert_called_once()


@pytest.mark.unit
class TestBuildLoginRateLimiter:
    """Tests for build_login_rate_limiter."""

    def test_no_url_returns_in_memory(self):
        limiter = build_login_rate_limiter(None, max_attempts=5, window_seconds=60)
        assert isinstance(limiter, InMemoryLoginRateLimiter)

    def test_empty_url_returns_in_memory(self):
        limiter = build_login_rate_limiter("", max_attempts=5, window_seconds=60)
        assert isinstance(limiter, InMemoryLoginRateLimiter)

    def test_redis_failure_falls_back_to_in_memory(self):
        with patch("file_organizer.api.auth_rate_limit.Redis") as mock_redis_cls:
            mock_client = MagicMock()
            mock_client.ping.side_effect = ConnectionError("refused")
            mock_redis_cls.from_url.return_value = mock_client
            limiter = build_login_rate_limiter(
                "redis://localhost:6379", max_attempts=5, window_seconds=60
            )
        assert isinstance(limiter, InMemoryLoginRateLimiter)

    def test_redis_success_returns_redis_limiter(self):
        with patch("file_organizer.api.auth_rate_limit.Redis") as mock_redis_cls:
            mock_client = MagicMock()
            mock_client.ping.return_value = True
            mock_redis_cls.from_url.return_value = mock_client
            limiter = build_login_rate_limiter(
                "redis://localhost:6379", max_attempts=5, window_seconds=60
            )
        assert isinstance(limiter, RedisLoginRateLimiter)
        assert limiter.max_attempts == 5
        assert limiter.window_seconds == 60
