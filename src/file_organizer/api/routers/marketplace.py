"""API routes for plugin marketplace operations."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from file_organizer.api.dependencies import UserLike, get_current_active_user
from file_organizer.api.exceptions import ApiError
from file_organizer.plugins.marketplace import (
    InstalledPlugin,
    MarketplaceError,
    MarketplaceService,
    PluginPackage,
    PluginReview,
)

router = APIRouter(
    tags=["marketplace"],
    dependencies=[Depends(get_current_active_user)],
)


class MarketplacePluginResponse(BaseModel):
    """Marketplace plugin details response model."""

    name: str
    version: str
    author: str
    description: str
    homepage: Optional[str]
    category: str
    tags: list[str]
    dependencies: list[str]
    downloads: int
    rating: float
    reviews_count: int
    min_organizer_version: str
    max_organizer_version: Optional[str]


class MarketplacePluginListResponse(BaseModel):
    """Paginated list of marketplace plugins."""

    items: list[MarketplacePluginResponse]
    page: int
    per_page: int
    total: int


class MarketplaceInstalledResponse(BaseModel):
    """Details of an installed marketplace plugin."""

    name: str
    version: str
    source_url: str
    installed_at: str


class MarketplaceUpdateResponse(BaseModel):
    """Result of a plugin update operation."""

    updated: bool
    plugin: Optional[MarketplaceInstalledResponse] = None


class MarketplaceReviewRequest(BaseModel):
    """Request body for submitting a plugin review."""

    rating: int = Field(..., ge=1, le=5)
    title: str = Field(..., min_length=1, max_length=120)
    content: str = Field(..., min_length=1, max_length=2000)


class MarketplaceReviewResponse(BaseModel):
    """Plugin review details response model."""

    plugin_name: str
    user_id: str
    rating: int
    title: str
    content: str
    created_at: str
    updated_at: str
    helpful_count: int


def _service() -> MarketplaceService:
    return MarketplaceService()


def _package_to_response(package: PluginPackage) -> MarketplacePluginResponse:
    return MarketplacePluginResponse(
        name=package.name,
        version=package.version,
        author=package.author,
        description=package.description,
        homepage=package.homepage,
        category=package.category,
        tags=list(package.tags),
        dependencies=list(package.dependencies),
        downloads=package.downloads,
        rating=package.rating,
        reviews_count=package.reviews_count,
        min_organizer_version=package.min_organizer_version,
        max_organizer_version=package.max_organizer_version,
    )


def _installed_to_response(installed: InstalledPlugin) -> MarketplaceInstalledResponse:
    return MarketplaceInstalledResponse(
        name=installed.name,
        version=installed.version,
        source_url=installed.source_url,
        installed_at=installed.installed_at,
    )


def _review_to_response(review: PluginReview) -> MarketplaceReviewResponse:
    return MarketplaceReviewResponse(
        plugin_name=review.plugin_name,
        user_id=review.user_id,
        rating=review.rating,
        title=review.title,
        content=review.content,
        created_at=review.created_at,
        updated_at=review.updated_at,
        helpful_count=review.helpful_count,
    )


def _raise_marketplace_error(exc: MarketplaceError) -> None:
    message = str(exc)
    lowered = message.lower()
    if "not found" in lowered:
        raise ApiError(status_code=404, error="not_found", message=message) from exc
    if "checksum" in lowered:
        raise ApiError(status_code=422, error="checksum_failed", message=message) from exc
    raise ApiError(status_code=400, error="marketplace_error", message=message) from exc


@router.get("/marketplace/plugins", response_model=MarketplacePluginListResponse)
def list_plugins(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    q: str = Query("", max_length=200),
    tags: Optional[list[str]] = Query(None),
    category: Optional[str] = Query(None, max_length=60),
) -> MarketplacePluginListResponse:
    """List plugins from the marketplace with optional filters."""
    try:
        items, total = _service().list_plugins(
            page=page,
            per_page=per_page,
            query=q,
            tags=tags,
            category=category,
        )
    except MarketplaceError as exc:
        _raise_marketplace_error(exc)
    return MarketplacePluginListResponse(
        items=[_package_to_response(item) for item in items],
        page=page,
        per_page=per_page,
        total=total,
    )


@router.get("/marketplace/plugins/{name}", response_model=MarketplacePluginResponse)
def get_plugin(name: str) -> MarketplacePluginResponse:
    """Retrieve details for a single marketplace plugin by name."""
    try:
        package = _service().get_plugin(name)
    except MarketplaceError as exc:
        _raise_marketplace_error(exc)
    return _package_to_response(package)


@router.get("/marketplace/installed", response_model=list[MarketplaceInstalledResponse])
def list_installed_plugins() -> list[MarketplaceInstalledResponse]:
    """List all currently installed plugins."""
    try:
        items = _service().list_installed()
    except MarketplaceError as exc:
        _raise_marketplace_error(exc)
    return [_installed_to_response(item) for item in items]


@router.get("/marketplace/updates", response_model=list[str])
def list_available_updates() -> list[str]:
    """List plugin names that have available updates."""
    try:
        return _service().check_updates()
    except MarketplaceError as exc:
        _raise_marketplace_error(exc)


@router.post("/marketplace/plugins/{name}/install", response_model=MarketplaceInstalledResponse)
def install_plugin(
    name: str,
    version: Optional[str] = Query(None),
) -> MarketplaceInstalledResponse:
    """Install a marketplace plugin by name and optional version."""
    try:
        installed = _service().install(name, version=version)
    except MarketplaceError as exc:
        _raise_marketplace_error(exc)
    return _installed_to_response(installed)


@router.delete("/marketplace/plugins/{name}")
def uninstall_plugin(name: str) -> dict[str, bool]:
    """Uninstall a marketplace plugin by name."""
    try:
        _service().uninstall(name)
    except MarketplaceError as exc:
        _raise_marketplace_error(exc)
    return {"uninstalled": True}


@router.post("/marketplace/plugins/{name}/update", response_model=MarketplaceUpdateResponse)
def update_plugin(name: str) -> MarketplaceUpdateResponse:
    """Update an installed plugin to the latest version."""
    try:
        updated = _service().update(name)
    except MarketplaceError as exc:
        _raise_marketplace_error(exc)
    if updated is None:
        return MarketplaceUpdateResponse(updated=False, plugin=None)
    return MarketplaceUpdateResponse(updated=True, plugin=_installed_to_response(updated))


@router.get("/marketplace/plugins/{name}/reviews", response_model=list[MarketplaceReviewResponse])
def list_reviews(
    name: str,
    limit: int = Query(10, ge=1, le=100),
) -> list[MarketplaceReviewResponse]:
    """List reviews for a marketplace plugin."""
    try:
        reviews = _service().get_reviews(name, limit=limit)
    except MarketplaceError as exc:
        _raise_marketplace_error(exc)
    return [_review_to_response(review) for review in reviews]


@router.post("/marketplace/plugins/{name}/reviews", response_model=MarketplaceReviewResponse)
def add_review(
    name: str,
    request: MarketplaceReviewRequest,
    user: UserLike = Depends(get_current_active_user),
) -> MarketplaceReviewResponse:
    """Submit a review for a marketplace plugin."""
    raw_user = getattr(user, "id", None)
    if not isinstance(raw_user, str) or not raw_user:
        raw_user = getattr(user, "username", "anonymous")
    review = PluginReview(
        plugin_name=name,
        user_id=raw_user,
        rating=request.rating,
        title=request.title,
        content=request.content,
    )
    try:
        service = _service()
        service.add_review(review)
        latest = service.get_reviews(name, limit=1)
    except MarketplaceError as exc:
        _raise_marketplace_error(exc)
    if not latest:
        raise ApiError(
            status_code=500, error="review_write_failed", message="Review was not saved."
        )
    return _review_to_response(latest[0])
