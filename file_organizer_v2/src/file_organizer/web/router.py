"""Web UI routes and template rendering.

This module acts as the top-level router that includes domain-specific
sub-routers for files, organization, settings, and profile management.
It also hosts lightweight routes that don't warrant their own module
(home page).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_settings
from file_organizer.web._helpers import STATIC_DIR, base_context, templates
from file_organizer.web.files_routes import files_router
from file_organizer.web.marketplace_routes import marketplace_router
from file_organizer.web.organize_routes import organize_router
from file_organizer.web.profile_routes import profile_router
from file_organizer.web.settings_routes import settings_router

# Re-export so ``from file_organizer.web.router import STATIC_DIR`` keeps working.
__all__ = ["STATIC_DIR", "router"]

router = APIRouter(tags=["web"])
router.include_router(files_router)
router.include_router(organize_router)
router.include_router(marketplace_router)
router.include_router(settings_router)
router.include_router(profile_router)


# ---------------------------------------------------------------------------
# Lightweight page routes
# ---------------------------------------------------------------------------


@router.get("/", response_class=HTMLResponse)
def home(request: Request, settings: ApiSettings = Depends(get_settings)) -> HTMLResponse:
    context = base_context(request, settings, active="home", title="Home")
    return templates.TemplateResponse("index.html", context)
