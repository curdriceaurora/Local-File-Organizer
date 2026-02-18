"""Unit tests for health check endpoint."""

from fastapi.testclient import TestClient

from file_organizer.api.main import create_app


def test_health_endpoint_returns_200():
    """Health check endpoint should return 200 OK status."""
    app = create_app()
    client = TestClient(app)

    response = client.get("/api/v1/health")

    assert response.status_code == 200


def test_health_endpoint_returns_json():
    """Health check endpoint should return JSON response."""
    app = create_app()
    client = TestClient(app)

    response = client.get("/api/v1/health")

    assert response.headers.get("content-type") is not None
    assert "application/json" in response.headers.get("content-type", "")


def test_health_endpoint_response_structure():
    """Health check endpoint should return expected JSON structure."""
    app = create_app()
    client = TestClient(app)

    response = client.get("/api/v1/health")
    data = response.json()

    assert "status" in data
    assert data["status"] == "healthy"
