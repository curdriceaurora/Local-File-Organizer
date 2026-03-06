"""Web UI routes for browsing and managing marketplace plugins."""

from __future__ import annotations

from html import escape
from typing import Optional

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_settings
from file_organizer.plugins.marketplace import MarketplaceError, MarketplaceService
from file_organizer.web._helpers import base_context, templates

marketplace_router = APIRouter(tags=["web"])


def _service() -> MarketplaceService:
    """Return a fresh ``MarketplaceService`` instance."""
    return MarketplaceService()


def _normalize_tags(raw_tags: Optional[list[str]]) -> list[str]:
    """Flatten and clean a list of possibly comma-separated tag strings.

    Args:
        raw_tags: Raw tag tokens that may contain comma-separated values.

    Returns:
        Stripped list of individual tag strings.
    """
    tags: list[str] = []
    for token in raw_tags or []:
        for part in token.split(","):
            cleaned = part.strip()
            if cleaned:
                tags.append(cleaned)
    return tags


def _render_marketplace_page(
    request: Request,
    settings: ApiSettings,
    *,
    query: str = "",
    category: Optional[str] = None,
    tags: Optional[list[str]] = None,
    page: int = 1,
    per_page: int = 24,
    message: Optional[str] = None,
    message_kind: str = "info",
) -> HTMLResponse:
    """Build the marketplace HTML page with plugin listing and optional flash message.

    Returns:
        Rendered marketplace index page.
    """
    error_message: Optional[str] = None
    plugins = []
    total = 0
    installed_names: set[str] = set()
    try:
        service = _service()
        plugins, total = service.list_plugins(
            page=page,
            per_page=per_page,
            query=query,
            category=category,
            tags=_normalize_tags(tags),
        )
        installed_names = {item.name for item in service.list_installed()}
    except MarketplaceError as exc:
        error_message = str(exc)

    context = base_context(
        request,
        settings,
        active="marketplace",
        title="Plugin Marketplace",
        extras={
            "plugins": plugins,
            "installed_names": installed_names,
            "total_plugins": total,
            "page": page,
            "per_page": per_page,
            "query": query,
            "category": category or "",
            "tags": _normalize_tags(tags),
            "message": message,
            "message_kind": message_kind,
            "error_message": error_message,
        },
    )
    return templates.TemplateResponse(request, "marketplace/index.html", context)


@marketplace_router.get("/marketplace", response_class=HTMLResponse)
def marketplace_home(
    request: Request,
    settings: ApiSettings = Depends(get_settings),
    q: str = Query("", alias="q"),
    category: Optional[str] = Query(None),
    tags: Optional[list[str]] = Query(None, alias="tag"),
    page: int = Query(1, ge=1),
    per_page: int = Query(24, ge=1, le=100),
) -> HTMLResponse:
    """Display the plugin marketplace with optional search, category, and tag filters.

    Returns:
        Rendered marketplace page.
    """
    return _render_marketplace_page(
        request,
        settings,
        query=q,
        category=category,
        tags=_normalize_tags(tags),
        page=page,
        per_page=per_page,
    )


@marketplace_router.post("/marketplace/plugins/{name}/install", response_class=HTMLResponse)
def install_plugin(
    request: Request,
    name: str,
    settings: ApiSettings = Depends(get_settings),
    q: str = Form(default=""),
    category: str = Form(default=""),
    tag_csv: str = Form(default=""),
) -> HTMLResponse:
    """Install a marketplace plugin by name and re-render the marketplace page.

    Args:
        request: Incoming FastAPI request.
        name: Plugin identifier from the URL path.
        settings: Application settings with allowed paths.
        q: Current search query to preserve across actions.
        category: Active category filter to preserve.
        tag_csv: Comma-separated tag filters to preserve.

    Returns:
        Marketplace page with a success or error flash message.
    """
    tags = _normalize_tags([tag_csv])
    try:
        installed = _service().install(name)
        message = f"Installed {installed.name} {installed.version}."
        message_kind = "success"
    except MarketplaceError as exc:
        message = str(exc)
        message_kind = "error"
    return _render_marketplace_page(
        request,
        settings,
        query=q,
        category=category or None,
        tags=tags,
        message=message,
        message_kind=message_kind,
    )


@marketplace_router.post("/marketplace/plugins/{name}/uninstall", response_class=HTMLResponse)
def uninstall_plugin(
    request: Request,
    name: str,
    settings: ApiSettings = Depends(get_settings),
    q: str = Form(default=""),
    category: str = Form(default=""),
    tag_csv: str = Form(default=""),
) -> HTMLResponse:
    """Uninstall a previously installed plugin and re-render the marketplace page.

    Args:
        request: Incoming FastAPI request.
        name: Plugin identifier from the URL path.
        settings: Application settings with allowed paths.
        q: Current search query to preserve across actions.
        category: Active category filter to preserve.
        tag_csv: Comma-separated tag filters to preserve.

    Returns:
        Marketplace page with a success or error flash message.
    """
    tags = _normalize_tags([tag_csv])
    try:
        _service().uninstall(name)
        message = f"Uninstalled {name}."
        message_kind = "success"
    except MarketplaceError as exc:
        message = str(exc)
        message_kind = "error"
    return _render_marketplace_page(
        request,
        settings,
        query=q,
        category=category or None,
        tags=tags,
        message=message,
        message_kind=message_kind,
    )


@marketplace_router.post("/marketplace/plugins/{name}/update", response_class=HTMLResponse)
def update_plugin(
    request: Request,
    name: str,
    settings: ApiSettings = Depends(get_settings),
    q: str = Form(default=""),
    category: str = Form(default=""),
    tag_csv: str = Form(default=""),
) -> HTMLResponse:
    """Update an installed plugin to the latest version.

    Args:
        request: Incoming FastAPI request.
        name: Plugin identifier from the URL path.
        settings: Application settings with allowed paths.
        q: Current search query to preserve across actions.
        category: Active category filter to preserve.
        tag_csv: Comma-separated tag filters to preserve.

    Returns:
        Marketplace page with an update status flash message.
    """
    tags = _normalize_tags([tag_csv])
    try:
        updated = _service().update(name)
        if updated is None:
            message = f"{name} is already up to date."
            message_kind = "info"
        else:
            message = f"Updated {updated.name} to {updated.version}."
            message_kind = "success"
    except MarketplaceError as exc:
        message = str(exc)
        message_kind = "error"
    return _render_marketplace_page(
        request,
        settings,
        query=q,
        category=category or None,
        tags=tags,
        message=message,
        message_kind=message_kind,
    )


@marketplace_router.get("/marketplace/plugins/{name}/details", response_class=HTMLResponse)
def plugin_details(
    request: Request,
    name: str,
    settings: ApiSettings = Depends(get_settings),
) -> HTMLResponse:
    """Display plugin details in a modal.

    Args:
        request: Incoming FastAPI request.
        name: Plugin identifier.
        settings: Application settings.

    Returns:
        Plugin details HTML fragment for modal.
    """
    try:
        service = _service()
        plugin = service.get_plugin(name)

        if not plugin:
            return HTMLResponse("<p>Plugin not found.</p>", status_code=404)

        context = base_context(
            request,
            settings,
            active="marketplace",
            title=f"{plugin.name} Details",
            extras={"plugin": plugin},
        )
        return templates.TemplateResponse(request, "marketplace/plugin_details.html", context)
    except MarketplaceError as exc:
        error_msg = escape(str(exc))
        return HTMLResponse(f"<p>Error loading plugin details: {error_msg}</p>", status_code=500)
