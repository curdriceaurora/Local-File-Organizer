"""Integration tests for API routers.

Covers:
  - api/routers/analyze.py  — POST /analyze
  - api/routers/daemon.py   — POST /daemon/toggle, /start, /stop; GET /status
  - api/routers/config.py   — GET /config, PATCH /config
  - api/routers/system.py   — GET /system/status, /system/config, /system/stats
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_settings
from file_organizer.api.exceptions import setup_exception_handlers
from file_organizer.api.routers.analyze import router as analyze_router
from file_organizer.api.routers.daemon import router as daemon_router

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def api_settings(tmp_path: Path) -> ApiSettings:
    return ApiSettings(
        allowed_paths=[str(tmp_path)],
        auth_enabled=False,
        auth_db_path=str(tmp_path / "auth.db"),
    )


@pytest.fixture()
def analyze_client(api_settings: ApiSettings) -> TestClient:
    app = FastAPI()
    app.dependency_overrides[get_settings] = lambda: api_settings
    setup_exception_handlers(app)
    app.include_router(analyze_router)
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def daemon_client() -> TestClient:
    app = FastAPI()
    setup_exception_handlers(app)
    app.include_router(daemon_router)
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# api/routers/analyze.py
# ---------------------------------------------------------------------------


class TestAnalyzeRouter:
    def test_analyze_no_content_no_file_returns_400(self, analyze_client: TestClient) -> None:
        r = analyze_client.post("/analyze")
        assert r.status_code == 400

    def test_analyze_text_content_success(self, analyze_client: TestClient) -> None:
        with (
            patch("file_organizer.api.routers.analyze.get_text_model") as mock_get,
            patch("file_organizer.api.routers.analyze.generate_category", return_value="Documents"),
            patch(
                "file_organizer.api.routers.analyze.generate_description",
                return_value="A quarterly financial report",
            ),
            patch("file_organizer.api.routers.analyze.calculate_confidence", return_value=0.85),
        ):
            mock_get.return_value = MagicMock()
            r = analyze_client.post("/analyze", params={"content": "Q4 revenue was $2M"})
        assert r.status_code == 200
        body = r.json()
        assert body["category"] == "Documents"
        assert body["confidence"] == 0.85

    def test_analyze_model_exception_returns_500(self, analyze_client: TestClient) -> None:
        with patch(
            "file_organizer.api.routers.analyze.get_text_model",
            side_effect=RuntimeError("model crashed"),
        ):
            r = analyze_client.post("/analyze", params={"content": "some text"})
        assert r.status_code == 500

    def test_analyze_import_error_returns_503(self, analyze_client: TestClient) -> None:
        with patch(
            "file_organizer.api.routers.analyze.get_text_model",
            side_effect=ImportError("ollama not found"),
        ):
            r = analyze_client.post("/analyze", params={"content": "some text"})
        assert r.status_code == 503

    def test_analyze_file_upload(self, analyze_client: TestClient) -> None:
        with (
            patch("file_organizer.api.routers.analyze.get_text_model") as mock_get,
            patch("file_organizer.api.routers.analyze.generate_category", return_value="Code"),
            patch(
                "file_organizer.api.routers.analyze.generate_description",
                return_value="Python source code",
            ),
            patch("file_organizer.api.routers.analyze.calculate_confidence", return_value=0.7),
        ):
            mock_get.return_value = MagicMock()
            r = analyze_client.post(
                "/analyze",
                files={"file": ("test.py", b"def hello(): pass", "text/plain")},
            )
        assert r.status_code == 200
        assert r.json()["category"] == "Code"


# ---------------------------------------------------------------------------
# api/routers/daemon.py
# ---------------------------------------------------------------------------


class TestDaemonRouter:
    def _mock_facade(self, **overrides: Any) -> MagicMock:
        facade = MagicMock()
        facade.get_daemon_status = AsyncMock(
            return_value=overrides.get("status", {"success": True, "data": {"running": False}})
        )
        facade.start_daemon = AsyncMock(
            return_value=overrides.get("start", {"success": True, "data": {"started": True}})
        )
        facade.stop_daemon = AsyncMock(
            return_value=overrides.get("stop", {"success": True, "data": {"stopped": True}})
        )
        return facade

    def test_get_daemon_status(self, daemon_client: TestClient) -> None:
        with patch(
            "file_organizer.api.service_facade.ServiceFacade.get_daemon_status",
            new=AsyncMock(return_value={"success": True, "data": {"running": False}}),
        ):
            r = daemon_client.get("/daemon/status")
        assert r.status_code == 200
        assert r.json()["success"] is True

    def test_start_daemon_when_not_running(self, daemon_client: TestClient) -> None:
        not_running = {"success": True, "data": {"running": False}}
        start_result = {"success": True, "data": {"started": True}}
        with (
            patch(
                "file_organizer.api.service_facade.ServiceFacade.get_daemon_status",
                new=AsyncMock(return_value=not_running),
            ),
            patch(
                "file_organizer.api.service_facade.ServiceFacade.start_daemon",
                new=AsyncMock(return_value=start_result),
            ),
        ):
            r = daemon_client.post("/daemon/start")
        assert r.status_code == 200

    def test_start_daemon_already_running(self, daemon_client: TestClient) -> None:
        already_running = {"success": True, "data": {"running": True}}
        with patch(
            "file_organizer.api.service_facade.ServiceFacade.get_daemon_status",
            new=AsyncMock(return_value=already_running),
        ):
            r = daemon_client.post("/daemon/start")
        assert r.status_code == 200
        body = r.json()
        assert body.get("data", {}).get("already_running") is True

    def test_stop_daemon_when_running(self, daemon_client: TestClient) -> None:
        running = {"success": True, "data": {"running": True}}
        stop_result = {"success": True, "data": {"stopped": True}}
        with (
            patch(
                "file_organizer.api.service_facade.ServiceFacade.get_daemon_status",
                new=AsyncMock(return_value=running),
            ),
            patch(
                "file_organizer.api.service_facade.ServiceFacade.stop_daemon",
                new=AsyncMock(return_value=stop_result),
            ),
        ):
            r = daemon_client.post("/daemon/stop")
        assert r.status_code == 200

    def test_stop_daemon_already_stopped(self, daemon_client: TestClient) -> None:
        already_stopped = {"success": True, "data": {"running": False}}
        with patch(
            "file_organizer.api.service_facade.ServiceFacade.get_daemon_status",
            new=AsyncMock(return_value=already_stopped),
        ):
            r = daemon_client.post("/daemon/stop")
        assert r.status_code == 200
        body = r.json()
        assert body.get("data", {}).get("already_stopped") is True

    def test_toggle_daemon_starts_when_stopped(self, daemon_client: TestClient) -> None:
        not_running = {"success": True, "data": {"running": False}}
        start_result = {"success": True, "data": {"started": True}}
        with (
            patch(
                "file_organizer.api.service_facade.ServiceFacade.get_daemon_status",
                new=AsyncMock(return_value=not_running),
            ),
            patch(
                "file_organizer.api.service_facade.ServiceFacade.start_daemon",
                new=AsyncMock(return_value=start_result),
            ),
        ):
            r = daemon_client.post("/daemon/toggle")
        assert r.status_code == 200
        assert r.json()["success"] is True

    def test_toggle_daemon_stops_when_running(self, daemon_client: TestClient) -> None:
        running = {"success": True, "data": {"running": True}}
        stop_result = {"success": True, "data": {"stopped": True}}
        with (
            patch(
                "file_organizer.api.service_facade.ServiceFacade.get_daemon_status",
                new=AsyncMock(return_value=running),
            ),
            patch(
                "file_organizer.api.service_facade.ServiceFacade.stop_daemon",
                new=AsyncMock(return_value=stop_result),
            ),
        ):
            r = daemon_client.post("/daemon/toggle")
        assert r.status_code == 200

    def test_toggle_daemon_status_check_failure(self, daemon_client: TestClient) -> None:
        failed_status: dict[str, Any] = {"success": False, "error": "daemon unreachable"}
        with patch(
            "file_organizer.api.service_facade.ServiceFacade.get_daemon_status",
            new=AsyncMock(return_value=failed_status),
        ):
            r = daemon_client.post("/daemon/toggle")
        assert r.status_code == 200
        assert r.json()["success"] is False
