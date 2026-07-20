"""Pydantic models for API client responses.

These models mirror the server-side API response shapes and provide
typed deserialization for the client libraries.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Response from the /api/v1/health endpoint."""

    status: str
    readiness: str
    version: str
    ollama: bool
    uptime: float


class FileInfo(BaseModel):
    """File metadata returned by the files API."""

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


class FileContentResponse(BaseModel):
    """File content returned by the read endpoint."""

    path: str
    content: str
    encoding: str
    truncated: bool
    size: int
    mime_type: str | None = None


class MoveFileResponse(BaseModel):
    """Response from file move operation."""

    source: str
    destination: str
    moved: bool
    dry_run: bool


class DeleteFileResponse(BaseModel):
    """Response from file delete operation."""

    path: str
    deleted: bool
    dry_run: bool
    trashed_path: str | None = None


class ScanResponse(BaseModel):
    """Response from the organize/scan endpoint."""

    input_dir: str
    total_files: int
    counts: dict[str, int]


class OrganizationError(BaseModel):
    """Details for a single file that failed during organization."""

    file: str
    error: str


class SourceFingerprintPayload(BaseModel):
    """Source fingerprint captured when a plan is reviewed."""

    size: int
    mtime_ns: int
    sha256: str | None = None


class OrganizationOperationPayload(BaseModel):
    """Executable organization operation."""

    operation_id: str
    source_path: str
    destination_path: str
    operation_type: Literal["copy", "hardlink"]
    collision_action: Literal["create", "skip_existing", "rename_with_counter"]
    status: Literal["ready", "skipped", "error"]
    folder_name: str
    file_name: str
    description: str = ""
    fingerprint: SourceFingerprintPayload | None = None
    error: str | None = None


class OrganizationPlanPayload(BaseModel):
    """Executable organization plan."""

    plan_id: str
    schema_version: int
    input_path: str
    output_path: str
    created_at: str
    skip_existing: bool
    use_hardlinks: bool
    total_files: int
    processed_files: int
    skipped_files: int
    failed_files: int
    deduplicated_files: int
    operations: list[OrganizationOperationPayload] = Field(default_factory=list)
    errors: list[tuple[str, str]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class OrganizationResultResponse(BaseModel):
    """Result of an organization operation."""

    total_files: int
    processed_files: int
    skipped_files: int
    failed_files: int
    deduplicated_files: int = 0
    processing_time: float
    organized_structure: dict[str, list[str]]
    errors: list[OrganizationError]
    plan: OrganizationPlanPayload | None = None


class OrganizeExecuteResponse(BaseModel):
    """Response from the organize/execute endpoint."""

    status: str
    job_id: str | None = None
    result: OrganizationResultResponse | None = None
    error: str | None = None


class JobStatusResponse(BaseModel):
    """Status of a background job."""

    job_id: str
    status: str
    created_at: datetime
    updated_at: datetime
    result: OrganizationResultResponse | None = None
    error: str | None = None


class TokenResponse(BaseModel):
    """Authentication token pair."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    """Registered user information."""

    id: str
    username: str
    email: str
    full_name: str | None = None
    is_active: bool
    is_admin: bool
    created_at: datetime
    last_login: datetime | None = None


class SystemStatusResponse(BaseModel):
    """Response from the system/status endpoint."""

    app: str
    version: str
    environment: str
    disk_total: int
    disk_used: int
    disk_free: int
    active_jobs: int


class ConfigResponse(BaseModel):
    """Response from the system/config endpoint."""

    profile: str
    config: dict[str, Any]
    profiles: list[str]


class StorageStatsResponse(BaseModel):
    """Response from the system/stats endpoint."""

    total_size: int
    organized_size: int
    saved_size: int
    file_count: int
    directory_count: int
    size_by_type: dict[str, int]
    largest_files: list[FileInfo]


class DedupeScanResponse(BaseModel):
    """Response from the dedupe/scan endpoint."""

    path: str
    duplicates: list[dict[str, Any]]
    stats: dict[str, int]


class DedupePreviewResponse(BaseModel):
    """Response from the dedupe/preview endpoint."""

    path: str
    preview: list[dict[str, Any]]
    stats: dict[str, int]


class DedupeExecuteResponse(BaseModel):
    """Response from the dedupe/execute endpoint."""

    path: str
    removed: list[str]
    dry_run: bool
    stats: dict[str, int]
