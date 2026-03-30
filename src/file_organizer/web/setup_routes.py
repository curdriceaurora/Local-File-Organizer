"""Web UI routes for the setup wizard.

This module provides a guided setup wizard interface that:
- detects Ollama installation and available models
- checks hardware capabilities (RAM, VRAM, GPU)
- recommends optimal AI models based on system specs
- guides users through organizing their first folder
- supports quick-start and power-user modes
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_settings
from file_organizer.web._helpers import base_context, templates

setup_router = APIRouter(tags=["web"])


@setup_router.get("/setup", response_class=HTMLResponse)
def setup_wizard(
    request: Request,
    settings: ApiSettings = Depends(get_settings),
) -> HTMLResponse:
    """Render the setup wizard page.

    This page guides users through initial configuration:
    - Hardware capability detection
    - Ollama and model discovery
    - AI model recommendations
    - Methodology selection
    - First folder organization preview

    Returns:
        Full HTML page for the setup wizard.
    """
    context = base_context(
        request,
        settings,
        active="setup",
        title="Setup Wizard",
        extras={
            "setup_mode": "quick_start",
            "show_wizard": True,
        },
    )
    return templates.TemplateResponse(request, "setup_wizard.html", context)
