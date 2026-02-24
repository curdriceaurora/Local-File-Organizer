"""Data models for progress persistence and job resumption.

This module defines the core data structures for tracking batch job state,
checkpoints, and job summaries used by the persistence and resume system.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from file_organizer._compat import StrEnum


class JobStatus(StrEnum):
    """Status of a batch processing job."""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class JobState:
    """Full state of a batch processing job.

    Attributes:
        id: Unique identifier for the job.
        status: Current status of the job.
        created: When the job was created (UTC).
        updated: When the job was last updated (UTC).
        total_files: Total number of files in the batch.
        completed_files: Number of files successfully processed.
        failed_files: Number of files that failed processing.
        config: Optional configuration dictionary for the job.
        error: Error message if the job failed.
    """

    id: str
    status: JobStatus = JobStatus.PENDING
    created: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated: datetime = field(default_factory=lambda: datetime.now(UTC))
    total_files: int = 0
    completed_files: int = 0
    failed_files: int = 0
    config: dict[str, object] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Serialize job state to a dictionary suitable for JSON storage."""
        return {
            "id": self.id,
            "status": str(self.status),
            "created": self.created.isoformat(),
            "updated": self.updated.isoformat(),
            "total_files": self.total_files,
            "completed_files": self.completed_files,
            "failed_files": self.failed_files,
            "config": self.config,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> JobState:
        """Deserialize a job state from a dictionary."""
        return cls(
            id=str(data["id"]),
            status=JobStatus(str(data["status"])),
            created=datetime.fromisoformat(str(data["created"])),
            updated=datetime.fromisoformat(str(data["updated"])),
            total_files=int(data.get("total_files", 0)),  # type: ignore[arg-type]
            completed_files=int(data.get("completed_files", 0)),  # type: ignore[arg-type]
            failed_files=int(data.get("failed_files", 0)),  # type: ignore[arg-type]
            config=dict(data.get("config", {})),  # type: ignore[arg-type]
            error=str(data["error"]) if data.get("error") is not None else None,
        )


@dataclass
class JobSummary:
    """Lightweight summary of a job for listing purposes.

    Attributes:
        id: Unique identifier for the job.
        status: Current status of the job.
        progress_percent: Completion percentage (0-100).
        created: When the job was created (UTC).
    """

    id: str
    status: JobStatus
    progress_percent: float
    created: datetime

    @classmethod
    def from_job_state(cls, job: JobState) -> JobSummary:
        """Create a summary from a full job state."""
        if job.total_files > 0:
            progress = (job.completed_files / job.total_files) * 100.0
        else:
            progress = 0.0
        return cls(
            id=job.id,
            status=job.status,
            progress_percent=round(progress, 1),
            created=job.created,
        )


@dataclass
class Checkpoint:
    """Checkpoint state for resumable batch processing.

    Stores which files have been completed, which are still pending,
    and file hashes for detecting modifications between runs.

    Attributes:
        job_id: Identifier of the associated job.
        completed_paths: Paths of files that have been processed.
        pending_paths: Paths of files still awaiting processing.
        file_hashes: Mapping from file path string to its content hash.
        last_updated: When the checkpoint was last updated (UTC).
    """

    job_id: str
    completed_paths: list[Path] = field(default_factory=list)
    pending_paths: list[Path] = field(default_factory=list)
    file_hashes: dict[str, str] = field(default_factory=dict)
    last_updated: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, object]:
        """Serialize checkpoint to a dictionary suitable for JSON storage."""
        return {
            "job_id": self.job_id,
            "completed_paths": [str(p) for p in self.completed_paths],
            "pending_paths": [str(p) for p in self.pending_paths],
            "file_hashes": self.file_hashes,
            "last_updated": self.last_updated.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> Checkpoint:
        """Deserialize a checkpoint from a dictionary."""
        completed_raw = data.get("completed_paths", [])
        pending_raw = data.get("pending_paths", [])
        hashes_raw = data.get("file_hashes", {})

        return cls(
            job_id=str(data["job_id"]),
            completed_paths=[Path(p) for p in completed_raw],  # type: ignore[union-attr]
            pending_paths=[Path(p) for p in pending_raw],  # type: ignore[union-attr]
            file_hashes=dict(hashes_raw),  # type: ignore[arg-type]
            last_updated=datetime.fromisoformat(str(data["last_updated"])),
        )
