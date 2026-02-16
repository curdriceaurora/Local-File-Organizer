"""Web UI routes for the multi-section settings page.

Settings are persisted to a JSON file at ``~/.config/file-organizer/web-settings.json``
and served via HTMX partials so that each section can be saved independently.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from loguru import logger

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_settings
from file_organizer.web._helpers import base_context, templates

settings_router = APIRouter(tags=["web"])

_SETTINGS_DIR = Path.home() / ".config" / "file-organizer"
_SETTINGS_FILE = _SETTINGS_DIR / "web-settings.json"

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

METHODOLOGY_OPTIONS = {
    "content_based": "Content-Based",
    "johnny_decimal": "Johnny Decimal",
    "para": "PARA",
    "date_based": "Date-Based",
}

LOG_LEVEL_OPTIONS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

THEME_OPTIONS = ["light", "dark", "auto"]


@dataclass
class WebSettings:
    """Persistent web UI settings."""

    # General
    default_input_dir: str = ""
    default_output_dir: str = ""

    # Models
    text_model: str = "qwen2.5:3b-instruct-q4_K_M"
    vision_model: str = "qwen2.5vl:7b-q4_K_M"

    # Organization
    default_methodology: str = "content_based"
    auto_organize: bool = False

    # Appearance
    theme: str = "light"

    # Advanced
    log_level: str = "INFO"
    cache_enabled: bool = True
    debug_mode: bool = False


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------


def _load_web_settings() -> WebSettings:
    """Load settings from disk, returning defaults on any error."""
    if not _SETTINGS_FILE.exists():
        return WebSettings()
    try:
        raw = json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return WebSettings()
        known_fields = {f.name for f in fields(WebSettings)}
        filtered = {k: v for k, v in raw.items() if k in known_fields}
        return WebSettings(**filtered)
    except Exception as exc:
        logger.warning("Failed to load web settings from {}: {}", _SETTINGS_FILE, exc)
        return WebSettings()


def _save_web_settings(ws: WebSettings) -> None:
    """Persist settings to disk."""
    try:
        _SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
        _SETTINGS_FILE.write_text(
            json.dumps(asdict(ws), indent=2) + "\n",
            encoding="utf-8",
        )
    except Exception as exc:
        logger.error("Failed to save web settings to {}: {}", _SETTINGS_FILE, exc)


def _update_web_settings(**kwargs: object) -> WebSettings:
    """Load current settings, apply overrides, save, and return the result."""
    ws = _load_web_settings()
    known_fields = {f.name for f in fields(WebSettings)}
    for key, value in kwargs.items():
        if key in known_fields:
            setattr(ws, key, value)
    _save_web_settings(ws)
    return ws


# ---------------------------------------------------------------------------
# Route helpers
# ---------------------------------------------------------------------------


def _section_context(
    request: Request,
    ws: WebSettings,
    *,
    section: str,
    success_message: str = "",
    error_message: str = "",
) -> dict[str, object]:
    """Build a template context dict for a section partial."""
    return {
        "request": request,
        "ws": ws,
        "section": section,
        "success_message": success_message,
        "error_message": error_message,
        "methodology_options": METHODOLOGY_OPTIONS,
        "log_level_options": LOG_LEVEL_OPTIONS,
        "theme_options": THEME_OPTIONS,
    }


def _as_form_bool(value: str | None) -> bool:
    """Interpret a form checkbox/toggle value as a boolean."""
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


# ---------------------------------------------------------------------------
# Full page
# ---------------------------------------------------------------------------


@settings_router.get("/settings", response_class=HTMLResponse)
def settings_page(
    request: Request,
    settings_obj: ApiSettings = Depends(get_settings),
) -> HTMLResponse:
    ws = _load_web_settings()
    context = base_context(
        request,
        settings_obj,
        active="settings",
        title="Settings",
        extras={
            "ws": ws,
            "methodology_options": METHODOLOGY_OPTIONS,
            "log_level_options": LOG_LEVEL_OPTIONS,
            "theme_options": THEME_OPTIONS,
        },
    )
    return templates.TemplateResponse("settings/index.html", context)


# ---------------------------------------------------------------------------
# General section
# ---------------------------------------------------------------------------


@settings_router.get("/settings/general", response_class=HTMLResponse)
def settings_general_get(request: Request) -> HTMLResponse:
    ws = _load_web_settings()
    ctx = _section_context(request, ws, section="general")
    return templates.TemplateResponse("settings/_general.html", ctx)


@settings_router.post("/settings/general", response_class=HTMLResponse)
def settings_general_post(
    request: Request,
    default_input_dir: str = Form(""),
    default_output_dir: str = Form(""),
) -> HTMLResponse:
    success = ""
    error = ""
    try:
        ws = _update_web_settings(
            default_input_dir=default_input_dir.strip(),
            default_output_dir=default_output_dir.strip(),
        )
        success = "General settings saved."
    except Exception as exc:
        logger.exception("Failed to save general settings")
        error = f"Failed to save settings: {exc}"
        ws = _load_web_settings()
    ctx = _section_context(request, ws, section="general", success_message=success, error_message=error)
    return templates.TemplateResponse("settings/_general.html", ctx)


# ---------------------------------------------------------------------------
# Models section
# ---------------------------------------------------------------------------


@settings_router.get("/settings/models", response_class=HTMLResponse)
def settings_models_get(request: Request) -> HTMLResponse:
    ws = _load_web_settings()
    ctx = _section_context(request, ws, section="models")
    return templates.TemplateResponse("settings/_models.html", ctx)


@settings_router.post("/settings/models", response_class=HTMLResponse)
def settings_models_post(
    request: Request,
    text_model: str = Form(""),
    vision_model: str = Form(""),
) -> HTMLResponse:
    success = ""
    error = ""
    try:
        text_val = text_model.strip() or "qwen2.5:3b-instruct-q4_K_M"
        vision_val = vision_model.strip() or "qwen2.5vl:7b-q4_K_M"
        ws = _update_web_settings(text_model=text_val, vision_model=vision_val)
        success = "Model settings saved."
    except Exception as exc:
        logger.exception("Failed to save model settings")
        error = f"Failed to save settings: {exc}"
        ws = _load_web_settings()
    ctx = _section_context(request, ws, section="models", success_message=success, error_message=error)
    return templates.TemplateResponse("settings/_models.html", ctx)


# ---------------------------------------------------------------------------
# Organization section
# ---------------------------------------------------------------------------


@settings_router.get("/settings/organization", response_class=HTMLResponse)
def settings_organization_get(request: Request) -> HTMLResponse:
    ws = _load_web_settings()
    ctx = _section_context(request, ws, section="organization")
    return templates.TemplateResponse("settings/_organization.html", ctx)


@settings_router.post("/settings/organization", response_class=HTMLResponse)
def settings_organization_post(
    request: Request,
    default_methodology: str = Form("content_based"),
    auto_organize: str = Form(""),
) -> HTMLResponse:
    success = ""
    error = ""
    try:
        methodology = default_methodology.strip().lower()
        if methodology not in METHODOLOGY_OPTIONS:
            methodology = "content_based"
        ws = _update_web_settings(
            default_methodology=methodology,
            auto_organize=_as_form_bool(auto_organize),
        )
        success = "Organization settings saved."
    except Exception as exc:
        logger.exception("Failed to save organization settings")
        error = f"Failed to save settings: {exc}"
        ws = _load_web_settings()
    ctx = _section_context(request, ws, section="organization", success_message=success, error_message=error)
    return templates.TemplateResponse("settings/_organization.html", ctx)


# ---------------------------------------------------------------------------
# Appearance section
# ---------------------------------------------------------------------------


@settings_router.get("/settings/appearance", response_class=HTMLResponse)
def settings_appearance_get(request: Request) -> HTMLResponse:
    ws = _load_web_settings()
    ctx = _section_context(request, ws, section="appearance")
    return templates.TemplateResponse("settings/_appearance.html", ctx)


@settings_router.post("/settings/appearance", response_class=HTMLResponse)
def settings_appearance_post(
    request: Request,
    theme: str = Form("light"),
) -> HTMLResponse:
    success = ""
    error = ""
    try:
        theme_val = theme.strip().lower()
        if theme_val not in THEME_OPTIONS:
            theme_val = "light"
        ws = _update_web_settings(theme=theme_val)
        success = "Appearance settings saved."
    except Exception as exc:
        logger.exception("Failed to save appearance settings")
        error = f"Failed to save settings: {exc}"
        ws = _load_web_settings()
    ctx = _section_context(request, ws, section="appearance", success_message=success, error_message=error)
    return templates.TemplateResponse("settings/_appearance.html", ctx)


# ---------------------------------------------------------------------------
# Advanced section
# ---------------------------------------------------------------------------


@settings_router.get("/settings/advanced", response_class=HTMLResponse)
def settings_advanced_get(request: Request) -> HTMLResponse:
    ws = _load_web_settings()
    ctx = _section_context(request, ws, section="advanced")
    return templates.TemplateResponse("settings/_advanced.html", ctx)


@settings_router.post("/settings/advanced", response_class=HTMLResponse)
def settings_advanced_post(
    request: Request,
    log_level: str = Form("INFO"),
    cache_enabled: str = Form(""),
    debug_mode: str = Form(""),
) -> HTMLResponse:
    success = ""
    error = ""
    try:
        level = log_level.strip().upper()
        if level not in LOG_LEVEL_OPTIONS:
            level = "INFO"
        ws = _update_web_settings(
            log_level=level,
            cache_enabled=_as_form_bool(cache_enabled),
            debug_mode=_as_form_bool(debug_mode),
        )
        success = "Advanced settings saved."
    except Exception as exc:
        logger.exception("Failed to save advanced settings")
        error = f"Failed to save settings: {exc}"
        ws = _load_web_settings()
    ctx = _section_context(request, ws, section="advanced", success_message=success, error_message=error)
    return templates.TemplateResponse("settings/_advanced.html", ctx)
