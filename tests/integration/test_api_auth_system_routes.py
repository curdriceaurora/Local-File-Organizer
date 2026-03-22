"""Integration tests for API auth and system routers.

Covers:
  - api/routers/auth.py — POST /auth/register, /auth/login, /auth/refresh,
    /auth/logout, GET /auth/me; error paths (duplicate user, bad password,
    bad credentials, bad refresh token, revoked token)
  - api/routers/system.py — GET /system/status, /system/config,
    PATCH /system/config, /system/stats; error paths (path not found,
    not a directory)
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_config_manager, get_settings
from file_organizer.api.exceptions import setup_exception_handlers
from file_organizer.api.routers.system import router as system_router
from file_organizer.api.test_utils import create_auth_client

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def auth_client(tmp_path: Path) -> tuple[TestClient, dict[str, str], dict[str, str]]:
    return create_auth_client(tmp_path, allowed_paths=[str(tmp_path)])


@pytest.fixture()
def system_test_settings(tmp_path: Path) -> ApiSettings:
    return ApiSettings(
        allowed_paths=[str(tmp_path)],
        auth_enabled=False,
        auth_db_path=str(tmp_path / "auth.db"),
    )


@pytest.fixture()
def system_client(system_test_settings: ApiSettings) -> TestClient:
    app = FastAPI()
    app.dependency_overrides[get_settings] = lambda: system_test_settings
    setup_exception_handlers(app)
    app.include_router(system_router)
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Auth router — /api/v1/auth/register
# ---------------------------------------------------------------------------


class TestAuthRegister:
    def test_register_new_user_returns_201(self, tmp_path: Path) -> None:
        client, headers, _ = create_auth_client(tmp_path)
        r = client.post(
            "/api/v1/auth/register",
            json={
                "username": "newuser_test",
                "email": "newuser_test@example.com",
                "password": "T3stP@ssword1!",
                "full_name": "New User",
            },
        )
        assert r.status_code == 201

    def test_register_duplicate_username_returns_400(self, tmp_path: Path) -> None:
        client, _, _ = create_auth_client(tmp_path)
        payload = {
            "username": "dupuser",
            "email": "dup@example.com",
            "password": "T3stP@ssword1!",
            "full_name": "Dup",
        }
        r1 = client.post("/api/v1/auth/register", json=payload)
        assert r1.status_code == 201
        r2 = client.post("/api/v1/auth/register", json=payload)
        assert r2.status_code == 400

    def test_register_weak_password_returns_400(self, tmp_path: Path) -> None:
        client, _, _ = create_auth_client(tmp_path)
        r = client.post(
            "/api/v1/auth/register",
            json={
                "username": "weakpass",
                "email": "weak@example.com",
                "password": "123",
                "full_name": "Weak",
            },
        )
        assert r.status_code == 400

    def test_register_response_has_user_fields(self, tmp_path: Path) -> None:
        client, _, _ = create_auth_client(tmp_path)
        r = client.post(
            "/api/v1/auth/register",
            json={
                "username": "fieldtest",
                "email": "field@example.com",
                "password": "T3stP@ssword1!",
                "full_name": "Field Test",
            },
        )
        assert r.status_code == 201
        body = r.json()
        assert "username" in body
        assert body["username"] == "fieldtest"


# ---------------------------------------------------------------------------
# Auth router — /api/v1/auth/login
# ---------------------------------------------------------------------------


class TestAuthLogin:
    def test_login_returns_access_token(self, auth_client: tuple) -> None:
        client, _, tokens = auth_client
        assert "access_token" in tokens
        assert tokens["access_token"] != ""

    def test_login_returns_refresh_token(self, auth_client: tuple) -> None:
        _, _, tokens = auth_client
        assert "refresh_token" in tokens

    def test_login_wrong_password_returns_401(self, tmp_path: Path) -> None:
        client, _, _ = create_auth_client(tmp_path, allowed_paths=[str(tmp_path)])
        r = client.post(
            "/api/v1/auth/register",
            json={
                "username": "wrongpw_user",
                "email": "wrongpw@example.com",
                "password": "T3stP@ssword1!",
                "full_name": "WP User",
            },
        )
        assert r.status_code == 201
        r = client.post(
            "/api/v1/auth/login",
            data={"username": "wrongpw_user", "password": "NotTheRightOne1!"},
        )
        assert r.status_code in (401, 400)

    def test_login_nonexistent_user_returns_error(self, tmp_path: Path) -> None:
        client, _, _ = create_auth_client(tmp_path)
        r = client.post(
            "/api/v1/auth/login",
            data={"username": "nosuchuser99999", "password": "T3stP@ssword1!"},
        )
        assert r.status_code in (401, 400)


# ---------------------------------------------------------------------------
# Auth router — /api/v1/auth/me
# ---------------------------------------------------------------------------


class TestAuthMe:
    def test_me_returns_current_user(self, auth_client: tuple) -> None:
        client, headers, _ = auth_client
        r = client.get("/api/v1/auth/me", headers=headers)
        assert r.status_code == 200
        body = r.json()
        assert "username" in body

    def test_me_without_token_returns_401(self, tmp_path: Path) -> None:
        client, _, _ = create_auth_client(tmp_path)
        r = client.get("/api/v1/auth/me")
        assert r.status_code == 401

    def test_me_with_invalid_token_returns_401(self, tmp_path: Path) -> None:
        client, _, _ = create_auth_client(tmp_path)
        r = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer invalid.token.here"})
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# Auth router — /api/v1/auth/refresh
# ---------------------------------------------------------------------------


class TestAuthRefresh:
    def test_refresh_returns_new_access_token(self, auth_client: tuple) -> None:
        client, headers, tokens = auth_client
        r = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": tokens["refresh_token"]},
        )
        assert r.status_code == 200
        body = r.json()
        assert "access_token" in body

    def test_refresh_with_bad_token_returns_error(self, tmp_path: Path) -> None:
        client, _, _ = create_auth_client(tmp_path)
        r = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "bad.refresh.token"},
        )
        assert r.status_code in (400, 401)

    def test_refresh_with_access_token_returns_error(self, auth_client: tuple) -> None:
        client, headers, tokens = auth_client
        access_token = tokens["access_token"]
        r = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": access_token},
        )
        assert r.status_code in (400, 401)


# ---------------------------------------------------------------------------
# Auth router — /api/v1/auth/logout
# ---------------------------------------------------------------------------


class TestAuthLogout:
    def test_logout_returns_204(self, auth_client: tuple) -> None:
        client, headers, tokens = auth_client
        r = client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": tokens["refresh_token"]},
            headers=headers,
        )
        assert r.status_code == 204

    def test_after_logout_refresh_token_is_invalidated(self, auth_client: tuple) -> None:
        client, headers, tokens = auth_client
        client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": tokens["refresh_token"]},
            headers=headers,
        )
        r = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": tokens["refresh_token"]},
        )
        assert r.status_code in (400, 401)


# ---------------------------------------------------------------------------
# System router — GET /system/status
# ---------------------------------------------------------------------------


class TestSystemStatus:
    def test_system_status_returns_200(self, system_client: TestClient, tmp_path: Path) -> None:
        r = system_client.get("/system/status", params={"path": str(tmp_path)})
        assert r.status_code == 200

    def test_system_status_response_shape(self, system_client: TestClient, tmp_path: Path) -> None:
        r = system_client.get("/system/status", params={"path": str(tmp_path)})
        body = r.json()
        assert "app" in body
        assert "version" in body
        assert "disk_total" in body
        assert "disk_used" in body
        assert "disk_free" in body
        assert "active_jobs" in body

    def test_system_status_nonexistent_path_returns_404(
        self, system_client: TestClient, tmp_path: Path
    ) -> None:
        r = system_client.get("/system/status", params={"path": str(tmp_path / "gone")})
        assert r.status_code == 404

    def test_system_status_file_path_returns_400(
        self, system_client: TestClient, tmp_path: Path
    ) -> None:
        f = tmp_path / "file.txt"
        f.write_text("x")
        r = system_client.get("/system/status", params={"path": str(f)})
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# System router — GET /system/config
# ---------------------------------------------------------------------------


class TestSystemConfig:
    def test_system_config_returns_200(self, system_client: TestClient) -> None:
        mock_manager = MagicMock()
        mock_config = MagicMock()
        mock_manager.load.return_value = mock_config
        mock_manager.config_to_dict.return_value = {"key": "val"}
        mock_manager.list_profiles.return_value = ["default"]
        system_client.app.dependency_overrides[get_config_manager] = lambda: mock_manager
        r = system_client.get("/system/config")
        system_client.app.dependency_overrides.pop(get_config_manager, None)
        assert r.status_code == 200

    def test_system_config_default_profile(self, system_client: TestClient) -> None:
        mock_manager = MagicMock()
        mock_config = MagicMock()
        mock_manager.load.return_value = mock_config
        mock_manager.config_to_dict.return_value = {}
        mock_manager.list_profiles.return_value = ["default"]
        system_client.app.dependency_overrides[get_config_manager] = lambda: mock_manager
        r = system_client.get("/system/config", params={"profile": "default"})
        system_client.app.dependency_overrides.pop(get_config_manager, None)
        assert r.status_code == 200
        mock_manager.load.assert_called_with("default")


# ---------------------------------------------------------------------------
# System router — GET /system/stats
# ---------------------------------------------------------------------------


class TestSystemStats:
    def test_system_stats_returns_200(self, system_client: TestClient, tmp_path: Path) -> None:
        mock_analyzer = MagicMock()
        mock_stats = MagicMock()
        mock_stats.total_size = 1024
        mock_stats.organized_size = 512
        mock_stats.saved_size = 0
        mock_stats.file_count = 3
        mock_stats.directory_count = 1
        mock_stats.size_by_type = {"txt": 512, "jpg": 512}
        mock_stats.largest_files = []
        mock_analyzer.analyze_directory.return_value = mock_stats
        with patch(
            "file_organizer.api.routers.system.StorageAnalyzer",
            return_value=mock_analyzer,
        ):
            r = system_client.get("/system/stats", params={"path": str(tmp_path)})
        assert r.status_code == 200
        body = r.json()
        assert body["total_size"] == 1024
        assert body["file_count"] == 3

    def test_system_stats_nonexistent_path_returns_404(
        self, system_client: TestClient, tmp_path: Path
    ) -> None:
        r = system_client.get("/system/stats", params={"path": str(tmp_path / "gone")})
        assert r.status_code == 404

    def test_system_stats_file_path_returns_400(
        self, system_client: TestClient, tmp_path: Path
    ) -> None:
        f = tmp_path / "file.txt"
        f.write_text("x")
        r = system_client.get("/system/stats", params={"path": str(f)})
        assert r.status_code == 400
