"""Tests for token storage (auth_store.py)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from file_organizer.api.auth_store import (
    InMemoryTokenStore,
    RedisTokenStore,
    build_token_store,
)


@pytest.mark.unit
class TestInMemoryTokenStore:
    """Tests for InMemoryTokenStore."""

    def test_refresh_not_active_initially(self):
        store = InMemoryTokenStore()
        assert store.is_refresh_active("jti-1") is False

    def test_store_and_check_refresh(self):
        store = InMemoryTokenStore()
        store.store_refresh("jti-1", "user-1", ttl_seconds=60)
        assert store.is_refresh_active("jti-1") is True

    def test_revoke_refresh_deactivates(self):
        store = InMemoryTokenStore()
        store.store_refresh("jti-1", "user-1", ttl_seconds=60)
        store.revoke_refresh("jti-1")
        assert store.is_refresh_active("jti-1") is False

    def test_access_not_revoked_initially(self):
        store = InMemoryTokenStore()
        assert store.is_access_revoked("jti-1") is False

    def test_revoke_and_check_access(self):
        store = InMemoryTokenStore()
        store.revoke_access("jti-1", ttl_seconds=60)
        assert store.is_access_revoked("jti-1") is True

    def test_expire_all_helper_expires_refresh(self):
        # S-1: use _expire_all helper instead of directly mutating _refresh/_revoked
        store = InMemoryTokenStore()
        store.store_refresh("jti-1", "user-1", ttl_seconds=60)
        assert store.is_refresh_active("jti-1") is True

        store._expire_all()
        assert store.is_refresh_active("jti-1") is False

    def test_expire_all_helper_expires_access_revocation(self):
        # S-1: expired revocation entries should be treated as unrevoked
        store = InMemoryTokenStore()
        store.revoke_access("jti-1", ttl_seconds=60)
        assert store.is_access_revoked("jti-1") is True

        store._expire_all()
        assert store.is_access_revoked("jti-1") is False

    def test_advance_time_helper_expires_refresh(self):
        # S-1: use _advance_time helper to simulate TTL expiry
        store = InMemoryTokenStore()
        store.store_refresh("jti-1", "user-1", ttl_seconds=60)
        store._advance_time(61)
        assert store.is_refresh_active("jti-1") is False

    def test_advance_time_helper_partial_does_not_expire(self):
        store = InMemoryTokenStore()
        store.store_refresh("jti-1", "user-1", ttl_seconds=60)
        store._advance_time(30)
        assert store.is_refresh_active("jti-1") is True

    def test_independent_jtis(self):
        store = InMemoryTokenStore()
        store.store_refresh("jti-1", "user-1", ttl_seconds=60)
        store.store_refresh("jti-2", "user-2", ttl_seconds=60)
        store.revoke_refresh("jti-1")
        assert store.is_refresh_active("jti-1") is False
        assert store.is_refresh_active("jti-2") is True

    def test_revoke_unknown_jti_is_noop(self):
        store = InMemoryTokenStore()
        # Should not raise
        store.revoke_refresh("does-not-exist")

    def test_revoke_access_ttl_zero_is_expired(self):
        store = InMemoryTokenStore()
        store.revoke_access("jti-1", ttl_seconds=0)
        # A TTL of 0 means it expires immediately; treat as unrevoked
        assert store.is_access_revoked("jti-1") is False


@pytest.mark.unit
class TestRedisTokenStore:
    """Tests for RedisTokenStore."""

    def _make_store(self):
        mock_redis = MagicMock()
        store = RedisTokenStore(redis=mock_redis)
        return store, mock_redis

    def test_refresh_key_includes_prefix(self):
        store, _ = self._make_store()
        assert store._refresh_key("abc") == "auth:refresh:abc"

    def test_revoked_key_includes_prefix(self):
        store, _ = self._make_store()
        assert store._revoked_key("abc") == "auth:revoked:abc"

    def test_store_refresh_calls_setex(self):
        store, mock_redis = self._make_store()
        store.store_refresh("jti-1", "user-1", ttl_seconds=3600)
        mock_redis.setex.assert_called_once_with("auth:refresh:jti-1", 3600, "user-1")

    def test_is_refresh_active_when_key_exists(self):
        store, mock_redis = self._make_store()
        mock_redis.exists.return_value = 1
        assert store.is_refresh_active("jti-1") is True

    def test_is_refresh_inactive_when_key_absent(self):
        store, mock_redis = self._make_store()
        mock_redis.exists.return_value = 0
        assert store.is_refresh_active("jti-1") is False

    def test_revoke_refresh_deletes_key(self):
        store, mock_redis = self._make_store()
        store.revoke_refresh("jti-1")
        mock_redis.delete.assert_called_once_with("auth:refresh:jti-1")

    def test_revoke_access_calls_setex(self):
        store, mock_redis = self._make_store()
        store.revoke_access("jti-1", ttl_seconds=300)
        mock_redis.setex.assert_called_once_with("auth:revoked:jti-1", 300, "1")

    def test_is_access_revoked_when_key_exists(self):
        store, mock_redis = self._make_store()
        mock_redis.exists.return_value = 1
        assert store.is_access_revoked("jti-1") is True

    def test_is_access_not_revoked_when_key_absent(self):
        store, mock_redis = self._make_store()
        mock_redis.exists.return_value = 0
        assert store.is_access_revoked("jti-1") is False

    def test_custom_prefixes(self):
        mock_redis = MagicMock()
        store = RedisTokenStore(
            redis=mock_redis,
            refresh_prefix="r:",
            revoked_prefix="v:",
        )
        assert store._refresh_key("x") == "r:x"
        assert store._revoked_key("x") == "v:x"


@pytest.mark.unit
class TestBuildTokenStore:
    """Tests for build_token_store."""

    def test_no_url_returns_in_memory(self):
        store = build_token_store(None)
        assert isinstance(store, InMemoryTokenStore)

    def test_empty_url_returns_in_memory(self):
        store = build_token_store("")
        assert isinstance(store, InMemoryTokenStore)

    def test_redis_failure_falls_back_to_in_memory(self):
        with patch("file_organizer.api.auth_store.Redis") as mock_redis_cls:
            mock_client = MagicMock()
            mock_client.ping.side_effect = ConnectionError("refused")
            mock_redis_cls.from_url.return_value = mock_client
            store = build_token_store("redis://localhost:6379")
        assert isinstance(store, InMemoryTokenStore)

    def test_redis_success_returns_redis_store(self):
        with patch("file_organizer.api.auth_store.Redis") as mock_redis_cls:
            mock_client = MagicMock()
            mock_client.ping.return_value = True
            mock_redis_cls.from_url.return_value = mock_client
            store = build_token_store("redis://localhost:6379")
        assert isinstance(store, RedisTokenStore)
