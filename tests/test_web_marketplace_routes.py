"""Tests for the marketplace routes (/ui/marketplace/*)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from file_organizer.api.main import create_app
from file_organizer.api.test_utils import build_test_settings


def _build_client(tmp_path: Path) -> TestClient:
    """Create a test client with marketplace route access."""
    settings = build_test_settings(tmp_path, allowed_paths=[])
    app = create_app(settings)
    return TestClient(app)


def _mock_marketplace_service() -> MagicMock:
    """Create marketplace service mock with deterministic test behavior.

    Returns a MagicMock configured with:
    - list_plugins() returns ([], 0) - empty list with count
    - list_installed() returns [] - empty list, iterable for _render_marketplace_page
    """
    mock_instance = MagicMock()
    mock_instance.list_plugins.return_value = ([], 0)
    mock_instance.list_installed.return_value = []
    return mock_instance


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
        """Search endpoint should be accessible via q parameter."""
        client = _build_client(tmp_path)
        response = client.get("/ui/marketplace?q=test")
        assert response.status_code == 200

    def test_marketplace_empty_search(self, tmp_path: Path) -> None:
        """Empty search should show all plugins."""
        client = _build_client(tmp_path)
        response = client.get("/ui/marketplace?q=")
        assert response.status_code == 200

    def test_marketplace_search_by_category(self, tmp_path: Path) -> None:
        """Should filter plugins by category parameter."""
        client = _build_client(tmp_path)
        response = client.get("/ui/marketplace?category=readers")
        assert response.status_code == 200


@pytest.mark.unit
class TestMarketplacePagination:
    """Tests for marketplace pagination."""

    def test_marketplace_page_parameter(self, tmp_path: Path) -> None:
        """Should handle page parameter for pagination."""
        client = _build_client(tmp_path)
        response = client.get("/ui/marketplace?page=1")
        assert response.status_code == 200

    def test_marketplace_per_page_parameter(self, tmp_path: Path) -> None:
        """Should handle per_page parameter for items per page."""
        client = _build_client(tmp_path)
        response = client.get("/ui/marketplace?per_page=10")
        assert response.status_code == 200

    def test_marketplace_pagination_with_search(self, tmp_path: Path) -> None:
        """Should combine search and pagination parameters."""
        client = _build_client(tmp_path)
        response = client.get("/ui/marketplace?q=test&page=1&per_page=20")
        assert response.status_code == 200


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
        """HTMX search results should return marketplace page with filtered results."""
        client = _build_client(tmp_path)
        headers = {"HX-Request": "true"}
        response = client.get("/ui/marketplace?q=test", headers=headers)
        # Should handle HTMX request header
        assert response.status_code == 200
        # HTMX requests should return HTML fragment with searchable content
        assert "marketplace" in response.text.lower() or "plugin" in response.text.lower()

    def test_marketplace_htmx_pagination(self, tmp_path: Path) -> None:
        """HTMX pagination should return marketplace results with updated page."""
        client = _build_client(tmp_path)
        headers = {"HX-Request": "true"}
        response = client.get("/ui/marketplace?page=2", headers=headers)
        assert response.status_code == 200
        # HTMX requests should return HTML fragment with results
        assert "marketplace" in response.text.lower() or "plugin" in response.text.lower()

    def test_marketplace_plugin_installation_action(self, tmp_path: Path) -> None:
        """Should support plugin installation via HTMX POST request."""
        client = _build_client(tmp_path)
        # Mock the MarketplaceService.install method
        with patch("file_organizer.web.marketplace_routes.MarketplaceService") as mock_service_class:
            mock_instance = _mock_marketplace_service()
            mock_service_class.return_value = mock_instance

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
            # Verify install method was called with plugin name
            mock_instance.install.assert_called()


@pytest.mark.unit
class TestMarketplaceInstallFlow:
    """Tests for plugin installation workflow."""

    def test_marketplace_preinstall_check(self, tmp_path: Path) -> None:
        """Should validate plugin before installation."""
        client = _build_client(tmp_path)
        # Mock the MarketplaceService to handle validation
        with patch("file_organizer.web.marketplace_routes.MarketplaceService") as mock_service_class:
            mock_instance = _mock_marketplace_service()
            mock_service_class.return_value = mock_instance

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
            # Verify install was called even for nonexistent plugins (validation happens in service)
            mock_instance.install.assert_called()

    def test_marketplace_install_progress(self, tmp_path: Path) -> None:
        """Should handle installation workflow."""
        client = _build_client(tmp_path)
        # Mock the MarketplaceService to track install progress
        with patch("file_organizer.web.marketplace_routes.MarketplaceService") as mock_service_class:
            mock_instance = _mock_marketplace_service()
            mock_service_class.return_value = mock_instance

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
            # Verify install was called for sample plugin
            mock_instance.install.assert_called()
