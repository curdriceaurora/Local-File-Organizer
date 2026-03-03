"""Unit tests for web settings_routes helpers and route handlers.

Tests internal helpers (_as_form_bool, _coerce_bool, _validate_choice,
_validate_methodology, _validate_rules, _load_web_settings, _save_web_settings,
_update_web_settings, _section_context, _render_section) and route handlers
(settings_page, settings_search, settings_export, settings_import, settings_reset,
settings_general_get, settings_general_post, etc.) using mocked templates/settings.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.api.config import ApiSettings
from file_organizer.web.settings_routes import (
    METHODOLOGY_OPTIONS,
    THEME_OPTIONS,
    WebSettings,
    _as_form_bool,
    _coerce_bool,
    _load_web_settings,
    _render_section,
    _save_web_settings,
    _section_context,
    _update_web_settings,
    _validate_choice,
    _validate_methodology,
    _validate_rules,
    settings_export,
    settings_general_get,
    settings_general_post,
    settings_page,
    settings_reset,
    settings_search,
)

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_request():
    """Mock FastAPI Request object."""
    req = MagicMock()
    req.url = MagicMock()
    req.url.path = "/ui/settings"
    return req


@pytest.fixture()
def mock_settings():
    """Mock ApiSettings object."""
    s = MagicMock(spec=ApiSettings)
    s.app_name = "File Organizer"
    s.version = "2.0.0"
    s.allowed_paths = ["/tmp/test"]
    s.db_url = "sqlite://"
    return s


@pytest.fixture()
def temp_settings_file(tmp_path):
    """Create a temporary settings file for testing."""
    settings_dir = tmp_path / "config"
    settings_dir.mkdir()
    settings_file = settings_dir / "web-settings.json"

    # Patch the settings file location
    with patch("file_organizer.web.settings_routes._SETTINGS_DIR", settings_dir):
        with patch("file_organizer.web.settings_routes._SETTINGS_FILE", settings_file):
            yield settings_file


# ---------------------------------------------------------------------------
# _as_form_bool
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAsFormBool:
    """Test _as_form_bool helper."""

    def test_none_returns_false(self):
        assert _as_form_bool(None) is False

    def test_empty_string_returns_false(self):
        assert _as_form_bool("") is False

    def test_whitespace_only_returns_false(self):
        assert _as_form_bool("   ") is False

    def test_one_returns_true(self):
        assert _as_form_bool("1") is True

    def test_true_returns_true(self):
        assert _as_form_bool("true") is True

    def test_yes_returns_true(self):
        assert _as_form_bool("yes") is True

    def test_on_returns_true(self):
        assert _as_form_bool("on") is True

    def test_true_uppercase_returns_true(self):
        assert _as_form_bool("TRUE") is True

    def test_zero_returns_false(self):
        assert _as_form_bool("0") is False

    def test_false_returns_false(self):
        assert _as_form_bool("false") is False

    def test_random_string_returns_false(self):
        assert _as_form_bool("random") is False


# ---------------------------------------------------------------------------
# _coerce_bool
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCoerceBool:
    """Test _coerce_bool helper."""

    def test_bool_true_returns_true(self):
        assert _coerce_bool(True, False) is True

    def test_bool_false_returns_false(self):
        assert _coerce_bool(False, True) is False

    def test_string_true_returns_true(self):
        assert _coerce_bool("true", False) is True

    def test_string_false_returns_false(self):
        assert _coerce_bool("false", True) is False

    def test_invalid_type_returns_default(self):
        assert _coerce_bool(123, True) is True
        assert _coerce_bool(123, False) is False

    def test_none_returns_default(self):
        assert _coerce_bool(None, True) is True
        assert _coerce_bool(None, False) is False


# ---------------------------------------------------------------------------
# _validate_choice
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestValidateChoice:
    """Test _validate_choice helper."""

    def test_valid_choice_returns_value(self):
        result = _validate_choice("en", ["en", "es", "fr"], "en")
        assert result == "en"

    def test_invalid_choice_returns_fallback(self):
        result = _validate_choice("invalid", ["en", "es", "fr"], "en")
        assert result == "en"

    def test_whitespace_stripped(self):
        result = _validate_choice("  en  ", ["en", "es", "fr"], "en")
        assert result == "en"

    def test_empty_string_returns_fallback(self):
        result = _validate_choice("", ["en", "es", "fr"], "en")
        assert result == "en"


# ---------------------------------------------------------------------------
# _validate_methodology
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestValidateMethodology:
    """Test _validate_methodology helper."""

    def test_valid_methodology_returns_value(self):
        result = _validate_methodology("content_based")
        assert result == "content_based"

    def test_uppercase_normalized(self):
        result = _validate_methodology("PARA")
        assert result == "para"

    def test_invalid_methodology_returns_default(self):
        result = _validate_methodology("invalid")
        assert result == "content_based"

    def test_whitespace_stripped(self):
        result = _validate_methodology("  johnny_decimal  ")
        assert result == "johnny_decimal"


# ---------------------------------------------------------------------------
# _validate_rules
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestValidateRules:
    """Test _validate_rules helper."""

    def test_valid_single_rule(self):
        valid, msg = _validate_rules("docs/* -> Documents")
        assert valid is True
        assert "valid" in msg.lower()

    def test_valid_multiple_rules(self):
        valid, msg = _validate_rules("docs/* -> Documents\nimages/* -> Media")
        assert valid is True

    def test_empty_rules_invalid(self):
        valid, msg = _validate_rules("")
        assert valid is False
        assert "empty" in msg.lower()

    def test_missing_arrow_invalid(self):
        valid, msg = _validate_rules("docs/* Documents")
        assert valid is False
        assert "->" in msg or "invalid" in msg.lower()

    def test_empty_pattern_invalid(self):
        valid, msg = _validate_rules(" -> Documents")
        assert valid is False

    def test_empty_destination_invalid(self):
        valid, msg = _validate_rules("docs/* -> ")
        assert valid is False

    def test_comments_ignored(self):
        valid, msg = _validate_rules("# This is a comment\ndocs/* -> Documents")
        assert valid is True

    def test_whitespace_only_lines_ignored(self):
        valid, msg = _validate_rules("   \n\ndocs/* -> Documents\n   ")
        assert valid is True


# ---------------------------------------------------------------------------
# _load_web_settings & _save_web_settings
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLoadSaveWebSettings:
    """Test _load_web_settings and _save_web_settings helpers."""

    def test_load_defaults_when_file_missing(self, temp_settings_file):
        """Load defaults when file doesn't exist."""
        ws = _load_web_settings()
        assert isinstance(ws, WebSettings)
        assert ws.language == "en"
        assert ws.theme == "light"

    def test_save_creates_file(self, temp_settings_file):
        """Save settings to disk."""
        ws = WebSettings(language="es", theme="dark")
        _save_web_settings(ws)
        assert temp_settings_file.exists()
        content = json.loads(temp_settings_file.read_text())
        assert content["language"] == "es"
        assert content["theme"] == "dark"

    def test_load_persisted_settings(self, temp_settings_file):
        """Load previously saved settings."""
        ws_original = WebSettings(language="fr", timezone="Europe/London")
        _save_web_settings(ws_original)

        ws_loaded = _load_web_settings()
        assert ws_loaded.language == "fr"
        assert ws_loaded.timezone == "Europe/London"

    def test_invalid_json_returns_defaults(self, temp_settings_file):
        """Invalid JSON in file returns defaults."""
        temp_settings_file.write_text("invalid json {", encoding="utf-8")
        ws = _load_web_settings()
        assert ws.language == "en"

    def test_non_dict_payload_returns_defaults(self, temp_settings_file):
        """Non-dict JSON payload returns defaults."""
        temp_settings_file.write_text('["not", "a", "dict"]', encoding="utf-8")
        ws = _load_web_settings()
        assert ws.language == "en"

    def test_unknown_fields_skipped(self, temp_settings_file):
        """Unknown fields in saved settings are skipped."""
        data = {
            "language": "de",
            "unknown_field": "should be skipped",
        }
        temp_settings_file.write_text(json.dumps(data), encoding="utf-8")
        ws = _load_web_settings()
        assert ws.language == "de"
        assert not hasattr(ws, "unknown_field")

    def test_bool_coercion_on_load(self, temp_settings_file):
        """Boolean values are properly coerced on load."""
        data = {
            "auto_organize": "true",
            "notifications_enabled": "1",
            "cache_enabled": "false",
        }
        temp_settings_file.write_text(json.dumps(data), encoding="utf-8")
        ws = _load_web_settings()
        assert ws.auto_organize is True
        assert ws.notifications_enabled is True
        assert ws.cache_enabled is False


# ---------------------------------------------------------------------------
# _update_web_settings
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUpdateWebSettings:
    """Test _update_web_settings helper."""

    def test_update_single_field(self, temp_settings_file):
        """Update a single field."""
        ws = _update_web_settings(language="es")
        assert ws.language == "es"
        # Verify it was saved
        ws_loaded = _load_web_settings()
        assert ws_loaded.language == "es"

    def test_update_multiple_fields(self, temp_settings_file):
        """Update multiple fields."""
        ws = _update_web_settings(language="fr", theme="dark", timezone="Europe/Paris")
        assert ws.language == "fr"
        assert ws.theme == "dark"
        assert ws.timezone == "Europe/Paris"

    def test_unknown_fields_ignored(self, temp_settings_file):
        """Unknown fields are ignored."""
        ws = _update_web_settings(language="de", unknown_field="ignored")
        assert ws.language == "de"
        assert not hasattr(ws, "unknown_field")


# ---------------------------------------------------------------------------
# _section_context
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSectionContext:
    """Test _section_context helper."""

    def test_basic_context(self, mock_request):
        """Build a basic section context."""
        ws = WebSettings()
        context = _section_context(mock_request, ws, section="general")

        assert context["request"] is mock_request
        assert context["ws"] is ws
        assert context["section"] == "general"
        assert context["methodology_options"] == METHODOLOGY_OPTIONS
        assert context["theme_options"] == THEME_OPTIONS

    def test_with_success_message(self, mock_request):
        """Include a success message."""
        ws = WebSettings()
        context = _section_context(
            mock_request, ws, section="general", success_message="Saved!"
        )
        assert context["success_message"] == "Saved!"

    def test_with_error_message(self, mock_request):
        """Include an error message."""
        ws = WebSettings()
        context = _section_context(
            mock_request, ws, section="general", error_message="Failed!"
        )
        assert context["error_message"] == "Failed!"


# ---------------------------------------------------------------------------
# _render_section
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRenderSection:
    """Test _render_section helper."""

    @patch("file_organizer.web.settings_routes.templates")
    def test_render_section_general(self, mock_templates, mock_request):
        """Render a settings section."""
        ws = WebSettings()
        mock_response = MagicMock()
        mock_templates.TemplateResponse.return_value = mock_response

        result = _render_section(mock_request, ws, section="general")

        assert result is mock_response
        mock_templates.TemplateResponse.assert_called_once()
        call_args = mock_templates.TemplateResponse.call_args
        assert call_args[0][1] == "settings/_general.html"

    @patch("file_organizer.web.settings_routes.templates")
    def test_render_section_with_messages(self, mock_templates, mock_request):
        """Render section with success/error messages."""
        ws = WebSettings()
        mock_response = MagicMock()
        mock_templates.TemplateResponse.return_value = mock_response

        result = _render_section(
            mock_request,
            ws,
            section="models",
            success_message="Settings saved!",
        )

        assert result is mock_response
        call_args = mock_templates.TemplateResponse.call_args
        context = call_args[0][2]
        assert context["success_message"] == "Settings saved!"


# ---------------------------------------------------------------------------
# Route handlers: settings_page
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSettingsPage:
    """Test settings_page route handler."""

    @patch("file_organizer.web.settings_routes._load_web_settings")
    @patch("file_organizer.web.settings_routes.base_context")
    @patch("file_organizer.web.settings_routes.templates")
    def test_settings_page(self, mock_templates, mock_base_context, mock_load,
                          mock_request, mock_settings):
        """GET /settings returns full page."""
        ws = WebSettings()
        mock_load.return_value = ws
        mock_context = {"request": mock_request, "ws": ws}
        mock_base_context.return_value = mock_context
        mock_response = MagicMock()
        mock_templates.TemplateResponse.return_value = mock_response

        result = settings_page(mock_request, mock_settings)

        assert result is mock_response
        mock_templates.TemplateResponse.assert_called_once()
        call_args = mock_templates.TemplateResponse.call_args
        assert call_args[0][1] == "settings/index.html"


# ---------------------------------------------------------------------------
# Route handlers: settings_search
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSettingsSearch:
    """Test settings_search route handler."""

    def test_search_empty_query_returns_empty(self):
        """Empty query returns empty response."""
        result = settings_search(query="")
        assert result.body == b""

    def test_search_matches_section_name(self):
        """Search matches section names."""
        result = settings_search(query="general")
        assert b"General" in result.body

    def test_search_matches_setting_term(self):
        """Search matches setting terms."""
        result = settings_search(query="theme")
        assert b"Appearance" in result.body

    def test_search_no_matches_returns_hint(self):
        """No matches returns a hint message."""
        result = settings_search(query="nonexistent")
        assert b"No matching" in result.body

    def test_search_case_insensitive(self):
        """Search is case-insensitive."""
        result = settings_search(query="GENERAL")
        assert b"General" in result.body


# ---------------------------------------------------------------------------
# Route handlers: settings_export
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSettingsExport:
    """Test settings_export route handler."""

    @patch("file_organizer.web.settings_routes._load_web_settings")
    def test_settings_export(self, mock_load):
        """Export settings as JSON."""
        ws = WebSettings(language="es", theme="dark")
        mock_load.return_value = ws

        result = settings_export()

        assert result.media_type == "application/json"
        assert "web-settings.json" in result.headers["Content-Disposition"]

        payload = json.loads(result.body.decode())
        assert payload["language"] == "es"
        assert payload["theme"] == "dark"


# ---------------------------------------------------------------------------
# Route handlers: settings_reset
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSettingsReset:
    """Test settings_reset route handler."""

    @patch("file_organizer.web.settings_routes._save_web_settings")
    @patch("file_organizer.web.settings_routes.templates")
    def test_settings_reset(self, mock_templates, mock_save, mock_request, temp_settings_file):
        """Reset settings to defaults."""
        mock_response = MagicMock()
        mock_templates.TemplateResponse.return_value = mock_response

        result = settings_reset(mock_request, section="general")

        assert result is mock_response
        mock_save.assert_called_once()
        call_args = mock_save.call_args
        saved_ws = call_args[0][0]
        assert isinstance(saved_ws, WebSettings)
        assert saved_ws.language == "en"  # defaults


# ---------------------------------------------------------------------------
# Route handlers: settings_general_get & settings_general_post
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSettingsGeneralRoutes:
    """Test settings_general_get and settings_general_post route handlers."""

    @patch("file_organizer.web.settings_routes._load_web_settings")
    @patch("file_organizer.web.settings_routes._render_section")
    def test_settings_general_get(self, mock_render, mock_load, mock_request,
                                 temp_settings_file):
        """GET /settings/general returns section partial."""
        ws = WebSettings()
        mock_load.return_value = ws
        mock_response = MagicMock()
        mock_render.return_value = mock_response

        result = settings_general_get(mock_request)

        assert result is mock_response
        mock_render.assert_called_once_with(mock_request, ws, section="general")

    @patch("file_organizer.web.settings_routes._update_web_settings")
    @patch("file_organizer.web.settings_routes._render_section")
    def test_settings_general_post(self, mock_render, mock_update, mock_request,
                                  temp_settings_file):
        """POST /settings/general saves and returns section partial."""
        ws = WebSettings(language="es", timezone="Europe/Madrid")
        mock_update.return_value = ws
        mock_response = MagicMock()
        mock_render.return_value = mock_response

        result = settings_general_post(
            mock_request,
            language="es",
            timezone="Europe/Madrid",
            default_input_dir="/home/user/Downloads",
            default_output_dir="/home/user/Organized",
        )

        assert result is mock_response
        mock_render.assert_called_once()
        call_args = mock_render.call_args
        assert call_args[1]["section"] == "general"
        assert "saved" in call_args[1]["success_message"].lower()
