"""Pydantic models for integration API endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from file_organizer.api.models import _validate_path, _validate_text


class IntegrationSettingsUpdateRequest(BaseModel):
    """Request body for updating integration settings."""

    settings: dict[str, Any] = Field(default_factory=dict)


class IntegrationConnectResponse(BaseModel):
    """Response for integration connect/disconnect operations."""

    integration: str
    connected: bool


class IntegrationFileSendRequest(BaseModel):
    """Request body for sending a file to an integration."""

    path: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        """Validate and return the file path."""
        return _validate_path(value)


class IntegrationFileSendResponse(BaseModel):
    """Response after sending a file to an integration."""

    integration: str
    sent: bool
    path: str


class IntegrationStatusPayload(BaseModel):
    """Status payload for a single integration."""

    name: str
    type: str
    enabled: bool
    connected: bool
    details: dict[str, Any] = Field(default_factory=dict)


class IntegrationStatusListResponse(BaseModel):
    """Response listing integration statuses."""

    items: list[IntegrationStatusPayload] = Field(default_factory=list)


class BrowserTokenIssueRequest(BaseModel):
    """Request body for issuing a browser extension token."""

    extension_id: str

    @field_validator("extension_id")
    @classmethod
    def validate_extension_id(cls, value: str) -> str:
        """Validate and return the extension ID."""
        return _validate_text(value.strip(), "extension_id", 120)


class BrowserTokenIssueResponse(BaseModel):
    """Response containing the issued token and its expiry."""

    token: str
    expires_at: datetime


class BrowserTokenVerifyRequest(BaseModel):
    """Request body for verifying a browser extension token."""

    token: str

    @field_validator("token")
    @classmethod
    def validate_token(cls, value: str) -> str:
        """Validate and return the token."""
        return _validate_text(value.strip(), "token", 512)


class BrowserTokenVerifyResponse(BaseModel):
    """Response indicating whether a browser extension token is valid."""

    valid: bool


class BrowserConfigResponse(BaseModel):
    """Response containing browser extension configuration."""

    allowed_origins: list[str] = Field(default_factory=list)
    token_ttl_seconds: int
