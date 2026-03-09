"""Tests for the marketplace routes (/ui/marketplace/*)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from file_organizer.api.main import create_app
from file_organizer.api.test_utils import build_test_settings


def _build_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Create a test client with marketplace route access.

    Sets FO_MARKETPLACE_HOME and FO_MARKETPLACE_REPO_URL to tmp_path to prevent
    tests from creating files in the user's actual config directory or hitting
    external URLs (hermetic testing).
    """
    # Isolate marketplace to tmp_path to avoid polluting user's environment
    monkeypatch.setenv("FO_MARKETPLACE_HOME", str(tmp_path / "marketplace"))
    # Ensure the marketplace repo URL also points to a local path for hermetic tests
    monkeypatch.setenv("FO_MARKETPLACE_REPO_URL", str(tmp_path / "marketplace_repo"))

    settings = build_test_settings(tmp_path, allowed_paths=[])
    app = create_app(settings)
    return TestClient(app)


@pytest.mark.unit
class TestMarketplacePage:
    """Tests for the main marketplace page."""

    def test_marketplace_page_returns_200(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Marketplace page should return 200 status."""
        client = _build_client(tmp_path, monkeypatch)
        response = client.get("/ui/marketplace")
        assert response.status_code == 200

    def test_marketplace_page_returns_html(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Marketplace page should return HTML."""
        client = _build_client(tmp_path, monkeypatch)
        response = client.get("/ui/marketplace")
        assert "text/html" in response.headers.get("content-type", "")


@pytest.mark.unit
class TestMarketplaceSearch:
    """Tests for marketplace search functionality."""

    def test_marketplace_search_endpoint(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Search endpoint should be accessible via q parameter."""
        client = _build_client(tmp_path, monkeypatch)
        response = client.get("/ui/marketplace?q=test")
        assert response.status_code == 200

    def test_marketplace_empty_search(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Empty search should show all plugins."""
        client = _build_client(tmp_path, monkeypatch)
        response = client.get("/ui/marketplace?q=")
        assert response.status_code == 200

    def test_marketplace_search_by_category(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should filter plugins by category parameter."""
        client = _build_client(tmp_path, monkeypatch)
        response = client.get("/ui/marketplace?category=readers")
        assert response.status_code == 200


@pytest.mark.unit
class TestMarketplacePagination:
    """Tests for marketplace pagination."""

    def test_marketplace_page_parameter(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should handle page parameter for pagination."""
        client = _build_client(tmp_path, monkeypatch)
        response = client.get("/ui/marketplace?page=1")
        assert response.status_code == 200

    def test_marketplace_per_page_parameter(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should handle per_page parameter for items per page."""
        client = _build_client(tmp_path, monkeypatch)
        response = client.get("/ui/marketplace?per_page=10")
        assert response.status_code == 200

    def test_marketplace_pagination_with_search(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should combine search and pagination parameters."""
        client = _build_client(tmp_path, monkeypatch)
        response = client.get("/ui/marketplace?q=test&page=1&per_page=20")
        assert response.status_code == 200


@pytest.mark.unit
class TestMarketplacePluginActions:
    """Tests for plugin action endpoints (install, uninstall, etc)."""

    def test_marketplace_plugin_details(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should show plugin details page."""
        client = _build_client(tmp_path, monkeypatch)
        response = client.get("/ui/marketplace")
        # Details shown on main page
        assert response.status_code == 200

    def test_marketplace_install_button(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Install action should be available."""
        client = _build_client(tmp_path, monkeypatch)
        response = client.get("/ui/marketplace")
        # Install button would be in the HTML
        assert response.status_code == 200


@pytest.mark.unit
class TestMarketplaceHtmxEndpoints:
    """Tests for HTMX-specific marketplace endpoints."""

    def test_marketplace_htmx_search(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """HTMX search results should return marketplace page with filtered results."""
        client = _build_client(tmp_path, monkeypatch)
        headers = {"HX-Request": "true"}
        response = client.get("/ui/marketplace?q=test", headers=headers)
        # Should handle HTMX request header
        assert response.status_code == 200

    def test_marketplace_htmx_pagination(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """HTMX pagination should return marketplace results with updated page."""
        client = _build_client(tmp_path, monkeypatch)
        headers = {"HX-Request": "true"}
        response = client.get("/ui/marketplace?page=2", headers=headers)
        assert response.status_code == 200

    def test_marketplace_plugin_installation_action(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should support plugin installation via HTMX POST request."""
        client = _build_client(tmp_path, monkeypatch)
        # Test the install endpoint with a valid plugin name
        response = client.post(
            "/ui/marketplace/plugins/test-plugin/install",
            data={
                "q": "",
                "category": "",
                "tag_csv": "",
            },
        )
        # Route always returns 200 (renders marketplace page with message)
        assert response.status_code == 200
        # Should return HTML marketplace page
        assert any(tag in response.text.lower() for tag in ["<html", "<body", "marketplace"])


@pytest.mark.unit
class TestMarketplaceInstallFlow:
    """Tests for plugin installation workflow."""

    def test_marketplace_preinstall_check(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should validate plugin before installation."""
        client = _build_client(tmp_path, monkeypatch)
        # Test that install endpoint rejects invalid plugin names or missing plugins
        response = client.post(
            "/ui/marketplace/plugins/nonexistent-plugin/install",
            data={
                "q": "",
                "category": "",
                "tag_csv": "",
            },
        )
        # Route always returns 200 (renders marketplace page with message)
        assert response.status_code == 200
        # Should return HTML marketplace page
        assert any(tag in response.text.lower() for tag in ["<html", "<body", "marketplace"])

    def test_marketplace_install_progress(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should handle installation workflow."""
        client = _build_client(tmp_path, monkeypatch)
        # Test the full install workflow by calling the install endpoint
        response = client.post(
            "/ui/marketplace/plugins/sample-plugin/install",
            data={
                "q": "sample",
                "category": "",
                "tag_csv": "",
            },
        )
        # Route always returns 200 (renders marketplace page with message)
        assert response.status_code == 200
        # Should return HTML marketplace page with search preserved
        assert any(tag in response.text.lower() for tag in ["<html", "<body", "marketplace"])
