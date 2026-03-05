"""Coverage tests for file_organizer.api.auth_store — uncovered branches."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from file_organizer.api.auth_store import (
    InMemoryTokenStore,
    RedisTokenStore,
    build_token_store,
)

pytestmark = pytest.mark.unit


class TestInMemoryTokenStore:
    """Covers expired token cleanup and edge cases."""

    def test_store_and_check_refresh(self) -> None:
        store = InMemoryTokenStore()
        store.store_refresh("jti1", "user1", 3600)
        assert store.is_refresh_active("jti1")

    def test_refresh_not_stored(self) -> None:
        store = InMemoryTokenStore()
        assert not store.is_refresh_active("nonexistent")

    def test_refresh_expired(self) -> None:
        store = InMemoryTokenStore()
        store._refresh["jti1"] = 0.0  # already expired
        assert not store.is_refresh_active("jti1")
        # Should clean up
        assert "jti1" not in store._refresh

    def test_revoke_refresh(self) -> None:
        store = InMemoryTokenStore()
        store.store_refresh("jti1", "user1", 3600)
        store.revoke_refresh("jti1")
        assert not store.is_refresh_active("jti1")

    def test_revoke_access_and_check(self) -> None:
        store = InMemoryTokenStore()
        store.revoke_access("jti_a", 3600)
        assert store.is_access_revoked("jti_a")

    def test_access_not_revoked(self) -> None:
        store = InMemoryTokenStore()
        assert not store.is_access_revoked("nonexistent")

    def test_access_expired_cleanup(self) -> None:
        store = InMemoryTokenStore()
        store._revoked["jti_a"] = 0.0  # expired
        assert not store.is_access_revoked("jti_a")
        assert "jti_a" not in store._revoked


class TestRedisTokenStore:
    """Covers Redis token store methods."""

    def test_store_refresh(self) -> None:
        mock_redis = MagicMock()
        store = RedisTokenStore(redis=mock_redis)
        store.store_refresh("jti1", "user1", 3600)
        mock_redis.setex.assert_called_once()

    def test_is_refresh_active(self) -> None:
        mock_redis = MagicMock()
        mock_redis.exists.return_value = 1
        store = RedisTokenStore(redis=mock_redis)
        assert store.is_refresh_active("jti1")

    def test_is_refresh_not_active(self) -> None:
        mock_redis = MagicMock()
        mock_redis.exists.return_value = 0
        store = RedisTokenStore(redis=mock_redis)
        assert not store.is_refresh_active("jti1")

    def test_revoke_refresh(self) -> None:
        mock_redis = MagicMock()
        store = RedisTokenStore(redis=mock_redis)
        store.revoke_refresh("jti1")
        mock_redis.delete.assert_called_once()

    def test_revoke_access(self) -> None:
        mock_redis = MagicMock()
        store = RedisTokenStore(redis=mock_redis)
        store.revoke_access("jti_a", 300)
        mock_redis.setex.assert_called_once()

    def test_is_access_revoked(self) -> None:
        mock_redis = MagicMock()
        mock_redis.exists.return_value = 1
        store = RedisTokenStore(redis=mock_redis)
        assert store.is_access_revoked("jti_a")

    def test_is_access_not_revoked(self) -> None:
        mock_redis = MagicMock()
        mock_redis.exists.return_value = 0
        store = RedisTokenStore(redis=mock_redis)
        assert not store.is_access_revoked("jti_a")


class TestBuildTokenStore:
    """Covers build_token_store."""

    def test_no_redis_url(self) -> None:
        store = build_token_store(None)
        assert isinstance(store, InMemoryTokenStore)

    def test_redis_unavailable(self) -> None:
        with patch(
            "file_organizer.api.auth_store.Redis.from_url",
            side_effect=ConnectionError("refused"),
        ):
            store = build_token_store("redis://localhost:6379")
        assert isinstance(store, InMemoryTokenStore)

    def test_redis_available(self) -> None:
        mock_client = MagicMock()
        mock_client.ping.return_value = True

        with patch(
            "file_organizer.api.auth_store.Redis.from_url",
            return_value=mock_client,
        ):
            store = build_token_store("redis://localhost:6379")
        assert isinstance(store, RedisTokenStore)
