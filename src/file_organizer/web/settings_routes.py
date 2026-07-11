"""Web UI routes for settings and configuration management.

This module powers a multi-section settings page with:
- persistence to JSON
- section-level HTMX saves
- import/export/reset flows
- lightweight validation helpers (rules + Ollama connectivity)
- simple search across settings sections
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields

import aiofiles
import httpx
from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, Response
from loguru import logger

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_config_manager, get_settings
from file_organizer.api.utils import resolve_path
from file_organizer.config.manager import ConfigManager
from file_organizer.config.methodology import DEFAULT as _DEFAULT_METHODOLOGY
from file_organizer.config.methodology import LABELS as METHODOLOGY_OPTIONS
from file_organizer.config.methodology import normalize as _normalize_methodology
from file_organizer.config.path_manager import get_config_dir
from file_organizer.config.schema import AppConfig
from file_organizer.utils.atomic_write import atomic_write_text
from file_organizer.web._helpers import base_context, templates

# Profile used for the AppConfig-backed fields shown on this page (default
# input/output dirs, methodology, text/vision model). The web UI does not
# yet expose profile switching, so it always reads/writes "default" — same
# as every other AppConfig consumer (TUI, CLI, API routers).
_PROFILE = "default"

settings_router = APIRouter(tags=["web"])

_SETTINGS_DIR = get_config_dir()
_SETTINGS_FILE = _SETTINGS_DIR / "web-settings.json"

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

_SECTION_INDEX = {
    "general": [
        "language",
        "timezone",
        "default input",
        "default output",
    ],
    "models": [
        "text model",
        "vision model",
        "ollama",
        "connection",
    ],
    "organization": [
        "methodology",
        "rules",
        "auto organize",
        "notifications",
        "filters",
    ],
    "appearance": [
        "theme",
        "custom theme",
    ],
    "advanced": [
        "log level",
        "cache",
        "debug",
        "performance",
        "import",
        "export",
        "reset",
    ],
}


@dataclass
class WebSettings:
    """Persistent settings for the web UI.

    Holds only fields with no canonical home elsewhere. The workflow fields
    shown alongside these on the settings page — default input/output dirs,
    methodology, text/vision model — live on the shared ``AppConfig``
    (``config.manager.ConfigManager``) instead, so a value set here is
    visible to the TUI, CLI, and API too (see #1539). Loaded/saved via
    ``_load_app_config``/``_save_app_config`` in the route handlers below.
    """

    # General
    language: str = "en"
    timezone: str = "UTC"

    # Models
    ollama_url: str = "http://localhost:11434"

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


def _as_form_bool(value: str | None) -> bool:
    """Convert an HTML form checkbox value to ``bool``."""
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _coerce_bool(value: object, default: bool) -> bool:
    """Coerce an arbitrary value to ``bool``, falling back to *default*."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return default


def _validate_choice(value: str, allowed: list[str], fallback: str) -> str:
    """Return *value* if it is in *allowed*, otherwise return *fallback*."""
    candidate = value.strip()
    return candidate if candidate in allowed else fallback


def _validate_rules(rules: str) -> tuple[bool, str]:
    """Validate organization rule text.

    Args:
        rules: Newline-separated ``pattern -> destination`` rules.

    Returns:
        Tuple of ``(is_valid, message)``.
    """
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


def _load_web_settings() -> WebSettings:
    """Load persisted ``WebSettings`` from disk, returning defaults on failure."""
    if not _SETTINGS_FILE.exists():
        return WebSettings()

    try:
        raw = json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return WebSettings()

        ws = WebSettings()
        known = {f.name for f in fields(WebSettings)}
        for key, value in raw.items():
            if key not in known:
                continue
            if key in {"auto_organize", "notifications_enabled", "cache_enabled", "debug_mode"}:
                setattr(ws, key, _coerce_bool(value, getattr(ws, key)))
                continue
            if isinstance(value, str):
                setattr(ws, key, value)
        ws.theme = _validate_choice(ws.theme, THEME_OPTIONS, "light")
        ws.log_level = _validate_choice(ws.log_level, LOG_LEVEL_OPTIONS, "INFO")
        ws.performance_mode = _validate_choice(ws.performance_mode, PERFORMANCE_MODES, "balanced")
        ws.language = _validate_choice(ws.language, LANGUAGE_OPTIONS, "en")
        ws.timezone = _validate_choice(ws.timezone, TIMEZONE_OPTIONS, "UTC")
        return ws
    except Exception as exc:
        logger.warning("Failed to load settings from {}: {}", _SETTINGS_FILE, exc)
        return WebSettings()


def _save_web_settings(ws: WebSettings) -> None:
    """Persist *ws* to the JSON settings file on disk."""
    try:
        _SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
        atomic_write_text(_SETTINGS_FILE, json.dumps(asdict(ws), indent=2) + "\n")
    except Exception as exc:
        logger.error("Failed to save settings to {}: {}", _SETTINGS_FILE, exc)


def _update_web_settings(**kwargs: object) -> WebSettings:
    """Load settings, apply *kwargs* overrides, save, and return the result."""
    ws = _load_web_settings()
    known_fields = {f.name for f in fields(WebSettings)}
    for key, value in kwargs.items():
        if key in known_fields:
            setattr(ws, key, value)
    _save_web_settings(ws)
    return ws


def _load_app_config(manager: ConfigManager) -> AppConfig:
    """Load the canonical ``AppConfig`` backing this page's workflow fields."""
    return manager.load(profile=_PROFILE)


def _save_app_config(manager: ConfigManager, config: AppConfig) -> None:
    """Persist *config*, the canonical ``AppConfig`` backing this page."""
    manager.save(config, profile=_PROFILE)


def _section_context(
    request: Request,
    ws: WebSettings,
    app_config: AppConfig,
    *,
    section: str,
    success_message: str = "",
    error_message: str = "",
) -> dict[str, object]:
    """Build the base template context dict for a settings section partial."""
    return {
        "request": request,
        "ws": ws,
        "app_config": app_config,
        "section": section,
        "success_message": success_message,
        "error_message": error_message,
        "methodology_options": METHODOLOGY_OPTIONS,
        "log_level_options": LOG_LEVEL_OPTIONS,
        "theme_options": THEME_OPTIONS,
        "language_options": LANGUAGE_OPTIONS,
        "timezone_options": TIMEZONE_OPTIONS,
        "performance_modes": PERFORMANCE_MODES,
    }


def _render_section(
    request: Request,
    ws: WebSettings,
    app_config: AppConfig,
    *,
    section: str,
    success_message: str = "",
    error_message: str = "",
) -> HTMLResponse:
    """Render a single settings section HTMX partial.

    Args:
        request: Incoming FastAPI request.
        ws: Current persisted web-only settings.
        app_config: Current shared AppConfig (dirs, methodology, model).
        section: Section name (e.g. ``"general"``, ``"models"``).
        success_message: Optional success flash.
        error_message: Optional error flash.

    Returns:
        Rendered HTML partial for the requested section.
    """
    context = _section_context(
        request,
        ws,
        app_config,
        section=section,
        success_message=success_message,
        error_message=error_message,
    )
    return templates.TemplateResponse(request, f"settings/_{section}.html", context)


@settings_router.get("/settings", response_class=HTMLResponse)
def settings_page(
    request: Request,
    settings_obj: ApiSettings = Depends(get_settings),
    manager: ConfigManager = Depends(get_config_manager),
) -> HTMLResponse:
    """Render the full settings page with all sections.

    Returns:
        Full HTML page for settings.
    """
    ws = _load_web_settings()
    app_config = _load_app_config(manager)
    context = base_context(
        request,
        settings_obj,
        active="settings",
        title="Settings",
        extras={
            "ws": ws,
            "app_config": app_config,
            "methodology_options": METHODOLOGY_OPTIONS,
            "log_level_options": LOG_LEVEL_OPTIONS,
            "theme_options": THEME_OPTIONS,
            "language_options": LANGUAGE_OPTIONS,
            "timezone_options": TIMEZONE_OPTIONS,
            "performance_modes": PERFORMANCE_MODES,
        },
    )
    return templates.TemplateResponse(request, "settings/index.html", context)


@settings_router.get("/settings/search", response_class=HTMLResponse)
def settings_search(query: str = Query("", alias="q")) -> HTMLResponse:
    """Search settings sections by keyword and return matching nav buttons.

    Returns:
        HTML fragment with section shortcut buttons, or an empty hint.
    """
    needle = query.strip().lower()
    if not needle:
        return HTMLResponse("")

    matches: list[str] = []
    for section, terms in _SECTION_INDEX.items():
        if needle in section or any(needle in term for term in terms):
            matches.append(section)

    if not matches:
        return HTMLResponse('<p class="form-hint">No matching settings sections.</p>')

    buttons = []
    for section in matches:
        label = section.capitalize()
        buttons.append(
            f'<button class="btn-ghost btn-sm" '
            f'hx-get="/ui/settings/{section}" hx-target="#settings-panel" '
            f'hx-swap="innerHTML">{label}</button>'
        )
    return HTMLResponse("".join(buttons))


@settings_router.get("/settings/export")
def settings_export(manager: ConfigManager = Depends(get_config_manager)) -> Response:
    """Export current web settings, plus the shared AppConfig fields shown on this page.

    Returns:
        A single downloadable JSON file.
    """
    ws = _load_web_settings()
    app_config = _load_app_config(manager)
    payload_dict = asdict(ws)
    payload_dict.update(
        default_input_dir=app_config.default_input_dir,
        default_output_dir=app_config.default_output_dir,
        text_model=app_config.models.text_model,
        vision_model=app_config.models.vision_model,
        default_methodology=app_config.default_methodology,
    )
    payload = json.dumps(payload_dict, indent=2) + "\n"
    return Response(
        content=payload,
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="web-settings.json"'},
    )


@settings_router.post("/settings/import", response_class=HTMLResponse)
async def settings_import(
    request: Request,
    section: str = Form("general"),
    settings_file: UploadFile | None = File(None),
    settings_path: str | None = Form(None),
    settings: ApiSettings = Depends(get_settings),
    manager: ConfigManager = Depends(get_config_manager),
) -> HTMLResponse:
    """Import web settings from an uploaded JSON file or a desktop file path.

    Accepts either a multipart ``settings_file`` upload (browser) or a
    ``settings_path`` string (desktop picker).  When both are present the
    uploaded file takes precedence.  The path is validated against
    ``settings.allowed_paths`` before reading (F4).

    Returns:
        Re-rendered section partial with a success or error flash.
    """
    valid_sections = {"general", "models", "organization", "appearance", "advanced"}
    target_section = section if section in valid_sections else "general"

    try:
        if settings_file is not None:
            raw_bytes = await settings_file.read()
            if not raw_bytes or not raw_bytes.strip():
                ws = _load_web_settings()
                return _render_section(
                    request,
                    ws,
                    _load_app_config(manager),
                    section=target_section,
                    error_message="Import failed: uploaded file is empty.",
                )
            raw = raw_bytes.decode("utf-8")
        elif settings_path and settings_path.strip():
            resolved = resolve_path(settings_path, settings.allowed_paths)
            async with aiofiles.open(resolved, encoding="utf-8") as fh:
                raw = await fh.read()
        else:
            ws = _load_web_settings()
            return _render_section(
                request,
                ws,
                _load_app_config(manager),
                section=target_section,
                error_message="Import failed: provide either a settings file or a valid path.",
            )
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("Imported payload must be a JSON object.")

        ws = _load_web_settings()
        known = {f.name for f in fields(WebSettings)}
        for key, value in payload.items():
            if key not in known:
                continue
            if isinstance(getattr(ws, key), bool):
                setattr(ws, key, _coerce_bool(value, getattr(ws, key)))
            elif isinstance(value, str):
                setattr(ws, key, value)

        ws.theme = _validate_choice(ws.theme, THEME_OPTIONS, "light")
        ws.log_level = _validate_choice(ws.log_level, LOG_LEVEL_OPTIONS, "INFO")
        ws.performance_mode = _validate_choice(ws.performance_mode, PERFORMANCE_MODES, "balanced")
        ws.language = _validate_choice(ws.language, LANGUAGE_OPTIONS, "en")
        ws.timezone = _validate_choice(ws.timezone, TIMEZONE_OPTIONS, "UTC")
        _save_web_settings(ws)

        # Shared AppConfig fields (dirs, methodology, model) are imported
        # separately since #1539 — WebSettings no longer carries them.
        app_config = _load_app_config(manager)
        if isinstance(payload.get("default_input_dir"), str):
            app_config.default_input_dir = payload["default_input_dir"].strip()
        if isinstance(payload.get("default_output_dir"), str):
            app_config.default_output_dir = payload["default_output_dir"].strip()
        if isinstance(payload.get("text_model"), str) and payload["text_model"].strip():
            app_config.models.text_model = payload["text_model"].strip()
        if isinstance(payload.get("vision_model"), str) and payload["vision_model"].strip():
            app_config.models.vision_model = payload["vision_model"].strip()
        if "default_methodology" in payload:
            app_config.default_methodology = _normalize_methodology(
                payload.get("default_methodology")
            )
        _save_app_config(manager, app_config)

        return _render_section(
            request,
            ws,
            app_config,
            section=target_section,
            success_message="Settings imported successfully.",
        )
    except Exception as exc:
        ws = _load_web_settings()
        return _render_section(
            request,
            ws,
            _load_app_config(manager),
            section=target_section,
            error_message=f"Import failed: {exc}",
        )


@settings_router.post("/settings/reset", response_class=HTMLResponse)
def settings_reset(
    request: Request,
    section: str = Form("general"),
    manager: ConfigManager = Depends(get_config_manager),
) -> HTMLResponse:
    """Reset all web settings, and the shared AppConfig fields shown on this page.

    Only the fields this page owns (default dirs, methodology, text/vision
    model) are reset on AppConfig — other AppConfig state (setup_completed,
    updates, module overrides, ...) is left untouched.

    Returns:
        Re-rendered section partial confirming the reset.
    """
    valid_sections = {"general", "models", "organization", "appearance", "advanced"}
    target_section = section if section in valid_sections else "general"
    try:
        ws = WebSettings()
        _save_web_settings(ws)

        defaults = AppConfig()
        app_config = _load_app_config(manager)
        app_config.default_input_dir = defaults.default_input_dir
        app_config.default_output_dir = defaults.default_output_dir
        app_config.default_methodology = defaults.default_methodology
        app_config.models.text_model = defaults.models.text_model
        app_config.models.vision_model = defaults.models.vision_model
        _save_app_config(manager, app_config)

        return _render_section(
            request,
            ws,
            app_config,
            section=target_section,
            success_message="Settings reset to defaults.",
        )
    except Exception as exc:
        logger.exception("Failed to reset settings")
        return _render_section(
            request,
            _load_web_settings(),
            _load_app_config(manager),
            section=target_section,
            error_message=f"Failed to reset settings: {exc}",
        )


@settings_router.get("/settings/general", response_class=HTMLResponse)
def settings_general_get(
    request: Request, manager: ConfigManager = Depends(get_config_manager)
) -> HTMLResponse:
    """Render the General settings section partial."""
    return _render_section(
        request, _load_web_settings(), _load_app_config(manager), section="general"
    )


@settings_router.post("/settings/general", response_class=HTMLResponse)
def settings_general_post(
    request: Request,
    language: str = Form("en"),
    timezone: str = Form("UTC"),
    default_input_dir: str = Form(""),
    default_output_dir: str = Form(""),
    manager: ConfigManager = Depends(get_config_manager),
) -> HTMLResponse:
    """Save General settings and re-render the section partial."""
    try:
        ws = _update_web_settings(
            language=_validate_choice(language, LANGUAGE_OPTIONS, "en"),
            timezone=_validate_choice(timezone, TIMEZONE_OPTIONS, "UTC"),
        )
        app_config = _load_app_config(manager)
        app_config.default_input_dir = default_input_dir.strip()
        app_config.default_output_dir = default_output_dir.strip()
        _save_app_config(manager, app_config)
        return _render_section(
            request,
            ws,
            app_config,
            section="general",
            success_message="General settings saved.",
        )
    except Exception as exc:
        logger.exception("Failed to save general settings")
        return _render_section(
            request,
            _load_web_settings(),
            _load_app_config(manager),
            section="general",
            error_message=f"Failed to save settings: {exc}",
        )


@settings_router.get("/settings/models", response_class=HTMLResponse)
def settings_models_get(
    request: Request, manager: ConfigManager = Depends(get_config_manager)
) -> HTMLResponse:
    """Render the Models settings section partial."""
    return _render_section(
        request, _load_web_settings(), _load_app_config(manager), section="models"
    )


@settings_router.post("/settings/models", response_class=HTMLResponse)
def settings_models_post(
    request: Request,
    text_model: str = Form(""),
    vision_model: str = Form(""),
    ollama_url: str = Form(""),
    manager: ConfigManager = Depends(get_config_manager),
) -> HTMLResponse:
    """Save Models settings and re-render the section partial."""
    try:
        ws = _update_web_settings(
            ollama_url=ollama_url.strip() or "http://localhost:11434",
        )
        app_config = _load_app_config(manager)
        defaults = AppConfig()
        app_config.models.text_model = text_model.strip() or defaults.models.text_model
        app_config.models.vision_model = vision_model.strip() or defaults.models.vision_model
        _save_app_config(manager, app_config)
        return _render_section(
            request,
            ws,
            app_config,
            section="models",
            success_message="Model settings saved.",
        )
    except Exception as exc:
        logger.exception("Failed to save model settings")
        return _render_section(
            request,
            _load_web_settings(),
            _load_app_config(manager),
            section="models",
            error_message=f"Failed to save settings: {exc}",
        )


@settings_router.post("/settings/models/test", response_class=HTMLResponse)
def settings_models_test(
    request: Request,
    ollama_url: str = Form(""),
    manager: ConfigManager = Depends(get_config_manager),
) -> HTMLResponse:
    """Test Ollama connectivity and re-render the Models section partial."""
    ws = _load_web_settings()
    app_config = _load_app_config(manager)
    target = ollama_url.strip() or ws.ollama_url
    try:
        with httpx.Client(timeout=3.0) as client:
            response = client.get(f"{target.rstrip('/')}/api/tags")
            response.raise_for_status()
        ws = _update_web_settings(ollama_url=target)
        return _render_section(
            request,
            ws,
            app_config,
            section="models",
            success_message="Ollama connection successful.",
        )
    except Exception as exc:
        return _render_section(
            request,
            ws,
            app_config,
            section="models",
            error_message=f"Ollama connection failed: {exc}",
        )


@settings_router.get("/settings/organization", response_class=HTMLResponse)
def settings_organization_get(
    request: Request, manager: ConfigManager = Depends(get_config_manager)
) -> HTMLResponse:
    """Render the Organization settings section partial."""
    return _render_section(
        request, _load_web_settings(), _load_app_config(manager), section="organization"
    )


@settings_router.post("/settings/organization/validate", response_class=HTMLResponse)
def settings_organization_validate(
    request: Request,
    organization_rules: str = Form(""),
    manager: ConfigManager = Depends(get_config_manager),
) -> HTMLResponse:
    """Validate organization rules and re-render the section partial."""
    ws = _load_web_settings()
    app_config = _load_app_config(manager)
    candidate_rules = organization_rules or ws.organization_rules
    valid, message = _validate_rules(candidate_rules)
    if valid:
        ws.organization_rules = candidate_rules
        _save_web_settings(ws)
        return _render_section(
            request,
            ws,
            app_config,
            section="organization",
            success_message=message,
        )
    ws.organization_rules = candidate_rules
    return _render_section(
        request,
        ws,
        app_config,
        section="organization",
        error_message=message,
    )


@settings_router.post("/settings/organization", response_class=HTMLResponse)
def settings_organization_post(
    request: Request,
    default_methodology: str = Form(_DEFAULT_METHODOLOGY),
    auto_organize: str | None = Form(None),
    notifications_enabled: str | None = Form(None),
    file_filter_glob: str = Form("*"),
    organization_rules: str = Form(""),
    manager: ConfigManager = Depends(get_config_manager),
) -> HTMLResponse:
    """Save Organization settings and re-render the section partial."""
    existing = _load_web_settings()
    candidate_rules = organization_rules or existing.organization_rules
    valid, message = _validate_rules(candidate_rules)
    if not valid:
        existing.organization_rules = candidate_rules
        return _render_section(
            request,
            existing,
            _load_app_config(manager),
            section="organization",
            error_message=message,
        )

    try:
        ws = _update_web_settings(
            auto_organize=_as_form_bool(auto_organize),
            notifications_enabled=_as_form_bool(notifications_enabled),
            file_filter_glob=file_filter_glob.strip() or "*",
            organization_rules=candidate_rules,
        )
        app_config = _load_app_config(manager)
        app_config.default_methodology = _normalize_methodology(default_methodology)
        _save_app_config(manager, app_config)
        return _render_section(
            request,
            ws,
            app_config,
            section="organization",
            success_message="Organization settings saved.",
        )
    except Exception as exc:
        logger.exception("Failed to save organization settings")
        return _render_section(
            request,
            _load_web_settings(),
            _load_app_config(manager),
            section="organization",
            error_message=f"Failed to save settings: {exc}",
        )


@settings_router.get("/settings/appearance", response_class=HTMLResponse)
def settings_appearance_get(
    request: Request, manager: ConfigManager = Depends(get_config_manager)
) -> HTMLResponse:
    """Render the Appearance settings section partial."""
    return _render_section(
        request, _load_web_settings(), _load_app_config(manager), section="appearance"
    )


@settings_router.post("/settings/appearance", response_class=HTMLResponse)
def settings_appearance_post(
    request: Request,
    theme: str = Form("light"),
    custom_theme_name: str = Form(""),
    manager: ConfigManager = Depends(get_config_manager),
) -> HTMLResponse:
    """Save Appearance settings and re-render the section partial."""
    try:
        ws = _update_web_settings(
            theme=_validate_choice(theme.lower(), THEME_OPTIONS, "light"),
            custom_theme_name=custom_theme_name.strip(),
        )
        return _render_section(
            request,
            ws,
            _load_app_config(manager),
            section="appearance",
            success_message="Appearance settings saved.",
        )
    except Exception as exc:
        logger.exception("Failed to save appearance settings")
        return _render_section(
            request,
            _load_web_settings(),
            _load_app_config(manager),
            section="appearance",
            error_message=f"Failed to save settings: {exc}",
        )


@settings_router.get("/settings/advanced", response_class=HTMLResponse)
def settings_advanced_get(
    request: Request, manager: ConfigManager = Depends(get_config_manager)
) -> HTMLResponse:
    """Render the Advanced settings section partial."""
    return _render_section(
        request, _load_web_settings(), _load_app_config(manager), section="advanced"
    )


@settings_router.post("/settings/advanced", response_class=HTMLResponse)
def settings_advanced_post(
    request: Request,
    log_level: str = Form("INFO"),
    cache_enabled: str | None = Form(None),
    debug_mode: str | None = Form(None),
    performance_mode: str = Form("balanced"),
    manager: ConfigManager = Depends(get_config_manager),
) -> HTMLResponse:
    """Save Advanced settings and re-render the section partial."""
    try:
        ws = _update_web_settings(
            log_level=_validate_choice(log_level.strip().upper(), LOG_LEVEL_OPTIONS, "INFO"),
            cache_enabled=_as_form_bool(cache_enabled),
            debug_mode=_as_form_bool(debug_mode),
            performance_mode=_validate_choice(
                performance_mode.strip().lower(),
                PERFORMANCE_MODES,
                "balanced",
            ),
        )
        return _render_section(
            request,
            ws,
            _load_app_config(manager),
            section="advanced",
            success_message="Advanced settings saved.",
        )
    except Exception as exc:
        logger.exception("Failed to save advanced settings")
        return _render_section(
            request,
            _load_web_settings(),
            _load_app_config(manager),
            section="advanced",
            error_message=f"Failed to save settings: {exc}",
        )
