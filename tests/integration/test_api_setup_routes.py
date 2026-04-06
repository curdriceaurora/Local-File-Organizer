"""Integration tests for api/routers/setup.py.

Covers:
  - GET /setup/status — completed flag, profile field
  - GET /setup/capabilities — hardware/ollama/models response shape
  - POST /setup/complete — success path, mode fallback to QUICK_START
  - GET /setup/browse-folder — non-darwin returns unavailable,
    darwin user-cancel returns cancelled
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_config_manager, get_settings
from file_organizer.api.exceptions import setup_exception_handlers
from file_organizer.api.routers.setup import router as setup_router
from file_organizer.core.hardware_profile import GpuType
from file_organizer.core.setup_wizard import SetupWizard

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def test_settings(tmp_path: Path) -> ApiSettings:
    return ApiSettings(
        allowed_paths=[str(tmp_path)],
        auth_enabled=False,
        auth_db_path=str(tmp_path / "auth.db"),
    )


def _make_mock_manager(completed: bool = True, profile: str = "default") -> MagicMock:
    mock_manager = MagicMock()
    mock_config = MagicMock()
    mock_config.setup_completed = completed
    mock_config.profile_name = profile
    mock_manager.load.return_value = mock_config
    return mock_manager


@pytest.fixture()
def setup_client(test_settings: ApiSettings) -> TestClient:
    mock_manager = _make_mock_manager()
    app = FastAPI()
    app.dependency_overrides[get_settings] = lambda: test_settings
    app.dependency_overrides[get_config_manager] = lambda: mock_manager
    setup_exception_handlers(app)
    app.include_router(setup_router)
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# GET /setup/status
# ---------------------------------------------------------------------------


class TestSetupStatus:
    def test_setup_status_returns_200(self, setup_client: TestClient) -> None:
        r = setup_client.get("/setup/status")
        assert r.status_code == 200

    def test_setup_status_completed_true(self, test_settings: ApiSettings) -> None:
        mock_manager = _make_mock_manager(completed=True, profile="default")
        app = FastAPI()
        app.dependency_overrides[get_settings] = lambda: test_settings
        app.dependency_overrides[get_config_manager] = lambda: mock_manager
        setup_exception_handlers(app)
        app.include_router(setup_router)
        client = TestClient(app, raise_server_exceptions=False)

        r = client.get("/setup/status")
        assert r.status_code == 200
        assert r.json()["completed"] is True

    def test_setup_status_completed_false(self, test_settings: ApiSettings) -> None:
        mock_manager = _make_mock_manager(completed=False, profile="default")
        app = FastAPI()
        app.dependency_overrides[get_settings] = lambda: test_settings
        app.dependency_overrides[get_config_manager] = lambda: mock_manager
        setup_exception_handlers(app)
        app.include_router(setup_router)
        client = TestClient(app, raise_server_exceptions=False)

        r = client.get("/setup/status")
        assert r.status_code == 200
        assert r.json()["completed"] is False

    def test_setup_status_response_has_profile(self, setup_client: TestClient) -> None:
        r = setup_client.get("/setup/status")
        assert r.status_code == 200
        body = r.json()
        assert "profile" in body
        assert isinstance(body["profile"], str)
        assert len(body["profile"]) > 0


# ---------------------------------------------------------------------------
# GET /setup/capabilities
# ---------------------------------------------------------------------------


class TestSetupCapabilities:
    def _make_mock_capabilities(self) -> MagicMock:
        mock_caps = MagicMock()
        mock_caps.hardware.ram_gb = 16.0
        mock_caps.hardware.gpu_type = GpuType.NONE
        mock_caps.hardware.vram_gb = None
        mock_caps.hardware.gpu_name = None
        mock_caps.hardware.cpu_cores = 8
        mock_caps.hardware.recommended_text_model.return_value = "qwen2.5:3b"
        mock_caps.ollama_status.installed = True
        mock_caps.ollama_status.running = True
        mock_caps.ollama_status.version = "0.4.0"
        mock_caps.ollama_status.models_count = 0
        mock_caps.installed_models = []
        return mock_caps

    def test_capabilities_returns_200(self, setup_client: TestClient) -> None:
        with patch.object(SetupWizard, "detect_capabilities") as mock_detect:
            mock_detect.return_value = self._make_mock_capabilities()
            r = setup_client.get("/setup/capabilities")
        assert r.status_code == 200

    def test_capabilities_response_has_hardware_ollama_models(
        self, setup_client: TestClient
    ) -> None:
        with patch.object(SetupWizard, "detect_capabilities") as mock_detect:
            mock_detect.return_value = self._make_mock_capabilities()
            r = setup_client.get("/setup/capabilities")
        assert r.status_code == 200
        body = r.json()
        assert "hardware" in body
        assert "ollama" in body
        assert "models" in body
        assert body["hardware"]["total_ram_gb"] == 16.0
        assert body["hardware"]["gpu_available"] is False
        assert body["hardware"]["cpu_cores"] == 8
        assert body["ollama"]["installed"] is True
        assert isinstance(body["models"], list)


# ---------------------------------------------------------------------------
# POST /setup/complete
# ---------------------------------------------------------------------------


class TestSetupComplete:
    def _patch_wizard(self) -> MagicMock:
        mock_wizard = MagicMock()
        mock_caps = MagicMock()
        mock_wizard.detect_capabilities.return_value = mock_caps
        mock_config = MagicMock()
        mock_config.models.text_model = "qwen2.5:3b"
        mock_wizard.generate_config.return_value = mock_config
        mock_wizard.validate_config.return_value = (True, [])
        return mock_wizard

    def test_complete_setup_returns_success_true(
        self, test_settings: ApiSettings, tmp_path: Path
    ) -> None:
        mock_mgr = MagicMock()
        app = FastAPI()
        app.dependency_overrides[get_settings] = lambda: test_settings
        app.dependency_overrides[get_config_manager] = lambda: mock_mgr
        setup_exception_handlers(app)
        app.include_router(setup_router)
        client = TestClient(app, raise_server_exceptions=False)

        with patch("file_organizer.api.routers.setup.SetupWizard") as mock_wizard_cls:
            mock_wizard_cls.return_value = self._patch_wizard()
            r = client.post(
                "/setup/complete",
                json={"mode": "quick_start", "profile": "default"},
            )

        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        assert body["profile"] == "default"
        assert len(body["messages"]) >= 1

    def test_complete_setup_invalid_mode_uses_quick_start(
        self, test_settings: ApiSettings, tmp_path: Path
    ) -> None:
        mock_mgr = MagicMock()
        app = FastAPI()
        app.dependency_overrides[get_settings] = lambda: test_settings
        app.dependency_overrides[get_config_manager] = lambda: mock_mgr
        setup_exception_handlers(app)
        app.include_router(setup_router)
        client = TestClient(app, raise_server_exceptions=False)

        with patch("file_organizer.api.routers.setup.SetupWizard") as mock_wizard_cls:
            mock_wizard_cls.return_value = self._patch_wizard()
            r = client.post(
                "/setup/complete",
                json={"mode": "invalid_mode", "profile": "default"},
            )

        # Invalid mode falls back to QUICK_START — request should still succeed
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True


# ---------------------------------------------------------------------------
# GET /setup/browse-folder
# ---------------------------------------------------------------------------


class TestBrowseFolder:
    def test_browse_folder_non_darwin_returns_unavailable(self, setup_client: TestClient) -> None:
        with patch.object(sys, "platform", "linux"):
            r = setup_client.get("/setup/browse-folder")
        assert r.status_code == 200
        body = r.json()
        assert body["available"] is False
        assert body["path"] == ""

    def test_browse_folder_darwin_cancelled_returns_cancelled(
        self, setup_client: TestClient
    ) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "User canceled."
        mock_result.stdout = ""

        with (
            patch.object(sys, "platform", "darwin"),
            patch("file_organizer.api.routers.setup.subprocess.run", return_value=mock_result),
        ):
            r = setup_client.get("/setup/browse-folder")

        assert r.status_code == 200
        body = r.json()
        assert body["available"] is True
        assert body["cancelled"] is True
        assert body["path"] == ""
