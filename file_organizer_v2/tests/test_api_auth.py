"""API tests for authentication flow."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from jose import jwt

from file_organizer.api.auth_db import create_session
from file_organizer.api.auth_models import User
from file_organizer.api.main import create_app
from file_organizer.api.test_utils import build_test_settings, create_auth_client

pytestmark = pytest.mark.ci


def _register(
    client: TestClient,
    username: str,
    email: str,
    password: str = "T3stP@ssword1!",
) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "username": username,
            "email": email,
            "password": password,
            "full_name": "Test User",
        },
    )
    assert response.status_code == 201


def _login(client: TestClient, username: str, password: str) -> Any:
    return client.post(
        "/api/v1/auth/login",
        data={"username": username, "password": password},
    )


def test_auth_login_refresh_logout(tmp_path: Path) -> None:
    client, headers, tokens = create_auth_client(tmp_path, [])

    me = client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["username"]

    refreshed = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert refreshed.status_code == 200
    refreshed_tokens = refreshed.json()

    logout = client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": refreshed_tokens["refresh_token"]},
        headers={"Authorization": f"Bearer {refreshed_tokens['access_token']}"},
    )
    assert logout.status_code == 204

    rejected = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refreshed_tokens["refresh_token"]},
    )
    assert rejected.status_code == 401


def test_register_rejects_weak_password(tmp_path: Path) -> None:
    settings = build_test_settings(
        tmp_path,
        auth_overrides={"auth_password_min_length": 12},
    )
    app = create_app(settings)
    client = TestClient(app)

    response = client.post(
        "/api/v1/auth/register",
        json={
            "username": "weak-user",
            "email": "weak@example.com",
            "password": "short",
            "full_name": "Weak User",
        },
    )
    assert response.status_code == 400
    assert "Password must be at least" in response.json()["detail"]


def test_register_duplicate_user(tmp_path: Path) -> None:
    settings = build_test_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    _register(client, "dup-user", "dup@example.com")

    duplicate_username = client.post(
        "/api/v1/auth/register",
        json={
            "username": "dup-user",
            "email": "other@example.com",
            "password": "T3stP@ssword1!",
            "full_name": "Dup User",
        },
    )
    assert duplicate_username.status_code == 400

    duplicate_email = client.post(
        "/api/v1/auth/register",
        json={
            "username": "dup-user-2",
            "email": "dup@example.com",
            "password": "T3stP@ssword1!",
            "full_name": "Dup User",
        },
    )
    assert duplicate_email.status_code == 400


def test_login_invalid_credentials(tmp_path: Path) -> None:
    settings = build_test_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    _register(client, "login-user", "login@example.com")
    response = _login(client, "login-user", "wrong-password")
    assert response.status_code == 401


def test_login_rate_limit_blocks_after_failures(tmp_path: Path) -> None:
    settings = build_test_settings(
        tmp_path,
        auth_overrides={
            "auth_login_max_attempts": 2,
            "auth_login_window_seconds": 60,
        },
    )
    app = create_app(settings)
    client = TestClient(app)

    _register(client, "rate-user", "rate@example.com")

    assert _login(client, "rate-user", "wrong-password").status_code == 401
    assert _login(client, "rate-user", "wrong-password").status_code == 401

    blocked = _login(client, "rate-user", "wrong-password")
    assert blocked.status_code == 429


def test_login_inactive_user_rejected(tmp_path: Path) -> None:
    settings = build_test_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    _register(client, "inactive-user", "inactive@example.com")

    session = create_session(settings.auth_db_path)
    try:
        user = session.query(User).filter(User.username == "inactive-user").first()
        assert user is not None
        user.is_active = False
        session.commit()
    finally:
        session.close()

    response = _login(client, "inactive-user", "T3stP@ssword1!")
    assert response.status_code == 400


def test_refresh_rejects_invalid_token(tmp_path: Path) -> None:
    settings = build_test_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    response = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": "not-a-token"},
    )
    assert response.status_code == 401


def test_refresh_rejects_expired_token(tmp_path: Path) -> None:
    settings = build_test_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    now = datetime.now(timezone.utc)
    payload = {
        "sub": "expired-user",
        "user_id": "expired-user-id",
        "type": "refresh",
        "jti": "expired-token",
        "iat": int((now - timedelta(days=2)).timestamp()),
        "exp": int((now - timedelta(days=1)).timestamp()),
    }
    token = jwt.encode(payload, settings.auth_jwt_secret.get_secret_value(), algorithm=settings.auth_jwt_algorithm)

    response = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": token},
    )
    assert response.status_code == 401


def test_logout_rejects_mismatched_refresh_token(tmp_path: Path) -> None:
    settings = build_test_settings(
        tmp_path,
        auth_overrides={
            "auth_bootstrap_admin": True,
            "auth_bootstrap_admin_local_only": False,
        },
    )
    app = create_app(settings)
    client = TestClient(app)

    _register(client, "user-a", "a@example.com")
    _register(client, "user-b", "b@example.com")

    login_a = _login(client, "user-a", "T3stP@ssword1!")
    login_b = _login(client, "user-b", "T3stP@ssword1!")
    assert login_a.status_code == 200
    assert login_b.status_code == 200

    tokens_a = login_a.json()
    tokens_b = login_b.json()

    response = client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": tokens_b["refresh_token"]},
        headers={"Authorization": f"Bearer {tokens_a['access_token']}"},
    )
    assert response.status_code == 401
