"""Integration tests for version, auth rate limiting, and token store.

Covers:
  - version.py                      — VersionInfo, parse_version, bump_version
  - api/auth_rate_limit.py          — InMemoryLoginRateLimiter, build_login_rate_limiter
  - api/auth_store.py               — InMemoryTokenStore, build_token_store
"""

from __future__ import annotations

import pytest

from file_organizer.api.auth_rate_limit import (
    InMemoryLoginRateLimiter,
    RateLimitState,
    build_login_rate_limiter,
)
from file_organizer.api.auth_store import InMemoryTokenStore, build_token_store
from file_organizer.version import (
    VersionInfo,
    bump_version,
    get_version,
    get_version_info,
    parse_version,
)

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# VersionInfo
# ---------------------------------------------------------------------------


class TestVersionInfo:
    def test_str_without_pre_release(self) -> None:
        v = VersionInfo(major=1, minor=2, patch=3)
        assert str(v) == "1.2.3"

    def test_str_with_pre_release(self) -> None:
        v = VersionInfo(major=1, minor=0, patch=0, pre_release="alpha.1")
        assert str(v) == "1.0.0-alpha.1"

    def test_is_pre_release_true(self) -> None:
        v = VersionInfo(1, 0, 0, pre_release="alpha")
        assert v.is_pre_release is True

    def test_is_pre_release_false(self) -> None:
        v = VersionInfo(1, 0, 0)
        assert v.is_pre_release is False

    def test_base_version(self) -> None:
        v = VersionInfo(2, 3, 4, pre_release="beta")
        assert v.base_version == "2.3.4"

    def test_lt_by_major(self) -> None:
        assert VersionInfo(1, 0, 0) < VersionInfo(2, 0, 0)

    def test_lt_by_minor(self) -> None:
        assert VersionInfo(1, 0, 0) < VersionInfo(1, 1, 0)

    def test_lt_by_patch(self) -> None:
        assert VersionInfo(1, 0, 0) < VersionInfo(1, 0, 1)

    def test_pre_release_lt_release(self) -> None:
        assert VersionInfo(1, 0, 0, pre_release="alpha") < VersionInfo(1, 0, 0)

    def test_release_not_lt_release(self) -> None:
        assert not (VersionInfo(1, 0, 0) < VersionInfo(1, 0, 0))

    def test_gt(self) -> None:
        assert VersionInfo(2, 0, 0) > VersionInfo(1, 0, 0)

    def test_le_equal(self) -> None:
        v = VersionInfo(1, 0, 0)
        assert v <= VersionInfo(1, 0, 0)

    def test_le_less(self) -> None:
        assert VersionInfo(1, 0, 0) <= VersionInfo(2, 0, 0)

    def test_ge_equal(self) -> None:
        assert VersionInfo(1, 0, 0) >= VersionInfo(1, 0, 0)

    def test_ge_greater(self) -> None:
        assert VersionInfo(2, 0, 0) >= VersionInfo(1, 0, 0)

    def test_lt_non_version_returns_not_implemented(self) -> None:
        v = VersionInfo(1, 0, 0)
        result = v.__lt__("other")
        assert result is NotImplemented


# ---------------------------------------------------------------------------
# parse_version
# ---------------------------------------------------------------------------


class TestParseVersion:
    def test_simple_version(self) -> None:
        v = parse_version("1.2.3")
        assert v.major == 1
        assert v.minor == 2
        assert v.patch == 3

    def test_pre_release(self) -> None:
        v = parse_version("2.0.0-alpha.1")
        assert v.pre_release == "alpha.1"

    def test_no_pre_release(self) -> None:
        v = parse_version("1.0.0")
        assert v.pre_release is None

    def test_zero_version(self) -> None:
        v = parse_version("0.0.0")
        assert v.major == 0

    def test_invalid_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid"):
            parse_version("not-a-version")

    def test_missing_patch_raises(self) -> None:
        with pytest.raises(ValueError):
            parse_version("1.2")

    def test_strips_whitespace(self) -> None:
        v = parse_version("  1.2.3  ")
        assert v.major == 1


# ---------------------------------------------------------------------------
# get_version / get_version_info
# ---------------------------------------------------------------------------


class TestGetVersion:
    def test_returns_string(self) -> None:
        assert len(get_version()) > 0

    def test_non_empty(self) -> None:
        assert len(get_version()) > 0


class TestGetVersionInfo:
    def test_returns_version_info(self) -> None:
        assert isinstance(get_version_info(), VersionInfo)

    def test_major_is_int(self) -> None:
        info = get_version_info()
        assert info.major >= 0


# ---------------------------------------------------------------------------
# bump_version
# ---------------------------------------------------------------------------


class TestBumpVersion:
    def test_bump_patch(self) -> None:
        assert bump_version("1.2.3", "patch") == "1.2.4"

    def test_bump_minor(self) -> None:
        assert bump_version("1.2.3", "minor") == "1.3.0"

    def test_bump_major(self) -> None:
        assert bump_version("1.2.3", "major") == "2.0.0"

    def test_bump_drops_pre_release(self) -> None:
        result = bump_version("1.0.0-alpha", "patch")
        assert "-" not in result

    def test_invalid_part_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid"):
            bump_version("1.0.0", "build")


# ---------------------------------------------------------------------------
# RateLimitState
# ---------------------------------------------------------------------------


class TestRateLimitState:
    def test_remaining_future_expiry(self) -> None:
        import time

        state = RateLimitState(count=1, expires_at=time.time() + 60)
        remaining = state.remaining(time.time())
        assert remaining > 0

    def test_remaining_expired(self) -> None:
        import time

        state = RateLimitState(count=1, expires_at=time.time() - 1)
        assert state.remaining(time.time()) == 0


# ---------------------------------------------------------------------------
# InMemoryLoginRateLimiter
# ---------------------------------------------------------------------------


class TestInMemoryLoginRateLimiter:
    def test_created(self) -> None:
        limiter = InMemoryLoginRateLimiter(max_attempts=5, window_seconds=60)
        assert limiter is not None

    def test_not_blocked_initially(self) -> None:
        limiter = InMemoryLoginRateLimiter(max_attempts=3, window_seconds=60)
        blocked, _ = limiter.is_blocked("user@example.com")
        assert blocked is False

    def test_record_failure_returns_tuple(self) -> None:
        limiter = InMemoryLoginRateLimiter(max_attempts=5, window_seconds=60)
        result = limiter.record_failure("user@example.com")
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_blocked_after_max_attempts(self) -> None:
        limiter = InMemoryLoginRateLimiter(max_attempts=3, window_seconds=60)
        for _ in range(3):
            limiter.record_failure("user@example.com")
        blocked, _ = limiter.is_blocked("user@example.com")
        assert blocked is True

    def test_not_blocked_before_max_attempts(self) -> None:
        limiter = InMemoryLoginRateLimiter(max_attempts=5, window_seconds=60)
        limiter.record_failure("user@example.com")
        blocked, _ = limiter.is_blocked("user@example.com")
        assert blocked is False

    def test_reset_clears_state(self) -> None:
        limiter = InMemoryLoginRateLimiter(max_attempts=3, window_seconds=60)
        for _ in range(3):
            limiter.record_failure("user@example.com")
        limiter.reset("user@example.com")
        blocked, _ = limiter.is_blocked("user@example.com")
        assert blocked is False

    def test_different_keys_independent(self) -> None:
        limiter = InMemoryLoginRateLimiter(max_attempts=2, window_seconds=60)
        for _ in range(2):
            limiter.record_failure("userA")
        blocked_a, _ = limiter.is_blocked("userA")
        blocked_b, _ = limiter.is_blocked("userB")
        assert blocked_a is True
        assert blocked_b is False

    def test_retry_after_positive_when_blocked(self) -> None:
        limiter = InMemoryLoginRateLimiter(max_attempts=1, window_seconds=30)
        limiter.record_failure("user")
        blocked, retry_after = limiter.is_blocked("user")
        assert blocked is True
        assert retry_after > 0


# ---------------------------------------------------------------------------
# build_login_rate_limiter
# ---------------------------------------------------------------------------


class TestBuildLoginRateLimiter:
    def test_no_redis_url_returns_in_memory(self) -> None:
        limiter = build_login_rate_limiter(None, max_attempts=5, window_seconds=60)
        assert isinstance(limiter, InMemoryLoginRateLimiter)

    def test_empty_redis_url_returns_in_memory(self) -> None:
        limiter = build_login_rate_limiter("", max_attempts=5, window_seconds=60)
        assert isinstance(limiter, InMemoryLoginRateLimiter)

    def test_invalid_redis_url_falls_back_to_in_memory(self) -> None:
        limiter = build_login_rate_limiter(
            "redis://nonexistent-host:9999/0", max_attempts=5, window_seconds=60
        )
        assert isinstance(limiter, InMemoryLoginRateLimiter)


# ---------------------------------------------------------------------------
# InMemoryTokenStore
# ---------------------------------------------------------------------------


class TestInMemoryTokenStore:
    def test_created(self) -> None:
        store = InMemoryTokenStore()
        assert store is not None

    def test_refresh_inactive_initially(self) -> None:
        store = InMemoryTokenStore()
        assert store.is_refresh_active("nonexistent") is False

    def test_store_and_check_refresh(self) -> None:
        store = InMemoryTokenStore()
        store.store_refresh("jti-abc", "user1", ttl_seconds=3600)
        assert store.is_refresh_active("jti-abc") is True

    def test_revoke_refresh(self) -> None:
        store = InMemoryTokenStore()
        store.store_refresh("jti-abc", "user1", ttl_seconds=3600)
        store.revoke_refresh("jti-abc")
        assert store.is_refresh_active("jti-abc") is False

    def test_access_not_revoked_initially(self) -> None:
        store = InMemoryTokenStore()
        assert store.is_access_revoked("jti-xyz") is False

    def test_revoke_access(self) -> None:
        store = InMemoryTokenStore()
        store.revoke_access("jti-xyz", ttl_seconds=3600)
        assert store.is_access_revoked("jti-xyz") is True

    def test_revoke_nonexistent_refresh_noop(self) -> None:
        store = InMemoryTokenStore()
        store.revoke_refresh("nonexistent")

    def test_expired_refresh_returns_false(self) -> None:
        store = InMemoryTokenStore()
        store.store_refresh("jti-expired", "user1", ttl_seconds=-1)
        assert store.is_refresh_active("jti-expired") is False


# ---------------------------------------------------------------------------
# build_token_store
# ---------------------------------------------------------------------------


class TestBuildTokenStore:
    def test_no_redis_url_returns_in_memory(self) -> None:
        store = build_token_store(None)
        assert isinstance(store, InMemoryTokenStore)

    def test_empty_redis_url_returns_in_memory(self) -> None:
        store = build_token_store("")
        assert isinstance(store, InMemoryTokenStore)

    def test_invalid_redis_url_falls_back_to_in_memory(self) -> None:
        store = build_token_store("redis://nonexistent-host:9999/0")
        assert isinstance(store, InMemoryTokenStore)
