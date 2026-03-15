"""JSON file-based job persistence for batch processing.

This module provides the JobPersistence class for saving, loading,
listing, and deleting job state files stored as JSON on the local
filesystem. Job data is stored in ~/.file-organizer/jobs/ by default.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from file_organizer.config.path_manager import get_data_dir
from file_organizer.config.path_migration import resolve_legacy_path
from file_organizer.parallel.models import JobState, JobStatus, JobSummary
from file_organizer.utils.atomic_io import fsync_directory

logger = logging.getLogger(__name__)

_DEFAULT_JOBS_DIR = resolve_legacy_path(
    get_data_dir() / "jobs",
    Path.home() / ".file-organizer" / "jobs",
)


class JobPersistence:
    """Manages persistent storage of batch job state as JSON files.

    Each job is stored as a separate JSON file named ``{job_id}.json``
    inside the configured jobs directory.

    Args:
        jobs_dir: Directory where job JSON files are stored.
            Defaults to ``~/.file-organizer/jobs/``.
    """

    def __init__(self, jobs_dir: Path | None = None) -> None:
        """Set up job persistence with the given storage directory."""
        self._jobs_dir = jobs_dir or _DEFAULT_JOBS_DIR

    @property
    def jobs_dir(self) -> Path:
        """Return the directory where job files are stored."""
        return self._jobs_dir

    def _ensure_dir(self) -> None:
        """Create the jobs directory if it does not exist."""
        self._jobs_dir.mkdir(parents=True, exist_ok=True)

    def _job_path(self, job_id: str) -> Path:
        """Return the file path for a given job ID."""
        return self._jobs_dir / f"{job_id}.json"

    def save_job(self, job: JobState) -> None:
        """Save a job state to disk as JSON.

        Creates or overwrites the JSON file for the given job.
        Uses an atomic write strategy (write to temp file then rename) so that
        readers never see a partially written file.

        Args:
            job: The job state to persist.
        """
        self._ensure_dir()
        path = self._job_path(job.id)
        data = job.to_dict()

        # Atomic write: write to temp file, fsync, rename, then fsync directory
        temp_path = path.with_suffix(".tmp")
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                f.write(json.dumps(data, indent=2, default=str))
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, path)
            fsync_directory(path)
            logger.debug("Saved job %s to %s", job.id, path)
        except Exception:
            # Clean up temp file if something went wrong
            if temp_path.exists():
                temp_path.unlink()
            raise

    def load_job(self, job_id: str) -> JobState | None:
        """Load a job state from disk.

        Args:
            job_id: The unique identifier of the job to load.

        Returns:
            The deserialized JobState, or None if the file does not exist.
        """
        path = self._job_path(job_id)
        if not path.exists():
            logger.debug("Job file not found: %s", path)
            return None

        try:
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw)
            return JobState.from_dict(data)
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            logger.warning("Failed to load job %s: %s", job_id, exc, exc_info=True)
            return None

    def list_jobs(self, status: JobStatus | None = None) -> list[JobSummary]:
        """List all persisted jobs, optionally filtering by status.

        Args:
            status: If provided, only return jobs with this status.

        Returns:
            List of job summaries sorted by creation time (newest first).
        """
        if not self._jobs_dir.exists():
            return []

        summaries: list[JobSummary] = []
        for path in self._jobs_dir.glob("*.json"):
            try:
                raw = path.read_text(encoding="utf-8")
                data = json.loads(raw)
                job = JobState.from_dict(data)
                if status is not None and job.status != status:
                    continue
                summaries.append(JobSummary.from_job_state(job))
            except (json.JSONDecodeError, KeyError, ValueError) as exc:
                logger.warning("Skipping invalid job file %s: %s", path, exc, exc_info=True)
                continue

        summaries.sort(key=lambda s: s.created, reverse=True)
        return summaries

    def delete_job(self, job_id: str) -> bool:
        """Delete a persisted job file.

        Args:
            job_id: The unique identifier of the job to delete.

        Returns:
            True if the file was deleted, False if it did not exist.
        """
        path = self._job_path(job_id)
        if path.exists():
            path.unlink()
            logger.debug("Deleted job file: %s", path)
            return True
        logger.debug("Job file not found for deletion: %s", path)
        return False

    def job_exists(self, job_id: str) -> bool:
        """Check whether a job file exists on disk.

        Args:
            job_id: The unique identifier of the job.

        Returns:
            True if the job file exists.
        """
        return self._job_path(job_id).exists()
