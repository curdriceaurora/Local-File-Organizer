"""Tests for the configuration API router."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from file_organizer.api.auth_models import User
from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import (
    get_current_active_user,
    get_settings,
)
from file_organizer.api.exceptions import setup_exception_handlers
from file_organizer.api.routers.config import ConfigResponse, router


def _build_app(admin_user: User | None = None, auth_enabled: bool = False) -> tuple[FastAPI, TestClient]:
    """Create a FastAPI app with config router and dependency overrides."""
    settings = ApiSettings(
        environment="test",
        auth_enabled=auth_enabled,
    )
    app = FastAPI()
    setup_exception_handlers(app)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_current_active_user] = lambda: admin_user
    app.include_router(router, prefix="/api/v1")
    client = TestClient(app)
    return app, client


@pytest.fixture(autouse=True)
def _reset_config() -> None:
    """Reset global config state before each test."""
    import file_organizer.api.routers.config as config_module

    config_module._config = ConfigResponse()


# ---------------------------------------------------------------------------
# get_config endpoint
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetConfig:
    """Tests for GET /api/v1/config."""

    def test_get_config_default(self) -> None:
        """Test getting default configuration."""
        _, client = _build_app()

        resp = client.get("/api/v1/config")
        assert resp.status_code == 200
        body = resp.json()
        assert body["version"] == "2.0.0"
        assert "ai" in body
        assert "storage" in body
        assert "organization" in body
        assert body["ai"]["model"] == "qwen2.5:3b-instruct-q4_K_M"
        assert body["storage"]["auto_backup"] is True
        assert body["organization"]["method"] == "PARA"

    def test_get_config_schema(self) -> None:
        """Test config response has correct schema."""
        _, client = _build_app()

        resp = client.get("/api/v1/config")
        assert resp.status_code == 200
        body = resp.json()

        # Verify structure
        assert isinstance(body["ai"], dict)
        assert isinstance(body["storage"], dict)
        assert isinstance(body["organization"], dict)

        # Verify AI settings schema
        assert "model" in body["ai"]
        assert "temperature" in body["ai"]
        assert "max_tokens" in body["ai"]

        # Verify storage settings schema
        assert "base_path" in body["storage"]
        assert "auto_backup" in body["storage"]

        # Verify organization settings schema
        assert "method" in body["organization"]
        assert "auto_organize" in body["organization"]


# ---------------------------------------------------------------------------
# update_config endpoint
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUpdateConfig:
    """Tests for PUT /api/v1/config."""

    def test_update_config_requires_admin(self) -> None:
        """Test that only admin users can update config."""
        # Non-admin user
        non_admin = MagicMock(spec=User)
        non_admin.is_admin = False
        non_admin.is_active = True
        _, client = _build_app(admin_user=non_admin, auth_enabled=True)

        update_payload = {
            "ai": {
                "model": "qwen2.5:7b",
                "temperature": 0.7,
                "max_tokens": 5000,
            }
        }
        resp = client.put("/api/v1/config", json=update_payload)
        assert resp.status_code in [401, 403]

    def test_update_config_ai_settings(self) -> None:
        """Test updating AI settings."""
        # Admin user
        admin = MagicMock(spec=User)
        admin.is_admin = True
        admin.is_active = True
        _, client = _build_app(admin_user=admin)

        update_payload = {
            "ai": {
                "model": "custom-model",
                "temperature": 0.8,
                "max_tokens": 4000,
            }
        }
        resp = client.put("/api/v1/config", json=update_payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["ai"]["model"] == "custom-model"
        assert body["ai"]["temperature"] == 0.8
        assert body["ai"]["max_tokens"] == 4000

    def test_update_config_storage_settings(self) -> None:
        """Test updating storage settings."""
        admin = MagicMock(spec=User)
        admin.is_admin = True
        admin.is_active = True
        _, client = _build_app(admin_user=admin)

        update_payload = {
            "storage": {
                "base_path": "/new/storage/path",
                "auto_backup": False,
            }
        }
        resp = client.put("/api/v1/config", json=update_payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["storage"]["base_path"] == "/new/storage/path"
        assert body["storage"]["auto_backup"] is False

    def test_update_config_organization_settings(self) -> None:
        """Test updating organization settings."""
        admin = MagicMock(spec=User)
        admin.is_admin = True
        admin.is_active = True
        _, client = _build_app(admin_user=admin)

        update_payload = {
            "organization": {
                "method": "JOHNNY_DECIMAL",
                "auto_organize": True,
            }
        }
        resp = client.put("/api/v1/config", json=update_payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["organization"]["method"] == "JOHNNY_DECIMAL"
        assert body["organization"]["auto_organize"] is True

    def test_update_config_partial_update(self) -> None:
        """Test partial config update preserves other settings."""
        admin = MagicMock(spec=User)
        admin.is_admin = True
        admin.is_active = True
        _, client = _build_app(admin_user=admin)

        # Update only AI settings
        update_payload = {
            "ai": {
                "model": "updated-model",
                "temperature": 0.6,
                "max_tokens": 2000,
            }
        }
        resp = client.put("/api/v1/config", json=update_payload)
        assert resp.status_code == 200
        body = resp.json()

        # Verify AI was updated
        assert body["ai"]["model"] == "updated-model"

        # Verify storage and organization remain default
        assert body["storage"]["auto_backup"] is True
        assert body["organization"]["method"] == "PARA"

    def test_update_config_empty_request(self) -> None:
        """Test update with no changes."""
        admin = MagicMock(spec=User)
        admin.is_admin = True
        admin.is_active = True
        _, client = _build_app(admin_user=admin)

        update_payload = {}
        resp = client.put("/api/v1/config", json=update_payload)
        assert resp.status_code == 200
        body = resp.json()
        # Should return current config unchanged
        assert body["version"] == "2.0.0"

    def test_update_config_multiple_sections(self) -> None:
        """Test updating multiple config sections at once."""
        admin = MagicMock(spec=User)
        admin.is_admin = True
        admin.is_active = True
        _, client = _build_app(admin_user=admin)

        update_payload = {
            "ai": {"model": "new-model", "temperature": 0.7, "max_tokens": 3500},
            "storage": {"base_path": "/path", "auto_backup": False},
            "organization": {"method": "CUSTOM", "auto_organize": True},
        }
        resp = client.put("/api/v1/config", json=update_payload)
        assert resp.status_code == 200
        body = resp.json()

        assert body["ai"]["model"] == "new-model"
        assert body["storage"]["auto_backup"] is False
        assert body["organization"]["method"] == "CUSTOM"


# ---------------------------------------------------------------------------
# reset_config endpoint
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestResetConfig:
    """Tests for POST /api/v1/config/reset."""

    def test_reset_config_requires_admin(self) -> None:
        """Test that only admin users can reset config."""
        non_admin = MagicMock(spec=User)
        non_admin.is_admin = False
        non_admin.is_active = True
        _, client = _build_app(admin_user=non_admin, auth_enabled=True)

        resp = client.post("/api/v1/config/reset")
        assert resp.status_code in [401, 403]

    def test_reset_config_to_defaults(self) -> None:
        """Test resetting config to defaults."""
        admin = MagicMock(spec=User)
        admin.is_admin = True
        admin.is_active = True
        _, client = _build_app(admin_user=admin)

        # First update config
        update_payload = {
            "ai": {"model": "custom", "temperature": 0.9, "max_tokens": 9000},
            "storage": {"base_path": "/custom/path", "auto_backup": False},
        }
        resp = client.put("/api/v1/config", json=update_payload)
        assert resp.status_code == 200

        # Now reset
        resp = client.post("/api/v1/config/reset")
        assert resp.status_code == 200
        body = resp.json()

        # Verify reset to defaults
        assert body["ai"]["model"] == "qwen2.5:3b-instruct-q4_K_M"
        assert body["ai"]["temperature"] == 0.5
        assert body["ai"]["max_tokens"] == 3000
        assert body["storage"]["base_path"] == "/default/path"
        assert body["storage"]["auto_backup"] is True
        assert body["organization"]["method"] == "PARA"

    def test_reset_config_returns_correct_schema(self) -> None:
        """Test reset returns properly formatted config."""
        admin = MagicMock(spec=User)
        admin.is_admin = True
        admin.is_active = True
        _, client = _build_app(admin_user=admin)

        resp = client.post("/api/v1/config/reset")
        assert resp.status_code == 200
        body = resp.json()

        assert body["version"] == "2.0.0"
        assert "ai" in body
        assert "storage" in body
        assert "organization" in body
        assert body["app_version"] == "2.0.0"
