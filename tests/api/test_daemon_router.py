"""Tests for the daemon API router."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_settings
from file_organizer.api.exceptions import setup_exception_handlers
from file_organizer.api.routers.daemon import router


def _build_app() -> tuple[FastAPI, TestClient]:
    """Create a FastAPI app with daemon router."""
    settings = ApiSettings(environment="test")
    app = FastAPI()
    setup_exception_handlers(app)
    app.dependency_overrides[get_settings] = lambda: settings
    app.include_router(router, prefix="/api/v1")
    client = TestClient(app)
    return app, client


# ---------------------------------------------------------------------------
# daemon_status endpoint
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDaemonStatus:
    """Tests for GET /api/v1/daemon/status."""

    def test_daemon_status_running(self) -> None:
        """Test getting daemon status when daemon is running."""
        _, client = _build_app()

        with patch("file_organizer.api.service_facade.ServiceFacade") as mock_facade_class:
            mock_facade = AsyncMock()
            mock_facade_class.return_value = mock_facade
            mock_facade.get_daemon_status.return_value = {
                "success": True,
                "data": {"running": True, "pid": 12345},
            }

            resp = client.get("/api/v1/daemon/status")
            assert resp.status_code == 200
            body = resp.json()
            assert body["success"] is True
            assert body["data"]["running"] is True

    def test_daemon_status_stopped(self) -> None:
        """Test getting daemon status when daemon is stopped."""
        _, client = _build_app()

        with patch("file_organizer.api.service_facade.ServiceFacade") as mock_facade_class:
            mock_facade = AsyncMock()
            mock_facade_class.return_value = mock_facade
            mock_facade.get_daemon_status.return_value = {
                "success": True,
                "data": {"running": False},
            }

            resp = client.get("/api/v1/daemon/status")
            assert resp.status_code == 200
            body = resp.json()
            assert body["success"] is True
            assert body["data"]["running"] is False

    def test_daemon_status_error(self) -> None:
        """Test daemon status when error occurs."""
        _, client = _build_app()

        with patch("file_organizer.api.service_facade.ServiceFacade") as mock_facade_class:
            mock_facade = AsyncMock()
            mock_facade_class.return_value = mock_facade
            mock_facade.get_daemon_status.return_value = {
                "success": False,
                "error": "Failed to check daemon status",
            }

            resp = client.get("/api/v1/daemon/status")
            assert resp.status_code == 200
            body = resp.json()
            assert body["success"] is False
            assert "error" in body


# ---------------------------------------------------------------------------
# start_daemon endpoint
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestStartDaemon:
    """Tests for POST /api/v1/daemon/start."""

    def test_start_daemon_success(self) -> None:
        """Test successfully starting daemon."""
        _, client = _build_app()

        with patch("file_organizer.api.service_facade.ServiceFacade") as mock_facade_class:
            mock_facade = AsyncMock()
            mock_facade_class.return_value = mock_facade
            mock_facade.get_daemon_status.return_value = {
                "success": True,
                "data": {"running": False},
            }
            mock_facade.start_daemon.return_value = {
                "success": True,
                "data": {"started": True},
            }

            resp = client.post("/api/v1/daemon/start")
            assert resp.status_code == 200
            body = resp.json()
            assert body["success"] is True

    def test_start_daemon_already_running(self) -> None:
        """Test starting daemon when already running."""
        _, client = _build_app()

        with patch("file_organizer.api.service_facade.ServiceFacade") as mock_facade_class:
            mock_facade = AsyncMock()
            mock_facade_class.return_value = mock_facade
            mock_facade.get_daemon_status.return_value = {
                "success": True,
                "data": {"running": True},
            }

            resp = client.post("/api/v1/daemon/start")
            assert resp.status_code == 200
            body = resp.json()
            assert body["success"] is True
            assert body["data"]["already_running"] is True

    def test_start_daemon_error(self) -> None:
        """Test daemon start error."""
        _, client = _build_app()

        with patch("file_organizer.api.service_facade.ServiceFacade") as mock_facade_class:
            mock_facade = AsyncMock()
            mock_facade_class.return_value = mock_facade
            mock_facade.get_daemon_status.return_value = {
                "success": False,
                "error": "Cannot check status",
            }
            # When status check fails, start_daemon is still called
            mock_facade.start_daemon.return_value = {
                "success": True,
                "data": {"started": True},
            }

            resp = client.post("/api/v1/daemon/start")
            assert resp.status_code == 200
            body = resp.json()
            # Should succeed since start_daemon is called
            assert body["success"] is True


# ---------------------------------------------------------------------------
# stop_daemon endpoint
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestStopDaemon:
    """Tests for POST /api/v1/daemon/stop."""

    def test_stop_daemon_success(self) -> None:
        """Test successfully stopping daemon."""
        _, client = _build_app()

        with patch("file_organizer.api.service_facade.ServiceFacade") as mock_facade_class:
            mock_facade = AsyncMock()
            mock_facade_class.return_value = mock_facade
            mock_facade.get_daemon_status.return_value = {
                "success": True,
                "data": {"running": True},
            }
            mock_facade.stop_daemon.return_value = {
                "success": True,
                "data": {"stopped": True},
            }

            resp = client.post("/api/v1/daemon/stop")
            assert resp.status_code == 200
            body = resp.json()
            assert body["success"] is True

    def test_stop_daemon_already_stopped(self) -> None:
        """Test stopping daemon when already stopped."""
        _, client = _build_app()

        with patch("file_organizer.api.service_facade.ServiceFacade") as mock_facade_class:
            mock_facade = AsyncMock()
            mock_facade_class.return_value = mock_facade
            mock_facade.get_daemon_status.return_value = {
                "success": True,
                "data": {"running": False},
            }

            resp = client.post("/api/v1/daemon/stop")
            assert resp.status_code == 200
            body = resp.json()
            assert body["success"] is True
            assert body["data"]["already_stopped"] is True

    def test_stop_daemon_error(self) -> None:
        """Test daemon stop error."""
        _, client = _build_app()

        with patch("file_organizer.api.service_facade.ServiceFacade") as mock_facade_class:
            mock_facade = AsyncMock()
            mock_facade_class.return_value = mock_facade
            mock_facade.get_daemon_status.return_value = {
                "success": False,
                "error": "Cannot check status",
            }
            # When status check fails, stop_daemon is still called
            mock_facade.stop_daemon.return_value = {
                "success": True,
                "data": {"stopped": True},
            }

            resp = client.post("/api/v1/daemon/stop")
            assert resp.status_code == 200
            body = resp.json()
            # Should succeed since stop_daemon is called
            assert body["success"] is True


# ---------------------------------------------------------------------------
# toggle_daemon endpoint
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestToggleDaemon:
    """Tests for POST /api/v1/daemon/toggle."""

    def test_toggle_daemon_running_to_stopped(self) -> None:
        """Test toggling daemon from running to stopped."""
        _, client = _build_app()

        with patch("file_organizer.api.service_facade.ServiceFacade") as mock_facade_class:
            mock_facade = AsyncMock()
            mock_facade_class.return_value = mock_facade
            mock_facade.get_daemon_status.return_value = {
                "success": True,
                "data": {"running": True},
            }
            mock_facade.stop_daemon.return_value = {
                "success": True,
                "data": {"stopped": True},
            }

            resp = client.post("/api/v1/daemon/toggle")
            assert resp.status_code == 200
            body = resp.json()
            assert body["success"] is True
            mock_facade.stop_daemon.assert_called_once()

    def test_toggle_daemon_stopped_to_running(self) -> None:
        """Test toggling daemon from stopped to running."""
        _, client = _build_app()

        with patch("file_organizer.api.service_facade.ServiceFacade") as mock_facade_class:
            mock_facade = AsyncMock()
            mock_facade_class.return_value = mock_facade
            mock_facade.get_daemon_status.return_value = {
                "success": True,
                "data": {"running": False},
            }
            mock_facade.start_daemon.return_value = {
                "success": True,
                "data": {"started": True},
            }

            resp = client.post("/api/v1/daemon/toggle")
            assert resp.status_code == 200
            body = resp.json()
            assert body["success"] is True
            mock_facade.start_daemon.assert_called_once()

    def test_toggle_daemon_status_check_fails(self) -> None:
        """Test toggle when status check fails."""
        _, client = _build_app()

        with patch("file_organizer.api.service_facade.ServiceFacade") as mock_facade_class:
            mock_facade = AsyncMock()
            mock_facade_class.return_value = mock_facade
            mock_facade.get_daemon_status.return_value = {
                "success": False,
                "error": "Cannot determine status",
            }

            resp = client.post("/api/v1/daemon/toggle")
            assert resp.status_code == 200
            body = resp.json()
            assert body["success"] is False
            assert "error" in body
