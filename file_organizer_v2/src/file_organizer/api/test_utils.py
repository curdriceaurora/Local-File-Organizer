"""Helpers for API authentication in tests."""
from __future__ import annotations

from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi.testclient import TestClient

from file_organizer.api.config import ApiSettings
from file_organizer.api.main import create_app


def build_test_settings(
    tmp_path: Path,
    allowed_paths: Optional[list[str]] = None,
    websocket_token: Optional[str] = None,
) -> ApiSettings:
    return ApiSettings(
        environment="test",
        enable_docs=False,
        allowed_paths=allowed_paths or [],
        websocket_token=websocket_token,
        auth_enabled=True,
        auth_db_path=str(tmp_path / "auth.db"),
        auth_jwt_secret="test-secret",
        auth_access_token_minutes=5,
        auth_refresh_token_days=1,
        auth_redis_url=None,
    )


def create_auth_client(
    tmp_path: Path,
    allowed_paths: Optional[list[str]] = None,
    websocket_token: Optional[str] = None,
    admin: bool = False,
) -> tuple[TestClient, dict[str, str], dict[str, str]]:
    settings = build_test_settings(tmp_path, allowed_paths, websocket_token)
    app = create_app(settings)
    client = TestClient(app)

    def _register(username: str, email: str) -> None:
        response = client.post(
            "/api/v1/auth/register",
            json={
                "username": username,
                "email": email,
                "password": "password123",
                "full_name": "Test User",
            },
        )
        assert response.status_code == 201

    if admin:
        username = f"admin-{uuid4().hex[:6]}"
        _register(username, f"{username}@example.com")
    else:
        admin_name = f"admin-{uuid4().hex[:6]}"
        _register(admin_name, f"{admin_name}@example.com")
        username = f"user-{uuid4().hex[:6]}"
        _register(username, f"{username}@example.com")

    login = client.post(
        "/api/v1/auth/login",
        data={"username": username, "password": "password123"},
    )
    assert login.status_code == 200
    tokens = login.json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    return client, headers, tokens
