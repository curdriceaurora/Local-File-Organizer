"""Helpers for API authentication in tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient

from file_organizer.api.config import ApiSettings
from file_organizer.api.main import create_app


def build_test_settings(
    tmp_path: Path,
    allowed_paths: list[str] | None = None,
    websocket_token: str | None = None,
    auth_overrides: dict[str, Any] | None = None,
) -> ApiSettings:
    """Build ApiSettings configured for testing."""
    data: dict[str, Any] = {
        "environment": "test",
        "enable_docs": False,
        "allowed_paths": allowed_paths or [],
        "websocket_token": websocket_token,
        "auth_enabled": True,
        "auth_db_path": str(tmp_path / "auth.db"),
        "auth_jwt_secret": "test-secret",
        "auth_access_token_minutes": 5,
        "auth_refresh_token_days": 1,
        "auth_redis_url": None,
        "rate_limit_enabled": False,
    }
    if auth_overrides:
        data.update(auth_overrides)
    return ApiSettings(**data)


def create_auth_client(
    tmp_path: Path,
    allowed_paths: list[str] | None = None,
    websocket_token: str | None = None,
    admin: bool = False,
    auth_overrides: dict[str, Any] | None = None,
) -> tuple[TestClient, dict[str, str], dict[str, str]]:
    """Create a TestClient with a registered and logged-in user."""
    overrides = dict(auth_overrides or {})
    if admin:
        overrides.setdefault("auth_bootstrap_admin", True)
        overrides.setdefault("auth_bootstrap_admin_local_only", False)
    settings = build_test_settings(tmp_path, allowed_paths, websocket_token, overrides)
    app = create_app(settings)
    client = TestClient(app)

    # Use a password that satisfies all validators (length>=12, uppercase,
    # digit, special char, not in common-passwords list).
    _TEST_PASSWORD = "T3stP@ssword1!"

    def _register(username: str, email: str) -> None:
        response = client.post(
            "/api/v1/auth/register",
            json={
                "username": username,
                "email": email,
                "password": _TEST_PASSWORD,
                "full_name": "Test User",
            },
        )
        assert response.status_code == 201

    if admin:
        username = f"admin-{uuid4().hex[:6]}"
        _register(username, f"{username}@example.com")
    else:
        username = f"user-{uuid4().hex[:6]}"
        _register(username, f"{username}@example.com")

    login = client.post(
        "/api/v1/auth/login",
        data={"username": username, "password": _TEST_PASSWORD},
    )
    assert login.status_code == 200
    tokens = login.json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    return client, headers, tokens
