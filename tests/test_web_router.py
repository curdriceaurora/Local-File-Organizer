"""Tests for the web UI router (routes at /ui/ prefix).

NOTE: This module tests the web router initialization and basic /ui/ route
accessibility. For comprehensive web route tests, see tests/web/ directory.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from file_organizer.api.main import create_app
from file_organizer.api.test_utils import build_test_settings


def _build_client(tmp_path: Path, auth_enabled: bool = False) -> TestClient:
    """Create a test client with the full FastAPI app."""
    settings = build_test_settings(
        tmp_path,
        allowed_paths=[],
        auth_overrides={"auth_enabled": auth_enabled},
    )
    app = create_app(settings)
    return TestClient(app)


@pytest.mark.unit
class TestHomeRoute:
    """Tests for the home page route."""

    def test_home_page_returns_200(self, tmp_path: Path) -> None:
        """Web home page should return 200 status."""
        client = _build_client(tmp_path)
        response = client.get("/ui/")
        assert response.status_code == 200

    def test_home_page_returns_html(self, tmp_path: Path) -> None:
        """Web home page should return HTML content."""
        client = _build_client(tmp_path)
        response = client.get("/ui/")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    def test_home_page_renders_template(self, tmp_path: Path) -> None:
        """Web home page should render the base template with expected HTML structure."""
        client = _build_client(tmp_path)
        response = client.get("/ui/")
        assert response.status_code == 200
        # Check for common HTML structural elements
        assert any(tag in response.text for tag in ("<!DOCTYPE html", "<html", "<head", "<body"))

    def test_home_page_with_auth_disabled(self, tmp_path: Path) -> None:
        """Web home page works with auth disabled."""
        client = _build_client(tmp_path, auth_enabled=False)
        response = client.get("/ui/")
        assert response.status_code == 200

    def test_home_page_with_auth_enabled(self, tmp_path: Path) -> None:
        """Web home page accessible with auth enabled."""
        client = _build_client(tmp_path, auth_enabled=True)
        response = client.get("/ui/")
        # May redirect to login or show home - either is acceptable
        assert response.status_code in [200, 303]


@pytest.mark.unit
class TestErrorPages:
    """Tests for error page handling."""

    def test_nonexistent_path_returns_404(self, tmp_path: Path) -> None:
        """Requesting nonexistent path should return 404."""
        client = _build_client(tmp_path)
        response = client.get("/ui/nonexistent/path/that/does/not/exist")
        assert response.status_code == 404

    def test_404_returns_valid_response(self, tmp_path: Path) -> None:
        """404 error should return valid response with appropriate content type."""
        client = _build_client(tmp_path)
        response = client.get("/ui/invalid")
        assert response.status_code == 404
        # FastAPI may return JSON or HTML depending on error handler configuration
        content_type = response.headers.get("content-type", "")
        assert "json" in content_type or "html" in content_type


@pytest.mark.unit
class TestRouterSetup:
    """Tests for router initialization and configuration."""

    def test_app_creates_successfully(self, tmp_path: Path) -> None:
        """App should initialize without errors."""
        settings = build_test_settings(tmp_path, allowed_paths=[])
        app = create_app(settings)
        assert app is not None

    def test_client_can_make_requests(self, tmp_path: Path) -> None:
        """Test client should be able to make requests to web routes."""
        client = _build_client(tmp_path)
        response = client.get("/ui/")
        assert response.status_code in [200, 303]  # Allow redirect for auth
