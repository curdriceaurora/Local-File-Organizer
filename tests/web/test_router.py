"""Unit tests for web router module.

Tests the main router setup and home page route.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from file_organizer.api.config import ApiSettings
from file_organizer.web.router import home

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_request():
    """Mock FastAPI Request object."""
    req = MagicMock()
    req.url = MagicMock()
    req.url.path = "/ui/"
    return req


@pytest.fixture()
def mock_settings():
    """Mock ApiSettings object."""
    s = MagicMock(spec=ApiSettings)
    s.app_name = "File Organizer"
    s.version = "2.0.0"
    return s


# ---------------------------------------------------------------------------
# home route
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestHomeRoute:
    """Test the home page route."""

    @patch("file_organizer.web.router.base_context")
    @patch("file_organizer.web.router.templates")
    def test_home_route(self, mock_templates, mock_base_context, mock_request, mock_settings):
        """GET / renders home page."""
        mock_context = {
            "request": mock_request,
            "app_name": "File Organizer",
            "version": "2.0.0",
            "active": "home",
            "page_title": "Home",
        }
        mock_base_context.return_value = mock_context
        mock_response = MagicMock()
        mock_templates.TemplateResponse.return_value = mock_response

        result = home(mock_request, mock_settings)

        assert result is mock_response
        mock_base_context.assert_called_once()
        call_kwargs = mock_base_context.call_args[1]
        assert call_kwargs["active"] == "home"
        assert call_kwargs["title"] == "Home"

        mock_templates.TemplateResponse.assert_called_once()
        template_call_args = mock_templates.TemplateResponse.call_args[0]
        assert template_call_args[1] == "index.html"

    @patch("file_organizer.web.router.base_context")
    @patch("file_organizer.web.router.templates")
    def test_home_route_context_has_request(self, mock_templates, mock_base_context,
                                            mock_request, mock_settings):
        """Home route context includes request."""
        mock_base_context.return_value = {}
        mock_response = MagicMock()
        mock_templates.TemplateResponse.return_value = mock_response

        home(mock_request, mock_settings)

        call_args, _ = mock_base_context.call_args
        assert call_args[0] is mock_request
        assert call_args[1] is mock_settings
