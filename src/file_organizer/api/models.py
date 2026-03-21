"""Pydantic models for API requests and responses."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, computed_field, field_validator

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
    """File metadata for API responses."""

    path: str
    name: str
    size: int
    created: datetime
    modified: datetime
    file_type: str
    mime_type: str | None = None


class FileListResponse(BaseModel):
    """Paginated list of files."""

    items: list[FileInfo]
    total: int
    skip: int
    limit: int

    @computed_field  # type: ignore[prop-decorator]
    @property
    def files(self) -> list[FileInfo]:
        """Alias for items field for API compatibility."""
        return self.items


class FileContentResponse(BaseModel):
    """Response containing file content and metadata."""

    path: str
    content: str
    encoding: str
    truncated: bool
    size: int
    mime_type: str | None = None


class MoveFileRequest(BaseModel):
    """Request body for moving a file."""

    source: str
    destination: str
    overwrite: bool = False
    allow_directory_overwrite: bool = False
    dry_run: bool = False

    @field_validator("source", "destination")
    @classmethod
    def validate_paths(cls, value: str) -> str:
        """Validate and return source or destination path."""
        return _validate_path(value)


class MoveFileResponse(BaseModel):
    """Response for file move operation."""

    source: str
    destination: str
    moved: bool
    dry_run: bool


class DeleteFileRequest(BaseModel):
    """Request body for deleting a file."""

    path: str
    permanent: bool = False
    dry_run: bool = False

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        """Validate and return the file path."""
        return _validate_path(value)


class DeleteFileResponse(BaseModel):
    """Response for file delete operation."""

    path: str
    deleted: bool
    dry_run: bool
    trashed_path: str | None = None


class ScanRequest(BaseModel):
    """Request body for directory scanning."""

    input_dir: str
    recursive: bool = True
    include_hidden: bool = False

    @field_validator("input_dir")
    @classmethod
    def validate_input_dir(cls, value: str) -> str:
        """Validate and return the input directory path."""
        return _validate_path(value)


class ScanResponse(BaseModel):
    """Response for directory scan with file counts by type."""

    input_dir: str
    total_files: int
    counts: dict[str, int]


class OrganizeRequest(BaseModel):
    """Request body for file organization."""

    input_dir: str
    output_dir: str
    skip_existing: bool = True
    dry_run: bool = False
    use_hardlinks: bool = True
    run_in_background: bool = True

    @field_validator("input_dir", "output_dir")
    @classmethod
    def validate_paths(cls, value: str) -> str:
        """Validate and return input or output directory paths."""
        return _validate_path(value)


class OrganizationError(BaseModel):
    """A single file organization error record."""

    file: str
    error: str


class OrganizationResultResponse(BaseModel):
    """Result of a file organization run."""

    total_files: int
    processed_files: int
    skipped_files: int
    failed_files: int
    deduplicated_files: int = 0
    processing_time: float
    organized_structure: dict[str, list[str]]
    errors: list[OrganizationError]


class OrganizeExecuteResponse(BaseModel):
    """Response for an organization execute request."""

    status: Literal["queued", "completed", "failed"]
    job_id: str | None = None
    result: OrganizationResultResponse | None = None
    error: str | None = None


class JobStatusResponse(BaseModel):
    """Status of a background organization job."""

    job_id: str
    status: Literal["queued", "running", "completed", "failed"]
    created_at: datetime
    updated_at: datetime
    result: OrganizationResultResponse | None = None
    error: str | None = None


class DedupeScanRequest(BaseModel):
    """Request body for duplicate file scanning."""

    path: str
    recursive: bool = True
    algorithm: Literal["md5", "sha256"] = "sha256"
    min_file_size: int = 0
    max_file_size: int | None = None
    include_patterns: list[str] | None = None
    exclude_patterns: list[str] | None = None

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        """Validate and return the scan path."""
        return _validate_path(value)


class DedupeFileInfo(BaseModel):
    """File info within a duplicate group."""

    path: str
    size: int
    modified: datetime
    accessed: datetime


class DedupeGroup(BaseModel):
    """A group of duplicate files sharing the same hash."""

    hash_value: str
    files: list[DedupeFileInfo]
    total_size: int
    wasted_space: int


class DedupeScanResponse(BaseModel):
    """Response for duplicate file scan."""

    path: str
    duplicates: list[DedupeGroup]
    stats: dict[str, int]


class DedupePreviewGroup(BaseModel):
    """Preview of which file to keep and which to remove from a group."""

    hash_value: str
    keep: str
    remove: list[str]


class DedupePreviewResponse(BaseModel):
    """Response for duplicate file preview."""

    path: str
    preview: list[DedupePreviewGroup]
    stats: dict[str, int]


class DedupeExecuteRequest(BaseModel):
    """Request body for duplicate file removal."""

    path: str
    recursive: bool = True
    algorithm: Literal["md5", "sha256"] = "sha256"
    min_file_size: int = 0
    max_file_size: int | None = None
    include_patterns: list[str] | None = None
    exclude_patterns: list[str] | None = None
    dry_run: bool = True
    trash: bool = True

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        """Validate and return the path for deduplication."""
        return _validate_path(value)


class DedupeExecuteResponse(BaseModel):
    """Response for duplicate file removal."""

    path: str
    removed: list[str]
    dry_run: bool
    stats: dict[str, int]


class SystemStatusResponse(BaseModel):
    """Response for system status endpoint."""

    app: str
    version: str
    environment: str
    disk_total: int
    disk_used: int
    disk_free: int
    active_jobs: int


class ConfigResponse(BaseModel):
    """Response for configuration endpoint."""

    profile: str
    config: dict[str, Any]
    profiles: list[str] = Field(default_factory=list)


class UserCreateRequest(BaseModel):
    """Request body for creating a new user."""

    username: str
    email: EmailStr
    password: str
    full_name: str | None = None

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        """Validate and return the username."""
        value = _validate_text(value, "Username", 32)
        if not _USERNAME_PATTERN.match(value):
            raise ValueError(
                "Username must be 3-32 characters and use letters, numbers, '.', '-', '_'"
            )
        return value

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, value: str | None) -> str | None:
        """Validate and return the full name."""
        if value is None:
            return value
        return _validate_text(value, "Full name", 120)


class UserResponse(BaseModel):
    """Response model for a user resource."""

    id: str
    username: str
    email: EmailStr
    full_name: str | None = None
    is_active: bool
    is_admin: bool
    created_at: datetime
    last_login: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    """Response containing JWT access and refresh tokens."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenRefreshRequest(BaseModel):
    """Request body for token refresh."""

    refresh_token: str


class TokenRevokeRequest(BaseModel):
    """Request body for token revocation."""

    refresh_token: str


class ModelPresetUpdate(BaseModel):
    """Partial update fields for the AI model preset."""

    text_model: str | None = None
    vision_model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    device: str | None = None
    framework: str | None = None


class UpdateSettingsUpdate(BaseModel):
    """Partial update fields for auto-update settings."""

    check_on_startup: bool | None = None
    interval_hours: int | None = None
    include_prereleases: bool | None = None
    repo: str | None = None


class ConfigUpdateRequest(BaseModel):
    """Request body for updating application configuration."""

    profile: str = "default"
    default_methodology: str | None = None
    models: ModelPresetUpdate | None = None
    updates: UpdateSettingsUpdate | None = None
    watcher: dict[str, Any] | None = None
    daemon: dict[str, Any] | None = None
    parallel: dict[str, Any] | None = None
    pipeline: dict[str, Any] | None = None
    events: dict[str, Any] | None = None
    deploy: dict[str, Any] | None = None
    para: dict[str, Any] | None = None
    johnny_decimal: dict[str, Any] | None = None


class StorageStatsResponse(BaseModel):
    """Response for storage statistics endpoint."""

    total_size: int
    organized_size: int
    saved_size: int
    file_count: int
    directory_count: int
    size_by_type: dict[str, int]
    largest_files: list[FileInfo]


class ApiErrorResponse(BaseModel):
    """Standard error response body."""

    error: str
    message: str
    details: Any | None = None
