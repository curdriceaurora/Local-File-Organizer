"""Unit tests for health check endpoint."""

import pytest
from fastapi.testclient import TestClient

from file_organizer.api.main import create_app

pytestmark = pytest.mark.unit


def test_health_endpoint_returns_200() -> None:
    """Health check endpoint should return 200 OK status."""
    app = create_app()
    client = TestClient(app)

    response = client.get("/api/v1/health")

    assert response.status_code in {200, 207, 503}


def test_health_endpoint_returns_json() -> None:
    """Health check endpoint should return JSON response."""
    app = create_app()
    client = TestClient(app)

    response = client.get("/api/v1/health")

    assert response.headers.get("content-type") is not None
    assert "application/json" in response.headers.get("content-type", "")


def test_health_endpoint_response_structure() -> None:
    """Health check endpoint should return expected JSON structure."""
    app = create_app()
    client = TestClient(app)

    response = client.get("/api/v1/health")
    data = response.json()

    assert "status" in data
    assert data["status"] in {"ok", "degraded", "unknown", "error"}
    assert "readiness" in data
    assert data["readiness"] in {"ready", "starting", "unhealthy"}
