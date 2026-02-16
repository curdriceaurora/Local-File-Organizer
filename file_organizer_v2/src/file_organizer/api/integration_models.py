"""Pydantic models for integration API endpoints."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from file_organizer.api.models import _validate_path, _validate_text


class IntegrationSettingsUpdateRequest(BaseModel):
    settings: dict[str, Any] = Field(default_factory=dict)


class IntegrationConnectResponse(BaseModel):
    integration: str
    connected: bool


class IntegrationFileSendRequest(BaseModel):
    path: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        return _validate_path(value)


class IntegrationFileSendResponse(BaseModel):
    integration: str
    sent: bool
    path: str


class IntegrationStatusPayload(BaseModel):
    name: str
    type: str
    enabled: bool
    connected: bool
    details: dict[str, Any] = Field(default_factory=dict)


class IntegrationStatusListResponse(BaseModel):
    items: list[IntegrationStatusPayload] = Field(default_factory=list)


class BrowserTokenIssueRequest(BaseModel):
    extension_id: str

    @field_validator("extension_id")
    @classmethod
    def validate_extension_id(cls, value: str) -> str:
        return _validate_text(value.strip(), "extension_id", 120)


class BrowserTokenIssueResponse(BaseModel):
    token: str
    expires_at: datetime


class BrowserTokenVerifyRequest(BaseModel):
    token: str

    @field_validator("token")
    @classmethod
    def validate_token(cls, value: str) -> str:
        return _validate_text(value.strip(), "token", 512)


class BrowserTokenVerifyResponse(BaseModel):
    valid: bool


class BrowserConfigResponse(BaseModel):
    allowed_origins: list[str] = Field(default_factory=list)
    token_ttl_seconds: int
