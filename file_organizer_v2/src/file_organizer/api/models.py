"""Pydantic models for API requests and responses."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class FileInfo(BaseModel):
    path: str
    name: str
    size: int
    created: datetime
    modified: datetime
    file_type: str
    mime_type: str | None = None


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
    mime_type: str | None = None


class MoveFileRequest(BaseModel):
    source: str
    destination: str
    overwrite: bool = False
    dry_run: bool = False


class MoveFileResponse(BaseModel):
    source: str
    destination: str
    moved: bool
    dry_run: bool


class DeleteFileRequest(BaseModel):
    path: str
    permanent: bool = False
    dry_run: bool = False


class DeleteFileResponse(BaseModel):
    path: str
    deleted: bool
    dry_run: bool
    trashed_path: str | None = None


class ScanRequest(BaseModel):
    input_dir: str
    recursive: bool = True
    include_hidden: bool = False


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
    job_id: str | None = None
    result: OrganizationResultResponse | None = None
    error: str | None = None


class JobStatusResponse(BaseModel):
    job_id: str
    status: Literal["queued", "running", "completed", "failed"]
    created_at: datetime
    updated_at: datetime
    result: OrganizationResultResponse | None = None
    error: str | None = None


class DedupeScanRequest(BaseModel):
    path: str
    recursive: bool = True
    algorithm: Literal["md5", "sha256"] = "sha256"
    min_file_size: int = 0
    max_file_size: int | None = None
    include_patterns: list[str] | None = None
    exclude_patterns: list[str] | None = None


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
    max_file_size: int | None = None
    include_patterns: list[str] | None = None
    exclude_patterns: list[str] | None = None
    dry_run: bool = True
    trash: bool = True


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


class ModelPresetUpdate(BaseModel):
    text_model: str | None = None
    vision_model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    device: str | None = None
    framework: str | None = None


class UpdateSettingsUpdate(BaseModel):
    check_on_startup: bool | None = None
    interval_hours: int | None = None
    include_prereleases: bool | None = None
    repo: str | None = None


class ConfigUpdateRequest(BaseModel):
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
    details: Any | None = None
