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
from collections.abc import Callable

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
from file_organizer.config.methodology import normalize as _methodology_normalize
from file_organizer.config.path_manager import get_config_dir
from file_organizer.config.schema import AppConfig
from file_organizer.web._forms import update_form_section
from file_organizer.web._helpers import base_context, templates
from file_organizer.web.settings_service import (
    LANGUAGE_OPTIONS,
    LOG_LEVEL_OPTIONS,
    PERFORMANCE_MODES,
    THEME_OPTIONS,
    TIMEZONE_OPTIONS,
    WebSettings,
    WebSettingsStore,
    apply_advanced_settings,
    apply_appearance_settings,
    apply_general_settings,
    apply_model_settings,
    apply_organization_settings,
    build_export_payload,
    import_settings_payload,
    load_app_config,
    reset_settings,
    save_app_config,
    validate_choice,
    validate_rules,
)

settings_router = APIRouter(tags=["web"])

_SETTINGS_DIR = get_config_dir()
_SETTINGS_FILE = _SETTINGS_DIR / "web-settings.json"

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


def _validate_choice(value: str, allowed: list[str], fallback: str) -> str:
    """Compatibility wrapper for settings choice validation."""
    return validate_choice(value, allowed, fallback)


def _validate_rules(rules: str) -> tuple[bool, str]:
    """Compatibility wrapper for organization rule validation."""
    return validate_rules(rules)


def _normalize_methodology(value: object) -> str:
    """Compatibility wrapper for canonical methodology normalization."""
    return _methodology_normalize(value)


def _settings_store() -> WebSettingsStore:
    """Build a store from the route-level paths, preserving test monkeypatches."""
    return WebSettingsStore(_SETTINGS_DIR, _SETTINGS_FILE)


def _load_web_settings() -> WebSettings:
    """Compatibility wrapper for loading persisted ``WebSettings``."""
    return _settings_store().load()


def _save_web_settings(ws: WebSettings) -> None:
    """Compatibility wrapper for persisting ``WebSettings``."""
    _settings_store().save(ws)


def _update_web_settings(**kwargs: object) -> WebSettings:
    """Compatibility wrapper for updating ``WebSettings``."""
    return _settings_store().update(**kwargs)


def _load_app_config(manager: ConfigManager) -> AppConfig:
    """Compatibility wrapper for loading settings-page ``AppConfig``."""
    return load_app_config(manager)


def _save_app_config(manager: ConfigManager, config: AppConfig) -> None:
    """Compatibility wrapper for saving settings-page ``AppConfig``."""
    save_app_config(manager, config)


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


def _run_section_post(
    request: Request,
    manager: ConfigManager,
    *,
    section: str,
    action: Callable[[], tuple[WebSettings, AppConfig]],
    success_message: str,
    failure_log: str,
    error_prefix: str = "Failed to save settings",
    on_rejected: Callable[[ValueError], HTMLResponse] | None = None,
) -> HTMLResponse:
    """Run the shared action → render-success / render-error flow for a section POST.

    ``action`` performs the persistence (usually a ``settings_service.apply_*``
    call) and returns the updated ``(WebSettings, AppConfig)`` pair to render.
    A ``ValueError`` is treated as a validation rejection and routed to
    ``on_rejected`` when provided (which owns its own logging and rendering);
    any other failure logs ``failure_log`` and re-renders the section from
    freshly loaded state with an error flash.
    """
    try:
        ws, app_config = action()
    except Exception as exc:
        # Deliberately broad: `action` is a settings_service.apply_* call whose
        # failure modes aren't enumerable here, and this is a user-facing form
        # POST handler — any unexpected error must degrade to a re-rendered
        # section with an error flash rather than an unhandled 500.
        if isinstance(exc, ValueError) and on_rejected is not None:
            return on_rejected(exc)
        logger.exception(failure_log)
        return _render_section(
            request,
            _load_web_settings(),
            _load_app_config(manager),
            section=section,
            error_message=f"{error_prefix}: {exc}",
        )
    return _render_section(
        request,
        ws,
        app_config,
        section=section,
        success_message=success_message,
    )


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
    payload = json.dumps(build_export_payload(ws, app_config), indent=2) + "\n"
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

        ws, app_config = import_settings_payload(_settings_store(), manager, payload)

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
    return _run_section_post(
        request,
        manager,
        section=target_section,
        action=lambda: reset_settings(_settings_store(), manager),
        success_message="Settings reset to defaults.",
        failure_log="Failed to reset settings",
        error_prefix="Failed to reset settings",
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
    return _run_section_post(
        request,
        manager,
        section="general",
        action=lambda: apply_general_settings(
            _settings_store(),
            manager,
            language=language,
            timezone=timezone,
            default_input_dir=default_input_dir,
            default_output_dir=default_output_dir,
        ),
        success_message="General settings saved.",
        failure_log="Failed to save general settings",
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
    return _run_section_post(
        request,
        manager,
        section="models",
        action=lambda: apply_model_settings(
            _settings_store(),
            manager,
            text_model=text_model,
            vision_model=vision_model,
            ollama_url=ollama_url,
        ),
        success_message="Model settings saved.",
        failure_log="Failed to save model settings",
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

    def render_rejected(exc: ValueError) -> HTMLResponse:
        logger.warning("Rejected organization settings: {}", exc)
        ws = _load_web_settings()
        ws.organization_rules = organization_rules or ws.organization_rules
        return _render_section(
            request,
            ws,
            _load_app_config(manager),
            section="organization",
            error_message=str(exc),
        )

    return _run_section_post(
        request,
        manager,
        section="organization",
        action=lambda: apply_organization_settings(
            _settings_store(),
            manager,
            default_methodology=default_methodology,
            auto_organize=auto_organize,
            notifications_enabled=notifications_enabled,
            file_filter_glob=file_filter_glob,
            organization_rules=organization_rules,
        ),
        success_message="Organization settings saved.",
        failure_log="Failed to save organization settings",
        on_rejected=render_rejected,
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

    def apply(ws: WebSettings) -> None:
        """Apply appearance form values to loaded settings."""
        apply_appearance_settings(ws, theme=theme, custom_theme_name=custom_theme_name)

    def render_success(ws: WebSettings) -> HTMLResponse:
        """Render the appearance section after a successful save."""
        return _render_section(
            request,
            ws,
            _load_app_config(manager),
            section="appearance",
            success_message="Appearance settings saved.",
        )

    def render_error(message: str) -> HTMLResponse:
        """Render the appearance section after a failed save."""
        logger.exception("Failed to save appearance settings")
        return _render_section(
            request,
            _load_web_settings(),
            _load_app_config(manager),
            section="appearance",
            error_message=message,
        )

    return update_form_section(
        load=_load_web_settings,
        apply=apply,
        save=_save_web_settings,
        render_success=render_success,
        render_error=render_error,
        error_prefix="Failed to save settings",
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

    def apply(ws: WebSettings) -> None:
        """Apply advanced form values to loaded settings."""
        apply_advanced_settings(
            ws,
            log_level=log_level,
            cache_enabled=cache_enabled,
            debug_mode=debug_mode,
            performance_mode=performance_mode,
        )

    def render_success(ws: WebSettings) -> HTMLResponse:
        """Render the advanced section after a successful save."""
        return _render_section(
            request,
            ws,
            _load_app_config(manager),
            section="advanced",
            success_message="Advanced settings saved.",
        )

    def render_error(message: str) -> HTMLResponse:
        """Render the advanced section after a failed save."""
        logger.exception("Failed to save advanced settings")
        return _render_section(
            request,
            _load_web_settings(),
            _load_app_config(manager),
            section="advanced",
            error_message=message,
        )

    return update_form_section(
        load=_load_web_settings,
        apply=apply,
        save=_save_web_settings,
        render_success=render_success,
        render_error=render_error,
        error_prefix="Failed to save settings",
    )
