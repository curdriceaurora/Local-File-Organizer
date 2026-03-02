"""Tests for file_organizer.api.auth_store module."""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from file_organizer.api.auth_store import (
    InMemoryTokenStore,
    build_token_store,
)

# ---------------------------------------------------------------------------
# InMemoryTokenStore
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestInMemoryTokenStore:
    """Tests for InMemoryTokenStore."""

    def test_store_and_check_refresh(self) -> None:
        store = InMemoryTokenStore()
        store.store_refresh("jti-1", "user-1", ttl_seconds=300)
        assert store.is_refresh_active("jti-1") is True

    def test_unknown_refresh_not_active(self) -> None:
        store = InMemoryTokenStore()
        assert store.is_refresh_active("nonexistent") is False

    def test_revoke_refresh(self) -> None:
        store = InMemoryTokenStore()
        store.store_refresh("jti-1", "user-1", ttl_seconds=300)
        store.revoke_refresh("jti-1")
        assert store.is_refresh_active("jti-1") is False

    def test_revoke_refresh_nonexistent_is_noop(self) -> None:
        store = InMemoryTokenStore()
        store.revoke_refresh("nonexistent")  # should not raise

    def test_revoke_access(self) -> None:
        store = InMemoryTokenStore()
        store.revoke_access("access-jti-1", ttl_seconds=300)
        assert store.is_access_revoked("access-jti-1") is True

    def test_access_not_revoked_by_default(self) -> None:
        store = InMemoryTokenStore()
        assert store.is_access_revoked("access-jti-1") is False

    def test_refresh_expiry_cleanup(self) -> None:
        store = InMemoryTokenStore()
        store.store_refresh("jti-1", "user-1", ttl_seconds=1)
        # Manipulate internal state to simulate TTL expiry (no public API for this)
        store._refresh["jti-1"] = time.time() - 1
        assert store.is_refresh_active("jti-1") is False

    def test_revoked_access_expiry_cleanup(self) -> None:
        store = InMemoryTokenStore()
        store.revoke_access("access-jti-1", ttl_seconds=1)
        # Manipulate internal state to simulate TTL expiry (no public API for this)
        store._revoked["access-jti-1"] = time.time() - 1
        assert store.is_access_revoked("access-jti-1") is False

    def test_multiple_refresh_tokens(self) -> None:
        store = InMemoryTokenStore()
        store.store_refresh("jti-1", "user-1", ttl_seconds=300)
        store.store_refresh("jti-2", "user-1", ttl_seconds=300)
        assert store.is_refresh_active("jti-1") is True
        assert store.is_refresh_active("jti-2") is True
        store.revoke_refresh("jti-1")
        assert store.is_refresh_active("jti-1") is False
        assert store.is_refresh_active("jti-2") is True

    def test_store_refresh_with_zero_ttl_expires_immediately(self) -> None:
        store = InMemoryTokenStore()
        with patch("file_organizer.api.auth_store.time.time", return_value=1_000.0):
            store.store_refresh("jti-1", "user-1", ttl_seconds=0)
        with patch("file_organizer.api.auth_store.time.time", return_value=1_000.0):
            assert store.is_refresh_active("jti-1") is False


# ---------------------------------------------------------------------------
# build_token_store
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBuildTokenStore:
    """Tests for build_token_store factory."""

    def test_returns_in_memory_when_redis_url_is_none(self) -> None:
        store = build_token_store(redis_url=None)
        assert isinstance(store, InMemoryTokenStore)

    def test_returns_in_memory_when_redis_url_is_empty(self) -> None:
        store = build_token_store(redis_url="")
        assert isinstance(store, InMemoryTokenStore)

    def test_in_memory_store_is_functional(self) -> None:
        store = build_token_store(redis_url=None)
        assert isinstance(store, InMemoryTokenStore)
        store.store_refresh("jti-factory", "user-1", ttl_seconds=60)
        assert store.is_refresh_active("jti-factory") is True
