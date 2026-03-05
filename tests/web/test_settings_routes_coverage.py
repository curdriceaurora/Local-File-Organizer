"""Coverage tests for file_organizer.web.settings_routes — route handler branches."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _use_temp_settings(monkeypatch, tmp_path):
    """Redirect settings I/O to tmp_path."""
    with (
        patch("file_organizer.web.settings_routes._SETTINGS_DIR", tmp_path),
        patch(
            "file_organizer.web.settings_routes._SETTINGS_FILE",
            tmp_path / "web-settings.json",
        ),
    ):
        yield tmp_path


@pytest.fixture()
def mock_templates():
    """Patch the Jinja templates object to avoid real template rendering."""
    response = MagicMock()
    response.headers = {}
    with patch("file_organizer.web.settings_routes.templates") as tmpl:
        tmpl.TemplateResponse.return_value = response
        yield tmpl


@pytest.fixture()
def mock_base_context():
    """Patch base_context to return a minimal dict."""
    with patch(
        "file_organizer.web.settings_routes.base_context",
        return_value={"request": MagicMock()},
    ) as ctx:
        yield ctx


class TestSettingsPageRoute:
    """Covers settings_page handler."""

    def test_settings_page(self, mock_templates, mock_base_context) -> None:
        from file_organizer.web.settings_routes import settings_page

        request = MagicMock()
        settings_obj = MagicMock()
        settings_page(request, settings_obj)
        mock_templates.TemplateResponse.assert_called_once()


class TestSettingsSearchRoute:
    """Covers settings_search handler."""

    def test_search_empty_query(self) -> None:
        from file_organizer.web.settings_routes import settings_search

        response = settings_search(query="")
        assert response.body == b""

    def test_search_with_match(self) -> None:
        from file_organizer.web.settings_routes import settings_search

        response = settings_search(query="theme")
        assert b"appearance" in response.body.lower()

    def test_search_no_match(self) -> None:
        from file_organizer.web.settings_routes import settings_search

        response = settings_search(query="zzzznonexistent")
        assert b"No matching" in response.body


class TestSettingsExportRoute:
    """Covers settings_export handler."""

    def test_export_returns_json(self) -> None:
        from file_organizer.web.settings_routes import settings_export

        response = settings_export()
        assert response.media_type == "application/json"
        payload = json.loads(response.body)
        assert "language" in payload


class TestSettingsImportRoute:
    """Covers settings_import handler."""

    @pytest.mark.asyncio
    async def test_import_valid(self, mock_templates) -> None:
        from file_organizer.web.settings_routes import settings_import

        upload = MagicMock()
        upload.read.return_value = json.dumps({"language": "fr", "theme": "dark"}).encode()
        request = MagicMock()
        await settings_import(request, section="general", settings_file=upload)
        mock_templates.TemplateResponse.assert_called_once()

    @pytest.mark.asyncio
    async def test_import_invalid_json(self, mock_templates) -> None:
        from file_organizer.web.settings_routes import settings_import

        upload = MagicMock()
        upload.read.return_value = b"not json"
        request = MagicMock()
        await settings_import(request, section="general", settings_file=upload)
        # Should render with error message
        mock_templates.TemplateResponse.assert_called_once()

    @pytest.mark.asyncio
    async def test_import_non_dict(self, mock_templates) -> None:
        from file_organizer.web.settings_routes import settings_import

        upload = MagicMock()
        upload.read.return_value = b'"just a string"'
        request = MagicMock()
        await settings_import(request, section="models", settings_file=upload)
        mock_templates.TemplateResponse.assert_called_once()


class TestSettingsResetRoute:
    """Covers settings_reset handler."""

    def test_reset(self, mock_templates) -> None:
        from file_organizer.web.settings_routes import settings_reset

        request = MagicMock()
        settings_reset(request, section="advanced")
        mock_templates.TemplateResponse.assert_called_once()


class TestSettingsSectionGetRoutes:
    """Covers GET section routes."""

    def test_general_get(self, mock_templates) -> None:
        from file_organizer.web.settings_routes import settings_general_get

        settings_general_get(MagicMock())
        mock_templates.TemplateResponse.assert_called_once()

    def test_models_get(self, mock_templates) -> None:
        from file_organizer.web.settings_routes import settings_models_get

        settings_models_get(MagicMock())
        mock_templates.TemplateResponse.assert_called_once()

    def test_organization_get(self, mock_templates) -> None:
        from file_organizer.web.settings_routes import settings_organization_get

        settings_organization_get(MagicMock())
        mock_templates.TemplateResponse.assert_called_once()

    def test_appearance_get(self, mock_templates) -> None:
        from file_organizer.web.settings_routes import settings_appearance_get

        settings_appearance_get(MagicMock())
        mock_templates.TemplateResponse.assert_called_once()

    def test_advanced_get(self, mock_templates) -> None:
        from file_organizer.web.settings_routes import settings_advanced_get

        settings_advanced_get(MagicMock())
        mock_templates.TemplateResponse.assert_called_once()


class TestSettingsSectionPostRoutes:
    """Covers POST section routes."""

    def test_general_post(self, mock_templates) -> None:
        from file_organizer.web.settings_routes import settings_general_post

        settings_general_post(
            MagicMock(), language="fr", timezone="UTC", default_input_dir="", default_output_dir=""
        )
        mock_templates.TemplateResponse.assert_called_once()

    def test_general_post_exception(self, mock_templates) -> None:
        from file_organizer.web.settings_routes import settings_general_post

        with patch(
            "file_organizer.web.settings_routes._update_web_settings",
            side_effect=RuntimeError("boom"),
        ):
            settings_general_post(
                MagicMock(),
                language="en",
                timezone="UTC",
                default_input_dir="",
                default_output_dir="",
            )
        mock_templates.TemplateResponse.assert_called_once()

    def test_models_post(self, mock_templates) -> None:
        from file_organizer.web.settings_routes import settings_models_post

        settings_models_post(
            MagicMock(), text_model="m1", vision_model="m2", ollama_url="http://localhost:11434"
        )
        mock_templates.TemplateResponse.assert_called_once()

    def test_models_post_exception(self, mock_templates) -> None:
        from file_organizer.web.settings_routes import settings_models_post

        with patch(
            "file_organizer.web.settings_routes._update_web_settings",
            side_effect=RuntimeError("boom"),
        ):
            settings_models_post(MagicMock(), text_model="", vision_model="", ollama_url="")
        mock_templates.TemplateResponse.assert_called_once()

    def test_models_test_success(self, mock_templates) -> None:
        from file_organizer.web.settings_routes import settings_models_test

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response

        with patch("file_organizer.web.settings_routes.httpx.Client", return_value=mock_client):
            settings_models_test(MagicMock(), ollama_url="http://localhost:11434")
        mock_templates.TemplateResponse.assert_called_once()

    def test_models_test_failure(self, mock_templates) -> None:
        from file_organizer.web.settings_routes import settings_models_test

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.side_effect = ConnectionError("refused")

        with patch("file_organizer.web.settings_routes.httpx.Client", return_value=mock_client):
            settings_models_test(MagicMock(), ollama_url="http://bad:1234")
        mock_templates.TemplateResponse.assert_called_once()

    def test_organization_post(self, mock_templates) -> None:
        from file_organizer.web.settings_routes import settings_organization_post

        settings_organization_post(
            MagicMock(),
            default_methodology="para",
            auto_organize="1",
            notifications_enabled="1",
            file_filter_glob="*",
            organization_rules="docs/* -> Documents",
        )
        mock_templates.TemplateResponse.assert_called_once()

    def test_organization_post_invalid_rules(self, mock_templates) -> None:
        from file_organizer.web.settings_routes import settings_organization_post

        settings_organization_post(
            MagicMock(),
            default_methodology="para",
            auto_organize=None,
            notifications_enabled=None,
            file_filter_glob="*",
            organization_rules="bad line without arrow",
        )
        mock_templates.TemplateResponse.assert_called_once()

    def test_organization_post_exception(self, mock_templates) -> None:
        from file_organizer.web.settings_routes import settings_organization_post

        with patch(
            "file_organizer.web.settings_routes._update_web_settings",
            side_effect=RuntimeError("boom"),
        ):
            settings_organization_post(
                MagicMock(),
                default_methodology="content_based",
                auto_organize=None,
                notifications_enabled=None,
                file_filter_glob="*",
                organization_rules="docs/* -> Documents",
            )
        mock_templates.TemplateResponse.assert_called_once()

    def test_organization_validate_valid(self, mock_templates) -> None:
        from file_organizer.web.settings_routes import settings_organization_validate

        settings_organization_validate(MagicMock(), organization_rules="docs/* -> Documents")
        mock_templates.TemplateResponse.assert_called_once()

    def test_organization_validate_invalid(self, mock_templates) -> None:
        from file_organizer.web.settings_routes import settings_organization_validate

        settings_organization_validate(MagicMock(), organization_rules="no arrow")
        mock_templates.TemplateResponse.assert_called_once()

    def test_appearance_post(self, mock_templates) -> None:
        from file_organizer.web.settings_routes import settings_appearance_post

        settings_appearance_post(MagicMock(), theme="dark", custom_theme_name="mytheme")
        mock_templates.TemplateResponse.assert_called_once()

    def test_appearance_post_exception(self, mock_templates) -> None:
        from file_organizer.web.settings_routes import settings_appearance_post

        with patch(
            "file_organizer.web.settings_routes._update_web_settings",
            side_effect=RuntimeError("boom"),
        ):
            settings_appearance_post(MagicMock(), theme="dark", custom_theme_name="")
        mock_templates.TemplateResponse.assert_called_once()

    def test_advanced_post(self, mock_templates) -> None:
        from file_organizer.web.settings_routes import settings_advanced_post

        settings_advanced_post(
            MagicMock(),
            log_level="DEBUG",
            cache_enabled="1",
            debug_mode="1",
            performance_mode="performance",
        )
        mock_templates.TemplateResponse.assert_called_once()

    def test_advanced_post_exception(self, mock_templates) -> None:
        from file_organizer.web.settings_routes import settings_advanced_post

        with patch(
            "file_organizer.web.settings_routes._update_web_settings",
            side_effect=RuntimeError("boom"),
        ):
            settings_advanced_post(
                MagicMock(),
                log_level="INFO",
                cache_enabled=None,
                debug_mode=None,
                performance_mode="balanced",
            )
        mock_templates.TemplateResponse.assert_called_once()


class TestLoadWebSettingsEdgeCases:
    """Covers _load_web_settings error branches."""

    def test_corrupt_json_returns_default(self) -> None:
        from file_organizer.web.settings_routes import (
            _SETTINGS_FILE,
            _load_web_settings,
        )

        _SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        _SETTINGS_FILE.write_text("not valid json!!!")
        ws = _load_web_settings()
        assert ws.language == "en"

    def test_non_dict_json_returns_default(self) -> None:
        from file_organizer.web.settings_routes import (
            _SETTINGS_FILE,
            _load_web_settings,
        )

        _SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        _SETTINGS_FILE.write_text('"just a string"')
        ws = _load_web_settings()
        assert ws.language == "en"

    def test_save_failure_does_not_raise(self) -> None:
        from file_organizer.web.settings_routes import WebSettings, _save_web_settings

        with patch(
            "file_organizer.web.settings_routes._SETTINGS_DIR",
            MagicMock(mkdir=MagicMock(side_effect=PermissionError("denied"))),
        ):
            # Should not raise
            _save_web_settings(WebSettings())
