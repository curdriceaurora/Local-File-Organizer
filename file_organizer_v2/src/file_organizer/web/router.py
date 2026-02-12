"""Web UI routes and template rendering.

This module acts as the top-level router that includes domain-specific
sub-routers for files and organization.  It also hosts lightweight routes
that don't warrant their own module (home, settings stub, profile stub).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_settings
from file_organizer.web._helpers import STATIC_DIR, base_context, templates
from file_organizer.web.files_routes import files_router
from file_organizer.web.organize_routes import organize_router

# Re-export so ``from file_organizer.web.router import STATIC_DIR`` keeps working.
__all__ = ["STATIC_DIR", "router"]

router = APIRouter(tags=["web"])
router.include_router(files_router)
router.include_router(organize_router)


# ---------------------------------------------------------------------------
# Lightweight page routes
# ---------------------------------------------------------------------------


@router.get("/", response_class=HTMLResponse)
def home(request: Request, settings: ApiSettings = Depends(get_settings)) -> HTMLResponse:
    context = base_context(request, settings, active="home", title="Home")
    return templates.TemplateResponse("index.html", context)


@router.get("/settings", response_class=HTMLResponse)
def settings(request: Request, settings_obj: ApiSettings = Depends(get_settings)) -> HTMLResponse:
    context = base_context(request, settings_obj, active="settings", title="Settings")
    return templates.TemplateResponse("settings/index.html", context)


@router.get("/profile", response_class=HTMLResponse)
def profile(request: Request, settings: ApiSettings = Depends(get_settings)) -> HTMLResponse:
    context = base_context(request, settings, active="profile", title="Profile")
    return templates.TemplateResponse("profile/index.html", context)
