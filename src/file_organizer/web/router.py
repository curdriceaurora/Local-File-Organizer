"""Web UI routes and template rendering.

This module acts as the top-level router that includes domain-specific
sub-routers for files, organization, settings, and profile management.
It also hosts lightweight routes that don't warrant their own module
(home page).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from loguru import logger

from file_organizer.api.auth_db import create_session
from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_settings
from file_organizer.api.jobs import list_jobs
from file_organizer.api.repositories.workspace_repo import WorkspaceRepository
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
    return templates.TemplateResponse(request, "index.html", context)


@router.get("/dashboard/pulse", response_class=HTMLResponse)
def dashboard_pulse(
    request: Request, settings: ApiSettings = Depends(get_settings)
) -> HTMLResponse:
    """Get dashboard metrics: active jobs, suggestions, and rules."""
    # Get active jobs from the job queue
    jobs = list_jobs()
    active_jobs = sum(1 for job in jobs if job.status in {"queued", "running"})

    # Get suggestions and rules from workspace settings
    suggestions = 0
    rules = 0
    try:
        with create_session(settings.auth_db_path) as session:
            repo = WorkspaceRepository(session)
            workspace = repo.get_active_workspace()
            if workspace:
                # Count organization rules (split by newline and filter empty)
                rules_text = getattr(workspace, "organization_rules", "")
                rules = len(
                    [line for line in rules_text.splitlines() if line.strip() and "->" in line]
                )
                # Suggestions could come from various sources - for now use 0
                suggestions = 0
    except Exception:
        # If database unavailable, use defaults
        logger.exception("Failed to fetch dashboard metrics")

    context = base_context(request, settings, active="home", title="Dashboard")
    return templates.TemplateResponse(
        request,
        "dashboard_pulse.html",
        {
            **context,
            "active_jobs": active_jobs,
            "suggestions": suggestions,
            "rules": rules,
        },
    )
