"""Configuration endpoints backed by the real ConfigManager."""

from __future__ import annotations

from threading import Lock, RLock

from fastapi import APIRouter, Depends, Query

from file_organizer.api.dependencies import get_config_manager, require_admin_user
from file_organizer.api.exceptions import ApiError
from file_organizer.api.models import ConfigResponse, ConfigUpdateRequest
from file_organizer.api.openapi_responses import (
    ADMIN_403_RESPONSE,
    INTERNAL_500_RESPONSE,
    api_error_response,
    merge_responses,
    success_response,
    validation_error_response,
)
from file_organizer.api.utils import apply_config_update
from file_organizer.config.defaults import DEFAULT_TEXT_MODEL
from file_organizer.config.manager import ConfigManager, UnsupportedConfigVersionError
from file_organizer.config.schema import AppConfig

router = APIRouter(tags=["config"], responses=INTERNAL_500_RESPONSE)

_CONFIG_UPDATE_LOCKS: dict[tuple[str, str], RLock] = {}
_CONFIG_UPDATE_LOCKS_GUARD = Lock()


def _profile_update_lock(manager: ConfigManager, profile: str) -> RLock:
    """Return the process-local lock for one persisted config profile."""
    key = (str(manager.config_dir.resolve()), profile)
    with _CONFIG_UPDATE_LOCKS_GUARD:
        return _CONFIG_UPDATE_LOCKS.setdefault(key, RLock())


def _response(manager: ConfigManager, profile: str, config: AppConfig) -> ConfigResponse:
    """Build a ConfigResponse from an AppConfig instance."""
    return ConfigResponse(
        profile=profile,
        config=manager.config_to_dict(config),
        profiles=manager.list_profiles(),
    )


@router.get(
    "/config",
    response_model=ConfigResponse,
    responses=merge_responses(
        success_response(
            "Returned configuration profile.",
            {
                "profile": "default",
                "config": {
                    "version": "1.0",
                    "default_methodology": "none",
                    "setup_completed": False,
                    "models": {"text_model": DEFAULT_TEXT_MODEL},
                },
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
    """Retrieve the persisted configuration for a named profile."""
    config = manager.load(profile)
    return _response(manager, profile, config)


@router.put(
    "/config",
    response_model=ConfigResponse,
    responses=merge_responses(
        success_response(
            "Updated configuration profile.",
            {
                "profile": "default",
                "config": {
                    "default_methodology": "para",
                    "models": {"text_model": "llama3:8b"},
                },
                "profiles": ["default"],
            },
        ),
        ADMIN_403_RESPONSE,
        api_error_response(
            409,
            error="unsupported_config_version",
            message="On-disk profile schema version is unsupported for safe overwrite",
        ),
        validation_error_response(),
    ),
)
def update_config(
    request: ConfigUpdateRequest,
    manager: ConfigManager = Depends(get_config_manager),
    _admin: object = Depends(require_admin_user),
) -> ConfigResponse:
    """Apply partial updates to a persisted configuration profile."""
    with _profile_update_lock(manager, request.profile):
        config = manager.load(request.profile)
        apply_config_update(config, request)

        try:
            manager.save(config, request.profile)
        except UnsupportedConfigVersionError as exc:
            raise ApiError(
                status_code=409,
                error="unsupported_config_version",
                message=str(exc),
            ) from exc

        return _response(manager, request.profile, config)


@router.post(
    "/config/reset",
    response_model=ConfigResponse,
    responses=merge_responses(
        success_response(
            "Reset configuration profile to defaults.",
            {
                "profile": "default",
                "config": {"default_methodology": "none", "setup_completed": False},
                "profiles": ["default"],
            },
        ),
        ADMIN_403_RESPONSE,
    ),
)
def reset_config(
    profile: str = Query("default"),
    manager: ConfigManager = Depends(get_config_manager),
    _admin: object = Depends(require_admin_user),
) -> ConfigResponse:
    """Reset a persisted configuration profile to defaults."""
    config = AppConfig(profile_name=profile)
    manager.save(config, profile, force=True)
    return _response(manager, profile, config)
