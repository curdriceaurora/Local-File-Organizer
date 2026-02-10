"""API tests for authentication flow."""
from __future__ import annotations

from pathlib import Path

import pytest

from file_organizer.api.test_utils import create_auth_client

pytestmark = pytest.mark.ci


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
