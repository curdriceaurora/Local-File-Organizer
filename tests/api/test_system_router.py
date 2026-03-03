"""Tests for the system API router."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from file_organizer.api.auth_models import User
from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import (
    get_config_manager,
    get_current_active_user,
    get_settings,
    require_admin_user,
)
from file_organizer.api.exceptions import setup_exception_handlers
from file_organizer.api.routers.system import router


def _build_app(
    tmp_path: Path, admin_user: User | None = None, auth_enabled: bool = False
) -> tuple[FastAPI, TestClient, ApiSettings]:
    """Create a FastAPI app with system router and dependency overrides."""
    settings = ApiSettings(
        environment="test",
        auth_enabled=auth_enabled,
        allowed_paths=[str(tmp_path)],
    )
    app = FastAPI()
    setup_exception_handlers(app)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_current_active_user] = lambda: admin_user
    # Only override require_admin_user for admin users; non-admin tests need the actual check
    if admin_user and admin_user.is_admin:
        app.dependency_overrides[require_admin_user] = lambda: admin_user
    app.dependency_overrides[get_config_manager] = lambda: MagicMock()
    app.include_router(router, prefix="/api/v1")
    client = TestClient(app)
    return app, client, settings


@pytest.mark.unit
class TestSystemStatus:
    """Tests for GET /api/v1/system/status."""

    def test_system_status_returns_disk_usage(self, tmp_path: Path) -> None:
        """Test that status endpoint returns disk usage."""
        _, client, _ = _build_app(tmp_path)

        resp = client.get(f"/api/v1/system/status?path={tmp_path}")
        assert resp.status_code == 200
        body = resp.json()

        # Verify schema
        assert "app" in body
        assert "version" in body
        assert "environment" in body
        assert "disk_total" in body
        assert "disk_used" in body
        assert "disk_free" in body
        assert "active_jobs" in body

        # Verify values are integers
        assert isinstance(body["disk_total"], int)
        assert isinstance(body["disk_used"], int)
        assert isinstance(body["disk_free"], int)
        assert isinstance(body["active_jobs"], int)

    def test_system_status_path_not_found(self, tmp_path: Path) -> None:
        """Test that status returns 404 for non-existent path."""
        _, client, _ = _build_app(tmp_path)

        resp = client.get(f"/api/v1/system/status?path={tmp_path}/nonexistent")
        assert resp.status_code == 404

    def test_system_status_path_is_file_fails(self, tmp_path: Path) -> None:
        """Test that status returns 400 if path is a file not directory."""
        _, client, _ = _build_app(tmp_path)

        # Create a file
        test_file = tmp_path / "test.txt"
        test_file.write_text("test")

        resp = client.get(f"/api/v1/system/status?path={test_file}")
        assert resp.status_code == 400

    def test_system_status_environment_info(self, tmp_path: Path) -> None:
        """Test that status returns environment information."""
        _, client, settings = _build_app(tmp_path)

        resp = client.get(f"/api/v1/system/status?path={tmp_path}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["environment"] == settings.environment
        assert body["app"] == settings.app_name
        assert body["version"] == settings.version

    @patch("file_organizer.api.routers.system.job_count")
    def test_system_status_active_jobs(self, mock_job_count: MagicMock, tmp_path: Path) -> None:
        """Test that status returns active job count."""
        mock_job_count.return_value = 5
        _, client, _ = _build_app(tmp_path)

        resp = client.get(f"/api/v1/system/status?path={tmp_path}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["active_jobs"] == 5
        mock_job_count.assert_called_once()


@pytest.mark.unit
class TestGetConfig:
    """Tests for GET /api/v1/system/config."""

    def test_get_config_default_profile(self, tmp_path: Path) -> None:
        """Test getting config for default profile."""
        app, client, _ = _build_app(tmp_path)

        # Mock ConfigManager
        mock_manager = MagicMock()
        mock_manager.load.return_value = MagicMock()
        mock_manager.config_to_dict.return_value = {"key": "value"}
        mock_manager.list_profiles.return_value = ["default", "work"]
        app.dependency_overrides[get_config_manager] = lambda: mock_manager

        resp = client.get("/api/v1/system/config")
        assert resp.status_code == 200
        body = resp.json()

        assert body["profile"] == "default"
        assert "config" in body
        assert "profiles" in body
        assert isinstance(body["profiles"], list)

    def test_get_config_named_profile(self, tmp_path: Path) -> None:
        """Test getting config for named profile."""
        app, client, _ = _build_app(tmp_path)

        # Mock ConfigManager
        mock_manager = MagicMock()
        mock_manager.load.return_value = MagicMock()
        mock_manager.config_to_dict.return_value = {"key": "value"}
        mock_manager.list_profiles.return_value = ["default", "work"]
        app.dependency_overrides[get_config_manager] = lambda: mock_manager

        resp = client.get("/api/v1/system/config?profile=work")
        assert resp.status_code == 200
        body = resp.json()

        assert body["profile"] == "work"
        mock_manager.load.assert_called_with("work")

    def test_get_config_schema(self, tmp_path: Path) -> None:
        """Test config response has correct schema."""
        app, client, _ = _build_app(tmp_path)

        # Mock ConfigManager
        mock_manager = MagicMock()
        mock_manager.load.return_value = MagicMock()
        mock_manager.config_to_dict.return_value = {"setting1": "value1"}
        mock_manager.list_profiles.return_value = ["default"]
        app.dependency_overrides[get_config_manager] = lambda: mock_manager

        resp = client.get("/api/v1/system/config")
        assert resp.status_code == 200
        body = resp.json()

        # Verify schema
        assert isinstance(body["profile"], str)
        assert isinstance(body["config"], dict)
        assert isinstance(body["profiles"], list)


@pytest.mark.unit
class TestUpdateConfig:
    """Tests for PATCH /api/v1/system/config."""

    def test_update_config_requires_admin(self, tmp_path: Path) -> None:
        """Test that only admin users can update config."""
        non_admin = MagicMock(spec=User)
        non_admin.is_admin = False
        non_admin.is_active = True
        _, client, _ = _build_app(tmp_path, admin_user=non_admin, auth_enabled=True)

        update_payload = {"profile": "default", "default_methodology": "PARA"}
        resp = client.patch("/api/v1/system/config", json=update_payload)
        assert resp.status_code in [401, 403]

    def test_update_config_success(self, tmp_path: Path) -> None:
        """Test updating config for a profile."""
        admin = MagicMock(spec=User)
        admin.is_admin = True
        admin.is_active = True
        app, client, _ = _build_app(tmp_path, admin_user=admin)

        # Mock ConfigManager
        mock_config = MagicMock()
        mock_config.models = MagicMock()
        mock_config.updates = MagicMock()
        mock_manager = MagicMock()
        mock_manager.load.return_value = mock_config
        mock_manager.config_to_dict.return_value = {"default_methodology": "PARA"}
        mock_manager.list_profiles.return_value = ["default"]
        app.dependency_overrides[get_config_manager] = lambda: mock_manager

        update_payload = {"profile": "default", "default_methodology": "PARA"}
        resp = client.patch("/api/v1/system/config", json=update_payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["profile"] == "default"

    def test_update_config_saves_changes(self, tmp_path: Path) -> None:
        """Test that config updates are saved."""
        admin = MagicMock(spec=User)
        admin.is_admin = True
        admin.is_active = True
        app, client, _ = _build_app(tmp_path, admin_user=admin)

        # Mock ConfigManager
        mock_config = MagicMock()
        mock_config.models = MagicMock()
        mock_config.updates = MagicMock()
        mock_manager = MagicMock()
        mock_manager.load.return_value = mock_config
        mock_manager.config_to_dict.return_value = {}
        mock_manager.list_profiles.return_value = ["default"]
        app.dependency_overrides[get_config_manager] = lambda: mock_manager

        update_payload = {"profile": "default", "default_methodology": "JOHNNY_DECIMAL"}
        resp = client.patch("/api/v1/system/config", json=update_payload)
        assert resp.status_code == 200

        # Verify save was called
        mock_manager.save.assert_called_once()


@pytest.mark.unit
class TestGetStats:
    """Tests for GET /api/v1/system/stats."""

    def test_get_stats_returns_storage_statistics(self, tmp_path: Path) -> None:
        """Test that stats endpoint returns storage statistics."""
        _, client, _ = _build_app(tmp_path)

        resp = client.get(f"/api/v1/system/stats?path={tmp_path}")
        assert resp.status_code == 200
        body = resp.json()

        # Verify schema
        assert "total_size" in body
        assert "organized_size" in body
        assert "saved_size" in body
        assert "file_count" in body
        assert "directory_count" in body
        assert "size_by_type" in body
        assert "largest_files" in body

        # Verify types
        assert isinstance(body["total_size"], int)
        assert isinstance(body["file_count"], int)
        assert isinstance(body["size_by_type"], dict)
        assert isinstance(body["largest_files"], list)

    def test_get_stats_path_not_found(self, tmp_path: Path) -> None:
        """Test that stats returns 404 for non-existent path."""
        _, client, _ = _build_app(tmp_path)

        resp = client.get(f"/api/v1/system/stats?path={tmp_path}/nonexistent")
        assert resp.status_code == 404

    def test_get_stats_path_is_file_fails(self, tmp_path: Path) -> None:
        """Test that stats returns 400 if path is a file not directory."""
        _, client, _ = _build_app(tmp_path)

        # Create a file
        test_file = tmp_path / "test.txt"
        test_file.write_text("test")

        resp = client.get(f"/api/v1/system/stats?path={test_file}")
        assert resp.status_code == 400

    def test_get_stats_with_max_depth(self, tmp_path: Path) -> None:
        """Test stats with max_depth parameter."""
        _, client, _ = _build_app(tmp_path)

        resp = client.get(f"/api/v1/system/stats?path={tmp_path}&max_depth=2")
        assert resp.status_code == 200
        body = resp.json()
        assert "total_size" in body

    def test_get_stats_with_cache_parameter(self, tmp_path: Path) -> None:
        """Test stats with use_cache parameter."""
        _, client, _ = _build_app(tmp_path)

        resp = client.get(f"/api/v1/system/stats?path={tmp_path}&use_cache=false")
        assert resp.status_code == 200
        body = resp.json()
        assert "total_size" in body

    def test_get_stats_no_depth_limit(self, tmp_path: Path) -> None:
        """Test stats without max_depth specified."""
        _, client, _ = _build_app(tmp_path)

        # Create some files for analysis
        (tmp_path / "test.txt").write_text("test")
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "test2.txt").write_text("test2")

        resp = client.get(f"/api/v1/system/stats?path={tmp_path}")
        assert resp.status_code == 200
        body = resp.json()
        assert "total_size" in body
        assert body["total_size"] >= 0
