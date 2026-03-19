"""Pydantic models for plugin-facing API endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from file_organizer.api.models import FileInfo
from file_organizer.plugins.api.hooks import HookEvent

_MAX_PATH_LENGTH = 4096
_MAX_CALLBACK_URL_LENGTH = 2048


def _validate_path(value: str) -> str:
    if not value:
        raise ValueError("Path must not be empty")
    if len(value) > _MAX_PATH_LENGTH:
        raise ValueError("Path exceeds maximum length")
    if "\x00" in value:
        raise ValueError("Path contains invalid characters")
    return value


def _validate_callback_url(value: str) -> str:
    candidate = value.strip()
    if not candidate:
        raise ValueError("Callback URL must not be empty")
    if len(candidate) > _MAX_CALLBACK_URL_LENGTH:
        raise ValueError("Callback URL exceeds maximum length")
    if "\x00" in candidate:
        raise ValueError("Callback URL contains invalid characters")
    return candidate


class PluginFileListResponse(BaseModel):
    """Response containing a paginated list of files."""

    items: list[FileInfo]
    total: int


class PluginOrganizeFileRequest(BaseModel):
    """Request body for organizing a file via the plugin API."""

    source_path: str
    destination_path: str
    overwrite: bool = False
    dry_run: bool = False

    @field_validator("source_path", "destination_path")
    @classmethod
    def validate_paths(cls, value: str) -> str:
        """Validate that source and destination paths are non-empty."""
        return _validate_path(value)


class PluginOrganizeFileResponse(BaseModel):
    """Response from a plugin file organization request."""

    source_path: str
    destination_path: str
    moved: bool
    dry_run: bool


class PluginConfigValueResponse(BaseModel):
    """Response containing a single plugin configuration value."""

    key: str
    value: Any


class PluginHookRegistrationRequest(BaseModel):
    """Request body for registering a webhook for a plugin hook event."""

    event: HookEvent
    callback_url: str
    secret: str | None = Field(default=None, max_length=256)

    @field_validator("callback_url")
    @classmethod
    def validate_callback_url(cls, value: str) -> str:
        """Validate and normalize the callback URL."""
        return _validate_callback_url(value)


class PluginHookUnregisterRequest(BaseModel):
    """Request body for unregistering a plugin webhook."""

    event: HookEvent
    callback_url: str

    @field_validator("callback_url")
    @classmethod
    def validate_callback_url(cls, value: str) -> str:
        """Validate and normalize the callback URL."""
        return _validate_callback_url(value)


class PluginHookRegistrationResponse(BaseModel):
    """Response confirming webhook registration for a plugin."""

    plugin_id: str
    event: HookEvent
    callback_url: str
    created_at: datetime
    registered: bool


class PluginHookListResponse(BaseModel):
    """Response listing all registered webhooks for a plugin."""

    items: list[PluginHookRegistrationResponse]


class PluginHookUnregisterResponse(BaseModel):
    """Response confirming webhook unregistration for a plugin."""

    plugin_id: str
    event: HookEvent
    callback_url: str
    removed: bool


class PluginHookTriggerRequest(BaseModel):
    """Request body for triggering a plugin hook event."""

    event: HookEvent
    payload: dict[str, Any] = Field(default_factory=dict)


class PluginHookTriggerResult(BaseModel):
    """Individual result for a single webhook delivery attempt."""

    plugin_id: str
    event: HookEvent
    callback_url: str
    status_code: int | None
    delivered: bool
    error: str | None = None


class PluginHookTriggerResponse(BaseModel):
    """Response summarizing the outcomes of triggering a plugin hook."""

    event: HookEvent
    delivered: int
    failed: int
    results: list[PluginHookTriggerResult]
