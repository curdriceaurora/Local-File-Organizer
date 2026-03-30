"""Web UI routes and template rendering.

This module acts as the top-level router that includes domain-specific
sub-routers for files, organization, settings, and profile management.
It also hosts lightweight routes that don't warrant their own module
(home page).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_settings
from file_organizer.config.manager import ConfigManager
from file_organizer.web._helpers import STATIC_DIR, base_context, templates
from file_organizer.web.files_routes import files_router
from file_organizer.web.marketplace_routes import marketplace_router
from file_organizer.web.organize_routes import organize_router
from file_organizer.web.profile_routes import profile_router
from file_organizer.web.settings_routes import settings_router
from file_organizer.web.setup_routes import setup_router

# Re-export so ``from file_organizer.web.router import STATIC_DIR`` keeps working.
__all__ = ["STATIC_DIR", "router"]

router = APIRouter(tags=["web"])
router.include_router(setup_router)
router.include_router(files_router)
router.include_router(organize_router)
router.include_router(marketplace_router)
router.include_router(settings_router)
router.include_router(profile_router)


# ---------------------------------------------------------------------------
# Lightweight page routes
# ---------------------------------------------------------------------------


@router.get("/", response_model=None)
def home(
    request: Request, settings: ApiSettings = Depends(get_settings)
) -> HTMLResponse | RedirectResponse:
    """Render the home page with base context.

    On first run (setup not completed), redirects to the setup wizard.
    After setup is complete, shows the dashboard.

    Returns:
        Full HTML page for the home view or redirect to setup wizard.
    """
    # Check if first-run setup has been completed
    config_manager = ConfigManager()
    config = config_manager.load()

    if not config.setup_completed:
        return RedirectResponse(url="/ui/setup", status_code=303)

    context = base_context(request, settings, active="home", title="Home")
    return templates.TemplateResponse(request, "index.html", context)
