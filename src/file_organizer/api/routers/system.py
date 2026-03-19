"""System endpoints for configuration and status."""

from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, Query

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import (
    get_config_manager,
    get_current_active_user,
    get_settings,
    require_admin_user,
)
from file_organizer.api.exceptions import ApiError
from file_organizer.api.jobs import job_count
from file_organizer.api.models import (
    ConfigResponse,
    ConfigUpdateRequest,
    StorageStatsResponse,
    SystemStatusResponse,
)
from file_organizer.api.utils import file_info_from_path, resolve_path
from file_organizer.config.manager import ConfigManager
from file_organizer.services.analytics.storage_analyzer import StorageAnalyzer

router = APIRouter(tags=["system"], dependencies=[Depends(get_current_active_user)])


@router.get("/system/status", response_model=SystemStatusResponse)
def system_status(
    settings: ApiSettings = Depends(get_settings),
    path: str = Query(".", description="Path for disk usage"),
) -> SystemStatusResponse:
    """Return system status including disk usage and active job count."""
    target = resolve_path(path, settings.allowed_paths)
    if not target.exists():
        raise ApiError(status_code=404, error="not_found", message="Path not found")
    if not target.is_dir():
        raise ApiError(status_code=400, error="invalid_path", message="Path is not a directory")
    disk = shutil.disk_usage(target)
    return SystemStatusResponse(
        app=settings.app_name,
        version=settings.version,
        environment=settings.environment,
        disk_total=disk.total,
        disk_used=disk.used,
        disk_free=disk.free,
        active_jobs=job_count(),
    )


@router.get("/system/config", response_model=ConfigResponse)
def get_config(
    profile: str = Query("default"),
    manager: ConfigManager = Depends(get_config_manager),
) -> ConfigResponse:
    """Retrieve the current configuration for a named profile."""
    config = manager.load(profile)
    payload = manager.config_to_dict(config)
    return ConfigResponse(profile=profile, config=payload, profiles=manager.list_profiles())


@router.patch("/system/config", response_model=ConfigResponse)
def update_config(
    request: ConfigUpdateRequest,
    manager: ConfigManager = Depends(get_config_manager),
    _admin: object = Depends(require_admin_user),
) -> ConfigResponse:
    """Apply partial updates to the configuration for a named profile."""
    config = manager.load(request.profile)

    if request.default_methodology is not None:
        config.default_methodology = request.default_methodology

    if request.models is not None:
        for field, value in request.models.model_dump(exclude_none=True).items():
            setattr(config.models, field, value)

    if request.updates is not None:
        for field, value in request.updates.model_dump(exclude_none=True).items():
            setattr(config.updates, field, value)

    excluded_fields = {"profile", "default_methodology", "models", "updates"}
    for name, value in request.model_dump(exclude_none=True).items():
        if name in excluded_fields:
            continue
        if hasattr(config, name):
            setattr(config, name, value)

    manager.save(config, request.profile)
    payload = manager.config_to_dict(config)
    return ConfigResponse(
        profile=request.profile,
        config=payload,
        profiles=manager.list_profiles(),
    )


@router.get("/system/stats", response_model=StorageStatsResponse)
def get_stats(
    path: str = Query(".", description="Directory to analyze"),
    max_depth: int | None = Query(None, ge=1),
    use_cache: bool = Query(True),
    settings: ApiSettings = Depends(get_settings),
) -> StorageStatsResponse:
    """Return storage statistics for the specified directory."""
    target = resolve_path(path, settings.allowed_paths)
    if not target.exists():
        raise ApiError(status_code=404, error="not_found", message="Path not found")
    if not target.is_dir():
        raise ApiError(status_code=400, error="invalid_path", message="Path is not a directory")

    analyzer = StorageAnalyzer()
    stats = analyzer.analyze_directory(target, max_depth=max_depth, use_cache=use_cache)

    largest_files = []
    for info in stats.largest_files:
        validated_path: Path = resolve_path(str(info.path), settings.allowed_paths)
        largest_files.append(file_info_from_path(validated_path))

    return StorageStatsResponse(
        total_size=stats.total_size,
        organized_size=stats.organized_size,
        saved_size=stats.saved_size,
        file_count=stats.file_count,
        directory_count=stats.directory_count,
        size_by_type=stats.size_by_type,
        largest_files=largest_files,
    )
