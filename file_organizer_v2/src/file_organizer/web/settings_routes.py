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
from pathlib import Path
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, Response
from loguru import logger

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_settings
from file_organizer.web._helpers import base_context, templates

settings_router = APIRouter(tags=["web"])

_SETTINGS_DIR = Path.home() / ".config" / "file-organizer"
_SETTINGS_FILE = _SETTINGS_DIR / "web-settings.json"

METHODOLOGY_OPTIONS = {
    "content_based": "Content-Based",
    "johnny_decimal": "Johnny Decimal",
    "para": "PARA",
    "date_based": "Date-Based",
}
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
    """Persistent settings for the web UI."""

    # General
    language: str = "en"
    timezone: str = "UTC"
    default_input_dir: str = ""
    default_output_dir: str = ""

    # Models
    text_model: str = "qwen2.5:3b-instruct-q4_K_M"
    vision_model: str = "qwen2.5vl:7b-q4_K_M"
    ollama_url: str = "http://localhost:11434"

    # Organization
    default_methodology: str = "content_based"
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


def _as_form_bool(value: Optional[str]) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _coerce_bool(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return default


def _validate_choice(value: str, allowed: list[str], fallback: str) -> str:
    candidate = value.strip()
    return candidate if candidate in allowed else fallback


def _validate_methodology(value: str) -> str:
    candidate = value.strip().lower()
    return candidate if candidate in METHODOLOGY_OPTIONS else "content_based"


def _validate_rules(rules: str) -> tuple[bool, str]:
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
        ws.default_methodology = _validate_methodology(ws.default_methodology)
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
    try:
        _SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
        _SETTINGS_FILE.write_text(json.dumps(asdict(ws), indent=2) + "\n", encoding="utf-8")
    except Exception as exc:
        logger.error("Failed to save settings to {}: {}", _SETTINGS_FILE, exc)


def _update_web_settings(**kwargs: object) -> WebSettings:
    ws = _load_web_settings()
    known_fields = {f.name for f in fields(WebSettings)}
    for key, value in kwargs.items():
        if key in known_fields:
            setattr(ws, key, value)
    _save_web_settings(ws)
    return ws


def _section_context(
    request: Request,
    ws: WebSettings,
    *,
    section: str,
    success_message: str = "",
    error_message: str = "",
) -> dict[str, object]:
    return {
        "request": request,
        "ws": ws,
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
    *,
    section: str,
    success_message: str = "",
    error_message: str = "",
) -> HTMLResponse:
    context = _section_context(
        request,
        ws,
        section=section,
        success_message=success_message,
        error_message=error_message,
    )
    return templates.TemplateResponse(f"settings/_{section}.html", context)


@settings_router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, settings_obj: ApiSettings = Depends(get_settings)) -> HTMLResponse:
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
            "language_options": LANGUAGE_OPTIONS,
            "timezone_options": TIMEZONE_OPTIONS,
            "performance_modes": PERFORMANCE_MODES,
        },
    )
    return templates.TemplateResponse("settings/index.html", context)


@settings_router.get("/settings/search", response_class=HTMLResponse)
def settings_search(query: str = Query("", alias="q")) -> HTMLResponse:
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
def settings_export() -> Response:
    ws = _load_web_settings()
    payload = json.dumps(asdict(ws), indent=2) + "\n"
    return Response(
        content=payload,
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="web-settings.json"'},
    )


@settings_router.post("/settings/import", response_class=HTMLResponse)
async def settings_import(
    request: Request,
    section: str = Form("general"),
    settings_file: UploadFile = File(...),
) -> HTMLResponse:
    valid_sections = {"general", "models", "organization", "appearance", "advanced"}
    target_section = section if section in valid_sections else "general"

    try:
        raw_bytes = await settings_file.read()
        payload = json.loads(raw_bytes.decode("utf-8"))
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

        ws.default_methodology = _validate_methodology(ws.default_methodology)
        ws.theme = _validate_choice(ws.theme, THEME_OPTIONS, "light")
        ws.log_level = _validate_choice(ws.log_level, LOG_LEVEL_OPTIONS, "INFO")
        ws.performance_mode = _validate_choice(ws.performance_mode, PERFORMANCE_MODES, "balanced")
        ws.language = _validate_choice(ws.language, LANGUAGE_OPTIONS, "en")
        ws.timezone = _validate_choice(ws.timezone, TIMEZONE_OPTIONS, "UTC")
        _save_web_settings(ws)

        return _render_section(
            request,
            ws,
            section=target_section,
            success_message="Settings imported successfully.",
        )
    except Exception as exc:
        ws = _load_web_settings()
        return _render_section(
            request,
            ws,
            section=target_section,
            error_message=f"Import failed: {exc}",
        )


@settings_router.post("/settings/reset", response_class=HTMLResponse)
def settings_reset(request: Request, section: str = Form("general")) -> HTMLResponse:
    valid_sections = {"general", "models", "organization", "appearance", "advanced"}
    target_section = section if section in valid_sections else "general"
    ws = WebSettings()
    _save_web_settings(ws)
    return _render_section(
        request,
        ws,
        section=target_section,
        success_message="Settings reset to defaults.",
    )


@settings_router.get("/settings/general", response_class=HTMLResponse)
def settings_general_get(request: Request) -> HTMLResponse:
    return _render_section(request, _load_web_settings(), section="general")


@settings_router.post("/settings/general", response_class=HTMLResponse)
def settings_general_post(
    request: Request,
    language: str = Form("en"),
    timezone: str = Form("UTC"),
    default_input_dir: str = Form(""),
    default_output_dir: str = Form(""),
) -> HTMLResponse:
    try:
        ws = _update_web_settings(
            language=_validate_choice(language, LANGUAGE_OPTIONS, "en"),
            timezone=_validate_choice(timezone, TIMEZONE_OPTIONS, "UTC"),
            default_input_dir=default_input_dir.strip(),
            default_output_dir=default_output_dir.strip(),
        )
        return _render_section(
            request,
            ws,
            section="general",
            success_message="General settings saved.",
        )
    except Exception as exc:
        logger.exception("Failed to save general settings")
        return _render_section(
            request,
            _load_web_settings(),
            section="general",
            error_message=f"Failed to save settings: {exc}",
        )


@settings_router.get("/settings/models", response_class=HTMLResponse)
def settings_models_get(request: Request) -> HTMLResponse:
    return _render_section(request, _load_web_settings(), section="models")


@settings_router.post("/settings/models", response_class=HTMLResponse)
def settings_models_post(
    request: Request,
    text_model: str = Form(""),
    vision_model: str = Form(""),
    ollama_url: str = Form(""),
) -> HTMLResponse:
    try:
        ws = _update_web_settings(
            text_model=text_model.strip() or "qwen2.5:3b-instruct-q4_K_M",
            vision_model=vision_model.strip() or "qwen2.5vl:7b-q4_K_M",
            ollama_url=ollama_url.strip() or "http://localhost:11434",
        )
        return _render_section(
            request,
            ws,
            section="models",
            success_message="Model settings saved.",
        )
    except Exception as exc:
        logger.exception("Failed to save model settings")
        return _render_section(
            request,
            _load_web_settings(),
            section="models",
            error_message=f"Failed to save settings: {exc}",
        )


@settings_router.post("/settings/models/test", response_class=HTMLResponse)
def settings_models_test(
    request: Request,
    ollama_url: str = Form(""),
) -> HTMLResponse:
    ws = _load_web_settings()
    target = ollama_url.strip() or ws.ollama_url
    try:
        with httpx.Client(timeout=3.0) as client:
            response = client.get(f"{target.rstrip('/')}/api/tags")
            response.raise_for_status()
        ws = _update_web_settings(ollama_url=target)
        return _render_section(
            request,
            ws,
            section="models",
            success_message="Ollama connection successful.",
        )
    except Exception as exc:
        return _render_section(
            request,
            ws,
            section="models",
            error_message=f"Ollama connection failed: {exc}",
        )


@settings_router.get("/settings/organization", response_class=HTMLResponse)
def settings_organization_get(request: Request) -> HTMLResponse:
    return _render_section(request, _load_web_settings(), section="organization")


@settings_router.post("/settings/organization/validate", response_class=HTMLResponse)
def settings_organization_validate(
    request: Request,
    organization_rules: str = Form(""),
) -> HTMLResponse:
    ws = _load_web_settings()
    candidate_rules = organization_rules or ws.organization_rules
    valid, message = _validate_rules(candidate_rules)
    if valid:
        ws.organization_rules = candidate_rules
        _save_web_settings(ws)
        return _render_section(
            request,
            ws,
            section="organization",
            success_message=message,
        )
    ws.organization_rules = candidate_rules
    return _render_section(
        request,
        ws,
        section="organization",
        error_message=message,
    )


@settings_router.post("/settings/organization", response_class=HTMLResponse)
def settings_organization_post(
    request: Request,
    default_methodology: str = Form("content_based"),
    auto_organize: Optional[str] = Form(None),
    notifications_enabled: Optional[str] = Form(None),
    file_filter_glob: str = Form("*"),
    organization_rules: str = Form(""),
) -> HTMLResponse:
    existing = _load_web_settings()
    candidate_rules = organization_rules or existing.organization_rules
    valid, message = _validate_rules(candidate_rules)
    if not valid:
        existing.organization_rules = candidate_rules
        return _render_section(
            request,
            existing,
            section="organization",
            error_message=message,
        )

    try:
        ws = _update_web_settings(
            default_methodology=_validate_methodology(default_methodology),
            auto_organize=_as_form_bool(auto_organize),
            notifications_enabled=_as_form_bool(notifications_enabled),
            file_filter_glob=file_filter_glob.strip() or "*",
            organization_rules=candidate_rules,
        )
        return _render_section(
            request,
            ws,
            section="organization",
            success_message="Organization settings saved.",
        )
    except Exception as exc:
        logger.exception("Failed to save organization settings")
        return _render_section(
            request,
            _load_web_settings(),
            section="organization",
            error_message=f"Failed to save settings: {exc}",
        )


@settings_router.get("/settings/appearance", response_class=HTMLResponse)
def settings_appearance_get(request: Request) -> HTMLResponse:
    return _render_section(request, _load_web_settings(), section="appearance")


@settings_router.post("/settings/appearance", response_class=HTMLResponse)
def settings_appearance_post(
    request: Request,
    theme: str = Form("light"),
    custom_theme_name: str = Form(""),
) -> HTMLResponse:
    try:
        ws = _update_web_settings(
            theme=_validate_choice(theme.lower(), THEME_OPTIONS, "light"),
            custom_theme_name=custom_theme_name.strip(),
        )
        return _render_section(
            request,
            ws,
            section="appearance",
            success_message="Appearance settings saved.",
        )
    except Exception as exc:
        logger.exception("Failed to save appearance settings")
        return _render_section(
            request,
            _load_web_settings(),
            section="appearance",
            error_message=f"Failed to save settings: {exc}",
        )


@settings_router.get("/settings/advanced", response_class=HTMLResponse)
def settings_advanced_get(request: Request) -> HTMLResponse:
    return _render_section(request, _load_web_settings(), section="advanced")


@settings_router.post("/settings/advanced", response_class=HTMLResponse)
def settings_advanced_post(
    request: Request,
    log_level: str = Form("INFO"),
    cache_enabled: Optional[str] = Form(None),
    debug_mode: Optional[str] = Form(None),
    performance_mode: str = Form("balanced"),
) -> HTMLResponse:
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
            section="advanced",
            success_message="Advanced settings saved.",
        )
    except Exception as exc:
        logger.exception("Failed to save advanced settings")
        return _render_section(
            request,
            _load_web_settings(),
            section="advanced",
            error_message=f"Failed to save settings: {exc}",
        )
