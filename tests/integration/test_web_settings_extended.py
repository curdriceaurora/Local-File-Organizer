"""Integration tests for web/settings_routes.py.

Covers: settings_page, settings_search, settings_export, settings_import,
settings_reset, all section GET/POST routes (general, models, organization,
appearance, advanced), settings_organization_validate, settings_models_test,
and the pure helpers (_as_form_bool, _coerce_bool, _validate_choice,
_validate_methodology, _validate_rules, WebSettings defaults).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from starlette.testclient import TestClient

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_settings
from file_organizer.api.exceptions import setup_exception_handlers
from file_organizer.web.settings_routes import settings_router

pytestmark = pytest.mark.integration

_HTML = HTMLResponse("<html><body>stub</body></html>")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def settings_settings(tmp_path: Path) -> ApiSettings:
    return ApiSettings(
        allowed_paths=[str(tmp_path)],
        auth_enabled=False,
        auth_db_path=str(tmp_path / "auth.db"),
    )


@pytest.fixture()
def settings_client(settings_settings: ApiSettings, tmp_path: Path) -> TestClient:
    app = FastAPI()
    app.dependency_overrides[get_settings] = lambda: settings_settings
    setup_exception_handlers(app)
    app.include_router(settings_router, prefix="/ui")
    client = TestClient(app, raise_server_exceptions=False)
    settings_file = tmp_path / "web-settings.json"
    with patch("file_organizer.web.settings_routes._SETTINGS_FILE", settings_file):
        with patch("file_organizer.web.settings_routes._SETTINGS_DIR", tmp_path):
            yield client


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


class TestAsFormBool:
    def test_none_returns_false(self) -> None:
        from file_organizer.web.settings_routes import _as_form_bool

        assert _as_form_bool(None) is False

    def test_true_string(self) -> None:
        from file_organizer.web.settings_routes import _as_form_bool

        for v in ("1", "true", "True", "TRUE", "yes", "on"):
            assert _as_form_bool(v) is True

    def test_false_string(self) -> None:
        from file_organizer.web.settings_routes import _as_form_bool

        for v in ("0", "false", "no", "off", ""):
            assert _as_form_bool(v) is False


class TestCoerceBool:
    def test_bool_passthrough(self) -> None:
        from file_organizer.web.settings_routes import _coerce_bool

        assert _coerce_bool(True, False) is True
        assert _coerce_bool(False, True) is False

    def test_string_truthy(self) -> None:
        from file_organizer.web.settings_routes import _coerce_bool

        assert _coerce_bool("1", False) is True
        assert _coerce_bool("true", False) is True

    def test_unknown_type_returns_default(self) -> None:
        from file_organizer.web.settings_routes import _coerce_bool

        assert _coerce_bool(42, True) is True
        assert _coerce_bool(42, False) is False


class TestValidateChoice:
    def test_valid_choice_returned(self) -> None:
        from file_organizer.web.settings_routes import _validate_choice

        result = _validate_choice("dark", ["light", "dark", "auto"], "light")
        assert result == "dark"

    def test_invalid_choice_returns_fallback(self) -> None:
        from file_organizer.web.settings_routes import _validate_choice

        result = _validate_choice("purple", ["light", "dark", "auto"], "light")
        assert result == "light"

    def test_whitespace_stripped(self) -> None:
        from file_organizer.web.settings_routes import _validate_choice

        result = _validate_choice("  dark  ", ["light", "dark", "auto"], "light")
        assert result == "dark"


class TestValidateMethodology:
    def test_valid_methodology(self) -> None:
        from file_organizer.web.settings_routes import _validate_methodology

        assert _validate_methodology("para") == "para"
        assert _validate_methodology("PARA") == "para"

    def test_invalid_methodology_returns_default(self) -> None:
        from file_organizer.web.settings_routes import _validate_methodology

        assert _validate_methodology("unknown_meth") == "content_based"


class TestValidateRules:
    def test_empty_rules_invalid(self) -> None:
        from file_organizer.web.settings_routes import _validate_rules

        valid, msg = _validate_rules("")
        assert valid is False
        assert "empty" in msg.lower()

    def test_valid_rules(self) -> None:
        from file_organizer.web.settings_routes import _validate_rules

        valid, msg = _validate_rules("docs/* -> Documents\nimages/* -> Media")
        assert valid is True

    def test_comment_line_skipped(self) -> None:
        from file_organizer.web.settings_routes import _validate_rules

        valid, _ = _validate_rules("# header comment\ndocs/* -> Documents")
        assert valid is True

    def test_missing_arrow_invalid(self) -> None:
        from file_organizer.web.settings_routes import _validate_rules

        valid, msg = _validate_rules("docs/* Documents")
        assert valid is False
        assert "invalid" in msg.lower()

    def test_missing_destination_invalid(self) -> None:
        from file_organizer.web.settings_routes import _validate_rules

        valid, msg = _validate_rules("docs/* ->")
        assert valid is False


class TestWebSettingsDefaults:
    def test_default_fields(self) -> None:
        from file_organizer.web.settings_routes import WebSettings

        ws = WebSettings()
        assert ws.language == "en"
        assert ws.timezone == "UTC"
        assert ws.theme == "light"
        assert ws.log_level == "INFO"
        assert ws.auto_organize is False
        assert ws.cache_enabled is True
        assert ws.debug_mode is False
        assert ws.performance_mode == "balanced"


# ---------------------------------------------------------------------------
# settings_search (no templates, no request)
# ---------------------------------------------------------------------------


class TestSettingsSearch:
    def test_empty_query_returns_empty(self, settings_client: TestClient) -> None:
        r = settings_client.get("/ui/settings/search", params={"q": ""})
        assert r.status_code == 200
        assert r.text == ""

    def test_no_query_param_returns_empty(self, settings_client: TestClient) -> None:
        r = settings_client.get("/ui/settings/search")
        assert r.status_code == 200
        assert r.text == ""

    def test_no_match_returns_hint(self, settings_client: TestClient) -> None:
        r = settings_client.get("/ui/settings/search", params={"q": "xyznonexistent9999"})
        assert r.status_code == 200
        assert "No matching" in r.text

    def test_match_general_returns_button(self, settings_client: TestClient) -> None:
        r = settings_client.get("/ui/settings/search", params={"q": "language"})
        assert r.status_code == 200
        assert "button" in r.text.lower()

    def test_match_models_section(self, settings_client: TestClient) -> None:
        r = settings_client.get("/ui/settings/search", params={"q": "ollama"})
        assert r.status_code == 200
        assert "button" in r.text.lower()

    def test_match_advanced_section(self, settings_client: TestClient) -> None:
        r = settings_client.get("/ui/settings/search", params={"q": "cache"})
        assert r.status_code == 200
        assert "button" in r.text.lower()

    def test_section_name_match(self, settings_client: TestClient) -> None:
        r = settings_client.get("/ui/settings/search", params={"q": "appear"})
        assert r.status_code == 200
        assert "button" in r.text.lower()


# ---------------------------------------------------------------------------
# settings_export (no templates)
# ---------------------------------------------------------------------------


class TestSettingsExport:
    def test_export_returns_200(self, settings_client: TestClient, tmp_path: Path) -> None:
        with patch("file_organizer.web.settings_routes._SETTINGS_FILE", tmp_path / "ws.json"):
            r = settings_client.get("/ui/settings/export")
        assert r.status_code == 200

    def test_export_content_type_json(self, settings_client: TestClient, tmp_path: Path) -> None:
        with patch("file_organizer.web.settings_routes._SETTINGS_FILE", tmp_path / "ws.json"):
            r = settings_client.get("/ui/settings/export")
        assert "application/json" in r.headers.get("content-type", "")

    def test_export_has_attachment_header(
        self, settings_client: TestClient, tmp_path: Path
    ) -> None:
        with patch("file_organizer.web.settings_routes._SETTINGS_FILE", tmp_path / "ws.json"):
            r = settings_client.get("/ui/settings/export")
        assert "attachment" in r.headers.get("content-disposition", "")

    def test_export_body_is_valid_json(self, settings_client: TestClient, tmp_path: Path) -> None:
        with patch("file_organizer.web.settings_routes._SETTINGS_FILE", tmp_path / "ws.json"):
            r = settings_client.get("/ui/settings/export")
        data = json.loads(r.text)
        assert "language" in data
        assert "theme" in data


# ---------------------------------------------------------------------------
# settings_page (full page — mocked templates)
# ---------------------------------------------------------------------------


class TestSettingsPage:
    def test_settings_page_returns_200(self, settings_client: TestClient, tmp_path: Path) -> None:
        with patch("file_organizer.web.settings_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            with patch("file_organizer.web.settings_routes._SETTINGS_FILE", tmp_path / "ws.json"):
                r = settings_client.get("/ui/settings")
        assert r.status_code == 200

    def test_settings_page_calls_template(
        self, settings_client: TestClient, tmp_path: Path
    ) -> None:
        with patch("file_organizer.web.settings_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            with patch("file_organizer.web.settings_routes._SETTINGS_FILE", tmp_path / "ws.json"):
                settings_client.get("/ui/settings")
        tpl.TemplateResponse.assert_called_once()


# ---------------------------------------------------------------------------
# Section GET routes
# ---------------------------------------------------------------------------


class TestSectionGets:
    def _get_section(self, client: TestClient, section: str, tmp_path: Path) -> int:
        with patch("file_organizer.web.settings_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            with patch("file_organizer.web.settings_routes._SETTINGS_FILE", tmp_path / "ws.json"):
                r = client.get(f"/ui/settings/{section}")
        return r.status_code

    def test_general_get_returns_200(self, settings_client: TestClient, tmp_path: Path) -> None:
        assert self._get_section(settings_client, "general", tmp_path) == 200

    def test_models_get_returns_200(self, settings_client: TestClient, tmp_path: Path) -> None:
        assert self._get_section(settings_client, "models", tmp_path) == 200

    def test_organization_get_returns_200(
        self, settings_client: TestClient, tmp_path: Path
    ) -> None:
        assert self._get_section(settings_client, "organization", tmp_path) == 200

    def test_appearance_get_returns_200(self, settings_client: TestClient, tmp_path: Path) -> None:
        assert self._get_section(settings_client, "appearance", tmp_path) == 200

    def test_advanced_get_returns_200(self, settings_client: TestClient, tmp_path: Path) -> None:
        assert self._get_section(settings_client, "advanced", tmp_path) == 200


# ---------------------------------------------------------------------------
# settings_general_post
# ---------------------------------------------------------------------------


class TestSettingsGeneralPost:
    def test_save_returns_200(self, settings_client: TestClient, tmp_path: Path) -> None:
        with patch("file_organizer.web.settings_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            with patch("file_organizer.web.settings_routes._SETTINGS_FILE", tmp_path / "ws.json"):
                with patch("file_organizer.web.settings_routes._SETTINGS_DIR", tmp_path):
                    r = settings_client.post(
                        "/ui/settings/general",
                        data={
                            "language": "fr",
                            "timezone": "Europe/London",
                            "default_input_dir": "/mock/in",
                            "default_output_dir": "/mock/out",
                        },
                    )
        assert r.status_code == 200

    def test_invalid_language_falls_back(self, settings_client: TestClient, tmp_path: Path) -> None:
        ws_file = tmp_path / "ws.json"
        with patch("file_organizer.web.settings_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            with patch("file_organizer.web.settings_routes._SETTINGS_FILE", ws_file):
                with patch("file_organizer.web.settings_routes._SETTINGS_DIR", tmp_path):
                    r = settings_client.post(
                        "/ui/settings/general",
                        data={"language": "klingon", "timezone": "UTC"},
                    )
        assert r.status_code == 200
        assert ws_file.exists()
        data = json.loads(ws_file.read_text())
        assert data["language"] == "en"


# ---------------------------------------------------------------------------
# settings_models_post
# ---------------------------------------------------------------------------


class TestSettingsModelsPost:
    def test_save_returns_200(self, settings_client: TestClient, tmp_path: Path) -> None:
        with patch("file_organizer.web.settings_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            with patch("file_organizer.web.settings_routes._SETTINGS_FILE", tmp_path / "ws.json"):
                with patch("file_organizer.web.settings_routes._SETTINGS_DIR", tmp_path):
                    r = settings_client.post(
                        "/ui/settings/models",
                        data={
                            "text_model": "llama3:8b",
                            "vision_model": "llava:7b",
                            "ollama_url": "http://localhost:11434",
                        },
                    )
        assert r.status_code == 200

    def test_empty_models_use_defaults(self, settings_client: TestClient, tmp_path: Path) -> None:
        ws_file = tmp_path / "ws.json"
        with patch("file_organizer.web.settings_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            with patch("file_organizer.web.settings_routes._SETTINGS_FILE", ws_file):
                with patch("file_organizer.web.settings_routes._SETTINGS_DIR", tmp_path):
                    r = settings_client.post(
                        "/ui/settings/models",
                        data={"text_model": "", "vision_model": "", "ollama_url": ""},
                    )
        assert r.status_code == 200
        if ws_file.exists():
            data = json.loads(ws_file.read_text())
            assert data["text_model"] == "qwen2.5:3b-instruct-q4_K_M"


# ---------------------------------------------------------------------------
# settings_models_test
# ---------------------------------------------------------------------------


class TestSettingsModelsTest:
    def test_ollama_failure_returns_200(self, settings_client: TestClient, tmp_path: Path) -> None:
        import httpx as _httpx

        with patch("file_organizer.web.settings_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            with patch("file_organizer.web.settings_routes._SETTINGS_FILE", tmp_path / "ws.json"):
                with patch("file_organizer.web.settings_routes._SETTINGS_DIR", tmp_path):
                    with patch("file_organizer.web.settings_routes.httpx.Client") as mock_client:
                        mock_client.return_value.__enter__.return_value.get.side_effect = (
                            _httpx.ConnectError("refused")
                        )
                        r = settings_client.post(
                            "/ui/settings/models/test",
                            data={"ollama_url": "http://localhost:11434"},
                        )
        assert r.status_code == 200
        ctx = tpl.TemplateResponse.call_args[0][2]
        assert ctx["error_message"] != ""
        assert ctx["success_message"] == ""

    def test_ollama_success_returns_200(self, settings_client: TestClient, tmp_path: Path) -> None:
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        with patch("file_organizer.web.settings_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            with patch("file_organizer.web.settings_routes._SETTINGS_FILE", tmp_path / "ws.json"):
                with patch("file_organizer.web.settings_routes._SETTINGS_DIR", tmp_path):
                    with patch("file_organizer.web.settings_routes.httpx.Client") as mock_client:
                        mock_client.return_value.__enter__.return_value.get.return_value = mock_resp
                        r = settings_client.post(
                            "/ui/settings/models/test",
                            data={"ollama_url": "http://localhost:11434"},
                        )
        assert r.status_code == 200
        ctx = tpl.TemplateResponse.call_args[0][2]
        assert ctx["success_message"] != ""
        assert ctx["error_message"] == ""


# ---------------------------------------------------------------------------
# settings_organization_validate
# ---------------------------------------------------------------------------


class TestSettingsOrganizationValidate:
    def test_valid_rules_returns_200(self, settings_client: TestClient, tmp_path: Path) -> None:
        with patch("file_organizer.web.settings_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            with patch("file_organizer.web.settings_routes._SETTINGS_FILE", tmp_path / "ws.json"):
                with patch("file_organizer.web.settings_routes._SETTINGS_DIR", tmp_path):
                    r = settings_client.post(
                        "/ui/settings/organization/validate",
                        data={"organization_rules": "docs/* -> Documents"},
                    )
        assert r.status_code == 200

    def test_invalid_rules_returns_200(self, settings_client: TestClient, tmp_path: Path) -> None:
        with patch("file_organizer.web.settings_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            with patch("file_organizer.web.settings_routes._SETTINGS_FILE", tmp_path / "ws.json"):
                r = settings_client.post(
                    "/ui/settings/organization/validate",
                    data={"organization_rules": "BAD RULE NO ARROW"},
                )
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# settings_organization_post
# ---------------------------------------------------------------------------


class TestSettingsOrganizationPost:
    def test_valid_save_returns_200(self, settings_client: TestClient, tmp_path: Path) -> None:
        with patch("file_organizer.web.settings_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            with patch("file_organizer.web.settings_routes._SETTINGS_FILE", tmp_path / "ws.json"):
                with patch("file_organizer.web.settings_routes._SETTINGS_DIR", tmp_path):
                    r = settings_client.post(
                        "/ui/settings/organization",
                        data={
                            "default_methodology": "para",
                            "auto_organize": "on",
                            "notifications_enabled": "on",
                            "file_filter_glob": "*.txt",
                            "organization_rules": "docs/* -> Documents",
                        },
                    )
        assert r.status_code == 200

    def test_invalid_rules_returns_200(self, settings_client: TestClient, tmp_path: Path) -> None:
        with patch("file_organizer.web.settings_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            with patch("file_organizer.web.settings_routes._SETTINGS_FILE", tmp_path / "ws.json"):
                r = settings_client.post(
                    "/ui/settings/organization",
                    data={
                        "default_methodology": "para",
                        "organization_rules": "no arrow here",
                    },
                )
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# settings_appearance_post
# ---------------------------------------------------------------------------


class TestSettingsAppearancePost:
    def test_save_returns_200(self, settings_client: TestClient, tmp_path: Path) -> None:
        with patch("file_organizer.web.settings_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            with patch("file_organizer.web.settings_routes._SETTINGS_FILE", tmp_path / "ws.json"):
                with patch("file_organizer.web.settings_routes._SETTINGS_DIR", tmp_path):
                    r = settings_client.post(
                        "/ui/settings/appearance",
                        data={"theme": "dark", "custom_theme_name": ""},
                    )
        assert r.status_code == 200

    def test_invalid_theme_uses_default(self, settings_client: TestClient, tmp_path: Path) -> None:
        ws_file = tmp_path / "ws.json"
        with patch("file_organizer.web.settings_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            with patch("file_organizer.web.settings_routes._SETTINGS_FILE", ws_file):
                with patch("file_organizer.web.settings_routes._SETTINGS_DIR", tmp_path):
                    r = settings_client.post(
                        "/ui/settings/appearance",
                        data={"theme": "rainbow", "custom_theme_name": ""},
                    )
        assert r.status_code == 200
        if ws_file.exists():
            data = json.loads(ws_file.read_text())
            assert data["theme"] == "light"


# ---------------------------------------------------------------------------
# settings_advanced_post
# ---------------------------------------------------------------------------


class TestSettingsAdvancedPost:
    def test_save_returns_200(self, settings_client: TestClient, tmp_path: Path) -> None:
        with patch("file_organizer.web.settings_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            with patch("file_organizer.web.settings_routes._SETTINGS_FILE", tmp_path / "ws.json"):
                with patch("file_organizer.web.settings_routes._SETTINGS_DIR", tmp_path):
                    r = settings_client.post(
                        "/ui/settings/advanced",
                        data={
                            "log_level": "DEBUG",
                            "cache_enabled": "on",
                            "debug_mode": "on",
                            "performance_mode": "performance",
                        },
                    )
        assert r.status_code == 200

    def test_invalid_log_level_falls_back(
        self, settings_client: TestClient, tmp_path: Path
    ) -> None:
        ws_file = tmp_path / "ws.json"
        with patch("file_organizer.web.settings_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            with patch("file_organizer.web.settings_routes._SETTINGS_FILE", ws_file):
                with patch("file_organizer.web.settings_routes._SETTINGS_DIR", tmp_path):
                    r = settings_client.post(
                        "/ui/settings/advanced",
                        data={"log_level": "VERBOSE", "performance_mode": "balanced"},
                    )
        assert r.status_code == 200
        if ws_file.exists():
            data = json.loads(ws_file.read_text())
            assert data["log_level"] == "INFO"


# ---------------------------------------------------------------------------
# settings_reset
# ---------------------------------------------------------------------------


class TestSettingsReset:
    def test_reset_returns_200(self, settings_client: TestClient, tmp_path: Path) -> None:
        with patch("file_organizer.web.settings_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            with patch("file_organizer.web.settings_routes._SETTINGS_FILE", tmp_path / "ws.json"):
                with patch("file_organizer.web.settings_routes._SETTINGS_DIR", tmp_path):
                    r = settings_client.post("/ui/settings/reset", data={"section": "general"})
        assert r.status_code == 200

    def test_reset_writes_defaults(self, settings_client: TestClient, tmp_path: Path) -> None:
        ws_file = tmp_path / "ws.json"
        ws_file.write_text(json.dumps({"theme": "dark", "language": "fr"}))
        with patch("file_organizer.web.settings_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            with patch("file_organizer.web.settings_routes._SETTINGS_FILE", ws_file):
                with patch("file_organizer.web.settings_routes._SETTINGS_DIR", tmp_path):
                    settings_client.post("/ui/settings/reset", data={"section": "general"})
        data = json.loads(ws_file.read_text())
        assert data["theme"] == "light"
        assert data["language"] == "en"

    def test_reset_invalid_section_uses_general(
        self, settings_client: TestClient, tmp_path: Path
    ) -> None:
        with patch("file_organizer.web.settings_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            with patch("file_organizer.web.settings_routes._SETTINGS_FILE", tmp_path / "ws.json"):
                with patch("file_organizer.web.settings_routes._SETTINGS_DIR", tmp_path):
                    r = settings_client.post("/ui/settings/reset", data={"section": "nonexistent"})
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# settings_import
# ---------------------------------------------------------------------------


class TestSettingsImport:
    def test_import_valid_json_returns_200(
        self, settings_client: TestClient, tmp_path: Path
    ) -> None:
        payload = json.dumps({"theme": "dark", "language": "fr"}).encode()
        with patch("file_organizer.web.settings_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            with patch("file_organizer.web.settings_routes._SETTINGS_FILE", tmp_path / "ws.json"):
                with patch("file_organizer.web.settings_routes._SETTINGS_DIR", tmp_path):
                    r = settings_client.post(
                        "/ui/settings/import",
                        data={"section": "general"},
                        files={"settings_file": ("ws.json", payload, "application/json")},
                    )
        assert r.status_code == 200

    def test_import_invalid_json_returns_200(
        self, settings_client: TestClient, tmp_path: Path
    ) -> None:
        with patch("file_organizer.web.settings_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            with patch("file_organizer.web.settings_routes._SETTINGS_FILE", tmp_path / "ws.json"):
                r = settings_client.post(
                    "/ui/settings/import",
                    data={"section": "general"},
                    files={"settings_file": ("ws.json", b"NOT JSON !!!!", "application/json")},
                )
        assert r.status_code == 200

    def test_import_non_dict_returns_200(self, settings_client: TestClient, tmp_path: Path) -> None:
        payload = json.dumps([1, 2, 3]).encode()
        with patch("file_organizer.web.settings_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            with patch("file_organizer.web.settings_routes._SETTINGS_FILE", tmp_path / "ws.json"):
                r = settings_client.post(
                    "/ui/settings/import",
                    data={"section": "general"},
                    files={"settings_file": ("ws.json", payload, "application/json")},
                )
        assert r.status_code == 200

    def test_import_updates_file_on_disk(self, settings_client: TestClient, tmp_path: Path) -> None:
        ws_file = tmp_path / "ws.json"
        payload = json.dumps({"theme": "dark"}).encode()
        with patch("file_organizer.web.settings_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            with patch("file_organizer.web.settings_routes._SETTINGS_FILE", ws_file):
                with patch("file_organizer.web.settings_routes._SETTINGS_DIR", tmp_path):
                    settings_client.post(
                        "/ui/settings/import",
                        data={"section": "general"},
                        files={"settings_file": ("ws.json", payload, "application/json")},
                    )
        assert ws_file.exists()
        data = json.loads(ws_file.read_text())
        assert data["theme"] == "dark"

    def test_import_invalid_section_falls_back_to_general(
        self, settings_client: TestClient, tmp_path: Path
    ) -> None:
        payload = json.dumps({"theme": "auto"}).encode()
        with patch("file_organizer.web.settings_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            with patch("file_organizer.web.settings_routes._SETTINGS_FILE", tmp_path / "ws.json"):
                with patch("file_organizer.web.settings_routes._SETTINGS_DIR", tmp_path):
                    r = settings_client.post(
                        "/ui/settings/import",
                        data={"section": "badname"},
                        files={"settings_file": ("ws.json", payload, "application/json")},
                    )
        assert r.status_code == 200
