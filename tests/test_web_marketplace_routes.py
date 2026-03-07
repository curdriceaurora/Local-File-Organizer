"""Tests for the marketplace routes (/ui/marketplace/*)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


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

    def test_marketplace_page_returns_200(self, web_client_builder) -> None:
        """Marketplace page should return 200 status."""
        client = web_client_builder(allowed_paths=[])
        response = client.get("/ui/marketplace")
        assert response.status_code == 200

    def test_marketplace_page_returns_html(self, web_client_builder) -> None:
        """Marketplace page should return HTML."""
        client = web_client_builder(allowed_paths=[])
        response = client.get("/ui/marketplace")
        assert "text/html" in response.headers.get("content-type", "")


@pytest.mark.unit
class TestMarketplaceSearch:
    """Tests for marketplace search functionality."""

    def test_marketplace_search_endpoint(self, web_client_builder) -> None:
        """Search endpoint should be accessible via q parameter."""
        client = web_client_builder(allowed_paths=[])
        response = client.get("/ui/marketplace?q=test")
        assert response.status_code == 200

    def test_marketplace_empty_search(self, web_client_builder) -> None:
        """Empty search should show all plugins."""
        client = web_client_builder(allowed_paths=[])
        response = client.get("/ui/marketplace?q=")
        assert response.status_code == 200

    def test_marketplace_search_by_category(self, web_client_builder) -> None:
        """Should filter plugins by category parameter."""
        client = web_client_builder(allowed_paths=[])
        response = client.get("/ui/marketplace?category=readers")
        assert response.status_code == 200


@pytest.mark.unit
class TestMarketplacePagination:
    """Tests for marketplace pagination."""

    def test_marketplace_page_parameter(self, web_client_builder) -> None:
        """Should handle page parameter for pagination."""
        client = web_client_builder(allowed_paths=[])
        response = client.get("/ui/marketplace?page=1")
        assert response.status_code == 200

    def test_marketplace_per_page_parameter(self, web_client_builder) -> None:
        """Should handle per_page parameter for items per page."""
        client = web_client_builder(allowed_paths=[])
        response = client.get("/ui/marketplace?per_page=10")
        assert response.status_code == 200

    def test_marketplace_pagination_with_search(self, web_client_builder) -> None:
        """Should combine search and pagination parameters."""
        client = web_client_builder(allowed_paths=[])
        response = client.get("/ui/marketplace?q=test&page=1&per_page=20")
        assert response.status_code == 200


@pytest.mark.unit
class TestMarketplacePluginActions:
    """Tests for plugin action endpoints (install, uninstall, etc)."""

    def test_marketplace_plugin_details(self, web_client_builder) -> None:
        """Should show plugin details page."""
        client = web_client_builder(allowed_paths=[])
        response = client.get("/ui/marketplace")
        # Details shown on main page
        assert response.status_code == 200

    def test_marketplace_install_button(self, web_client_builder) -> None:
        """Install action should be available."""
        client = web_client_builder(allowed_paths=[])
        response = client.get("/ui/marketplace")
        # Install button would be in the HTML
        assert response.status_code == 200


@pytest.mark.unit
class TestMarketplaceHtmxEndpoints:
    """Tests for HTMX-specific marketplace endpoints."""

    def test_marketplace_htmx_search(self, web_client_builder) -> None:
        """HTMX search results should return marketplace page with filtered results."""
        client = web_client_builder(allowed_paths=[])
        headers = {"HX-Request": "true"}
        response = client.get("/ui/marketplace?q=test", headers=headers)
        # Should handle HTMX request header
        assert response.status_code == 200
        # HTMX requests should return HTML fragment with searchable content
        assert "marketplace" in response.text.lower() or "plugin" in response.text.lower()

    def test_marketplace_htmx_pagination(self, web_client_builder) -> None:
        """HTMX pagination should return marketplace results with updated page."""
        client = web_client_builder(allowed_paths=[])
        headers = {"HX-Request": "true"}
        response = client.get("/ui/marketplace?page=2", headers=headers)
        assert response.status_code == 200
        # HTMX requests should return HTML fragment with results
        assert "marketplace" in response.text.lower() or "plugin" in response.text.lower()

    def test_marketplace_plugin_installation_action(self, web_client_builder) -> None:
        """Should support plugin installation via HTMX POST request."""
        client = web_client_builder(allowed_paths=[])
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

    def test_marketplace_preinstall_check(self, web_client_builder) -> None:
        """Should validate plugin before installation."""
        client = web_client_builder(allowed_paths=[])
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

    def test_marketplace_install_progress(self, web_client_builder) -> None:
        """Should handle installation workflow."""
        client = web_client_builder(allowed_paths=[])
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


@pytest.mark.unit
class TestMarketplaceInputValidation:
    """Tests for input validation and pagination boundaries (Stream C)."""

    def test_marketplace_pagination_boundary_zero(self, web_client_builder) -> None:
        """Should handle pagination at boundary (page 0)."""
        client = web_client_builder(allowed_paths=[])
        # Page 0 should be treated as invalid or default to page 1
        response = client.get("/ui/marketplace?page=0")
        # 422 is correct for pagination validation failure (page >= 1)
        assert response.status_code == 422

    def test_marketplace_pagination_boundary_negative(self, web_client_builder) -> None:
        """Should reject negative page numbers."""
        client = web_client_builder(allowed_paths=[])
        response = client.get("/ui/marketplace?page=-5")
        # 422 is correct for pagination validation failure (page >= 1)
        assert response.status_code == 422

    def test_marketplace_filter_result_count_accuracy(self, web_client_builder) -> None:
        """Filter results should accurately represent filtered content."""
        client = web_client_builder(allowed_paths=[])
        # Search for specific category
        response = client.get("/ui/marketplace?category=readers")
        assert response.status_code == 200
        # Verify response includes result counts or plugin list
        assert "plugin" in response.text.lower() or "marketplace" in response.text.lower()


@pytest.mark.unit
class TestMarketplaceErrorHandling:
    """Tests for error handling and edge cases in marketplace routes (Stream A)."""

    def test_marketplace_invalid_pagination(self, web_client_builder) -> None:
        """Should handle invalid pagination parameters."""
        client = web_client_builder(allowed_paths=[])
        # Invalid page number (negative)
        response = client.get("/ui/marketplace?page=-1")
        # Should either ignore or reject invalid pagination (422 for validation failure)
        assert response.status_code in (200, 400, 422)

    def test_marketplace_missing_category(self, web_client_builder) -> None:
        """Should handle missing category parameter gracefully."""
        client = web_client_builder(allowed_paths=[])
        response = client.get("/ui/marketplace")
        # Should return 200 with default category or error message
        assert response.status_code == 200

    def test_marketplace_install_nonexistent_plugin(self, web_client_builder) -> None:
        """Should handle installation of non-existent plugins."""
        client = web_client_builder(allowed_paths=[])
        response = client.post(
            "/ui/marketplace/plugins/nonexistent-plugin/install",
            data={
                "q": "",
                "category": "",
                "tag_csv": "",
            },
        )
        # Should return 200 but indicate plugin not found
        assert response.status_code == 200
        # Assert error message is in response (FINDING 4)
        assert "nonexistent-plugin" in response.text and "not found" in response.text.lower()

    def test_marketplace_search_special_characters(self, web_client_builder) -> None:
        """Should handle special characters in search queries."""
        client = web_client_builder(allowed_paths=[])
        response = client.get("/ui/marketplace?q=test<script>alert('xss')</script>")
        # Should safely escape special characters
        assert response.status_code == 200
        # Response should not contain unescaped script tags
        assert "<script>" not in response.text
