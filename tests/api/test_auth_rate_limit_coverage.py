"""Coverage tests for file_organizer.api.auth_rate_limit — uncovered branches."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from file_organizer.api.auth_rate_limit import (
    InMemoryLoginRateLimiter,
    RateLimitState,
    RedisLoginRateLimiter,
    build_login_rate_limiter,
)

pytestmark = pytest.mark.unit


class TestRateLimitState:
    """Covers RateLimitState.remaining."""

    def test_remaining_positive(self) -> None:
        state = RateLimitState(count=3, expires_at=1000.0)
        assert state.remaining(990.0) == 10

    def test_remaining_zero(self) -> None:
        state = RateLimitState(count=3, expires_at=1000.0)
        assert state.remaining(1005.0) == 0


class TestInMemoryLoginRateLimiter:
    """Covers in-memory limiter edge cases."""

    def test_is_blocked_expired_window(self) -> None:
        """When window has expired, state should be cleaned up."""
        limiter = InMemoryLoginRateLimiter(max_attempts=3, window_seconds=60)
        # Inject expired state
        limiter._state["key1"] = RateLimitState(count=5, expires_at=0.0)
        blocked, retry = limiter.is_blocked("key1")
        assert not blocked
        assert retry == 0

    def test_record_failure_creates_new_window(self) -> None:
        limiter = InMemoryLoginRateLimiter(max_attempts=3, window_seconds=60)
        blocked, retry = limiter.record_failure("key1")
        assert not blocked  # count=1, need 3

    def test_record_failure_increments_existing(self) -> None:
        limiter = InMemoryLoginRateLimiter(max_attempts=2, window_seconds=60)
        limiter.record_failure("key1")
        blocked, retry = limiter.record_failure("key1")
        assert blocked
        assert retry > 0

    def test_reset_clears_state(self) -> None:
        limiter = InMemoryLoginRateLimiter(max_attempts=3, window_seconds=60)
        limiter.record_failure("key1")
        limiter.reset("key1")
        blocked, _ = limiter.is_blocked("key1")
        assert not blocked

    def test_is_blocked_under_limit(self) -> None:
        limiter = InMemoryLoginRateLimiter(max_attempts=5, window_seconds=60)
        limiter.record_failure("key1")
        blocked, retry = limiter.is_blocked("key1")
        assert not blocked
        assert retry == 0


class TestRedisLoginRateLimiter:
    """Covers Redis limiter methods."""

    def test_is_blocked_no_value(self) -> None:
        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        limiter = RedisLoginRateLimiter(redis=mock_redis, max_attempts=3, window_seconds=60)
        blocked, retry = limiter.is_blocked("key1")
        assert not blocked

    def test_is_blocked_invalid_value(self) -> None:
        mock_redis = MagicMock()
        mock_redis.get.return_value = "not_a_number"
        limiter = RedisLoginRateLimiter(redis=mock_redis, max_attempts=3, window_seconds=60)
        blocked, retry = limiter.is_blocked("key1")
        assert not blocked
        mock_redis.delete.assert_called_once()

    def test_is_blocked_under_limit(self) -> None:
        mock_redis = MagicMock()
        mock_redis.get.return_value = "1"
        mock_redis.ttl.return_value = 30
        limiter = RedisLoginRateLimiter(redis=mock_redis, max_attempts=3, window_seconds=60)
        blocked, retry = limiter.is_blocked("key1")
        assert not blocked

    def test_is_blocked_at_limit(self) -> None:
        mock_redis = MagicMock()
        mock_redis.get.return_value = "3"
        mock_redis.ttl.return_value = 45
        limiter = RedisLoginRateLimiter(redis=mock_redis, max_attempts=3, window_seconds=60)
        blocked, retry = limiter.is_blocked("key1")
        assert blocked
        assert retry == 45

    def test_record_failure_new_key(self) -> None:
        mock_redis = MagicMock()
        mock_pipe = MagicMock()
        mock_pipe.execute.return_value = [1, -1]
        mock_redis.pipeline.return_value = mock_pipe
        limiter = RedisLoginRateLimiter(redis=mock_redis, max_attempts=3, window_seconds=60)
        blocked, retry = limiter.record_failure("key1")
        assert not blocked
        mock_redis.expire.assert_called_once()

    def test_record_failure_existing_key(self) -> None:
        mock_redis = MagicMock()
        mock_pipe = MagicMock()
        mock_pipe.execute.return_value = [3, 30]
        mock_redis.pipeline.return_value = mock_pipe
        limiter = RedisLoginRateLimiter(redis=mock_redis, max_attempts=3, window_seconds=60)
        blocked, retry = limiter.record_failure("key1")
        assert blocked
        assert retry == 30

    def test_reset(self) -> None:
        mock_redis = MagicMock()
        limiter = RedisLoginRateLimiter(redis=mock_redis, max_attempts=3, window_seconds=60)
        limiter.reset("key1")
        mock_redis.delete.assert_called_once()

    def test_ttl_negative(self) -> None:
        mock_redis = MagicMock()
        mock_redis.ttl.return_value = -1
        limiter = RedisLoginRateLimiter(redis=mock_redis, max_attempts=3, window_seconds=60)
        assert limiter._ttl("any_key") == 60

    def test_ttl_none(self) -> None:
        mock_redis = MagicMock()
        mock_redis.ttl.return_value = None
        limiter = RedisLoginRateLimiter(redis=mock_redis, max_attempts=3, window_seconds=60)
        assert limiter._ttl("any_key") == 60


class TestBuildLoginRateLimiter:
    """Covers build_login_rate_limiter."""

    def test_no_redis_url(self) -> None:
        limiter = build_login_rate_limiter(None, max_attempts=5, window_seconds=300)
        assert isinstance(limiter, InMemoryLoginRateLimiter)

    def test_redis_unavailable(self) -> None:
        with patch(
            "file_organizer.api.auth_rate_limit.Redis.from_url",
            side_effect=ConnectionError("refused"),
        ):
            limiter = build_login_rate_limiter(
                "redis://localhost:6379", max_attempts=5, window_seconds=300
            )
        assert isinstance(limiter, InMemoryLoginRateLimiter)

    def test_redis_available(self) -> None:
        mock_client = MagicMock()
        mock_client.ping.return_value = True

        with patch(
            "file_organizer.api.auth_rate_limit.Redis.from_url",
            return_value=mock_client,
        ):
            limiter = build_login_rate_limiter(
                "redis://localhost:6379", max_attempts=5, window_seconds=300
            )
        assert isinstance(limiter, RedisLoginRateLimiter)
