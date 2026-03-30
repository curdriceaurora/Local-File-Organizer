"""Tests for API dependency providers (auth, user resolution)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from file_organizer.api.api_keys import generate_api_key, hash_api_key
from file_organizer.api.auth import create_token_bundle
from file_organizer.api.auth_models import User
from file_organizer.api.auth_store import InMemoryTokenStore
from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import (
    AnonymousUser,
    ApiKeyIdentity,
    get_current_active_user,
    get_current_user,
    require_admin_user,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_settings(**overrides: Any) -> ApiSettings:
    """Create an ApiSettings with test-friendly defaults."""
    defaults: dict[str, Any] = {
        "environment": "test",
    }
    defaults.update(overrides)
    return ApiSettings(**defaults)


def _mock_request(headers: dict[str, str] | None = None) -> MagicMock:
    """Build a mock Request with the given headers."""
    req = MagicMock()
    req.headers = headers or {}
    req.state = MagicMock(spec=[])
    return req


def _mock_db(user: User | None = None) -> MagicMock:
    """Build a mock db session that returns user from .query().filter().first()."""
    db = MagicMock()
    # Mirrors the ORM call chain in dependencies.py:168 —
    # db.query(User).filter(User.id == user_id).first()
    db.query.return_value.filter.return_value.first.return_value = user
    return db


def _make_user(
    *,
    user_id: str = "user-1",
    username: str = "testuser",
    is_active: bool = True,
    is_admin: bool = False,
) -> User:
    """Create a User ORM object with the given attributes."""
    user = User()
    user.id = user_id
    user.username = username
    user.email = f"{username}@example.com"
    user.hashed_password = "hashed"
    user.is_active = is_active
    user.is_admin = is_admin
    return user


# ---------------------------------------------------------------------------
# AnonymousUser tests
# ---------------------------------------------------------------------------


class TestAnonymousUser:
    """Tests for the AnonymousUser dataclass."""

    def test_defaults(self) -> None:
        anon = AnonymousUser()
        assert anon.id == "anonymous"
        assert anon.username == "anonymous"
        assert anon.is_active is True
        assert anon.is_admin is False
        assert anon.email == "anonymous@example.com"

    def test_has_expected_attributes(self) -> None:
        anon = AnonymousUser()
        assert hasattr(anon, "id")
        assert hasattr(anon, "username")
        assert hasattr(anon, "is_active")
        assert hasattr(anon, "is_admin")
        assert hasattr(anon, "created_at")


# ---------------------------------------------------------------------------
# ApiKeyIdentity tests
# ---------------------------------------------------------------------------


class TestApiKeyIdentity:
    """Tests for the ApiKeyIdentity dataclass."""

    def test_required_fields(self) -> None:
        identity = ApiKeyIdentity(id="key-1", username="api-key-1")
        assert identity.id == "key-1"
        assert identity.username == "api-key-1"

    def test_defaults(self) -> None:
        identity = ApiKeyIdentity(id="key-1", username="api-key-1")
        assert identity.is_active is True
        assert identity.is_admin is False
        assert identity.auth_type == "api_key"


# ---------------------------------------------------------------------------
# get_current_user tests
# ---------------------------------------------------------------------------


class TestGetCurrentUser:
    """Tests for the get_current_user dependency."""

    def test_auth_disabled_returns_anonymous(self) -> None:
        settings = _make_settings(auth_enabled=False)
        request = _mock_request()
        db = _mock_db()
        store = InMemoryTokenStore()

        result = get_current_user(request, token=None, settings=settings, db=db, token_store=store)

        assert isinstance(result, AnonymousUser)

    def test_no_token_no_api_key_raises_401(self) -> None:
        settings = _make_settings(auth_enabled=True, api_key_enabled=False)
        request = _mock_request()
        db = _mock_db()
        store = InMemoryTokenStore()

        with pytest.raises(HTTPException) as exc_info:
            get_current_user(request, token=None, settings=settings, db=db, token_store=store)

        assert exc_info.value.status_code == 401

    def test_valid_api_key_returns_identity(self) -> None:
        raw_key = generate_api_key()
        key_hash = hash_api_key(raw_key)
        settings = _make_settings(
            auth_enabled=True,
            api_key_enabled=True,
            api_key_hashes=[key_hash],
            api_key_admin=False,
            api_key_header="X-API-Key",
        )
        request = _mock_request(headers={"X-API-Key": raw_key})
        db = _mock_db()
        store = InMemoryTokenStore()

        result = get_current_user(request, token=None, settings=settings, db=db, token_store=store)

        assert isinstance(result, ApiKeyIdentity)
        assert result.id.startswith("api-key:")
        assert result.is_admin is False

    def test_api_key_admin_flag_propagates(self) -> None:
        raw_key = generate_api_key()
        key_hash = hash_api_key(raw_key)
        settings = _make_settings(
            auth_enabled=True,
            api_key_enabled=True,
            api_key_hashes=[key_hash],
            api_key_admin=True,
            api_key_header="X-API-Key",
        )
        request = _mock_request(headers={"X-API-Key": raw_key})
        db = _mock_db()
        store = InMemoryTokenStore()

        result = get_current_user(request, token=None, settings=settings, db=db, token_store=store)

        assert isinstance(result, ApiKeyIdentity)
        assert result.is_admin is True

    def test_invalid_api_key_raises_401(self) -> None:
        settings = _make_settings(
            auth_enabled=True,
            api_key_enabled=True,
            api_key_hashes=[hash_api_key("some-other-key")],
            api_key_header="X-API-Key",
        )
        request = _mock_request(headers={"X-API-Key": "wrong-key"})
        db = _mock_db()
        store = InMemoryTokenStore()

        with pytest.raises(HTTPException) as exc_info:
            get_current_user(request, token=None, settings=settings, db=db, token_store=store)

        assert exc_info.value.status_code == 401

    def test_valid_token_returns_user(self) -> None:
        settings = _make_settings(auth_enabled=True)
        user = _make_user(user_id="user-1", username="testuser")
        bundle = create_token_bundle("user-1", "testuser", settings)
        request = _mock_request()
        db = _mock_db(user=user)
        store = InMemoryTokenStore()

        result = get_current_user(
            request,
            token=bundle.access_token,
            settings=settings,
            db=db,
            token_store=store,
        )

        assert hasattr(result, "id")
        assert result.username == "testuser"

    def test_revoked_access_token_raises_401(self) -> None:
        settings = _make_settings(auth_enabled=True)
        user = _make_user()
        bundle = create_token_bundle("user-1", "testuser", settings)
        request = _mock_request()
        db = _mock_db(user=user)
        store = InMemoryTokenStore()
        store.revoke_access(bundle.access_jti, ttl_seconds=3600)

        with pytest.raises(HTTPException) as exc_info:
            get_current_user(
                request,
                token=bundle.access_token,
                settings=settings,
                db=db,
                token_store=store,
            )

        assert exc_info.value.status_code == 401

    def test_refresh_token_rejected_as_access(self) -> None:
        settings = _make_settings(auth_enabled=True)
        bundle = create_token_bundle("user-1", "testuser", settings)
        request = _mock_request()
        db = _mock_db()
        store = InMemoryTokenStore()

        with pytest.raises(HTTPException) as exc_info:
            get_current_user(
                request,
                token=bundle.refresh_token,
                settings=settings,
                db=db,
                token_store=store,
            )

        assert exc_info.value.status_code == 401

    def test_user_not_in_db_raises_401(self) -> None:
        settings = _make_settings(auth_enabled=True)
        bundle = create_token_bundle("nonexistent", "ghost", settings)
        request = _mock_request()
        db = _mock_db(user=None)
        store = InMemoryTokenStore()

        with pytest.raises(HTTPException) as exc_info:
            get_current_user(
                request,
                token=bundle.access_token,
                settings=settings,
                db=db,
                token_store=store,
            )

        assert exc_info.value.status_code == 401

    def test_invalid_token_raises_401(self) -> None:
        settings = _make_settings(auth_enabled=True)
        request = _mock_request()
        db = _mock_db()
        store = InMemoryTokenStore()

        with pytest.raises(HTTPException) as exc_info:
            get_current_user(
                request,
                token="not.a.valid.jwt",
                settings=settings,
                db=db,
                token_store=store,
            )

        assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# get_current_active_user tests
# ---------------------------------------------------------------------------


class TestGetCurrentActiveUser:
    """Tests for the get_current_active_user dependency."""

    def test_auth_disabled_returns_user_as_is(self) -> None:
        settings = _make_settings(auth_enabled=False)
        user = AnonymousUser()

        result = get_current_active_user(user, settings=settings)

        assert result is user

    def test_inactive_user_raises_400(self) -> None:
        settings = _make_settings(auth_enabled=True)
        user = _make_user(is_active=False)

        with pytest.raises(HTTPException) as exc_info:
            get_current_active_user(user, settings=settings)

        assert exc_info.value.status_code == 400
        assert "Inactive" in str(exc_info.value.detail)

    def test_active_user_returns_user(self) -> None:
        settings = _make_settings(auth_enabled=True)
        user = _make_user(is_active=True)

        result = get_current_active_user(user, settings=settings)

        assert result is user


# ---------------------------------------------------------------------------
# require_admin_user tests
# ---------------------------------------------------------------------------


class TestRequireAdminUser:
    """Tests for the require_admin_user dependency."""

    def test_auth_disabled_returns_user_as_is(self) -> None:
        settings = _make_settings(auth_enabled=False)
        user = AnonymousUser()

        result = require_admin_user(user, settings=settings)

        assert result is user

    def test_non_admin_raises_403(self) -> None:
        settings = _make_settings(auth_enabled=True)
        user = _make_user(is_admin=False)

        with pytest.raises(HTTPException) as exc_info:
            require_admin_user(user, settings=settings)

        assert exc_info.value.status_code == 403
        assert "Admin" in str(exc_info.value.detail)

    def test_admin_user_returns_user(self) -> None:
        settings = _make_settings(auth_enabled=True)
        user = _make_user(is_admin=True)

        result = require_admin_user(user, settings=settings)

        assert result is user
