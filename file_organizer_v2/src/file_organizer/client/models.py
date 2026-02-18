"""Pydantic models for API client responses.

These models mirror the server-side API response shapes and provide
typed deserialization for the client libraries.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Response from the /api/v1/health endpoint."""

    status: str
    version: str
    environment: str
    timestamp: str


class FileInfo(BaseModel):
    """File metadata returned by the files API."""

    path: str
    name: str
    size: int
    created: datetime
    modified: datetime
    file_type: str
    mime_type: Optional[str] = None


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
    mime_type: Optional[str] = None


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
    trashed_path: Optional[str] = None


class ScanResponse(BaseModel):
    """Response from the organize/scan endpoint."""

    input_dir: str
    total_files: int
    counts: dict[str, int]


class OrganizationError(BaseModel):
    """Details for a single file that failed during organization."""

    file: str
    error: str


class OrganizationResultResponse(BaseModel):
    """Result of an organization operation."""

    total_files: int
    processed_files: int
    skipped_files: int
    failed_files: int
    processing_time: float
    organized_structure: dict[str, list[str]]
    errors: list[OrganizationError]


class OrganizeExecuteResponse(BaseModel):
    """Response from the organize/execute endpoint."""

    status: str
    job_id: Optional[str] = None
    result: Optional[OrganizationResultResponse] = None
    error: Optional[str] = None


class JobStatusResponse(BaseModel):
    """Status of a background job."""

    job_id: str
    status: str
    created_at: datetime
    updated_at: datetime
    result: Optional[OrganizationResultResponse] = None
    error: Optional[str] = None


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
    full_name: Optional[str] = None
    is_active: bool
    is_admin: bool
    created_at: datetime
    last_login: Optional[datetime] = None


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
