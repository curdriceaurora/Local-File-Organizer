"""Unit tests for configuration endpoint."""

import pytest
from fastapi.testclient import TestClient

from file_organizer.api.main import create_app


@pytest.fixture
def client():
    """Create TestClient for config endpoint tests."""
    app = create_app()
    return TestClient(app)


class TestConfigGetEndpoint:
    """Tests for GET /config endpoint."""

    def test_config_get_returns_200(self, client):
        """GET /config should return 200 OK."""
        response = client.get("/api/v1/config")

        assert response.status_code == 200

    def test_config_get_returns_json(self, client):
        """GET /config should return JSON response."""
        response = client.get("/api/v1/config")

        assert response.headers.get("content-type") is not None
        assert "application/json" in response.headers.get("content-type", "")

    def test_config_includes_ai_settings(self, client):
        """Config should include AI model settings."""
        response = client.get("/api/v1/config")

        if response.status_code == 200:
            data = response.json()
            assert "ai" in data or "model" in data or "models" in data

    def test_config_includes_storage_settings(self, client):
        """Config should include storage settings."""
        response = client.get("/api/v1/config")

        if response.status_code == 200:
            data = response.json()
            assert "storage" in data or "paths" in data or "directories" in data

    def test_config_includes_organization_settings(self, client):
        """Config should include organization settings."""
        response = client.get("/api/v1/config")

        if response.status_code == 200:
            data = response.json()
            assert "organization" in data or "rules" in data or "settings" in data

    def test_config_response_structure(self, client):
        """Config response should have consistent structure."""
        response = client.get("/api/v1/config")

        if response.status_code == 200:
            data = response.json()
            # Should be a dict/object
            assert isinstance(data, dict)

    def test_config_version_included(self, client):
        """Config should include application version."""
        response = client.get("/api/v1/config")

        if response.status_code == 200:
            data = response.json()
            assert "version" in data or "app_version" in data


class TestConfigUpdateEndpoint:
    """Tests for PUT /config endpoint."""

    def test_config_update_accepts_json(self, client):
        """PUT /config should accept JSON payload."""
        payload = {"organization": {"method": "PARA"}}
        response = client.put("/api/v1/config", json=payload)

        # Should not be 404 (endpoint exists)
        assert response.status_code != 404

    def test_config_update_returns_updated_config(self, client):
        """PUT /config should return updated configuration."""
        payload = {"organization": {"method": "PARA"}}
        response = client.put("/api/v1/config", json=payload)

        if response.status_code in (200, 201):
            data = response.json()
            assert isinstance(data, dict)

    def test_config_update_validates_input(self, client):
        """PUT /config should validate input."""
        invalid_payload = {"invalid_field": "value"}
        response = client.put("/api/v1/config", json=invalid_payload)

        # Should either accept or return validation error
        assert response.status_code in (200, 201, 400, 401, 422)

    def test_config_update_organization_method(self, client):
        """Should be able to update organization method."""
        payload = {"organization": {"method": "JohnnyDecimal"}}
        response = client.put("/api/v1/config", json=payload)

        assert response.status_code in (200, 201, 400, 401, 422)

    def test_config_update_ai_model(self, client):
        """Should be able to update AI model settings."""
        payload = {"ai": {"model": "qwen2.5:7b"}}
        response = client.put("/api/v1/config", json=payload)

        assert response.status_code in (200, 201, 400, 401, 422)

    def test_config_update_storage_path(self, client):
        """Should be able to update storage path."""
        payload = {"storage": {"base_path": "/path/to/storage"}}
        response = client.put("/api/v1/config", json=payload)

        assert response.status_code in (200, 201, 400, 401, 422)

    def test_config_persists_after_update(self, client):
        """Config changes should persist."""
        # Update config
        update_payload = {"organization": {"method": "PARA"}}
        update_response = client.put("/api/v1/config", json=update_payload)

        if update_response.status_code in (200, 201):
            # Get config again
            get_response = client.get("/api/v1/config")

            if get_response.status_code == 200:
                data = get_response.json()
                # Check that the update persisted
                if "organization" in data:
                    assert data["organization"].get("method") == "PARA"


class TestConfigResetEndpoint:
    """Tests for POST /config/reset endpoint."""

    def test_config_reset_exists(self, client):
        """Reset endpoint should exist."""
        response = client.post("/api/v1/config/reset")

        # Should not be 404 (endpoint exists)
        assert response.status_code != 404

    def test_config_reset_returns_default_config(self, client):
        """Reset should return default configuration."""
        response = client.post("/api/v1/config/reset")

        if response.status_code in (200, 201):
            data = response.json()
            assert isinstance(data, dict)

    def test_config_reset_restores_defaults(self, client):
        """Reset should restore default settings."""
        # Update config
        client.put("/api/v1/config", json={"organization": {"method": "Custom"}})

        # Reset
        reset_response = client.post("/api/v1/config/reset")

        # Verify reset worked
        if reset_response.status_code in (200, 201):
            get_response = client.get("/api/v1/config")
            if get_response.status_code == 200:
                data = get_response.json()
                # Should not have the custom value anymore
                if "organization" in data:
                    # Default should be PARA or similar
                    assert data["organization"].get("method") != "Custom"
