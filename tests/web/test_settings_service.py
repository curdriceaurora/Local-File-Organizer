"""Tests for route-independent web settings service helpers."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from file_organizer.config.schema import AppConfig
from file_organizer.web.settings_service import (
    WebSettings,
    WebSettingsStore,
    apply_advanced_settings,
    apply_app_config_payload,
    apply_general_settings,
    apply_model_settings,
    apply_organization_settings,
    apply_web_settings_payload,
    build_export_payload,
    import_settings_payload,
    reset_settings,
    validate_rules,
)

pytestmark = [pytest.mark.unit, pytest.mark.ci]


def _store(tmp_path) -> WebSettingsStore:
    return WebSettingsStore(tmp_path, tmp_path / "web-settings.json")


def _manager(config: AppConfig | None = None) -> MagicMock:
    manager = MagicMock()
    manager.load.return_value = config or AppConfig()
    return manager


def test_store_load_coerces_and_sanitizes_settings(tmp_path) -> None:
    settings_file = tmp_path / "web-settings.json"
    settings_file.write_text(
        json.dumps(
            {
                "language": "bogus",
                "theme": "dark",
                "cache_enabled": "false",
                "debug_mode": "on",
                "unknown": "ignored",
            }
        ),
        encoding="utf-8",
    )

    ws = _store(tmp_path).load()

    assert ws.language == "en"
    assert ws.theme == "dark"
    assert ws.cache_enabled is False
    assert ws.debug_mode is True
    assert not hasattr(ws, "unknown")


def test_store_update_ignores_unknown_fields(tmp_path) -> None:
    ws = _store(tmp_path).update(language="fr", unknown="value")

    assert ws.language == "fr"
    assert not hasattr(ws, "unknown")


def test_store_save_propagates_write_failures(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = _store(tmp_path)

    def fail_write(*_args, **_kwargs) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("file_organizer.web.settings_service.atomic_write_text", fail_write)

    with pytest.raises(OSError, match="disk full"):
        store.save(WebSettings())


def test_apply_web_settings_payload_only_accepts_known_typed_fields() -> None:
    ws = WebSettings()

    apply_web_settings_payload(
        ws,
        {
            "theme": "auto",
            "auto_organize": "yes",
            "organization_rules": 123,
            "unknown": "ignored",
        },
    )

    assert ws.theme == "auto"
    assert ws.auto_organize is True
    assert ws.organization_rules == "docs/* -> Documents\nimages/* -> Media/Images"
    assert not hasattr(ws, "unknown")


def test_apply_app_config_payload_trims_and_normalizes_shared_fields(tmp_path) -> None:
    app_config = AppConfig()
    input_dir = tmp_path / "in"
    output_dir = tmp_path / "out"

    apply_app_config_payload(
        app_config,
        {
            "default_input_dir": f" {input_dir} ",
            "default_output_dir": f" {output_dir} ",
            "text_model": " llama3 ",
            "vision_model": " llava ",
            "default_methodology": "johnny_decimal",
        },
    )

    assert app_config.default_input_dir == str(input_dir)
    assert app_config.default_output_dir == str(output_dir)
    assert app_config.models.text_model == "llama3"
    assert app_config.models.vision_model == "llava"
    assert app_config.default_methodology == "jd"


def test_import_settings_payload_persists_web_and_app_config_fields(tmp_path) -> None:
    store = _store(tmp_path)
    manager = _manager()
    input_dir = tmp_path / "input"

    ws, app_config = import_settings_payload(
        store,
        manager,
        {
            "language": "es",
            "theme": "unknown",
            "default_input_dir": str(input_dir),
            "default_methodology": "para",
        },
    )

    assert ws.language == "es"
    assert ws.theme == "light"
    assert app_config.default_input_dir == str(input_dir)
    assert app_config.default_methodology == "para"
    manager.save.assert_called_once()


def test_import_settings_payload_rejects_invalid_rules_without_saving(tmp_path) -> None:
    store = _store(tmp_path)
    manager = _manager()

    with pytest.raises(ValueError, match="Expected 'pattern -> destination'"):
        import_settings_payload(
            store,
            manager,
            {
                "language": "es",
                "organization_rules": "bad rule",
            },
        )

    assert not (tmp_path / "web-settings.json").exists()
    manager.save.assert_not_called()


def test_build_export_payload_includes_web_and_shared_fields(tmp_path) -> None:
    app_config = AppConfig()
    input_dir = tmp_path / "input"
    app_config.default_input_dir = str(input_dir)
    app_config.models.text_model = "llama3"

    payload = build_export_payload(WebSettings(language="ja"), app_config)

    assert payload["language"] == "ja"
    assert payload["default_input_dir"] == str(input_dir)
    assert payload["text_model"] == "llama3"
    assert payload["default_methodology"] == app_config.default_methodology


def test_reset_settings_only_resets_settings_page_app_config_fields(tmp_path) -> None:
    app_config = AppConfig()
    app_config.default_input_dir = "/custom/in"
    app_config.models.text_model = "custom-text"
    manager = _manager(app_config)

    ws, reset_config = reset_settings(_store(tmp_path), manager)

    assert ws == WebSettings()
    assert reset_config.default_input_dir == AppConfig().default_input_dir
    assert reset_config.models.text_model == AppConfig().models.text_model
    manager.save.assert_called_once()


def test_apply_general_and_model_settings_update_store_and_app_config(tmp_path) -> None:
    store = _store(tmp_path)
    manager = _manager()
    input_dir = tmp_path / "in"
    output_dir = tmp_path / "out"

    ws, app_config = apply_general_settings(
        store,
        manager,
        language="de",
        timezone="Europe/London",
        default_input_dir=f" {input_dir} ",
        default_output_dir=f" {output_dir} ",
    )
    assert ws.language == "de"
    assert app_config.default_input_dir == str(input_dir)
    assert app_config.default_output_dir == str(output_dir)

    ws, app_config = apply_model_settings(
        store,
        manager,
        text_model=" llama3 ",
        vision_model=" llava ",
        ollama_url=" http://localhost:11434 ",
    )
    assert ws.ollama_url == "http://localhost:11434"
    assert app_config.models.text_model == "llama3"
    assert app_config.models.vision_model == "llava"


def test_apply_organization_settings_validates_rules_before_saving(tmp_path) -> None:
    store = _store(tmp_path)
    manager = _manager()

    with pytest.raises(ValueError, match="Expected 'pattern -> destination'"):
        apply_organization_settings(
            store,
            manager,
            default_methodology="para",
            auto_organize="1",
            notifications_enabled=None,
            file_filter_glob="",
            organization_rules="bad rule",
        )

    ws, app_config = apply_organization_settings(
        store,
        manager,
        default_methodology="para",
        auto_organize="1",
        notifications_enabled=None,
        file_filter_glob="",
        organization_rules="docs/* -> Documents",
    )
    assert ws.auto_organize is True
    assert ws.notifications_enabled is False
    assert ws.file_filter_glob == "*"
    assert app_config.default_methodology == "para"


def test_apply_advanced_settings_normalizes_options() -> None:
    ws = WebSettings()

    apply_advanced_settings(
        ws,
        log_level="debug",
        cache_enabled=None,
        debug_mode="on",
        performance_mode="PERFORMANCE",
    )

    assert ws.log_level == "DEBUG"
    assert ws.cache_enabled is False
    assert ws.debug_mode is True
    assert ws.performance_mode == "performance"


def test_validate_rules_allows_comments_and_rejects_empty() -> None:
    assert validate_rules("# comment\ndocs/* -> Documents")[0] is True
    assert validate_rules("")[0] is False
