"""API endpoints for third-party integration management."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Request

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_current_active_user, get_settings
from file_organizer.api.exceptions import ApiError
from file_organizer.api.integration_models import (
    BrowserConfigResponse,
    BrowserTokenIssueRequest,
    BrowserTokenIssueResponse,
    BrowserTokenVerifyRequest,
    BrowserTokenVerifyResponse,
    IntegrationConnectResponse,
    IntegrationFileSendRequest,
    IntegrationFileSendResponse,
    IntegrationSettingsUpdateRequest,
    IntegrationStatusListResponse,
    IntegrationStatusPayload,
)
from file_organizer.api.utils import resolve_path
from file_organizer.integrations import (
    BrowserExtensionManager,
    IntegrationConfig,
    IntegrationManager,
    IntegrationType,
    ObsidianIntegration,
    VSCodeIntegration,
    WorkflowIntegration,
)

router = APIRouter(tags=["integrations"], dependencies=[Depends(get_current_active_user)])


def _default_integration_root() -> Path:
    return Path.home() / ".config" / "file-organizer" / "integrations"


def build_integration_manager(settings: ApiSettings) -> IntegrationManager:
    """Construct integration manager with default adapters."""
    root = _default_integration_root()
    root.mkdir(parents=True, exist_ok=True)

    default_allowed = settings.allowed_paths[0] if settings.allowed_paths else str(Path.home())
    obsidian_vault = os.environ.get("FO_OBSIDIAN_VAULT_PATH", default_allowed)
    vscode_workspace = os.environ.get("FO_VSCODE_WORKSPACE_PATH", default_allowed)
    workflow_output = os.environ.get("FO_WORKFLOW_OUTPUT_PATH", str(root / "workflow"))
    vscode_commands = os.environ.get("FO_VSCODE_COMMAND_PATH", str(root / "vscode-commands.jsonl"))

    manager = IntegrationManager()
    manager.register(
        ObsidianIntegration(
            IntegrationConfig(
                name="obsidian",
                integration_type=IntegrationType.DESKTOP_APP,
                auth_method="none",
                settings={
                    "vault_path": obsidian_vault,
                    "attachments_subdir": "Attachments",
                    "notes_subdir": "Notes",
                },
            )
        )
    )
    manager.register(
        VSCodeIntegration(
            IntegrationConfig(
                name="vscode",
                integration_type=IntegrationType.EDITOR,
                auth_method="none",
                settings={
                    "workspace_path": vscode_workspace,
                    "command_output_path": vscode_commands,
                },
            )
        )
    )
    manager.register(
        WorkflowIntegration(
            IntegrationConfig(
                name="workflow",
                integration_type=IntegrationType.WORKFLOW,
                auth_method="none",
                settings={
                    "output_dir": workflow_output,
                },
            )
        )
    )
    return manager


def build_browser_extension_manager(settings: ApiSettings) -> BrowserExtensionManager:
    """Construct browser extension auth/config manager."""
    return BrowserExtensionManager(allowed_origins=settings.cors_origins, token_ttl_seconds=3600)


def get_integration_manager(
    request: Request, settings: ApiSettings = Depends(get_settings)
) -> IntegrationManager:
    manager = getattr(request.app.state, "integration_manager", None)
    if manager is None:
        manager = build_integration_manager(settings)
        request.app.state.integration_manager = manager
    return manager


def get_browser_extension_manager(
    request: Request,
    settings: ApiSettings = Depends(get_settings),
) -> BrowserExtensionManager:
    manager = getattr(request.app.state, "browser_extension_manager", None)
    if manager is None:
        manager = build_browser_extension_manager(settings)
        request.app.state.browser_extension_manager = manager
    return manager


def _validate_setting_paths(
    settings_update: dict[str, Any],
    settings: ApiSettings,
) -> dict[str, Any]:
    normalized = dict(settings_update)
    path_keys = {"vault_path", "workspace_path", "output_dir", "command_output_path"}
    for key in path_keys:
        value = normalized.get(key)
        if not isinstance(value, str) or not value.strip():
            continue
        raw_path = os.path.expanduser(value)
        if key == "command_output_path":
            directory = os.path.dirname(raw_path)
            if directory:
                candidate = directory
            else:
                # Bare filenames should resolve to a deterministic base directory.
                candidate = (
                    settings.allowed_paths[0] if settings.allowed_paths else str(Path.home())
                )
            validated_root = resolve_path(candidate, settings.allowed_paths)
            base_name = os.path.basename(raw_path)
            # Validate basename to prevent path traversal attacks
            if not base_name or "/" in base_name or "\\" in base_name or ".." in base_name:
                raise ApiError(
                    status_code=400, error="invalid_filename", message="Invalid filename in path"
                )
            normalized[key] = os.path.join(str(validated_root), base_name)
        else:
            validated_root = resolve_path(raw_path, settings.allowed_paths)
            normalized[key] = str(validated_root)
    return normalized


def _require_integration(manager: IntegrationManager, integration_name: str) -> None:
    if manager.get(integration_name) is None:
        raise ApiError(status_code=404, error="not_found", message="Integration not found")


@router.get("/integrations", response_model=IntegrationStatusListResponse)
async def list_integrations(
    manager: IntegrationManager = Depends(get_integration_manager),
) -> IntegrationStatusListResponse:
    statuses = await manager.list_statuses()
    return IntegrationStatusListResponse(
        items=[
            IntegrationStatusPayload(
                name=item.name,
                type=item.integration_type.value,
                enabled=item.enabled,
                connected=item.connected,
                details=item.details,
            )
            for item in statuses
        ]
    )


@router.post("/integrations/{integration_name}/settings", response_model=IntegrationConnectResponse)
async def update_integration_settings(
    integration_name: str,
    request: IntegrationSettingsUpdateRequest,
    manager: IntegrationManager = Depends(get_integration_manager),
    settings: ApiSettings = Depends(get_settings),
) -> IntegrationConnectResponse:
    _require_integration(manager, integration_name)

    normalized_settings = _validate_setting_paths(request.settings, settings)
    manager.update_settings(integration_name, normalized_settings)
    return IntegrationConnectResponse(integration=integration_name, connected=False)


@router.post("/integrations/{integration_name}/connect", response_model=IntegrationConnectResponse)
async def connect_integration(
    integration_name: str,
    manager: IntegrationManager = Depends(get_integration_manager),
) -> IntegrationConnectResponse:
    _require_integration(manager, integration_name)
    connected = await manager.connect(integration_name)
    return IntegrationConnectResponse(integration=integration_name, connected=connected)


@router.post(
    "/integrations/{integration_name}/disconnect", response_model=IntegrationConnectResponse
)
async def disconnect_integration(
    integration_name: str,
    manager: IntegrationManager = Depends(get_integration_manager),
) -> IntegrationConnectResponse:
    _require_integration(manager, integration_name)
    disconnected = await manager.disconnect(integration_name)
    return IntegrationConnectResponse(integration=integration_name, connected=not disconnected)


@router.post("/integrations/{integration_name}/send", response_model=IntegrationFileSendResponse)
async def send_file_to_integration(
    integration_name: str,
    request: IntegrationFileSendRequest,
    manager: IntegrationManager = Depends(get_integration_manager),
    settings: ApiSettings = Depends(get_settings),
) -> IntegrationFileSendResponse:
    _require_integration(manager, integration_name)

    safe_path = resolve_path(request.path, settings.allowed_paths)
    sent = await manager.send_file(integration_name, str(safe_path), metadata=request.metadata)
    return IntegrationFileSendResponse(integration=integration_name, sent=sent, path=str(safe_path))


@router.get("/integrations/browser/config", response_model=BrowserConfigResponse)
def browser_extension_config(
    manager: BrowserExtensionManager = Depends(get_browser_extension_manager),
) -> BrowserConfigResponse:
    payload = manager.get_config()
    return BrowserConfigResponse(**payload)


@router.post("/integrations/browser/token", response_model=BrowserTokenIssueResponse)
def issue_browser_extension_token(
    request: BrowserTokenIssueRequest,
    manager: BrowserExtensionManager = Depends(get_browser_extension_manager),
) -> BrowserTokenIssueResponse:
    record = manager.issue_token(request.extension_id)
    return BrowserTokenIssueResponse(token=record.token, expires_at=record.expires_at)


@router.post("/integrations/browser/verify", response_model=BrowserTokenVerifyResponse)
def verify_browser_extension_token(
    request: BrowserTokenVerifyRequest,
    manager: BrowserExtensionManager = Depends(get_browser_extension_manager),
) -> BrowserTokenVerifyResponse:
    return BrowserTokenVerifyResponse(valid=manager.verify_token(request.token))
