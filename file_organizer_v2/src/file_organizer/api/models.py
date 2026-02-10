"""Pydantic models for API requests and responses."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

_MAX_PATH_LENGTH = 4096
_USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,31}$")


def _validate_path(value: str) -> str:
    if not value:
        raise ValueError("Path must not be empty")
    if len(value) > _MAX_PATH_LENGTH:
        raise ValueError("Path exceeds maximum length")
    if "\x00" in value:
        raise ValueError("Path contains null bytes")
    return value


def _validate_text(value: str, field_name: str, max_length: int) -> str:
    if not value:
        raise ValueError(f"{field_name} must not be empty")
    if len(value) > max_length:
        raise ValueError(f"{field_name} exceeds maximum length")
    if "\x00" in value:
        raise ValueError(f"{field_name} contains invalid characters")
    return value


class FileInfo(BaseModel):
    path: str
    name: str
    size: int
    created: datetime
    modified: datetime
    file_type: str
    mime_type: Optional[str] = None


class FileListResponse(BaseModel):
    items: list[FileInfo]
    total: int
    skip: int
    limit: int


class FileContentResponse(BaseModel):
    path: str
    content: str
    encoding: str
    truncated: bool
    size: int
    mime_type: Optional[str] = None


class MoveFileRequest(BaseModel):
    source: str
    destination: str
    overwrite: bool = False
    allow_directory_overwrite: bool = False
    dry_run: bool = False

    @field_validator("source", "destination")
    @classmethod
    def validate_paths(cls, value: str) -> str:
        return _validate_path(value)


class MoveFileResponse(BaseModel):
    source: str
    destination: str
    moved: bool
    dry_run: bool


class DeleteFileRequest(BaseModel):
    path: str
    permanent: bool = False
    dry_run: bool = False

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        return _validate_path(value)


class DeleteFileResponse(BaseModel):
    path: str
    deleted: bool
    dry_run: bool
    trashed_path: Optional[str] = None


class ScanRequest(BaseModel):
    input_dir: str
    recursive: bool = True
    include_hidden: bool = False

    @field_validator("input_dir")
    @classmethod
    def validate_input_dir(cls, value: str) -> str:
        return _validate_path(value)


class ScanResponse(BaseModel):
    input_dir: str
    total_files: int
    counts: dict[str, int]


class OrganizeRequest(BaseModel):
    input_dir: str
    output_dir: str
    skip_existing: bool = True
    dry_run: bool = False
    use_hardlinks: bool = True
    run_in_background: bool = True

    @field_validator("input_dir", "output_dir")
    @classmethod
    def validate_paths(cls, value: str) -> str:
        return _validate_path(value)


class OrganizationError(BaseModel):
    file: str
    error: str


class OrganizationResultResponse(BaseModel):
    total_files: int
    processed_files: int
    skipped_files: int
    failed_files: int
    processing_time: float
    organized_structure: dict[str, list[str]]
    errors: list[OrganizationError]


class OrganizeExecuteResponse(BaseModel):
    status: Literal["queued", "completed", "failed"]
    job_id: Optional[str] = None
    result: Optional[OrganizationResultResponse] = None
    error: Optional[str] = None


class JobStatusResponse(BaseModel):
    job_id: str
    status: Literal["queued", "running", "completed", "failed"]
    created_at: datetime
    updated_at: datetime
    result: Optional[OrganizationResultResponse] = None
    error: Optional[str] = None


class DedupeScanRequest(BaseModel):
    path: str
    recursive: bool = True
    algorithm: Literal["md5", "sha256"] = "sha256"
    min_file_size: int = 0
    max_file_size: Optional[int] = None
    include_patterns: Optional[list[str]] = None
    exclude_patterns: Optional[list[str]] = None

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        return _validate_path(value)


class DedupeFileInfo(BaseModel):
    path: str
    size: int
    modified: datetime
    accessed: datetime


class DedupeGroup(BaseModel):
    hash_value: str
    files: list[DedupeFileInfo]
    total_size: int
    wasted_space: int


class DedupeScanResponse(BaseModel):
    path: str
    duplicates: list[DedupeGroup]
    stats: dict[str, int]


class DedupePreviewGroup(BaseModel):
    hash_value: str
    keep: str
    remove: list[str]


class DedupePreviewResponse(BaseModel):
    path: str
    preview: list[DedupePreviewGroup]
    stats: dict[str, int]


class DedupeExecuteRequest(BaseModel):
    path: str
    recursive: bool = True
    algorithm: Literal["md5", "sha256"] = "sha256"
    min_file_size: int = 0
    max_file_size: Optional[int] = None
    include_patterns: Optional[list[str]] = None
    exclude_patterns: Optional[list[str]] = None
    dry_run: bool = True
    trash: bool = True

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        return _validate_path(value)


class DedupeExecuteResponse(BaseModel):
    path: str
    removed: list[str]
    dry_run: bool
    stats: dict[str, int]


class SystemStatusResponse(BaseModel):
    app: str
    version: str
    environment: str
    disk_total: int
    disk_used: int
    disk_free: int
    active_jobs: int


class ConfigResponse(BaseModel):
    profile: str
    config: dict[str, Any]
    profiles: list[str] = Field(default_factory=list)


class UserCreateRequest(BaseModel):
    username: str
    email: EmailStr
    password: str
    full_name: Optional[str] = None

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        value = _validate_text(value, "Username", 32)
        if not _USERNAME_PATTERN.match(value):
            raise ValueError(
                "Username must be 3-32 characters and use letters, numbers, '.', '-', '_'"
            )
        return value

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        return _validate_text(value, "Full name", 120)


class UserResponse(BaseModel):
    id: str
    username: str
    email: EmailStr
    full_name: Optional[str] = None
    is_active: bool
    is_admin: bool
    created_at: datetime
    last_login: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenRefreshRequest(BaseModel):
    refresh_token: str


class TokenRevokeRequest(BaseModel):
    refresh_token: str


class ModelPresetUpdate(BaseModel):
    text_model: Optional[str] = None
    vision_model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    device: Optional[str] = None
    framework: Optional[str] = None


class UpdateSettingsUpdate(BaseModel):
    check_on_startup: Optional[bool] = None
    interval_hours: Optional[int] = None
    include_prereleases: Optional[bool] = None
    repo: Optional[str] = None


class ConfigUpdateRequest(BaseModel):
    profile: str = "default"
    default_methodology: Optional[str] = None
    models: Optional[ModelPresetUpdate] = None
    updates: Optional[UpdateSettingsUpdate] = None
    watcher: Optional[dict[str, Any]] = None
    daemon: Optional[dict[str, Any]] = None
    parallel: Optional[dict[str, Any]] = None
    pipeline: Optional[dict[str, Any]] = None
    events: Optional[dict[str, Any]] = None
    deploy: Optional[dict[str, Any]] = None
    para: Optional[dict[str, Any]] = None
    johnny_decimal: Optional[dict[str, Any]] = None


class StorageStatsResponse(BaseModel):
    total_size: int
    organized_size: int
    saved_size: int
    file_count: int
    directory_count: int
    size_by_type: dict[str, int]
    largest_files: list[FileInfo]


class ApiErrorResponse(BaseModel):
    error: str
    message: str
    details: Optional[Any] = None
