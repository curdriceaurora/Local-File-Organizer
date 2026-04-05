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
from file_organizer.api.openapi_responses import (
    ADMIN_403_RESPONSE,
    AUTH_401_RESPONSE,
    INTERNAL_500_RESPONSE,
    api_error_response,
    merge_responses,
    success_response,
    validation_error_response,
)
from file_organizer.api.utils import file_info_from_path, resolve_path
from file_organizer.config.manager import ConfigManager
from file_organizer.services.analytics.storage_analyzer import StorageAnalyzer

router = APIRouter(
    tags=["system"],
    dependencies=[Depends(get_current_active_user)],
    responses=merge_responses(AUTH_401_RESPONSE, INTERNAL_500_RESPONSE),
)


@router.get(
    "/system/status",
    response_model=SystemStatusResponse,
    responses=merge_responses(
        success_response(
            "Returned runtime system status.",
            {
                "app": "File Organizer",
                "version": "2.0.0-alpha.3",
                "environment": "production",
                "disk_total": 1000000,
                "disk_used": 400000,
                "disk_free": 600000,
                "active_jobs": 0,
            },
        ),
        api_error_response(400, error="invalid_path", message="Path is not a directory"),
        api_error_response(404, error="not_found", message="Path not found"),
        validation_error_response(),
    ),
)
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


@router.get(
    "/system/config",
    response_model=ConfigResponse,
    responses=merge_responses(
        success_response(
            "Returned configuration profile.",
            {
                "profile": "default",
                "config": {"default_methodology": "PARA"},
                "profiles": ["default"],
            },
        ),
        validation_error_response(),
    ),
)
def get_config(
    profile: str = Query("default"),
    manager: ConfigManager = Depends(get_config_manager),
) -> ConfigResponse:
    """Retrieve the current configuration for a named profile."""
    config = manager.load(profile)
    payload = manager.config_to_dict(config)
    return ConfigResponse(profile=profile, config=payload, profiles=manager.list_profiles())


@router.patch(
    "/system/config",
    response_model=ConfigResponse,
    responses=merge_responses(
        success_response(
            "Updated configuration profile.",
            {
                "profile": "default",
                "config": {"default_methodology": "PARA"},
                "profiles": ["default"],
            },
        ),
        ADMIN_403_RESPONSE,
        validation_error_response(),
    ),
)
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
        models = request.models
        for field, value in models.model_dump(exclude_none=True).items():
            setattr(config.models, field, value)

    if request.updates is not None:
        updates = request.updates
        for field, value in updates.model_dump(exclude_none=True).items():
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


@router.get(
    "/system/stats",
    response_model=StorageStatsResponse,
    responses=merge_responses(
        success_response(
            "Returned storage statistics.",
            {
                "total_size": 1000000,
                "organized_size": 750000,
                "saved_size": 250000,
                "file_count": 120,
                "directory_count": 18,
                "size_by_type": {"pdf": 400000},
                "largest_files": [],
            },
        ),
        api_error_response(400, error="invalid_path", message="Path is not a directory"),
        api_error_response(404, error="not_found", message="Path not found"),
        validation_error_response(),
    ),
)
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
