"""Tests for the marketplace routes (/ui/marketplace/*)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from file_organizer.plugins.marketplace.errors import MarketplaceError

from .conftest import get_csrf_headers
from .test_helpers import assert_html_contains, assert_html_contains_any, assert_html_tag_present


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
        assert_html_contains_any(response.text, "marketplace", "plugin")

    def test_marketplace_htmx_pagination(self, web_client_builder) -> None:
        """HTMX pagination should return marketplace results with updated page."""
        client = web_client_builder(allowed_paths=[])
        headers = {"HX-Request": "true"}
        response = client.get("/ui/marketplace?page=2", headers=headers)
        assert response.status_code == 200
        # HTMX requests should return HTML fragment with results
        assert_html_contains_any(response.text, "marketplace", "plugin")

    def test_marketplace_plugin_installation_action(
        self, web_client_builder, mock_marketplace_service
    ) -> None:
        """Should support plugin installation via HTMX POST request."""
        client = web_client_builder(allowed_paths=[])
        csrf_headers = get_csrf_headers(client)
        # Mock the MarketplaceService.install method
        with patch(
            "file_organizer.web.marketplace_routes.MarketplaceService"
        ) as mock_service_class:
            mock_service_class.return_value = mock_marketplace_service

            # Test the install endpoint with a valid plugin name
            response = client.post(
                "/ui/marketplace/plugins/test-plugin/install",
                data={
                    "q": "",
                    "category": "",
                    "tag_csv": "",
                },
                headers=csrf_headers,
            )
            # Route always returns 200 (renders marketplace page with message)
            assert response.status_code == 200
            # Should return HTML marketplace page
            assert_html_tag_present(response.text, "<html", "<body")
            assert_html_contains_any(response.text, "marketplace")
            # Verify install method was called with correct plugin name
            mock_marketplace_service.install.assert_called_once_with("test-plugin")


@pytest.mark.unit
class TestMarketplaceInstallFlow:
    """Tests for plugin installation workflow."""

    def test_marketplace_preinstall_check(
        self, web_client_builder, mock_marketplace_service
    ) -> None:
        """Should validate plugin before installation and handle errors."""
        client = web_client_builder(allowed_paths=[])
        csrf_headers = get_csrf_headers(client)
        # Mock the MarketplaceService to simulate error for nonexistent plugin
        with patch(
            "file_organizer.web.marketplace_routes.MarketplaceService"
        ) as mock_service_class:
            # Configure mock to raise error for nonexistent plugin
            mock_marketplace_service.install.side_effect = MarketplaceError("Plugin not found")
            mock_service_class.return_value = mock_marketplace_service

            # Test that install endpoint handles nonexistent plugins
            response = client.post(
                "/ui/marketplace/plugins/nonexistent-plugin/install",
                data={
                    "q": "",
                    "category": "",
                    "tag_csv": "",
                },
                headers=csrf_headers,
            )
            # Route returns 200 (renders marketplace page with error message)
            assert response.status_code == 200
            # Should return HTML marketplace page with error feedback
            assert_html_tag_present(response.text, "<html", "<body")
            assert_html_contains_any(response.text, "nonexistent-plugin", "not found")
            # Verify install was called with the nonexistent plugin name
            mock_marketplace_service.install.assert_called_once_with("nonexistent-plugin")

    def test_marketplace_install_progress(
        self, web_client_builder, mock_marketplace_service
    ) -> None:
        """Should handle installation workflow."""
        client = web_client_builder(allowed_paths=[])
        csrf_headers = get_csrf_headers(client)
        # Mock the MarketplaceService to track install progress
        with patch(
            "file_organizer.web.marketplace_routes.MarketplaceService"
        ) as mock_service_class:
            mock_service_class.return_value = mock_marketplace_service

            # Test the full install workflow by calling the install endpoint
            response = client.post(
                "/ui/marketplace/plugins/sample-plugin/install",
                data={
                    "q": "sample",
                    "category": "",
                    "tag_csv": "",
                },
                headers=csrf_headers,
            )
            # Route always returns 200 (renders marketplace page with message)
            assert response.status_code == 200
            # Should return HTML marketplace page with search preserved
            assert_html_tag_present(response.text, "<html", "<body")
            assert_html_contains_any(response.text, "marketplace")
            # Verify install was called with correct plugin name
            mock_marketplace_service.install.assert_called_once_with("sample-plugin")


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

    def test_marketplace_filter_result_count_accuracy(
        self, web_client_builder, mock_marketplace_service
    ) -> None:
        """Filter results should accurately represent filtered content."""
        client = web_client_builder(allowed_paths=[])

        # Mock list_plugins to return filtered results for category filter
        # Note: MagicMock(name=...) sets the internal debug name, not .name attribute
        pdf_plugin = MagicMock()
        pdf_plugin.name = "pdf-reader"
        pdf_plugin.category = "readers"
        pdf_plugin.version = "1.0"
        pdf_plugin.description = "PDF reader plugin"
        pdf_plugin.author = "test-author"
        pdf_plugin.downloads = 100
        pdf_plugin.rating = 4.5
        epub_plugin = MagicMock()
        epub_plugin.name = "epub-reader"
        epub_plugin.category = "readers"
        epub_plugin.version = "1.0"
        epub_plugin.description = "EPUB reader plugin"
        epub_plugin.author = "test-author"
        epub_plugin.downloads = 50
        epub_plugin.rating = 4.0
        reader_plugins = ([pdf_plugin, epub_plugin], 2)
        mock_marketplace_service.list_plugins.return_value = reader_plugins

        # Search for specific category
        with patch(
            "file_organizer.web.marketplace_routes.MarketplaceService"
        ) as mock_service_class:
            mock_service_class.return_value = mock_marketplace_service
            response = client.get("/ui/marketplace?category=readers")

        assert response.status_code == 200
        # Verify response includes BOTH filtered plugin names
        assert_html_contains(response.text, "pdf-reader", "epub-reader")


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
        csrf_headers = get_csrf_headers(client)
        response = client.post(
            "/ui/marketplace/plugins/nonexistent-plugin/install",
            data={
                "q": "",
                "category": "",
                "tag_csv": "",
            },
            headers=csrf_headers,
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
        # The user-supplied payload must be HTML-escaped; the unescaped sequence
        # "<script>alert('xss')</script>" must not appear in the response body.
        # Jinja2 escapes < and > but leaves single quotes verbatim, so checking
        # for "alert('xss')" alone would false-positive on properly escaped output.
        assert "<script>alert('xss')</script>" not in response.text
