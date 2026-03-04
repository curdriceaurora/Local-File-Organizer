"""Tests for the integrations API router."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import (
    get_current_active_user,
    get_settings,
)
from file_organizer.api.exceptions import setup_exception_handlers
from file_organizer.api.routers.integrations import (
    get_browser_extension_manager,
    get_integration_manager,
    router,
)


def _build_app(
    tmp_path: Path,
    mock_integration_manager: MagicMock | None = None,
    mock_browser_manager: MagicMock | None = None,
) -> tuple[FastAPI, TestClient]:
    """Create a FastAPI app with integrations router."""
    settings = ApiSettings(
        environment="test",
        auth_enabled=False,
        allowed_paths=[str(tmp_path)],
    )
    app = FastAPI()
    setup_exception_handlers(app)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_current_active_user] = lambda: MagicMock(
        is_active=True, is_admin=True
    )

    # Set up mock overrides if provided
    if mock_integration_manager is not None:
        app.dependency_overrides[get_integration_manager] = lambda: mock_integration_manager
    if mock_browser_manager is not None:
        app.dependency_overrides[get_browser_extension_manager] = lambda: mock_browser_manager

    app.include_router(router, prefix="/api/v1")
    client = TestClient(app)
    return app, client


@pytest.mark.unit
class TestListIntegrations:
    """Tests for GET /api/v1/integrations."""

    def test_list_integrations_returns_list(self, tmp_path: Path) -> None:
        """Test listing all integrations returns items array."""
        mock_manager = MagicMock()
        mock_status_1 = MagicMock()
        mock_status_1.name = "obsidian"
        mock_status_1.integration_type.value = "desktop_app"
        mock_status_1.enabled = True
        mock_status_1.connected = True
        mock_status_1.details = {"vault": "/path/to/vault"}

        mock_status_2 = MagicMock()
        mock_status_2.name = "vscode"
        mock_status_2.integration_type.value = "editor"
        mock_status_2.enabled = True
        mock_status_2.connected = False
        mock_status_2.details = {}

        # Setup async method
        mock_manager.list_statuses = AsyncMock(
            return_value=[mock_status_1, mock_status_2]
        )

        _, client = _build_app(tmp_path, mock_integration_manager=mock_manager)
        resp = client.get("/api/v1/integrations")

        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert len(body["items"]) == 2
        assert body["items"][0]["name"] == "obsidian"
        assert body["items"][0]["connected"] is True
        assert body["items"][1]["name"] == "vscode"
        assert body["items"][1]["connected"] is False

    def test_list_integrations_empty(self, tmp_path: Path) -> None:
        """Test listing integrations when none are available."""
        mock_manager = MagicMock()
        mock_manager.list_statuses = AsyncMock(return_value=[])

        _, client = _build_app(tmp_path, mock_integration_manager=mock_manager)
        resp = client.get("/api/v1/integrations")

        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []

    def test_list_integrations_schema(self, tmp_path: Path) -> None:
        """Test integration list response has correct schema."""
        mock_manager = MagicMock()
        mock_status = MagicMock()
        mock_status.name = "test"
        mock_status.integration_type.value = "desktop_app"
        mock_status.enabled = True
        mock_status.connected = True
        mock_status.details = {}

        mock_manager.list_statuses = AsyncMock(return_value=[mock_status])

        _, client = _build_app(tmp_path, mock_integration_manager=mock_manager)
        resp = client.get("/api/v1/integrations")

        assert resp.status_code == 200
        body = resp.json()
        item = body["items"][0]
        assert "name" in item
        assert "type" in item
        assert "enabled" in item
        assert "connected" in item
        assert "details" in item


@pytest.mark.unit
class TestUpdateIntegrationSettings:
    """Tests for POST /api/v1/integrations/{integration_name}/settings."""

    def test_update_settings_success(self, tmp_path: Path) -> None:
        """Test updating integration settings."""
        mock_manager = MagicMock()
        mock_manager.get.return_value = MagicMock()  # Integration exists
        mock_manager.update_settings.return_value = None

        payload = {"settings": {"vault_path": str(tmp_path)}}

        _, client = _build_app(tmp_path, mock_integration_manager=mock_manager)
        resp = client.post(
            "/api/v1/integrations/obsidian/settings", json=payload
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["integration"] == "obsidian"
        assert "connected" in body

    def test_update_settings_missing_integration(self, tmp_path: Path) -> None:
        """Test updating settings for non-existent integration."""
        mock_manager = MagicMock()
        mock_manager.get.return_value = None  # Integration does not exist

        payload = {"settings": {}}  # Empty settings - no path validation

        _, client = _build_app(tmp_path, mock_integration_manager=mock_manager)
        resp = client.post(
            "/api/v1/integrations/nonexistent/settings", json=payload
        )

        assert resp.status_code == 404
        body = resp.json()
        assert "error" in body

    def test_update_settings_invalid_path(self, tmp_path: Path) -> None:
        """Test updating settings with path outside allowed_paths."""
        mock_manager = MagicMock()
        mock_manager.get.return_value = MagicMock()

        # Path outside allowed_paths should be rejected
        payload = {"settings": {"vault_path": "/etc/passwd"}}

        _, client = _build_app(tmp_path, mock_integration_manager=mock_manager)
        resp = client.post(
            "/api/v1/integrations/obsidian/settings", json=payload
        )

        # Should get 403 from path validation (path not allowed)
        assert resp.status_code == 403


@pytest.mark.unit
class TestConnectIntegration:
    """Tests for POST /api/v1/integrations/{integration_name}/connect."""

    def test_connect_success(self, tmp_path: Path) -> None:
        """Test successfully connecting an integration."""
        mock_manager = MagicMock()
        mock_manager.get.return_value = MagicMock()
        mock_manager.connect = AsyncMock(return_value=True)

        _, client = _build_app(tmp_path, mock_integration_manager=mock_manager)
        resp = client.post("/api/v1/integrations/obsidian/connect")

        assert resp.status_code == 200
        body = resp.json()
        assert body["integration"] == "obsidian"
        assert body["connected"] is True

    def test_connect_missing_integration(self, tmp_path: Path) -> None:
        """Test connecting non-existent integration."""
        mock_manager = MagicMock()
        mock_manager.get.return_value = None

        _, client = _build_app(tmp_path, mock_integration_manager=mock_manager)
        resp = client.post("/api/v1/integrations/nonexistent/connect")

        assert resp.status_code == 404

    def test_connect_already_connected(self, tmp_path: Path) -> None:
        """Test connecting when already connected."""
        mock_manager = MagicMock()
        mock_manager.get.return_value = MagicMock()
        mock_manager.connect = AsyncMock(return_value=False)

        _, client = _build_app(tmp_path, mock_integration_manager=mock_manager)
        resp = client.post("/api/v1/integrations/obsidian/connect")

        assert resp.status_code == 200
        body = resp.json()
        assert body["connected"] is False


@pytest.mark.unit
class TestDisconnectIntegration:
    """Tests for POST /api/v1/integrations/{integration_name}/disconnect."""

    def test_disconnect_success(self, tmp_path: Path) -> None:
        """Test successfully disconnecting an integration."""
        mock_manager = MagicMock()
        mock_manager.get.return_value = MagicMock()
        mock_manager.disconnect = AsyncMock(return_value=True)

        _, client = _build_app(tmp_path, mock_integration_manager=mock_manager)
        resp = client.post("/api/v1/integrations/obsidian/disconnect")

        assert resp.status_code == 200
        body = resp.json()
        assert body["integration"] == "obsidian"
        assert body["connected"] is False

    def test_disconnect_missing_integration(self, tmp_path: Path) -> None:
        """Test disconnecting non-existent integration."""
        mock_manager = MagicMock()
        mock_manager.get.return_value = None

        _, client = _build_app(tmp_path, mock_integration_manager=mock_manager)
        resp = client.post("/api/v1/integrations/nonexistent/disconnect")

        assert resp.status_code == 404

    def test_disconnect_already_disconnected(self, tmp_path: Path) -> None:
        """Test disconnecting when already disconnected."""
        mock_manager = MagicMock()
        mock_manager.get.return_value = MagicMock()
        mock_manager.disconnect = AsyncMock(return_value=False)

        _, client = _build_app(tmp_path, mock_integration_manager=mock_manager)
        resp = client.post("/api/v1/integrations/obsidian/disconnect")

        assert resp.status_code == 200
        body = resp.json()
        assert body["connected"] is True


@pytest.mark.unit
class TestSendFileToIntegration:
    """Tests for POST /api/v1/integrations/{integration_name}/send."""

    def test_send_file_success(self, tmp_path: Path) -> None:
        """Test successfully sending a file to integration."""
        # Create a test file
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        mock_manager = MagicMock()
        mock_manager.get.return_value = MagicMock()
        mock_manager.send_file = AsyncMock(return_value=True)

        payload = {"path": str(test_file), "metadata": {"tag": "test"}}

        _, client = _build_app(tmp_path, mock_integration_manager=mock_manager)
        resp = client.post("/api/v1/integrations/obsidian/send", json=payload)

        assert resp.status_code == 200
        body = resp.json()
        assert body["integration"] == "obsidian"
        assert body["sent"] is True
        assert "path" in body

    def test_send_file_missing_integration(self, tmp_path: Path) -> None:
        """Test sending file to non-existent integration."""
        mock_manager = MagicMock()
        mock_manager.get.return_value = None

        payload = {"path": str(tmp_path / "test.txt"), "metadata": {}}

        _, client = _build_app(tmp_path, mock_integration_manager=mock_manager)
        resp = client.post(
            "/api/v1/integrations/nonexistent/send", json=payload
        )

        assert resp.status_code == 404

    def test_send_file_invalid_path(self, tmp_path: Path) -> None:
        """Test sending file with path outside allowed_paths."""
        mock_manager = MagicMock()
        mock_manager.get.return_value = MagicMock()

        payload = {"path": "/etc/passwd", "metadata": {}}

        _, client = _build_app(tmp_path, mock_integration_manager=mock_manager)
        resp = client.post(
            "/api/v1/integrations/obsidian/send", json=payload
        )

        # Should get 403 from path validation (path not allowed)
        assert resp.status_code == 403

    def test_send_file_with_metadata(self, tmp_path: Path) -> None:
        """Test sending file with metadata."""
        test_file = tmp_path / "document.pdf"
        test_file.write_text("pdf content")

        mock_manager = MagicMock()
        mock_manager.get.return_value = MagicMock()
        mock_manager.send_file = AsyncMock(return_value=True)

        payload = {
            "path": str(test_file),
            "metadata": {"category": "research", "date": "2026-03-03"},
        }

        _, client = _build_app(tmp_path, mock_integration_manager=mock_manager)
        resp = client.post(
            "/api/v1/integrations/vscode/send", json=payload
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["sent"] is True


@pytest.mark.unit
class TestBrowserExtensionConfig:
    """Tests for GET /api/v1/integrations/browser/config."""

    def test_get_browser_config_success(self, tmp_path: Path) -> None:
        """Test getting browser extension configuration."""
        mock_manager = MagicMock()
        mock_manager.get_config.return_value = {
            "allowed_origins": ["https://example.com"],
            "token_ttl_seconds": 3600,
        }

        _, client = _build_app(tmp_path, mock_browser_manager=mock_manager)
        resp = client.get("/api/v1/integrations/browser/config")

        assert resp.status_code == 200
        body = resp.json()
        assert "allowed_origins" in body
        assert "token_ttl_seconds" in body

    def test_browser_config_schema(self, tmp_path: Path) -> None:
        """Test browser config response schema."""
        mock_manager = MagicMock()
        mock_manager.get_config.return_value = {
            "allowed_origins": [],
            "token_ttl_seconds": 3600,
        }

        _, client = _build_app(tmp_path, mock_browser_manager=mock_manager)
        resp = client.get("/api/v1/integrations/browser/config")

        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, dict)


@pytest.mark.unit
class TestIssueBrowserToken:
    """Tests for POST /api/v1/integrations/browser/token."""

    def test_issue_token_success(self, tmp_path: Path) -> None:
        """Test successfully issuing a browser token."""
        mock_manager = MagicMock()
        expires_at = datetime.now(UTC) + timedelta(hours=1)
        mock_record = MagicMock()
        mock_record.token = "test-token-abc123"
        mock_record.expires_at = expires_at
        mock_manager.issue_token.return_value = mock_record

        payload = {"extension_id": "my-extension"}

        _, client = _build_app(tmp_path, mock_browser_manager=mock_manager)
        resp = client.post("/api/v1/integrations/browser/token", json=payload)

        assert resp.status_code == 200
        body = resp.json()
        assert "token" in body
        assert "expires_at" in body
        assert body["token"] == "test-token-abc123"

    def test_issue_token_schema(self, tmp_path: Path) -> None:
        """Test token issue response schema."""
        mock_manager = MagicMock()
        expires_at = datetime.now(UTC) + timedelta(hours=2)
        mock_record = MagicMock()
        mock_record.token = "token-value"
        mock_record.expires_at = expires_at
        mock_manager.issue_token.return_value = mock_record

        payload = {"extension_id": "chrome-ext-123"}

        _, client = _build_app(tmp_path, mock_browser_manager=mock_manager)
        resp = client.post("/api/v1/integrations/browser/token", json=payload)

        assert resp.status_code == 200
        body = resp.json()
        assert "token" in body
        assert "expires_at" in body
        assert isinstance(body["token"], str)
        assert isinstance(body["expires_at"], str)


@pytest.mark.unit
class TestVerifyBrowserToken:
    """Tests for POST /api/v1/integrations/browser/verify."""

    def test_verify_token_valid(self, tmp_path: Path) -> None:
        """Test verifying a valid browser token."""
        mock_manager = MagicMock()
        mock_manager.verify_token.return_value = True

        payload = {"token": "valid-token"}

        _, client = _build_app(tmp_path, mock_browser_manager=mock_manager)
        resp = client.post(
            "/api/v1/integrations/browser/verify", json=payload
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] is True

    def test_verify_token_invalid(self, tmp_path: Path) -> None:
        """Test verifying an invalid browser token."""
        mock_manager = MagicMock()
        mock_manager.verify_token.return_value = False

        payload = {"token": "invalid-token"}

        _, client = _build_app(tmp_path, mock_browser_manager=mock_manager)
        resp = client.post(
            "/api/v1/integrations/browser/verify", json=payload
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] is False

    def test_verify_token_expired(self, tmp_path: Path) -> None:
        """Test verifying an expired token."""
        mock_manager = MagicMock()
        mock_manager.verify_token.return_value = False

        payload = {"token": "expired-token"}

        _, client = _build_app(tmp_path, mock_browser_manager=mock_manager)
        resp = client.post(
            "/api/v1/integrations/browser/verify", json=payload
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] is False
