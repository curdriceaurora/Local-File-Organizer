"""Tests for the API health endpoint."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_settings
from file_organizer.api.main import create_app

pytestmark = pytest.mark.ci


def test_health_endpoint_returns_status() -> None:
    settings = ApiSettings(environment="test", enable_docs=False)
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["environment"] == "test"
    assert "timestamp" in payload
