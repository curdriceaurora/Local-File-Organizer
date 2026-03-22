"""Integration tests for api/cache.py, api/api_keys.py, and api/auth_rate_limit.py.

Covers: InMemoryCache (get/set/delete/close/expiry), build_cache_backend
(no url → in-memory, invalid scheme → in-memory, bad redis → in-memory),
generate_api_key, hash_api_key, verify_api_key, match_api_key_hash,
api_key_identifier, InMemoryLoginRateLimiter (is_blocked/record_failure/reset),
build_login_rate_limiter (no redis → in-memory, bad url → in-memory).
"""

from __future__ import annotations

import time

import pytest

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# InMemoryCache
# ---------------------------------------------------------------------------


class TestInMemoryCache:
    def test_get_missing_key_returns_none(self) -> None:
        from file_organizer.api.cache import InMemoryCache

        cache = InMemoryCache()
        assert cache.get("nonexistent") is None

    def test_set_and_get_returns_value(self) -> None:
        from file_organizer.api.cache import InMemoryCache

        cache = InMemoryCache()
        cache.set("k1", "hello", ttl_seconds=60)
        assert cache.get("k1") == "hello"

    def test_expired_entry_returns_none(self) -> None:
        from file_organizer.api.cache import InMemoryCache

        cache = InMemoryCache()
        cache.set("k2", "value", ttl_seconds=1)
        cache._entries["k2"].expires_at = time.time() - 1
        assert cache.get("k2") is None

    def test_delete_removes_key(self) -> None:
        from file_organizer.api.cache import InMemoryCache

        cache = InMemoryCache()
        cache.set("k3", "data", ttl_seconds=60)
        cache.delete("k3")
        assert cache.get("k3") is None

    def test_delete_missing_key_no_error(self) -> None:
        from file_organizer.api.cache import InMemoryCache

        cache = InMemoryCache()
        cache.delete("ghost")  # should not raise

    def test_close_clears_all_entries(self) -> None:
        from file_organizer.api.cache import InMemoryCache

        cache = InMemoryCache()
        cache.set("a", "1", ttl_seconds=60)
        cache.set("b", "2", ttl_seconds=60)
        cache.close()
        assert cache.get("a") is None
        assert cache.get("b") is None

    def test_overwrite_updates_value(self) -> None:
        from file_organizer.api.cache import InMemoryCache

        cache = InMemoryCache()
        cache.set("key", "v1", ttl_seconds=60)
        cache.set("key", "v2", ttl_seconds=60)
        assert cache.get("key") == "v2"

    def test_ttl_minimum_one_second(self) -> None:
        from file_organizer.api.cache import InMemoryCache

        cache = InMemoryCache()
        cache.set("k4", "val", ttl_seconds=0)
        assert cache.get("k4") == "val"


# ---------------------------------------------------------------------------
# build_cache_backend
# ---------------------------------------------------------------------------


class TestBuildCacheBackend:
    def test_no_url_returns_in_memory(self) -> None:
        from file_organizer.api.cache import InMemoryCache, build_cache_backend

        backend = build_cache_backend(None)
        assert isinstance(backend, InMemoryCache)
        backend.set("k", "v", ttl_seconds=60)
        assert backend.get("k") == "v"

    def test_empty_url_returns_in_memory(self) -> None:
        from file_organizer.api.cache import InMemoryCache, build_cache_backend

        backend = build_cache_backend("")
        assert isinstance(backend, InMemoryCache)
        backend.set("k", "v", ttl_seconds=60)
        assert backend.get("k") == "v"

    def test_invalid_scheme_returns_in_memory(self) -> None:
        from file_organizer.api.cache import InMemoryCache, build_cache_backend

        backend = build_cache_backend("http://localhost:6379")
        assert isinstance(backend, InMemoryCache)
        backend.set("k", "v", ttl_seconds=60)
        assert backend.get("k") == "v"

    def test_bad_redis_url_returns_a_cache_backend(self) -> None:
        from file_organizer.api.cache import build_cache_backend

        backend = build_cache_backend("redis://unreachable-host-xyz:9999/0")
        assert hasattr(backend, "get") and hasattr(backend, "set")

    def test_is_valid_redis_url_recognizes_valid_schemes(self) -> None:
        from file_organizer.api.cache import _is_valid_redis_url

        assert _is_valid_redis_url("redis://localhost:6379") is True
        assert _is_valid_redis_url("rediss://localhost:6380") is True

    def test_is_valid_redis_url_rejects_invalid_schemes(self) -> None:
        from file_organizer.api.cache import _is_valid_redis_url

        assert _is_valid_redis_url("http://localhost:6379") is False
        assert _is_valid_redis_url("ftp://localhost") is False


# ---------------------------------------------------------------------------
# api_keys
# ---------------------------------------------------------------------------


class TestApiKeys:
    def test_generate_api_key_has_prefix(self) -> None:
        from file_organizer.api.api_keys import generate_api_key

        key = generate_api_key("fo")
        assert key.startswith("fo_")

    def test_generate_api_key_unique(self) -> None:
        from file_organizer.api.api_keys import generate_api_key

        k1 = generate_api_key()
        k2 = generate_api_key()
        assert k1 != k2

    def test_generate_api_key_at_least_three_parts(self) -> None:
        from file_organizer.api.api_keys import generate_api_key

        key = generate_api_key("fo")
        assert len(key.split("_", 2)) == 3

    def test_hash_api_key_returns_string(self) -> None:
        from file_organizer.api.api_keys import hash_api_key

        h = hash_api_key("fo_abc_token123")
        assert isinstance(h, str)
        assert len(h) > 0

    def test_verify_api_key_true_for_valid(self) -> None:
        from file_organizer.api.api_keys import generate_api_key, hash_api_key, verify_api_key

        key = generate_api_key()
        hashed = hash_api_key(key)
        assert verify_api_key(key, [hashed]) is True

    def test_verify_api_key_false_for_wrong_key(self) -> None:
        from file_organizer.api.api_keys import generate_api_key, hash_api_key, verify_api_key

        key = generate_api_key()
        other_key = generate_api_key()
        hashed = hash_api_key(key)
        assert verify_api_key(other_key, [hashed]) is False

    def test_verify_api_key_false_for_empty_hashes(self) -> None:
        from file_organizer.api.api_keys import verify_api_key

        assert verify_api_key("fo_abc_token", []) is False

    def test_match_api_key_hash_returns_matching_hash(self) -> None:
        from file_organizer.api.api_keys import generate_api_key, hash_api_key, match_api_key_hash

        key = generate_api_key()
        hashed = hash_api_key(key)
        result = match_api_key_hash(key, [hashed])
        assert result == hashed

    def test_match_api_key_hash_returns_none_for_no_match(self) -> None:
        from file_organizer.api.api_keys import match_api_key_hash

        assert match_api_key_hash("wrong_key", []) is None

    def test_match_api_key_hash_skips_invalid_hashes(self) -> None:
        from file_organizer.api.api_keys import generate_api_key, hash_api_key, match_api_key_hash

        real_key = generate_api_key("fo")
        valid_hash = hash_api_key(real_key)
        result = match_api_key_hash(
            "fo_abc_token", ["not_a_bcrypt_hash", "also_invalid", valid_hash]
        )
        assert result is None

    def test_api_key_identifier_returns_key_id_part(self) -> None:
        from file_organizer.api.api_keys import api_key_identifier, generate_api_key, hash_api_key

        key = generate_api_key("fo")
        hashed = hash_api_key(key)
        identifier = api_key_identifier(key, [hashed])
        assert identifier is not None
        key_id = key.split("_")[1]
        assert identifier == key_id

    def test_api_key_identifier_returns_none_for_no_match(self) -> None:
        from file_organizer.api.api_keys import api_key_identifier

        assert api_key_identifier("fo_abc_token", []) is None


# ---------------------------------------------------------------------------
# InMemoryLoginRateLimiter
# ---------------------------------------------------------------------------


class TestInMemoryLoginRateLimiter:
    def test_new_key_not_blocked(self) -> None:
        from file_organizer.api.auth_rate_limit import InMemoryLoginRateLimiter

        limiter = InMemoryLoginRateLimiter(max_attempts=5, window_seconds=60)
        blocked, retry_after = limiter.is_blocked("user@example.com")
        assert blocked is False
        assert retry_after == 0

    def test_record_failure_below_limit_not_blocked(self) -> None:
        from file_organizer.api.auth_rate_limit import InMemoryLoginRateLimiter

        limiter = InMemoryLoginRateLimiter(max_attempts=5, window_seconds=60)
        for _ in range(4):
            blocked, _ = limiter.record_failure("user@example.com")
            assert blocked is False

    def test_record_failure_at_limit_blocked(self) -> None:
        from file_organizer.api.auth_rate_limit import InMemoryLoginRateLimiter

        limiter = InMemoryLoginRateLimiter(max_attempts=3, window_seconds=60)
        for _ in range(3):
            limiter.record_failure("user@example.com")
        blocked, _ = limiter.is_blocked("user@example.com")
        assert blocked is True

    def test_reset_clears_state(self) -> None:
        from file_organizer.api.auth_rate_limit import InMemoryLoginRateLimiter

        limiter = InMemoryLoginRateLimiter(max_attempts=2, window_seconds=60)
        limiter.record_failure("user@test.com")
        limiter.record_failure("user@test.com")
        limiter.reset("user@test.com")
        blocked, _ = limiter.is_blocked("user@test.com")
        assert blocked is False

    def test_expired_window_resets_count(self) -> None:
        from file_organizer.api.auth_rate_limit import InMemoryLoginRateLimiter

        limiter = InMemoryLoginRateLimiter(max_attempts=2, window_seconds=1)
        limiter.record_failure("u@e.com")
        limiter.record_failure("u@e.com")
        limiter._state["u@e.com"].expires_at = time.time() - 1
        blocked, _ = limiter.is_blocked("u@e.com")
        assert blocked is False

    def test_retry_after_is_positive_when_blocked(self) -> None:
        from file_organizer.api.auth_rate_limit import InMemoryLoginRateLimiter

        limiter = InMemoryLoginRateLimiter(max_attempts=1, window_seconds=30)
        blocked, retry_after = limiter.record_failure("user@x.com")
        assert blocked is True
        assert retry_after > 0

    def test_reset_missing_key_no_error(self) -> None:
        from file_organizer.api.auth_rate_limit import InMemoryLoginRateLimiter

        limiter = InMemoryLoginRateLimiter(max_attempts=5, window_seconds=60)
        limiter.reset("ghost@example.com")  # should not raise

    def test_remaining_returns_nonnegative(self) -> None:
        from file_organizer.api.auth_rate_limit import RateLimitState

        state = RateLimitState(count=1, expires_at=time.time() + 10)
        assert state.remaining(time.time()) > 0

    def test_remaining_zero_when_expired(self) -> None:
        from file_organizer.api.auth_rate_limit import RateLimitState

        state = RateLimitState(count=1, expires_at=time.time() - 5)
        assert state.remaining(time.time()) == 0


# ---------------------------------------------------------------------------
# build_login_rate_limiter
# ---------------------------------------------------------------------------


class TestBuildLoginRateLimiter:
    def test_no_redis_url_returns_in_memory(self) -> None:
        from file_organizer.api.auth_rate_limit import (
            InMemoryLoginRateLimiter,
            build_login_rate_limiter,
        )

        limiter = build_login_rate_limiter(None, max_attempts=5, window_seconds=60)
        assert isinstance(limiter, InMemoryLoginRateLimiter)
        blocked, _ = limiter.is_blocked("u@x.com")
        assert blocked is False

    def test_bad_redis_url_falls_back_to_in_memory(self) -> None:
        from file_organizer.api.auth_rate_limit import (
            InMemoryLoginRateLimiter,
            build_login_rate_limiter,
        )

        limiter = build_login_rate_limiter(
            "redis://unreachable:9999", max_attempts=5, window_seconds=60
        )
        assert isinstance(limiter, InMemoryLoginRateLimiter)
        blocked, _ = limiter.is_blocked("u@x.com")
        assert blocked is False
