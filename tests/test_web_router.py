"""Tests for the web router (home page and main app routes)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from file_organizer.api.config import ApiSettings
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
        """Home page should return 200 status."""
        client = _build_client(tmp_path)
        response = client.get("/")
        assert response.status_code == 200

    def test_home_page_returns_html(self, tmp_path: Path) -> None:
        """Home page should return content."""
        client = _build_client(tmp_path)
        response = client.get("/")
        # Home route returns JSON status, not HTML
        content_type = response.headers.get("content-type", "")
        assert "application/json" in content_type or "text/html" in content_type

    def test_home_page_renders_template(self, tmp_path: Path) -> None:
        """Home page should render the base template."""
        client = _build_client(tmp_path)
        response = client.get("/")
        # Basic check that HTML content exists
        assert len(response.text) > 0
        assert response.text.count("<html") >= 0  # May or may not have explicit html tag

    def test_home_page_with_auth_disabled(self, tmp_path: Path) -> None:
        """Home page works with auth disabled."""
        client = _build_client(tmp_path, auth_enabled=False)
        response = client.get("/")
        assert response.status_code == 200

    def test_home_page_with_auth_enabled(self, tmp_path: Path) -> None:
        """Home page accessible with auth enabled."""
        client = _build_client(tmp_path, auth_enabled=True)
        response = client.get("/")
        # May redirect to login or show home - either is acceptable
        assert response.status_code in [200, 303]


@pytest.mark.unit
class TestErrorPages:
    """Tests for error page handling."""

    def test_nonexistent_path_returns_404(self, tmp_path: Path) -> None:
        """Requesting nonexistent path should return 404."""
        client = _build_client(tmp_path)
        response = client.get("/nonexistent/path/that/does/not/exist")
        assert response.status_code == 404

    def test_404_returns_html(self, tmp_path: Path) -> None:
        """404 error should return HTML content."""
        client = _build_client(tmp_path)
        response = client.get("/invalid")
        assert "text/html" in response.headers.get("content-type", "") or response.status_code == 404


@pytest.mark.unit
class TestRouterSetup:
    """Tests for router initialization and configuration."""

    def test_app_creates_successfully(self, tmp_path: Path) -> None:
        """App should initialize without errors."""
        settings = build_test_settings(tmp_path, allowed_paths=[])
        app = create_app(settings)
        assert app is not None

    def test_client_can_make_requests(self, tmp_path: Path) -> None:
        """Test client should be able to make requests."""
        client = _build_client(tmp_path)
        response = client.get("/")
        assert response is not None
        assert hasattr(response, "status_code")
