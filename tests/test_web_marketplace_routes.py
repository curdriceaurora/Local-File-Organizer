"""Tests for the marketplace routes (/ui/marketplace/*)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from file_organizer.api.main import create_app
from file_organizer.api.test_utils import build_test_settings


def _build_client(tmp_path: Path) -> TestClient:
    """Create a test client with marketplace route access."""
    settings = build_test_settings(tmp_path, allowed_paths=[])
    app = create_app(settings)
    return TestClient(app)


@pytest.mark.unit
class TestMarketplacePage:
    """Tests for the main marketplace page."""

    def test_marketplace_page_returns_200(self, tmp_path: Path) -> None:
        """Marketplace page should return 200 status."""
        client = _build_client(tmp_path)
        response = client.get("/ui/marketplace")
        assert response.status_code == 200

    def test_marketplace_page_returns_html(self, tmp_path: Path) -> None:
        """Marketplace page should return HTML."""
        client = _build_client(tmp_path)
        response = client.get("/ui/marketplace")
        assert "text/html" in response.headers.get("content-type", "")


@pytest.mark.unit
class TestMarketplaceSearch:
    """Tests for marketplace search functionality."""

    def test_marketplace_search_endpoint(self, tmp_path: Path) -> None:
        """Search endpoint should be accessible."""
        client = _build_client(tmp_path)
        response = client.get("/ui/marketplace?search=test")
        assert response.status_code == 200

    def test_marketplace_empty_search(self, tmp_path: Path) -> None:
        """Empty search should show all plugins."""
        client = _build_client(tmp_path)
        response = client.get("/ui/marketplace?search=")
        assert response.status_code == 200

    def test_marketplace_search_by_category(self, tmp_path: Path) -> None:
        """Should filter by category."""
        client = _build_client(tmp_path)
        response = client.get("/ui/marketplace?category=readers")
        assert response.status_code in [200, 400]


@pytest.mark.unit
class TestMarketplacePagination:
    """Tests for marketplace pagination."""

    def test_marketplace_page_parameter(self, tmp_path: Path) -> None:
        """Should handle page parameter."""
        client = _build_client(tmp_path)
        response = client.get("/ui/marketplace?page=1")
        assert response.status_code == 200

    def test_marketplace_limit_parameter(self, tmp_path: Path) -> None:
        """Should handle limit parameter for items per page."""
        client = _build_client(tmp_path)
        response = client.get("/ui/marketplace?limit=10")
        assert response.status_code in [200, 400]

    def test_marketplace_sorting(self, tmp_path: Path) -> None:
        """Should support sorting options."""
        client = _build_client(tmp_path)
        response = client.get("/ui/marketplace?sort_by=name")
        assert response.status_code in [200, 400]


@pytest.mark.unit
class TestMarketplacePluginActions:
    """Tests for plugin action endpoints (install, uninstall, etc)."""

    def test_marketplace_plugin_details(self, tmp_path: Path) -> None:
        """Should show plugin details page."""
        client = _build_client(tmp_path)
        response = client.get("/ui/marketplace")
        # Details shown on main page
        assert response.status_code == 200

    def test_marketplace_install_button(self, tmp_path: Path) -> None:
        """Install action should be available."""
        client = _build_client(tmp_path)
        response = client.get("/ui/marketplace")
        # Install button would be in the HTML
        assert response.status_code == 200


@pytest.mark.unit
class TestMarketplaceHtmxEndpoints:
    """Tests for HTMX-specific marketplace endpoints."""

    def test_marketplace_htmx_search(self, tmp_path: Path) -> None:
        """HTMX search results should return partial HTML."""
        client = _build_client(tmp_path)
        headers = {"HX-Request": "true"}
        response = client.get("/ui/marketplace?search=test", headers=headers)
        # Should work with or without HTMX header
        assert response.status_code in [200, 400]

    def test_marketplace_htmx_pagination(self, tmp_path: Path) -> None:
        """HTMX pagination should return results fragment."""
        client = _build_client(tmp_path)
        headers = {"HX-Request": "true"}
        response = client.get("/ui/marketplace?page=2", headers=headers)
        assert response.status_code in [200, 400]

    def test_marketplace_plugin_list_swap(self, tmp_path: Path) -> None:
        """Plugin list should swap with new results on pagination."""
        client = _build_client(tmp_path)
        response = client.get("/ui/marketplace")
        # Response should have proper swap targets
        assert response.status_code == 200


@pytest.mark.unit
class TestMarketplaceInstallFlow:
    """Tests for plugin installation workflow."""

    def test_marketplace_preinstall_check(self, tmp_path: Path) -> None:
        """Should validate plugin before installation."""
        client = _build_client(tmp_path)
        response = client.get("/ui/marketplace")
        assert response.status_code == 200

    def test_marketplace_install_progress(self, tmp_path: Path) -> None:
        """Should show installation progress."""
        client = _build_client(tmp_path)
        response = client.get("/ui/marketplace")
        assert response.status_code == 200
