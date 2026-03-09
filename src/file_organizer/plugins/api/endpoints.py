"""FastAPI endpoints for plugin-facing capabilities."""

from __future__ import annotations

import shutil
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import (
    UserLike,
    get_config_manager,
    get_current_active_user,
    get_settings,
)
from file_organizer.api.exceptions import ApiError
from file_organizer.api.models import FileInfo
from file_organizer.api.utils import file_info_from_path, is_hidden, resolve_path
from file_organizer.config.manager import ConfigManager
from file_organizer.plugins.api.hooks import HookEvent, PluginHookManager
from file_organizer.plugins.api.models import (
    PluginConfigValueResponse,
    PluginFileListResponse,
    PluginHookListResponse,
    PluginHookRegistrationRequest,
    PluginHookRegistrationResponse,
    PluginHookTriggerRequest,
    PluginHookTriggerResponse,
    PluginHookTriggerResult,
    PluginHookUnregisterRequest,
    PluginHookUnregisterResponse,
    PluginOrganizeFileRequest,
    PluginOrganizeFileResponse,
)

router = APIRouter(tags=["plugins"], dependencies=[Depends(get_current_active_user)])


@lru_cache
def get_hook_manager() -> PluginHookManager:
    """Return process-local hook manager instance."""
    return PluginHookManager()


def _plugin_identity(user: UserLike) -> str:
    """Derive stable plugin identity from current authenticated principal."""
    raw = getattr(user, "id", None)
    if not isinstance(raw, str) or not raw:
        raw = getattr(user, "username", "anonymous")
    return str(raw).replace(":", "_")


def _collect_files(path: Path, recursive: bool, include_hidden: bool) -> list[Path]:
    files: list[Path] = []
    if path.is_file():
        if include_hidden or not is_hidden(path):
            files.append(path)
        return files

    iterator = path.rglob("*") if recursive else path.glob("*")
    for entry in iterator:
        if not entry.is_file():
            continue
        if not include_hidden and is_hidden(entry):
            continue
        files.append(entry)
    files.sort(key=lambda entry: entry.name.lower())
    return files


def _read_config_key(manager: ConfigManager, profile: str, key: str) -> Any:
    cleaned_key = key.strip()
    if not cleaned_key:
        raise ApiError(status_code=400, error="invalid_key", message="Config key must not be empty")

    config = manager.load(profile)
    payload = manager.config_to_dict(config)
    current: Any = payload
    for segment in cleaned_key.split("."):
        if not segment:
            continue
        if isinstance(current, Mapping) and segment in current:
            current = current[segment]
            continue
        raise ApiError(
            status_code=404,
            error="config_key_not_found",
            message=f"Config key not found: {cleaned_key}",
        )
    return current


@router.get("/plugins/files/list", response_model=PluginFileListResponse)
def list_files_for_plugins(
    path: str = Query(..., description="Directory or file path"),
    recursive: bool = Query(False),
    include_hidden: bool = Query(False),
    max_items: int = Query(200, ge=1, le=1000),
    settings: ApiSettings = Depends(get_settings),
) -> PluginFileListResponse:
    """List files accessible to plugins."""
    target = resolve_path(path, settings.allowed_paths)
    if not target.exists():
        raise ApiError(status_code=404, error="not_found", message="Path does not exist")

    files = _collect_files(target, recursive, include_hidden)
    items = [file_info_from_path(entry) for entry in files[:max_items]]
    return PluginFileListResponse(items=items, total=len(files))


@router.get("/plugins/files/metadata", response_model=FileInfo)
def get_file_metadata_for_plugins(
    path: str = Query(..., description="File path"),
    settings: ApiSettings = Depends(get_settings),
) -> FileInfo:
    """Get metadata for a file accessible to plugins."""
    target = resolve_path(path, settings.allowed_paths)
    if not target.exists():
        raise ApiError(status_code=404, error="not_found", message="File not found")
    if not target.is_file():
        raise ApiError(status_code=400, error="invalid_path", message="Path is not a file")
    return file_info_from_path(target)


@router.post("/plugins/files/organize", response_model=PluginOrganizeFileResponse)
def organize_file_for_plugins(
    request: PluginOrganizeFileRequest,
    settings: ApiSettings = Depends(get_settings),
) -> PluginOrganizeFileResponse:
    """Organize a file using the plugin API."""
    source = resolve_path(request.source_path, settings.allowed_paths)
    destination = resolve_path(request.destination_path, settings.allowed_paths)

    if not source.exists() or not source.is_file():
        raise ApiError(status_code=404, error="not_found", message="Source file not found")

    if destination.exists() and not request.overwrite:
        raise ApiError(status_code=409, error="conflict", message="Destination already exists")

    if request.dry_run:
        return PluginOrganizeFileResponse(
            source_path=str(source),
            destination_path=str(destination),
            moved=False,
            dry_run=True,
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and request.overwrite:
        if destination.is_dir():
            shutil.rmtree(destination)
        else:
            destination.unlink()

    shutil.move(str(source), str(destination))
    return PluginOrganizeFileResponse(
        source_path=str(source),
        destination_path=str(destination),
        moved=True,
        dry_run=False,
    )


@router.get("/plugins/config/get", response_model=PluginConfigValueResponse)
def get_config_for_plugins(
    key: str = Query(..., description="Dot path to config value, e.g. updates.interval_hours"),
    profile: str = Query("default"),
    manager: ConfigManager = Depends(get_config_manager),
) -> PluginConfigValueResponse:
    """Retrieve a configuration value accessible to plugins."""
    value = _read_config_key(manager, profile, key)
    return PluginConfigValueResponse(key=key, value=value)


@router.post("/plugins/hooks/register", response_model=PluginHookRegistrationResponse)
def register_plugin_hook(
    request: PluginHookRegistrationRequest,
    user: UserLike = Depends(get_current_active_user),
    hook_manager: PluginHookManager = Depends(get_hook_manager),
) -> PluginHookRegistrationResponse:
    """Register a webhook callback for a plugin hook event."""
    plugin_id = _plugin_identity(user)
    try:
        registration, created = hook_manager.register_webhook(
            plugin_id=plugin_id,
            event=request.event,
            callback_url=request.callback_url,
            secret=request.secret,
        )
    except ValueError as exc:
        raise ApiError(
            status_code=400,
            error="invalid_callback_url",
            message=str(exc),
        ) from exc
    return PluginHookRegistrationResponse(
        plugin_id=registration.plugin_id,
        event=registration.event,
        callback_url=registration.callback_url,
        created_at=registration.created_at,
        registered=created,
    )


@router.post("/plugins/hooks/unregister", response_model=PluginHookUnregisterResponse)
def unregister_plugin_hook(
    request: PluginHookUnregisterRequest,
    user: UserLike = Depends(get_current_active_user),
    hook_manager: PluginHookManager = Depends(get_hook_manager),
) -> PluginHookUnregisterResponse:
    """Register a webhook callback for a plugin hook event."""
    plugin_id = _plugin_identity(user)
    try:
        removed = hook_manager.unregister_webhook(
            plugin_id=plugin_id,
            event=request.event,
            callback_url=request.callback_url,
        )
    except ValueError as exc:
        raise ApiError(
            status_code=400,
            error="invalid_callback_url",
            message=str(exc),
        ) from exc
    return PluginHookUnregisterResponse(
        plugin_id=plugin_id,
        event=request.event,
        callback_url=request.callback_url,
        removed=removed,
    )


@router.get("/plugins/hooks", response_model=PluginHookListResponse)
def list_plugin_hooks(
    event: Optional[HookEvent] = Query(None),
    user: UserLike = Depends(get_current_active_user),
    hook_manager: PluginHookManager = Depends(get_hook_manager),
) -> PluginHookListResponse:
    """List all registered webhooks for a plugin."""
    plugin_id = _plugin_identity(user)
    webhooks = hook_manager.list_webhooks(plugin_id=plugin_id, event=event)
    items = [
        PluginHookRegistrationResponse(
            plugin_id=webhook.plugin_id,
            event=webhook.event,
            callback_url=webhook.callback_url,
            created_at=webhook.created_at,
            registered=True,
        )
        for webhook in webhooks
    ]
    return PluginHookListResponse(items=items)


@router.post("/plugins/hooks/trigger", response_model=PluginHookTriggerResponse)
def trigger_plugin_hook_event(
    request: PluginHookTriggerRequest,
    user: UserLike = Depends(get_current_active_user),
    hook_manager: PluginHookManager = Depends(get_hook_manager),
) -> PluginHookTriggerResponse:
    """Trigger a plugin hook event and deliver to registered callbacks."""
    plugin_id = _plugin_identity(user)
    local_payload = dict(request.payload)
    local_payload["triggered_by"] = plugin_id

    # Trigger in-process hooks and webhooks with the same event payload.
    hook_manager.trigger_local_hooks(request.event, local_payload)
    deliveries = hook_manager.trigger_event(request.event, local_payload)

    results = [
        PluginHookTriggerResult(
            plugin_id=delivery.plugin_id,
            event=delivery.event,
            callback_url=delivery.callback_url,
            status_code=delivery.status_code,
            delivered=delivery.delivered,
            error=delivery.error,
        )
        for delivery in deliveries
    ]
    delivered = sum(1 for result in results if result.delivered)
    failed = len(results) - delivered
    return PluginHookTriggerResponse(
        event=request.event,
        delivered=delivered,
        failed=failed,
        results=results,
    )
