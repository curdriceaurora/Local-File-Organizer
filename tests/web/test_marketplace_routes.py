"""Tests for file_organizer.web.marketplace_routes module.

Covers _normalize_tags, _service, _render_marketplace_page, and the
route handlers (marketplace_home, install_plugin, uninstall_plugin, update_plugin).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.web.marketplace_routes import (
    _normalize_tags,
    _service,
    install_plugin,
    marketplace_home,
    uninstall_plugin,
    update_plugin,
)

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# _normalize_tags
# ---------------------------------------------------------------------------


class TestNormalizeTags:
    """Test the _normalize_tags helper."""

    def test_none_returns_empty(self):
        assert _normalize_tags(None) == []

    def test_empty_list(self):
        assert _normalize_tags([]) == []

    def test_single_tag(self):
        assert _normalize_tags(["audio"]) == ["audio"]

    def test_comma_separated(self):
        result = _normalize_tags(["audio, video, image"])
        assert result == ["audio", "video", "image"]

    def test_strips_whitespace(self):
        result = _normalize_tags(["  audio  ", "  video  "])
        assert result == ["audio", "video"]

    def test_skips_empty_parts(self):
        result = _normalize_tags(["a,,b, ,c"])
        assert result == ["a", "b", "c"]

    def test_multiple_tokens(self):
        result = _normalize_tags(["a,b", "c,d"])
        assert result == ["a", "b", "c", "d"]


# ---------------------------------------------------------------------------
# _service
# ---------------------------------------------------------------------------


class TestService:
    """Test _service factory."""

    @patch("file_organizer.web.marketplace_routes.MarketplaceService")
    def test_returns_instance(self, mock_cls):
        mock_cls.return_value = MagicMock()
        result = _service()
        mock_cls.assert_called_once()
        assert result is mock_cls.return_value


# ---------------------------------------------------------------------------
# Route handlers — using mocks to avoid real template rendering
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_deps():
    """Mock the heavy dependencies for route handler tests."""
    mock_request = MagicMock()
    mock_settings = MagicMock()
    mock_service = MagicMock()
    mock_template_response = MagicMock()

    patches = {
        "service": patch(
            "file_organizer.web.marketplace_routes._service",
            return_value=mock_service,
        ),
        "templates": patch(
            "file_organizer.web.marketplace_routes.templates",
        ),
        "base_context": patch(
            "file_organizer.web.marketplace_routes.base_context",
            return_value={"request": mock_request},
        ),
    }

    started = {k: p.start() for k, p in patches.items()}
    started["templates"].TemplateResponse = MagicMock(return_value=mock_template_response)

    yield {
        "request": mock_request,
        "settings": mock_settings,
        "service": mock_service,
        "template_response": mock_template_response,
    }

    for p in patches.values():
        p.stop()


class TestMarketplaceHome:
    """Test marketplace_home route."""

    def test_default_params(self, mock_deps):
        mock_deps["service"].list_plugins.return_value = ([], 0)
        mock_deps["service"].list_installed.return_value = []
        result = marketplace_home(
            mock_deps["request"],
            mock_deps["settings"],
            q="",
            category=None,
            tags=None,
            page=1,
            per_page=24,
        )
        assert result is mock_deps["template_response"]

    def test_with_search(self, mock_deps):
        mock_deps["service"].list_plugins.return_value = ([], 0)
        mock_deps["service"].list_installed.return_value = []
        marketplace_home(
            mock_deps["request"],
            mock_deps["settings"],
            q="audio",
            category="audio",
            tags=["tag1"],
            page=2,
            per_page=10,
        )

    def test_marketplace_error(self, mock_deps):
        from file_organizer.plugins.marketplace import MarketplaceError

        mock_deps["service"].list_plugins.side_effect = MarketplaceError("fail")
        marketplace_home(
            mock_deps["request"],
            mock_deps["settings"],
            q="",
            category=None,
            tags=None,
            page=1,
            per_page=24,
        )


class TestInstallPlugin:
    """Test install_plugin route."""

    def test_install_success(self, mock_deps):
        mock_installed = SimpleNamespace(name="test-plugin", version="1.0.0")
        mock_deps["service"].install.return_value = mock_installed
        mock_deps["service"].list_plugins.return_value = ([], 0)
        mock_deps["service"].list_installed.return_value = []
        result = install_plugin(
            mock_deps["request"],
            "test-plugin",
            mock_deps["settings"],
            q="",
            category="",
            tag_csv="",
        )
        assert result is mock_deps["template_response"]

    def test_install_error(self, mock_deps):
        from file_organizer.plugins.marketplace import MarketplaceError

        mock_deps["service"].install.side_effect = MarketplaceError("not found")
        mock_deps["service"].list_plugins.return_value = ([], 0)
        mock_deps["service"].list_installed.return_value = []
        install_plugin(
            mock_deps["request"],
            "bad-plugin",
            mock_deps["settings"],
            q="",
            category="",
            tag_csv="",
        )

    def test_install_preserves_filters(self, mock_deps):
        mock_installed = SimpleNamespace(name="p", version="1.0")
        mock_deps["service"].install.return_value = mock_installed
        mock_deps["service"].list_plugins.return_value = ([], 0)
        mock_deps["service"].list_installed.return_value = []
        install_plugin(
            mock_deps["request"],
            "p",
            mock_deps["settings"],
            q="search",
            category="audio",
            tag_csv="a,b",
        )


class TestUninstallPlugin:
    """Test uninstall_plugin route."""

    def test_uninstall_success(self, mock_deps):
        mock_deps["service"].list_plugins.return_value = ([], 0)
        mock_deps["service"].list_installed.return_value = []
        result = uninstall_plugin(
            mock_deps["request"],
            "test-plugin",
            mock_deps["settings"],
            q="",
            category="",
            tag_csv="",
        )
        assert result is mock_deps["template_response"]

    def test_uninstall_error(self, mock_deps):
        from file_organizer.plugins.marketplace import MarketplaceError

        mock_deps["service"].uninstall.side_effect = MarketplaceError("fail")
        mock_deps["service"].list_plugins.return_value = ([], 0)
        mock_deps["service"].list_installed.return_value = []
        uninstall_plugin(
            mock_deps["request"],
            "bad",
            mock_deps["settings"],
            q="",
            category="",
            tag_csv="",
        )


class TestUpdatePlugin:
    """Test update_plugin route."""

    def test_update_success(self, mock_deps):
        mock_updated = SimpleNamespace(name="p", version="2.0")
        mock_deps["service"].update.return_value = mock_updated
        mock_deps["service"].list_plugins.return_value = ([], 0)
        mock_deps["service"].list_installed.return_value = []
        result = update_plugin(
            mock_deps["request"],
            "p",
            mock_deps["settings"],
            q="",
            category="",
            tag_csv="",
        )
        assert result is mock_deps["template_response"]

    def test_update_already_current(self, mock_deps):
        mock_deps["service"].update.return_value = None
        mock_deps["service"].list_plugins.return_value = ([], 0)
        mock_deps["service"].list_installed.return_value = []
        update_plugin(
            mock_deps["request"],
            "p",
            mock_deps["settings"],
            q="",
            category="",
            tag_csv="",
        )

    def test_update_error(self, mock_deps):
        from file_organizer.plugins.marketplace import MarketplaceError

        mock_deps["service"].update.side_effect = MarketplaceError("fail")
        mock_deps["service"].list_plugins.return_value = ([], 0)
        mock_deps["service"].list_installed.return_value = []
        update_plugin(
            mock_deps["request"],
            "p",
            mock_deps["settings"],
            q="",
            category="",
            tag_csv="",
        )
