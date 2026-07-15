"""Route-independent settings helpers for the web UI."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from loguru import logger

from file_organizer.config.defaults import DEFAULT_OLLAMA_URL
from file_organizer.config.manager import ConfigManager
from file_organizer.config.methodology import normalize as normalize_methodology
from file_organizer.config.schema import AppConfig
from file_organizer.utils.atomic_write import atomic_write_text
from file_organizer.web._forms import coerce_bool, form_bool

PROFILE = "default"

LOG_LEVEL_OPTIONS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
THEME_OPTIONS = ["light", "dark", "auto", "custom"]
LANGUAGE_OPTIONS = ["en", "es", "fr", "de", "ja"]
TIMEZONE_OPTIONS = [
    "UTC",
    "America/New_York",
    "America/Chicago",
    "America/Denver",
    "America/Los_Angeles",
    "Europe/London",
]
PERFORMANCE_MODES = ["balanced", "performance", "memory_saver"]

BOOLEAN_FIELDS = {"auto_organize", "notifications_enabled", "cache_enabled", "debug_mode"}


@dataclass
class WebSettings:
    """Persistent settings for the web UI.

    Holds only fields with no canonical home elsewhere. The workflow fields
    shown alongside these on the settings page -- default input/output dirs,
    methodology, text/vision model -- live on the shared ``AppConfig``.
    """

    # General
    language: str = "en"
    timezone: str = "UTC"

    # Models
    ollama_url: str = DEFAULT_OLLAMA_URL

    # Organization
    auto_organize: bool = False
    notifications_enabled: bool = True
    file_filter_glob: str = "*"
    organization_rules: str = "docs/* -> Documents\nimages/* -> Media/Images"

    # Appearance
    theme: str = "light"
    custom_theme_name: str = ""

    # Advanced
    log_level: str = "INFO"
    cache_enabled: bool = True
    debug_mode: bool = False
    performance_mode: str = "balanced"


def validate_choice(value: str, allowed: list[str], fallback: str) -> str:
    """Return *value* if it is in *allowed*, otherwise return *fallback*."""
    candidate = value.strip()
    return candidate if candidate in allowed else fallback


def validate_rules(rules: str) -> tuple[bool, str]:
    """Validate newline-separated ``pattern -> destination`` rules."""
    lines = [line.strip() for line in rules.splitlines() if line.strip()]
    if not lines:
        return False, "Rules cannot be empty."
    for idx, line in enumerate(lines, start=1):
        if line.startswith("#"):
            continue
        if "->" not in line:
            return False, f"Line {idx} is invalid. Expected 'pattern -> destination'."
        left, right = [part.strip() for part in line.split("->", 1)]
        if not left or not right:
            return False, f"Line {idx} is invalid. Both pattern and destination are required."
    return True, "Rules look valid."


def sanitize_web_settings(ws: WebSettings) -> WebSettings:
    """Normalize option-backed settings after loading or importing."""
    ws.theme = validate_choice(ws.theme, THEME_OPTIONS, "light")
    ws.log_level = validate_choice(ws.log_level, LOG_LEVEL_OPTIONS, "INFO")
    ws.performance_mode = validate_choice(ws.performance_mode, PERFORMANCE_MODES, "balanced")
    ws.language = validate_choice(ws.language, LANGUAGE_OPTIONS, "en")
    ws.timezone = validate_choice(ws.timezone, TIMEZONE_OPTIONS, "UTC")
    return ws


class WebSettingsStore:
    """JSON-backed persistence for ``WebSettings``."""

    def __init__(self, settings_dir: Path, settings_file: Path) -> None:
        """Store the directory and JSON file used for settings persistence."""
        self.settings_dir = settings_dir
        self.settings_file = settings_file

    def load(self) -> WebSettings:
        """Load persisted settings, returning defaults on missing or invalid data."""
        if not self.settings_file.exists():
            return WebSettings()

        try:
            raw = json.loads(self.settings_file.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return WebSettings()

            ws = WebSettings()
            apply_web_settings_payload(ws, raw)
            return sanitize_web_settings(ws)
        except Exception as exc:
            logger.warning("Failed to load settings from {}: {}", self.settings_file, exc)
            return WebSettings()

    def save(self, ws: WebSettings) -> None:
        """Persist settings to disk."""
        try:
            self.settings_dir.mkdir(parents=True, exist_ok=True)
            atomic_write_text(self.settings_file, json.dumps(asdict(ws), indent=2) + "\n")
        except Exception as exc:
            logger.error("Failed to save settings to {}: {}", self.settings_file, exc)

    def update(self, **kwargs: object) -> WebSettings:
        """Load settings, apply known-field overrides, save, and return the result."""
        ws = self.load()
        known_fields = {field.name for field in fields(WebSettings)}
        for key, value in kwargs.items():
            if key in known_fields:
                setattr(ws, key, value)
        self.save(ws)
        return ws


def load_app_config(manager: ConfigManager) -> AppConfig:
    """Load the canonical ``AppConfig`` backing workflow fields on this page."""
    return manager.load(profile=PROFILE)


def save_app_config(manager: ConfigManager, config: AppConfig) -> None:
    """Persist the canonical ``AppConfig`` backing workflow fields on this page."""
    manager.save(config, profile=PROFILE)


def apply_web_settings_payload(ws: WebSettings, payload: dict[str, object]) -> WebSettings:
    """Apply imported or persisted web-only settings to an existing settings object."""
    known = {field.name for field in fields(WebSettings)}
    for key, value in payload.items():
        if key not in known:
            continue
        if key in BOOLEAN_FIELDS:
            setattr(ws, key, coerce_bool(value, getattr(ws, key)))
        elif isinstance(value, str):
            setattr(ws, key, value)
    return ws


def apply_app_config_payload(app_config: AppConfig, payload: dict[str, object]) -> AppConfig:
    """Apply imported shared settings fields to ``AppConfig``."""
    if isinstance(payload.get("default_input_dir"), str):
        app_config.default_input_dir = payload["default_input_dir"].strip()
    if isinstance(payload.get("default_output_dir"), str):
        app_config.default_output_dir = payload["default_output_dir"].strip()
    if isinstance(payload.get("text_model"), str) and payload["text_model"].strip():
        app_config.models.text_model = payload["text_model"].strip()
    if isinstance(payload.get("vision_model"), str) and payload["vision_model"].strip():
        app_config.models.vision_model = payload["vision_model"].strip()
    if "default_methodology" in payload:
        app_config.default_methodology = normalize_methodology(payload.get("default_methodology"))
    return app_config


def build_export_payload(ws: WebSettings, app_config: AppConfig) -> dict[str, object]:
    """Build the combined JSON export payload for web and shared settings fields."""
    payload = asdict(ws)
    payload.update(
        default_input_dir=app_config.default_input_dir,
        default_output_dir=app_config.default_output_dir,
        text_model=app_config.models.text_model,
        vision_model=app_config.models.vision_model,
        default_methodology=app_config.default_methodology,
    )
    return payload


def import_settings_payload(
    store: WebSettingsStore,
    manager: ConfigManager,
    payload: dict[str, object],
) -> tuple[WebSettings, AppConfig]:
    """Persist an imported settings payload and return updated web/app settings."""
    ws = store.load()
    apply_web_settings_payload(ws, payload)
    sanitize_web_settings(ws)
    store.save(ws)

    app_config = load_app_config(manager)
    apply_app_config_payload(app_config, payload)
    save_app_config(manager, app_config)
    return ws, app_config


def reset_settings(store: WebSettingsStore, manager: ConfigManager) -> tuple[WebSettings, AppConfig]:
    """Reset fields owned by the settings page to their defaults."""
    ws = WebSettings()
    store.save(ws)

    defaults = AppConfig()
    app_config = load_app_config(manager)
    app_config.default_input_dir = defaults.default_input_dir
    app_config.default_output_dir = defaults.default_output_dir
    app_config.default_methodology = defaults.default_methodology
    app_config.models.text_model = defaults.models.text_model
    app_config.models.vision_model = defaults.models.vision_model
    save_app_config(manager, app_config)
    return ws, app_config


def apply_general_settings(
    store: WebSettingsStore,
    manager: ConfigManager,
    *,
    language: str,
    timezone: str,
    default_input_dir: str,
    default_output_dir: str,
) -> tuple[WebSettings, AppConfig]:
    """Persist the General settings section."""
    ws = store.update(
        language=validate_choice(language, LANGUAGE_OPTIONS, "en"),
        timezone=validate_choice(timezone, TIMEZONE_OPTIONS, "UTC"),
    )
    app_config = load_app_config(manager)
    app_config.default_input_dir = default_input_dir.strip()
    app_config.default_output_dir = default_output_dir.strip()
    save_app_config(manager, app_config)
    return ws, app_config


def apply_model_settings(
    store: WebSettingsStore,
    manager: ConfigManager,
    *,
    text_model: str,
    vision_model: str,
    ollama_url: str,
) -> tuple[WebSettings, AppConfig]:
    """Persist the Models settings section."""
    ws = store.update(ollama_url=ollama_url.strip() or DEFAULT_OLLAMA_URL)
    app_config = load_app_config(manager)
    defaults = AppConfig()
    app_config.models.text_model = text_model.strip() or defaults.models.text_model
    app_config.models.vision_model = vision_model.strip() or defaults.models.vision_model
    save_app_config(manager, app_config)
    return ws, app_config


def apply_organization_settings(
    store: WebSettingsStore,
    manager: ConfigManager,
    *,
    default_methodology: str,
    auto_organize: str | None,
    notifications_enabled: str | None,
    file_filter_glob: str,
    organization_rules: str,
) -> tuple[WebSettings, AppConfig]:
    """Persist the Organization settings section after validating rules."""
    existing = store.load()
    candidate_rules = organization_rules or existing.organization_rules
    valid, message = validate_rules(candidate_rules)
    if not valid:
        existing.organization_rules = candidate_rules
        raise ValueError(message)

    ws = store.update(
        auto_organize=form_bool(auto_organize),
        notifications_enabled=form_bool(notifications_enabled),
        file_filter_glob=file_filter_glob.strip() or "*",
        organization_rules=candidate_rules,
    )
    app_config = load_app_config(manager)
    app_config.default_methodology = normalize_methodology(default_methodology)
    save_app_config(manager, app_config)
    return ws, app_config


def apply_appearance_settings(ws: WebSettings, *, theme: str, custom_theme_name: str) -> None:
    """Apply Appearance form values to ``WebSettings``."""
    ws.theme = validate_choice(theme.lower(), THEME_OPTIONS, "light")
    ws.custom_theme_name = custom_theme_name.strip()


def apply_advanced_settings(
    ws: WebSettings,
    *,
    log_level: str,
    cache_enabled: str | None,
    debug_mode: str | None,
    performance_mode: str,
) -> None:
    """Apply Advanced form values to ``WebSettings``."""
    ws.log_level = validate_choice(log_level.strip().upper(), LOG_LEVEL_OPTIONS, "INFO")
    ws.cache_enabled = form_bool(cache_enabled)
    ws.debug_mode = form_bool(debug_mode)
    ws.performance_mode = validate_choice(
        performance_mode.strip().lower(),
        PERFORMANCE_MODES,
        "balanced",
    )
