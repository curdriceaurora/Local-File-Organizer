"""Tests for the web UI settings page and section routes."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from file_organizer.api.dependencies import get_config_manager
from file_organizer.api.main import create_app
from file_organizer.api.test_utils import build_test_settings, csrf_headers, seed_csrf_token
from file_organizer.config.manager import ConfigManager
from file_organizer.config.schema import AppConfig


def _build_client(tmp_path: Path) -> TestClient:
    settings = build_test_settings(
        tmp_path,
        allowed_paths=[],
        auth_overrides={"auth_enabled": False},
    )
    app = create_app(settings)
    app.dependency_overrides[get_config_manager] = lambda: ConfigManager(
        config_dir=tmp_path / "app-config"
    )
    client = TestClient(app)
    seed_csrf_token(client)
    return client


def _load_app_config(tmp_path: Path) -> AppConfig:
    """Load the AppConfig backing a test client built by ``_build_client``."""
    return ConfigManager(config_dir=tmp_path / "app-config").load()


@pytest.fixture()
def _patch_settings_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect the web settings JSON file to a temp directory."""
    settings_mod = importlib.import_module("file_organizer.web.settings_routes")
    settings_dir = tmp_path / "config" / "file-organizer"
    settings_file = settings_dir / "web-settings.json"
    monkeypatch.setattr(settings_mod, "_SETTINGS_DIR", settings_dir)
    monkeypatch.setattr(settings_mod, "_SETTINGS_FILE", settings_file)
    return settings_file


# ---------------------------------------------------------------------------
# Full page
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSettingsFullPage:
    """Test the full settings page renders correctly."""

    @pytest.mark.usefixtures("_patch_settings_file")
    def test_settings_page_renders_tabs(self, tmp_path: Path) -> None:
        client = _build_client(tmp_path)
        response = client.get("/ui/settings")
        assert response.status_code == 200
        html = response.text
        assert "Configuration" in html
        assert "General" in html
        assert "Models" in html
        assert "Organization" in html
        assert "Appearance" in html
        assert "Advanced" in html
        assert "settings-panel" in html

    @pytest.mark.usefixtures("_patch_settings_file")
    def test_settings_page_loads_general_on_init(self, tmp_path: Path) -> None:
        client = _build_client(tmp_path)
        response = client.get("/ui/settings")
        assert response.status_code == 200
        assert 'hx-get="/ui/settings/general"' in response.text


# ---------------------------------------------------------------------------
# Section partials - GET
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSettingsSectionPartials:
    """Test each section partial loads correctly."""

    @pytest.mark.usefixtures("_patch_settings_file")
    @pytest.mark.parametrize(
        "section,expected_text",
        [
            ("general", "General settings"),
            ("models", "Model settings"),
            ("organization", "Organization settings"),
            ("appearance", "Appearance settings"),
            ("advanced", "Advanced settings"),
        ],
    )
    def test_section_partial_loads(self, tmp_path: Path, section: str, expected_text: str) -> None:
        client = _build_client(tmp_path)
        response = client.get(f"/ui/settings/{section}")
        assert response.status_code == 200
        assert expected_text in response.text

    @pytest.mark.usefixtures("_patch_settings_file")
    def test_general_partial_shows_default_values(self, tmp_path: Path) -> None:
        client = _build_client(tmp_path)
        response = client.get("/ui/settings/general")
        assert response.status_code == 200
        assert 'name="default_input_dir"' in response.text
        assert 'name="default_output_dir"' in response.text

    @pytest.mark.usefixtures("_patch_settings_file")
    def test_models_partial_shows_model_fields(self, tmp_path: Path) -> None:
        client = _build_client(tmp_path)
        response = client.get("/ui/settings/models")
        assert response.status_code == 200
        assert "qwen2.5:3b-instruct-q4_K_M" in response.text
        assert "qwen2.5vl:7b-q4_K_M" in response.text

    @pytest.mark.usefixtures("_patch_settings_file")
    def test_organization_partial_shows_methodology(self, tmp_path: Path) -> None:
        client = _build_client(tmp_path)
        response = client.get("/ui/settings/organization")
        assert response.status_code == 200
        assert "None (flat / content-based)" in response.text
        assert "Johnny Decimal" in response.text
        assert "PARA" in response.text

    @pytest.mark.usefixtures("_patch_settings_file")
    def test_appearance_partial_shows_theme(self, tmp_path: Path) -> None:
        client = _build_client(tmp_path)
        response = client.get("/ui/settings/appearance")
        assert response.status_code == 200
        assert "Light" in response.text
        assert "Dark" in response.text

    @pytest.mark.usefixtures("_patch_settings_file")
    def test_advanced_partial_shows_log_levels(self, tmp_path: Path) -> None:
        client = _build_client(tmp_path)
        response = client.get("/ui/settings/advanced")
        assert response.status_code == 200
        assert "DEBUG" in response.text
        assert "INFO" in response.text
        assert "WARNING" in response.text


# ---------------------------------------------------------------------------
# Section saves - POST
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSettingsSectionSaves:
    """Test saving settings via POST returns updated partials."""

    @pytest.mark.usefixtures("_patch_settings_file")
    def test_save_general_settings(self, tmp_path: Path, _patch_settings_file: Path) -> None:
        client = _build_client(tmp_path)
        input_dir = str(tmp_path / "input")
        output_dir = str(tmp_path / "output")
        response = client.post(
            "/ui/settings/general",
            data={
                "default_input_dir": input_dir,
                "default_output_dir": output_dir,
            },
            headers=csrf_headers(client),
        )
        assert response.status_code == 200
        assert "General settings saved" in response.text

        # Verify persisted to the shared AppConfig, not web-settings.json.
        app_config = _load_app_config(tmp_path)
        assert app_config.default_input_dir == input_dir
        assert app_config.default_output_dir == output_dir

    @pytest.mark.usefixtures("_patch_settings_file")
    def test_save_model_settings(self, tmp_path: Path, _patch_settings_file: Path) -> None:
        client = _build_client(tmp_path)
        response = client.post(
            "/ui/settings/models",
            data={
                "text_model": "llama3:8b",
                "vision_model": "llava:7b",
            },
            headers=csrf_headers(client),
        )
        assert response.status_code == 200
        assert "Model settings saved" in response.text

        app_config = _load_app_config(tmp_path)
        assert app_config.models.text_model == "llama3:8b"
        assert app_config.models.vision_model == "llava:7b"

    @pytest.mark.usefixtures("_patch_settings_file")
    def test_save_organization_settings(self, tmp_path: Path, _patch_settings_file: Path) -> None:
        client = _build_client(tmp_path)
        response = client.post(
            "/ui/settings/organization",
            data={
                "default_methodology": "para",
                "auto_organize": "1",
            },
            headers=csrf_headers(client),
        )
        assert response.status_code == 200
        assert "Organization settings saved" in response.text

        app_config = _load_app_config(tmp_path)
        assert app_config.default_methodology == "para"
        data = json.loads(_patch_settings_file.read_text(encoding="utf-8"))
        assert data["auto_organize"] is True

    @pytest.mark.usefixtures("_patch_settings_file")
    def test_save_appearance_settings(self, tmp_path: Path, _patch_settings_file: Path) -> None:
        client = _build_client(tmp_path)
        response = client.post(
            "/ui/settings/appearance",
            data={"theme": "dark"},
            headers=csrf_headers(client),
        )
        assert response.status_code == 200
        assert "Appearance settings saved" in response.text

        data = json.loads(_patch_settings_file.read_text(encoding="utf-8"))
        assert data["theme"] == "dark"

    @pytest.mark.usefixtures("_patch_settings_file")
    def test_save_advanced_settings(self, tmp_path: Path, _patch_settings_file: Path) -> None:
        client = _build_client(tmp_path)
        response = client.post(
            "/ui/settings/advanced",
            data={
                "log_level": "DEBUG",
                "cache_enabled": "1",
                "debug_mode": "1",
            },
            headers=csrf_headers(client),
        )
        assert response.status_code == 200
        assert "Advanced settings saved" in response.text

        data = json.loads(_patch_settings_file.read_text(encoding="utf-8"))
        assert data["log_level"] == "DEBUG"
        assert data["cache_enabled"] is True
        assert data["debug_mode"] is True


# ---------------------------------------------------------------------------
# Input validation and edge cases
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSettingsValidation:
    """Test handling of invalid inputs and edge cases."""

    @pytest.mark.usefixtures("_patch_settings_file")
    def test_invalid_methodology_defaults_to_none(
        self, tmp_path: Path, _patch_settings_file: Path
    ) -> None:
        client = _build_client(tmp_path)
        response = client.post(
            "/ui/settings/organization",
            data={"default_methodology": "not_a_real_method"},
            headers=csrf_headers(client),
        )
        assert response.status_code == 200
        assert "Organization settings saved" in response.text

        app_config = _load_app_config(tmp_path)
        assert app_config.default_methodology == "none"

    @pytest.mark.usefixtures("_patch_settings_file")
    def test_invalid_theme_defaults_to_light(
        self, tmp_path: Path, _patch_settings_file: Path
    ) -> None:
        client = _build_client(tmp_path)
        response = client.post(
            "/ui/settings/appearance",
            data={"theme": "neon"},
            headers=csrf_headers(client),
        )
        assert response.status_code == 200

        data = json.loads(_patch_settings_file.read_text(encoding="utf-8"))
        assert data["theme"] == "light"

    @pytest.mark.usefixtures("_patch_settings_file")
    def test_invalid_log_level_defaults_to_info(
        self, tmp_path: Path, _patch_settings_file: Path
    ) -> None:
        client = _build_client(tmp_path)
        response = client.post(
            "/ui/settings/advanced",
            data={"log_level": "INVALID_LEVEL"},
            headers=csrf_headers(client),
        )
        assert response.status_code == 200

        data = json.loads(_patch_settings_file.read_text(encoding="utf-8"))
        assert data["log_level"] == "INFO"

    @pytest.mark.usefixtures("_patch_settings_file")
    def test_empty_model_names_use_defaults(
        self, tmp_path: Path, _patch_settings_file: Path
    ) -> None:
        client = _build_client(tmp_path)
        response = client.post(
            "/ui/settings/models",
            data={"text_model": "", "vision_model": ""},
            headers=csrf_headers(client),
        )
        assert response.status_code == 200

        app_config = _load_app_config(tmp_path)
        assert app_config.models.text_model == "qwen2.5:3b-instruct-q4_K_M"
        assert app_config.models.vision_model == "qwen2.5vl:7b-q4_K_M"

    @pytest.mark.usefixtures("_patch_settings_file")
    def test_unchecked_checkboxes_save_as_false(
        self, tmp_path: Path, _patch_settings_file: Path
    ) -> None:
        # First save with checkboxes on
        client = _build_client(tmp_path)
        client.post(
            "/ui/settings/advanced",
            data={"log_level": "INFO", "cache_enabled": "1", "debug_mode": "1"},
            headers=csrf_headers(client),
        )
        # Then save without checkboxes (unchecked = not sent)
        client.post(
            "/ui/settings/advanced",
            data={"log_level": "INFO"},
            headers=csrf_headers(client),
        )

        data = json.loads(_patch_settings_file.read_text(encoding="utf-8"))
        assert data["cache_enabled"] is False
        assert data["debug_mode"] is False

    @pytest.mark.usefixtures("_patch_settings_file")
    def test_settings_persist_across_reads(
        self, tmp_path: Path, _patch_settings_file: Path
    ) -> None:
        client = _build_client(tmp_path)
        client.post(
            "/ui/settings/general",
            data={
                "default_input_dir": "/my/custom/path",
                "default_output_dir": "/my/output",
            },
            headers=csrf_headers(client),
        )

        # Read back via GET
        response = client.get("/ui/settings/general")
        assert response.status_code == 200
        assert "/my/custom/path" in response.text
        assert "/my/output" in response.text

    @pytest.mark.usefixtures("_patch_settings_file")
    def test_settings_loads_defaults_when_file_missing(self, tmp_path: Path) -> None:
        client = _build_client(tmp_path)
        response = client.get("/ui/settings/general")
        assert response.status_code == 200
        assert "General settings" in response.text


@pytest.mark.unit
class TestSettingsUtilities:
    """Tests for search/import/export/reset and validation helpers."""

    @pytest.mark.usefixtures("_patch_settings_file")
    def test_settings_search_returns_matching_sections(self, tmp_path: Path) -> None:
        client = _build_client(tmp_path)
        response = client.get("/ui/settings/search", params={"q": "timezone"})
        assert response.status_code == 200
        assert "General" in response.text

    @pytest.mark.usefixtures("_patch_settings_file")
    def test_settings_export_download(self, tmp_path: Path) -> None:
        client = _build_client(tmp_path)
        response = client.get("/ui/settings/export")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/json")
        assert "Content-Disposition" in response.headers

    @pytest.mark.usefixtures("_patch_settings_file")
    @pytest.mark.ci
    def test_settings_import(self, tmp_path: Path, _patch_settings_file: Path) -> None:
        client = _build_client(tmp_path)
        payload = {
            "language": "fr",
            "timezone": "Europe/London",
            "default_input_dir": "/import/input",
            "default_output_dir": "/import/output",
        }
        response = client.post(
            "/ui/settings/import",
            data={"section": "general"},
            files={"settings_file": ("settings.json", json.dumps(payload), "application/json")},
            headers=csrf_headers(client),
        )
        assert response.status_code == 200
        assert "Settings imported successfully" in response.text
        stored = json.loads(_patch_settings_file.read_text(encoding="utf-8"))
        assert stored["language"] == "fr"
        assert stored["timezone"] == "Europe/London"
        # Shared workflow fields persist to AppConfig, not web-settings.json.
        app_config = _load_app_config(tmp_path)
        assert app_config.default_input_dir == "/import/input"
        assert app_config.default_output_dir == "/import/output"

    @pytest.mark.usefixtures("_patch_settings_file")
    def test_settings_reset(self, tmp_path: Path, _patch_settings_file: Path) -> None:
        client = _build_client(tmp_path)
        client.post(
            "/ui/settings/general",
            data={"default_input_dir": "/custom", "default_output_dir": "/custom-out"},
            headers=csrf_headers(client),
        )
        response = client.post(
            "/ui/settings/reset",
            data={"section": "general"},
            headers=csrf_headers(client),
        )
        assert response.status_code == 200
        assert "Settings reset to defaults" in response.text
        app_config = _load_app_config(tmp_path)
        assert app_config.default_input_dir == ""
        assert app_config.default_output_dir == ""

    @pytest.mark.usefixtures("_patch_settings_file")
    def test_rules_validation_endpoint(self, tmp_path: Path) -> None:
        client = _build_client(tmp_path)
        ok = client.post(
            "/ui/settings/organization/validate",
            data={"organization_rules": "docs/* -> Documents"},
            headers=csrf_headers(client),
        )
        assert ok.status_code == 200
        assert "Rules look valid" in ok.text

        bad = client.post(
            "/ui/settings/organization/validate",
            data={"organization_rules": "invalid rule line"},
            headers=csrf_headers(client),
        )
        assert bad.status_code == 200
        assert "invalid" in bad.text.lower()

    @pytest.mark.usefixtures("_patch_settings_file")
    def test_model_connection_failure_returns_error(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        class BrokenClient:
            def __enter__(self) -> BrokenClient:
                return self

            def __exit__(self, *_args: object) -> None:
                return None

            def get(self, _url: str) -> None:
                raise RuntimeError("connection failed")

        settings_mod = importlib.import_module("file_organizer.web.settings_routes")
        monkeypatch.setattr(settings_mod.httpx, "Client", lambda timeout: BrokenClient())

        client = _build_client(tmp_path)
        response = client.post(
            "/ui/settings/models/test",
            data={"ollama_url": "http://localhost:11434"},
            headers=csrf_headers(client),
        )
        assert response.status_code == 200
        assert "connection failed" in response.text
