"""Tests for file_organizer.api.auth_rate_limit module."""

from __future__ import annotations

import time

from file_organizer.api.auth_rate_limit import (
    InMemoryLoginRateLimiter,
    RateLimitState,
    build_login_rate_limiter,
)

# ---------------------------------------------------------------------------
# RateLimitState
# ---------------------------------------------------------------------------


class TestRateLimitState:
    """Tests for RateLimitState.remaining."""

    def test_remaining_positive(self) -> None:
        now = time.time()
        state = RateLimitState(count=1, expires_at=now + 30)
        assert state.remaining(now) == 30

    def test_remaining_zero_when_expired(self) -> None:
        now = time.time()
        state = RateLimitState(count=1, expires_at=now - 10)
        assert state.remaining(now) == 0

    def test_remaining_zero_at_exact_expiry(self) -> None:
        now = time.time()
        state = RateLimitState(count=1, expires_at=now)
        assert state.remaining(now) == 0

    def test_remaining_truncates_to_int(self) -> None:
        now = 1000.0
        state = RateLimitState(count=1, expires_at=1010.9)
        assert state.remaining(now) == 10


# ---------------------------------------------------------------------------
# InMemoryLoginRateLimiter
# ---------------------------------------------------------------------------


class TestInMemoryLoginRateLimiter:
    """Tests for InMemoryLoginRateLimiter."""

    def test_new_key_not_blocked(self) -> None:
        limiter = InMemoryLoginRateLimiter(max_attempts=3, window_seconds=60)
        blocked, retry = limiter.is_blocked("user1")
        assert blocked is False
        assert retry == 0

    def test_record_failure_increments(self) -> None:
        limiter = InMemoryLoginRateLimiter(max_attempts=3, window_seconds=60)
        blocked, _ = limiter.record_failure("user1")
        assert blocked is False
        blocked, _ = limiter.record_failure("user1")
        assert blocked is False

    def test_blocked_at_max_attempts(self) -> None:
        limiter = InMemoryLoginRateLimiter(max_attempts=3, window_seconds=60)
        limiter.record_failure("user1")
        limiter.record_failure("user1")
        blocked, retry = limiter.record_failure("user1")
        assert blocked is True
        assert retry > 0

    def test_is_blocked_after_reaching_max(self) -> None:
        limiter = InMemoryLoginRateLimiter(max_attempts=2, window_seconds=60)
        limiter.record_failure("user1")
        limiter.record_failure("user1")
        blocked, retry = limiter.is_blocked("user1")
        assert blocked is True
        assert retry > 0

    def test_reset_clears_state(self) -> None:
        limiter = InMemoryLoginRateLimiter(max_attempts=2, window_seconds=60)
        limiter.record_failure("user1")
        limiter.record_failure("user1")
        limiter.reset("user1")
        blocked, retry = limiter.is_blocked("user1")
        assert blocked is False
        assert retry == 0

    def test_reset_nonexistent_key_is_noop(self) -> None:
        limiter = InMemoryLoginRateLimiter(max_attempts=3, window_seconds=60)
        limiter.reset("nonexistent")  # should not raise

    def test_window_expiry_cleanup(self) -> None:
        limiter = InMemoryLoginRateLimiter(max_attempts=2, window_seconds=60)
        limiter.record_failure("user1")
        limiter.record_failure("user1")
        # Manipulate internal state to simulate window expiry (no public API for this)
        state = limiter._state["user1"]
        state.expires_at = time.time() - 1
        blocked, retry = limiter.is_blocked("user1")
        assert blocked is False
        assert retry == 0

    def test_different_keys_independent(self) -> None:
        limiter = InMemoryLoginRateLimiter(max_attempts=2, window_seconds=60)
        limiter.record_failure("user1")
        limiter.record_failure("user1")
        blocked_u1, _ = limiter.is_blocked("user1")
        blocked_u2, _ = limiter.is_blocked("user2")
        assert blocked_u1 is True
        assert blocked_u2 is False


# ---------------------------------------------------------------------------
# build_login_rate_limiter
# ---------------------------------------------------------------------------


class TestBuildLoginRateLimiter:
    """Tests for build_login_rate_limiter factory."""

    def test_returns_in_memory_when_redis_url_is_none(self) -> None:
        limiter = build_login_rate_limiter(
            redis_url=None, max_attempts=5, window_seconds=300
        )
        assert isinstance(limiter, InMemoryLoginRateLimiter)

    def test_returns_in_memory_when_redis_url_is_empty(self) -> None:
        limiter = build_login_rate_limiter(
            redis_url="", max_attempts=5, window_seconds=300
        )
        assert isinstance(limiter, InMemoryLoginRateLimiter)

    def test_in_memory_limiter_has_correct_config(self) -> None:
        limiter = build_login_rate_limiter(
            redis_url=None, max_attempts=10, window_seconds=120
        )
        assert isinstance(limiter, InMemoryLoginRateLimiter)
        assert limiter.max_attempts == 10
        assert limiter.window_seconds == 120
