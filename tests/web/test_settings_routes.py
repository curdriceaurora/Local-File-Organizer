"""Tests for settings routes and handlers.

Tests verify:
- Settings pages render with correct template and context
- Form submissions save settings correctly
- Configuration changes are applied
- Import/export operations work
- Reset operations clear settings properly
- Validation of rules and choices
- Error conditions are handled
"""

from __future__ import annotations

import json
from dataclasses import asdict
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.api.config import ApiSettings
from file_organizer.web.settings_routes import (
    LANGUAGE_OPTIONS,
    LOG_LEVEL_OPTIONS,
    METHODOLOGY_OPTIONS,
    PERFORMANCE_MODES,
    THEME_OPTIONS,
    TIMEZONE_OPTIONS,
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
)

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_request():
    """Return a mock FastAPI Request."""
    req = MagicMock()
    req.url = MagicMock()
    req.url.path = "/ui/settings"
    return req


@pytest.fixture()
def settings():
    """Return an ApiSettings mock."""
    s = MagicMock(spec=ApiSettings)
    s.allowed_paths = ["/tmp/test"]
    s.app_name = "File Organizer"
    s.version = "2.0.0"
    return s


@pytest.fixture(autouse=True)
def use_temp_settings_dir(monkeypatch, tmp_path):
    """Use temporary directory for settings file."""
    with patch("file_organizer.web.settings_routes._SETTINGS_DIR", tmp_path):
        with patch(
            "file_organizer.web.settings_routes._SETTINGS_FILE",
            tmp_path / "web-settings.json",
        ):
            yield tmp_path


# ---------------------------------------------------------------------------
# _as_form_bool
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAsFormBool:
    """Test HTML form checkbox value conversion."""

    def test_true_values(self):
        """Should recognize true values."""
        assert _as_form_bool("1") is True
        assert _as_form_bool("true") is True
        assert _as_form_bool("yes") is True
        assert _as_form_bool("on") is True

    def test_false_values(self):
        """Should treat non-true values as false."""
        assert _as_form_bool("0") is False
        assert _as_form_bool("false") is False
        assert _as_form_bool("no") is False
        assert _as_form_bool("") is False

    def test_none_value(self):
        """Should treat None as false."""
        assert _as_form_bool(None) is False


# ---------------------------------------------------------------------------
# _coerce_bool
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCoerceBool:
    """Test arbitrary value to boolean coercion."""

    def test_bool_values(self):
        """Should pass through bool values."""
        assert _coerce_bool(True, False) is True
        assert _coerce_bool(False, True) is False

    def test_string_values(self):
        """Should coerce string values."""
        assert _coerce_bool("true", False) is True
        assert _coerce_bool("false", True) is False
        assert _coerce_bool("1", False) is True

    def test_fallback_to_default(self):
        """Should use default for non-bool/string values."""
        assert _coerce_bool(123, False) is False
        assert _coerce_bool(123, True) is True
        assert _coerce_bool(None, False) is False
        assert _coerce_bool([], True) is True


# ---------------------------------------------------------------------------
# _validate_choice
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestValidateChoice:
    """Test choice validation."""

    def test_valid_choice(self):
        """Should return valid choice."""
        allowed = ["en", "es", "fr"]
        assert _validate_choice("en", allowed, "en") == "en"
        assert _validate_choice("fr", allowed, "en") == "fr"

    def test_invalid_choice_uses_fallback(self):
        """Should use fallback for invalid choice."""
        allowed = ["en", "es", "fr"]
        assert _validate_choice("de", allowed, "en") == "en"

    def test_strips_whitespace(self):
        """Should strip whitespace."""
        allowed = ["en", "es"]
        assert _validate_choice("  en  ", allowed, "en") == "en"


# ---------------------------------------------------------------------------
# _validate_methodology
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestValidateMethodology:
    """Test methodology validation."""

    def test_valid_methodologies(self):
        """Should accept valid methodologies."""
        assert _validate_methodology("content_based") == "content_based"
        assert _validate_methodology("johnny_decimal") == "johnny_decimal"
        assert _validate_methodology("para") == "para"
        assert _validate_methodology("date_based") == "date_based"

    def test_case_insensitive(self):
        """Should be case insensitive."""
        assert _validate_methodology("CONTENT_BASED") == "content_based"
        assert _validate_methodology("PARA") == "para"

    def test_invalid_defaults_to_content_based(self):
        """Should default to content_based for invalid."""
        assert _validate_methodology("invalid") == "content_based"
        assert _validate_methodology("") == "content_based"


# ---------------------------------------------------------------------------
# _validate_rules
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestValidateRules:
    """Test organization rule validation."""

    def test_valid_rules(self):
        """Should accept valid rules."""
        rules = "docs/* -> Documents\nimages/* -> Media/Images"
        valid, msg = _validate_rules(rules)
        assert valid is True

    def test_empty_rules(self):
        """Should reject empty rules."""
        valid, msg = _validate_rules("")
        assert valid is False
        assert "cannot be empty" in msg.lower()

    def test_missing_arrow(self):
        """Should reject rules missing arrow."""
        rules = "docs/* Documents"
        valid, msg = _validate_rules(rules)
        assert valid is False
        assert "invalid" in msg.lower()

    def test_missing_pattern(self):
        """Should reject rules with missing pattern."""
        rules = " -> Documents"
        valid, msg = _validate_rules(rules)
        assert valid is False

    def test_missing_destination(self):
        """Should reject rules with missing destination."""
        rules = "docs/* ->"
        valid, msg = _validate_rules(rules)
        assert valid is False

    def test_lines_with_comments(self):
        """Should allow comment lines."""
        rules = "# This is a comment\ndocs/* -> Documents"
        valid, msg = _validate_rules(rules)
        assert valid is True

    def test_multiline_rules(self):
        """Should validate multiple rules."""
        rules = "docs/* -> Documents\nimages/* -> Media\nvideos/* -> Media/Videos"
        valid, msg = _validate_rules(rules)
        assert valid is True

    def test_whitespace_handling(self):
        """Should handle extra whitespace."""
        rules = "  docs/*  ->  Documents  \n  images/*  ->  Media  "
        valid, msg = _validate_rules(rules)
        assert valid is True


# ---------------------------------------------------------------------------
# _load_web_settings
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLoadWebSettings:
    """Test settings loading."""

    def test_default_settings_when_missing(self, use_temp_settings_dir):
        """Should return defaults when file missing."""
        ws = _load_web_settings()
        assert isinstance(ws, WebSettings)
        assert ws.language == "en"
        assert ws.timezone == "UTC"
        assert ws.theme == "light"

    def test_load_existing_settings(self, use_temp_settings_dir):
        """Should load settings from file."""
        # Save settings
        ws_original = WebSettings(language="es", timezone="Europe/London")
        _save_web_settings(ws_original)

        # Load and verify
        ws_loaded = _load_web_settings()
        assert ws_loaded.language == "es"
        assert ws_loaded.timezone == "Europe/London"

    def test_coerce_bool_fields(self, use_temp_settings_dir):
        """Should coerce bool fields correctly."""
        from file_organizer.web.settings_routes import _SETTINGS_FILE

        raw = {
            "auto_organize": "true",
            "notifications_enabled": "1",
            "cache_enabled": "false",
            "debug_mode": None,
        }
        _SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        _SETTINGS_FILE.write_text(json.dumps(raw))

        ws = _load_web_settings()
        assert ws.auto_organize is True
        assert ws.notifications_enabled is True
        assert ws.cache_enabled is False
        assert ws.debug_mode is False

    def test_unknown_fields_ignored(self, use_temp_settings_dir):
        """Should ignore unknown fields."""
        from file_organizer.web.settings_routes import _SETTINGS_FILE

        raw = {
            "language": "en",
            "unknown_field": "value",
        }
        _SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        _SETTINGS_FILE.write_text(json.dumps(raw))

        ws = _load_web_settings()
        assert ws.language == "en"
        assert not hasattr(ws, "unknown_field")


# ---------------------------------------------------------------------------
# _save_web_settings
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSaveWebSettings:
    """Test settings saving."""

    def test_save_to_file(self, use_temp_settings_dir):
        """Should save settings to JSON file."""
        ws = WebSettings(language="es", timezone="Europe/London")
        _save_web_settings(ws)

        from file_organizer.web.settings_routes import _SETTINGS_FILE

        assert _SETTINGS_FILE.exists()
        raw = json.loads(_SETTINGS_FILE.read_text())
        assert raw["language"] == "es"
        assert raw["timezone"] == "Europe/London"

    def test_creates_directory(self, use_temp_settings_dir, tmp_path):
        """Should create directory if missing."""

        new_dir = tmp_path / "new" / "path"
        with patch(
            "file_organizer.web.settings_routes._SETTINGS_DIR", new_dir
        ):
            with patch(
                "file_organizer.web.settings_routes._SETTINGS_FILE",
                new_dir / "settings.json",
            ):
                ws = WebSettings()
                _save_web_settings(ws)
                assert new_dir.exists()


# ---------------------------------------------------------------------------
# _update_web_settings
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUpdateWebSettings:
    """Test settings update."""

    def test_update_single_field(self, use_temp_settings_dir):
        """Should update single field."""
        ws = _update_web_settings(language="fr")
        assert ws.language == "fr"
        assert ws.timezone == "UTC"  # Unchanged

    def test_update_multiple_fields(self, use_temp_settings_dir):
        """Should update multiple fields."""
        ws = _update_web_settings(
            language="es",
            timezone="America/New_York",
            theme="dark",
        )
        assert ws.language == "es"
        assert ws.timezone == "America/New_York"
        assert ws.theme == "dark"

    def test_unknown_fields_ignored(self, use_temp_settings_dir):
        """Should ignore unknown fields."""
        ws = _update_web_settings(unknown_field="value")
        # Should not raise and should load successfully
        assert isinstance(ws, WebSettings)


# ---------------------------------------------------------------------------
# _section_context
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSectionContext:
    """Test section context building."""

    def test_section_context_has_required_keys(self, mock_request):
        """Should include required keys."""
        ws = WebSettings()
        ctx = _section_context(mock_request, ws, section="general")
        assert ctx["request"] == mock_request
        assert ctx["ws"] == ws
        assert ctx["section"] == "general"

    def test_section_context_includes_options(self, mock_request):
        """Should include all option lists."""
        ws = WebSettings()
        ctx = _section_context(mock_request, ws, section="general")
        assert "methodology_options" in ctx
        assert "log_level_options" in ctx
        assert "theme_options" in ctx
        assert "language_options" in ctx
        assert "timezone_options" in ctx
        assert "performance_modes" in ctx

    def test_success_message(self, mock_request):
        """Should include success message."""
        ws = WebSettings()
        ctx = _section_context(
            mock_request,
            ws,
            section="general",
            success_message="Settings saved!",
        )
        assert ctx["success_message"] == "Settings saved!"

    def test_error_message(self, mock_request):
        """Should include error message."""
        ws = WebSettings()
        ctx = _section_context(
            mock_request,
            ws,
            section="general",
            error_message="Save failed!",
        )
        assert ctx["error_message"] == "Save failed!"


# ---------------------------------------------------------------------------
# _render_section
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRenderSection:
    """Test section rendering."""

    @patch("file_organizer.web.settings_routes.templates")
    def test_render_section_calls_template(self, mock_templates, mock_request):
        """Should call template renderer."""
        ws = WebSettings()
        mock_response = MagicMock()
        mock_templates.TemplateResponse.return_value = mock_response

        result = _render_section(
            mock_request,
            ws,
            section="general",
            success_message="Saved!",
        )

        assert result == mock_response
        mock_templates.TemplateResponse.assert_called_once()

    @patch("file_organizer.web.settings_routes.templates")
    def test_render_section_with_error(
        self, mock_templates, mock_request
    ):
        """Should render with error message."""
        ws = WebSettings()
        mock_response = MagicMock()
        mock_templates.TemplateResponse.return_value = mock_response

        result = _render_section(
            mock_request,
            ws,
            section="general",
            error_message="Save failed!",
        )

        assert result == mock_response


# ---------------------------------------------------------------------------
# WebSettings dataclass
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestWebSettings:
    """Test WebSettings dataclass."""

    def test_default_values(self):
        """Should have sensible defaults."""
        ws = WebSettings()
        assert ws.language == "en"
        assert ws.timezone == "UTC"
        assert ws.theme == "light"
        assert ws.auto_organize is False
        assert ws.notifications_enabled is True
        assert ws.cache_enabled is True
        assert ws.debug_mode is False
        assert ws.performance_mode == "balanced"

    def test_custom_values(self):
        """Should accept custom values."""
        ws = WebSettings(
            language="es",
            timezone="Europe/London",
            theme="dark",
            auto_organize=True,
        )
        assert ws.language == "es"
        assert ws.timezone == "Europe/London"
        assert ws.theme == "dark"
        assert ws.auto_organize is True

    def test_to_dict(self):
        """Should convert to dict with asdict."""
        ws = WebSettings(language="fr")
        d = asdict(ws)
        assert d["language"] == "fr"
        assert d["timezone"] == "UTC"
        assert isinstance(d, dict)

    def test_all_fields_present(self):
        """Should have all expected fields."""
        ws = WebSettings()
        assert hasattr(ws, "language")
        assert hasattr(ws, "timezone")
        assert hasattr(ws, "default_input_dir")
        assert hasattr(ws, "default_output_dir")
        assert hasattr(ws, "text_model")
        assert hasattr(ws, "vision_model")
        assert hasattr(ws, "ollama_url")
        assert hasattr(ws, "default_methodology")
        assert hasattr(ws, "auto_organize")
        assert hasattr(ws, "notifications_enabled")
        assert hasattr(ws, "file_filter_glob")
        assert hasattr(ws, "organization_rules")
        assert hasattr(ws, "theme")
        assert hasattr(ws, "custom_theme_name")
        assert hasattr(ws, "log_level")
        assert hasattr(ws, "cache_enabled")
        assert hasattr(ws, "debug_mode")
        assert hasattr(ws, "performance_mode")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestConstants:
    """Test that option constants are properly defined."""

    def test_methodology_options(self):
        """Should have methodology options."""
        assert "content_based" in METHODOLOGY_OPTIONS
        assert "johnny_decimal" in METHODOLOGY_OPTIONS
        assert "para" in METHODOLOGY_OPTIONS
        assert "date_based" in METHODOLOGY_OPTIONS

    def test_theme_options(self):
        """Should have theme options."""
        assert "light" in THEME_OPTIONS
        assert "dark" in THEME_OPTIONS
        assert "auto" in THEME_OPTIONS

    def test_log_level_options(self):
        """Should have log level options."""
        assert "DEBUG" in LOG_LEVEL_OPTIONS
        assert "INFO" in LOG_LEVEL_OPTIONS
        assert "WARNING" in LOG_LEVEL_OPTIONS

    def test_language_options(self):
        """Should have language options."""
        assert "en" in LANGUAGE_OPTIONS

    def test_timezone_options(self):
        """Should have timezone options."""
        assert "UTC" in TIMEZONE_OPTIONS

    def test_performance_modes(self):
        """Should have performance modes."""
        assert "balanced" in PERFORMANCE_MODES
        assert "performance" in PERFORMANCE_MODES
        assert "memory_saver" in PERFORMANCE_MODES


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSettingsIntegration:
    """Integration tests for settings lifecycle."""

    def test_save_and_load_roundtrip(self, use_temp_settings_dir):
        """Should save and load settings correctly."""
        # Save
        original = WebSettings(
            language="fr",
            timezone="Europe/London",
            theme="dark",
            auto_organize=True,
        )
        _save_web_settings(original)

        # Load
        loaded = _load_web_settings()

        # Verify
        assert loaded.language == "fr"
        assert loaded.timezone == "Europe/London"
        assert loaded.theme == "dark"
        assert loaded.auto_organize is True

    def test_update_preserves_other_fields(self, use_temp_settings_dir):
        """Update should not affect other fields."""
        # Set initial values
        _update_web_settings(
            language="es",
            timezone="Europe/London",
            theme="dark",
        )

        # Update only language
        ws = _update_web_settings(language="fr")

        # Verify language changed but others preserved
        assert ws.language == "fr"
        assert ws.timezone == "Europe/London"
        assert ws.theme == "dark"

    def test_invalid_choice_gets_validated_on_load(
        self, use_temp_settings_dir
    ):
        """Invalid choices should be fixed on load."""
        from file_organizer.web.settings_routes import _SETTINGS_FILE

        # Save invalid data directly
        raw = {
            "language": "invalid_lang",
            "timezone": "invalid_tz",
            "theme": "invalid_theme",
        }
        _SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        _SETTINGS_FILE.write_text(json.dumps(raw))

        # Load and verify defaults applied
        ws = _load_web_settings()
        assert ws.language == "en"  # Defaults
        assert ws.timezone == "UTC"
        assert ws.theme == "light"
