"""Web UI routes and template rendering."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_settings

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

router = APIRouter(tags=["web"])

_templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

_NAV_ITEMS = [
    ("Home", "/ui/"),
    ("Files", "/ui/files"),
    ("Organize", "/ui/organize"),
    ("Settings", "/ui/settings"),
    ("Profile", "/ui/profile"),
]


def _base_context(
    request: Request,
    settings: ApiSettings,
    *,
    active: str,
    title: str,
    extras: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context: dict[str, Any] = {
        "request": request,
        "app_name": settings.app_name,
        "version": settings.version,
        "active": active,
        "page_title": title,
        "nav_items": _NAV_ITEMS,
        "year": datetime.now(timezone.utc).year,
    }
    if extras:
        context.update(extras)
    return context


@router.get("/", response_class=HTMLResponse)
async def home(request: Request, settings: ApiSettings = Depends(get_settings)) -> HTMLResponse:
    context = _base_context(request, settings, active="home", title="Home")
    return _templates.TemplateResponse("index.html", context)


@router.get("/files", response_class=HTMLResponse)
async def files_browser(request: Request, settings: ApiSettings = Depends(get_settings)) -> HTMLResponse:
    context = _base_context(request, settings, active="files", title="Files")
    return _templates.TemplateResponse("files/browser.html", context)


@router.get("/organize", response_class=HTMLResponse)
async def organize_dashboard(request: Request, settings: ApiSettings = Depends(get_settings)) -> HTMLResponse:
    context = _base_context(request, settings, active="organize", title="Organize")
    return _templates.TemplateResponse("organize/dashboard.html", context)


@router.get("/settings", response_class=HTMLResponse)
async def settings(request: Request, settings_obj: ApiSettings = Depends(get_settings)) -> HTMLResponse:
    context = _base_context(request, settings_obj, active="settings", title="Settings")
    return _templates.TemplateResponse("settings/index.html", context)


@router.get("/profile", response_class=HTMLResponse)
async def profile(request: Request, settings: ApiSettings = Depends(get_settings)) -> HTMLResponse:
    context = _base_context(request, settings, active="profile", title="Profile")
    return _templates.TemplateResponse("profile/index.html", context)
