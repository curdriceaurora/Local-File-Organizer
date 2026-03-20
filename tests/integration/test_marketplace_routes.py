"""Integration tests for the marketplace web UI routes.

Covers:
  - web/marketplace_routes.py — GET /marketplace, install/uninstall/update,
                                plugin details
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from starlette.testclient import TestClient

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_settings
from file_organizer.api.exceptions import setup_exception_handlers
from file_organizer.plugins.marketplace import MarketplaceError
from file_organizer.web.marketplace_routes import marketplace_router

pytestmark = pytest.mark.integration

_HTML = HTMLResponse("<html><body>marketplace stub</body></html>")


@pytest.fixture()
def mkt_settings(tmp_path: Path) -> ApiSettings:
    return ApiSettings(
        allowed_paths=[str(tmp_path)],
        auth_enabled=False,
        auth_db_path=str(tmp_path / "auth.db"),
    )


@pytest.fixture()
def mkt_client(mkt_settings: ApiSettings) -> TestClient:
    app = FastAPI()
    app.dependency_overrides[get_settings] = lambda: mkt_settings
    setup_exception_handlers(app)
    app.include_router(marketplace_router, prefix="/ui")
    return TestClient(app, raise_server_exceptions=False)


def _mock_service(plugins: list | None = None, installed: list | None = None) -> MagicMock:
    svc = MagicMock()
    svc.list_plugins.return_value = (plugins or [], 0)
    svc.list_installed.return_value = installed or []
    return svc


class TestMarketplaceHome:
    def test_returns_200(self, mkt_client: TestClient) -> None:
        with (
            patch("file_organizer.web.marketplace_routes._service") as mock_svc,
            patch("file_organizer.web.marketplace_routes.templates") as tpl,
        ):
            mock_svc.return_value = _mock_service()
            tpl.TemplateResponse.return_value = _HTML
            r = mkt_client.get("/ui/marketplace")
        assert r.status_code == 200

    def test_with_search_query(self, mkt_client: TestClient) -> None:
        with (
            patch("file_organizer.web.marketplace_routes._service") as mock_svc,
            patch("file_organizer.web.marketplace_routes.templates") as tpl,
        ):
            mock_svc.return_value = _mock_service()
            tpl.TemplateResponse.return_value = _HTML
            r = mkt_client.get("/ui/marketplace?q=test")
        assert r.status_code == 200

    def test_with_category_filter(self, mkt_client: TestClient) -> None:
        with (
            patch("file_organizer.web.marketplace_routes._service") as mock_svc,
            patch("file_organizer.web.marketplace_routes.templates") as tpl,
        ):
            mock_svc.return_value = _mock_service()
            tpl.TemplateResponse.return_value = _HTML
            r = mkt_client.get("/ui/marketplace?category=organizer")
        assert r.status_code == 200

    def test_marketplace_error_renders_page(self, mkt_client: TestClient) -> None:
        with (
            patch("file_organizer.web.marketplace_routes._service") as mock_svc,
            patch("file_organizer.web.marketplace_routes.templates") as tpl,
        ):
            mock_svc.return_value.list_plugins.side_effect = MarketplaceError("network error")
            tpl.TemplateResponse.return_value = _HTML
            r = mkt_client.get("/ui/marketplace")
        assert r.status_code == 200  # renders error in template, not 500

    def test_with_tag_filters(self, mkt_client: TestClient) -> None:
        with (
            patch("file_organizer.web.marketplace_routes._service") as mock_svc,
            patch("file_organizer.web.marketplace_routes.templates") as tpl,
        ):
            mock_svc.return_value = _mock_service()
            tpl.TemplateResponse.return_value = _HTML
            r = mkt_client.get("/ui/marketplace?tag=ai&tag=python")
        assert r.status_code == 200

    def test_pagination_params(self, mkt_client: TestClient) -> None:
        with (
            patch("file_organizer.web.marketplace_routes._service") as mock_svc,
            patch("file_organizer.web.marketplace_routes.templates") as tpl,
        ):
            mock_svc.return_value = _mock_service()
            tpl.TemplateResponse.return_value = _HTML
            r = mkt_client.get("/ui/marketplace?page=2&per_page=12")
        assert r.status_code == 200


class TestMarketplaceInstall:
    def test_install_success(self, mkt_client: TestClient) -> None:
        installed_plugin = MagicMock()
        installed_plugin.name = "my-plugin"
        installed_plugin.version = "1.0.0"
        with (
            patch("file_organizer.web.marketplace_routes._service") as mock_svc,
            patch("file_organizer.web.marketplace_routes.templates") as tpl,
        ):
            svc_instance = _mock_service()
            svc_instance.install.return_value = installed_plugin
            mock_svc.return_value = svc_instance
            tpl.TemplateResponse.return_value = _HTML
            r = mkt_client.post(
                "/ui/marketplace/plugins/my-plugin/install",
                data={"q": "", "category": "", "tag_csv": ""},
            )
        assert r.status_code == 200

    def test_install_error_renders_page(self, mkt_client: TestClient) -> None:
        with (
            patch("file_organizer.web.marketplace_routes._service") as mock_svc,
            patch("file_organizer.web.marketplace_routes.templates") as tpl,
        ):
            svc_instance = _mock_service()
            svc_instance.install.side_effect = MarketplaceError("not found")
            mock_svc.return_value = svc_instance
            tpl.TemplateResponse.return_value = _HTML
            r = mkt_client.post(
                "/ui/marketplace/plugins/missing/install",
                data={"q": "", "category": "", "tag_csv": ""},
            )
        assert r.status_code == 200


class TestMarketplaceUninstall:
    def test_uninstall_success(self, mkt_client: TestClient) -> None:
        with (
            patch("file_organizer.web.marketplace_routes._service") as mock_svc,
            patch("file_organizer.web.marketplace_routes.templates") as tpl,
        ):
            svc_instance = _mock_service()
            svc_instance.uninstall.return_value = None
            mock_svc.return_value = svc_instance
            tpl.TemplateResponse.return_value = _HTML
            r = mkt_client.post(
                "/ui/marketplace/plugins/my-plugin/uninstall",
                data={"q": "", "category": "", "tag_csv": ""},
            )
        assert r.status_code == 200

    def test_uninstall_error_renders_page(self, mkt_client: TestClient) -> None:
        with (
            patch("file_organizer.web.marketplace_routes._service") as mock_svc,
            patch("file_organizer.web.marketplace_routes.templates") as tpl,
        ):
            svc_instance = _mock_service()
            svc_instance.uninstall.side_effect = MarketplaceError("not installed")
            mock_svc.return_value = svc_instance
            tpl.TemplateResponse.return_value = _HTML
            r = mkt_client.post(
                "/ui/marketplace/plugins/my-plugin/uninstall",
                data={"q": "", "category": "", "tag_csv": ""},
            )
        assert r.status_code == 200


class TestMarketplaceUpdate:
    def test_update_success(self, mkt_client: TestClient) -> None:
        updated_plugin = MagicMock()
        updated_plugin.name = "my-plugin"
        updated_plugin.version = "2.0.0"
        with (
            patch("file_organizer.web.marketplace_routes._service") as mock_svc,
            patch("file_organizer.web.marketplace_routes.templates") as tpl,
        ):
            svc_instance = _mock_service()
            svc_instance.update.return_value = updated_plugin
            mock_svc.return_value = svc_instance
            tpl.TemplateResponse.return_value = _HTML
            r = mkt_client.post(
                "/ui/marketplace/plugins/my-plugin/update",
                data={"q": "", "category": "", "tag_csv": ""},
            )
        assert r.status_code == 200

    def test_update_already_latest(self, mkt_client: TestClient) -> None:
        with (
            patch("file_organizer.web.marketplace_routes._service") as mock_svc,
            patch("file_organizer.web.marketplace_routes.templates") as tpl,
        ):
            svc_instance = _mock_service()
            svc_instance.update.return_value = None  # already up to date
            mock_svc.return_value = svc_instance
            tpl.TemplateResponse.return_value = _HTML
            r = mkt_client.post(
                "/ui/marketplace/plugins/my-plugin/update",
                data={"q": "", "category": "", "tag_csv": ""},
            )
        assert r.status_code == 200

    def test_update_error_renders_page(self, mkt_client: TestClient) -> None:
        with (
            patch("file_organizer.web.marketplace_routes._service") as mock_svc,
            patch("file_organizer.web.marketplace_routes.templates") as tpl,
        ):
            svc_instance = _mock_service()
            svc_instance.update.side_effect = MarketplaceError("network timeout")
            mock_svc.return_value = svc_instance
            tpl.TemplateResponse.return_value = _HTML
            r = mkt_client.post(
                "/ui/marketplace/plugins/my-plugin/update",
                data={"q": "", "category": "", "tag_csv": ""},
            )
        assert r.status_code == 200


class TestMarketplacePluginDetails:
    def test_plugin_found_returns_200(self, mkt_client: TestClient) -> None:
        plugin = MagicMock()
        plugin.name = "test-plugin"
        with (
            patch("file_organizer.web.marketplace_routes._service") as mock_svc,
            patch("file_organizer.web.marketplace_routes.templates") as tpl,
        ):
            svc_instance = _mock_service()
            svc_instance.get_plugin.return_value = plugin
            mock_svc.return_value = svc_instance
            tpl.TemplateResponse.return_value = _HTML
            r = mkt_client.get("/ui/marketplace/plugins/test-plugin/details")
        assert r.status_code == 200

    def test_plugin_not_found_returns_404(self, mkt_client: TestClient) -> None:
        with patch("file_organizer.web.marketplace_routes._service") as mock_svc:
            svc_instance = _mock_service()
            svc_instance.get_plugin.return_value = None
            mock_svc.return_value = svc_instance
            r = mkt_client.get("/ui/marketplace/plugins/missing/details")
        assert r.status_code == 404

    def test_marketplace_error_returns_500(self, mkt_client: TestClient) -> None:
        with patch("file_organizer.web.marketplace_routes._service") as mock_svc:
            svc_instance = _mock_service()
            svc_instance.get_plugin.side_effect = MarketplaceError("service down")
            mock_svc.return_value = svc_instance
            r = mkt_client.get("/ui/marketplace/plugins/test-plugin/details")
        assert r.status_code == 500
