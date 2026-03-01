"""Tests for API dependency providers (dependencies.py)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from file_organizer.api.dependencies import (
    AnonymousUser,
    ApiKeyIdentity,
    get_login_rate_limiter,
    get_token_store,
)
from file_organizer.api.test_utils import build_test_settings, create_auth_client


@pytest.mark.unit
class TestAnonymousUser:
    """Tests for AnonymousUser dataclass."""

    def test_defaults(self):
        user = AnonymousUser()
        assert user.id == "anonymous"
        assert user.username == "anonymous"
        assert user.is_active is True
        assert user.is_admin is True

    def test_immutable(self):
        user = AnonymousUser()
        with pytest.raises(AttributeError):
            user.id = "other"  # type: ignore[misc]


@pytest.mark.unit
class TestApiKeyIdentity:
    """Tests for ApiKeyIdentity dataclass."""

    def test_defaults(self):
        identity = ApiKeyIdentity(id="key:abc", username="api-key-abc")
        assert identity.is_active is True
        assert identity.is_admin is False
        assert identity.auth_type == "api_key"

    def test_immutable(self):
        identity = ApiKeyIdentity(id="key:abc", username="api-key-abc")
        with pytest.raises(AttributeError):
            identity.id = "other"  # type: ignore[misc]


@pytest.mark.unit
class TestGetCurrentUser:
    """Tests for get_current_user dependency."""

    def test_returns_anonymous_when_auth_disabled(self, tmp_path):
        settings = build_test_settings(tmp_path, auth_overrides={"auth_enabled": False})
        from file_organizer.api.main import create_app
        app = create_app(settings)
        client = TestClient(app)
        response = client.get("/api/v1/auth/me")
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "anonymous"

    def test_rejects_missing_token_when_auth_enabled(self, tmp_path):
        settings = build_test_settings(tmp_path)
        from file_organizer.api.main import create_app
        app = create_app(settings)
        client = TestClient(app)
        response = client.get("/api/v1/auth/me")
        assert response.status_code == 401

    def test_accepts_valid_token(self, tmp_path):
        client, headers, _ = create_auth_client(tmp_path)
        response = client.get("/api/v1/auth/me", headers=headers)
        assert response.status_code == 200

    def test_rejects_tampered_token(self, tmp_path):
        client, _, _ = create_auth_client(tmp_path)
        response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer tampered.token.value"},
        )
        assert response.status_code == 401

    def test_rejects_missing_user_in_db(self, tmp_path):
        """get_current_user queries db for the user after decoding the token.

        Mock target: dependencies.py line 168 --
            user = db.query(User).filter(User.id == user_id).first()

        S-2: The mock chain below mirrors the exact ORM call pattern at that line.
        If the query expression changes, this test will fail with a TypeError or
        return a MagicMock instead of None, making the breakage obvious.
        """
        settings = build_test_settings(tmp_path)
        from file_organizer.api.auth import create_token_bundle

        token_bundle = create_token_bundle("nonexistent-id", "ghost", settings)

        from file_organizer.api.main import create_app
        app = create_app(settings)
        client = TestClient(app)

        with patch("file_organizer.api.dependencies.create_session") as mock_session_factory:
            db = MagicMock()
            mock_session_factory.return_value = db
            # S-2: chain mirrors db.query(User).filter(User.id == user_id).first()
            db.query.return_value.filter.return_value.first.return_value = None
            response = client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {token_bundle.access_token}"},
            )

        assert response.status_code == 401

    def test_api_key_auth_returns_key_identity(self, tmp_path):
        from file_organizer.api.api_keys import hash_api_key
        raw_key = "test-api-key-value"
        key_hash = hash_api_key(raw_key)
        settings = build_test_settings(
            tmp_path,
            auth_overrides={
                "api_key_enabled": True,
                "api_key_hashes": [key_hash],
                "auth_enabled": True,
            },
        )
        from file_organizer.api.main import create_app
        app = create_app(settings)
        client = TestClient(app)
        response = client.get(
            "/api/v1/auth/me",
            headers={settings.api_key_header: raw_key},
        )
        assert response.status_code == 200
        data = response.json()
        assert "api-key" in data["username"]


@pytest.mark.unit
class TestGetTokenStore:
    """Tests for get_token_store dependency."""

    def test_returns_in_memory_store_by_default(self, tmp_path):
        from file_organizer.api.auth_store import InMemoryTokenStore
        settings = build_test_settings(tmp_path)
        store = get_token_store(settings)
        assert isinstance(store, InMemoryTokenStore)


@pytest.mark.unit
class TestGetLoginRateLimiter:
    """Tests for get_login_rate_limiter dependency."""

    def test_returns_in_memory_limiter_by_default(self, tmp_path):
        from file_organizer.api.auth_rate_limit import InMemoryLoginRateLimiter
        settings = build_test_settings(tmp_path)
        limiter = get_login_rate_limiter(settings)
        assert isinstance(limiter, InMemoryLoginRateLimiter)

    def test_respects_max_attempts_setting(self, tmp_path):
        from file_organizer.api.auth_rate_limit import InMemoryLoginRateLimiter
        settings = build_test_settings(
            tmp_path, auth_overrides={"auth_login_max_attempts": 7}
        )
        limiter = get_login_rate_limiter(settings)
        assert isinstance(limiter, InMemoryLoginRateLimiter)
        assert limiter.max_attempts == 7
