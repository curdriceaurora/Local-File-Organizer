"""
Resumable batch processing with checkpoint support.

This module provides the ResumableProcessor class that wraps ParallelProcessor
with automatic checkpointing and resume capabilities. Interrupted batch jobs
can be resumed from where they left off, with file hash verification to detect
modifications between runs.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from file_organizer.parallel.checkpoint import CheckpointManager
from file_organizer.parallel.config import ParallelConfig
from file_organizer.parallel.models import Checkpoint, JobState, JobStatus
from file_organizer.parallel.persistence import JobPersistence
from file_organizer.parallel.processor import ParallelProcessor
from file_organizer.parallel.result import BatchResult, FileResult

logger = logging.getLogger(__name__)


class ResumableProcessor:
    """
    Wraps ParallelProcessor with checkpoint and resume logic.

    Tracks job state via JobPersistence and file-level progress via
    CheckpointManager. When processing is interrupted, a subsequent
    call to resume_job will skip already-completed files (after verifying
    their content hashes have not changed).

    Args:
        config: Parallel processing configuration.
        persistence: JobPersistence instance for storing job state.
        checkpoint_mgr: CheckpointManager instance for file-level tracking.
    """

    def __init__(
        self,
        config: ParallelConfig | None = None,
        persistence: JobPersistence | None = None,
        checkpoint_mgr: CheckpointManager | None = None,
    ) -> None:
        self._config = config or ParallelConfig()
        self._processor = ParallelProcessor(config=self._config)
        self._persistence = persistence or JobPersistence()
        self._checkpoint_mgr = checkpoint_mgr or CheckpointManager()

    def process_with_resume(
        self,
        files: list[Path],
        process_fn: Callable[[Path], Any],
        job_id: str | None = None,
    ) -> BatchResult:
        """
        Process a batch of files with automatic checkpointing.

        Creates a new job (or uses the provided job_id), then processes
        files in parallel. After each file completes, the checkpoint is
        updated so the job can be resumed if interrupted.

        Args:
            files: List of file paths to process.
            process_fn: Function to apply to each file path.
            job_id: Optional identifier for the job. Auto-generated if None.

        Returns:
            BatchResult with aggregated results.
        """
        if job_id is None:
            job_id = str(uuid.uuid4())

        # Create job state
        now = datetime.now(timezone.utc)
        job = JobState(
            id=job_id,
            status=JobStatus.RUNNING,
            created=now,
            updated=now,
            total_files=len(files),
        )
        self._persistence.save_job(job)

        # Create initial checkpoint
        checkpoint = self._checkpoint_mgr.create_checkpoint(
            job_id=job_id,
            completed_files=[],
            pending_files=files,
        )

        # Process with per-file checkpoint updates
        result = self._process_and_checkpoint(
            job=job,
            files=files,
            process_fn=process_fn,
            checkpoint=checkpoint,
        )
        return result

    def resume_job(
        self,
        job_id: str,
        process_fn: Callable[[Path], Any],
    ) -> BatchResult:
        """
        Resume an interrupted job from its last checkpoint.

        Loads the job state and checkpoint, filters out already-completed
        files (verifying their hashes have not changed), and processes
        only the remaining files.

        Files whose content has changed since the checkpoint are re-added
        to the pending list for reprocessing.

        Args:
            job_id: Identifier of the job to resume.
            process_fn: Function to apply to each pending file.

        Returns:
            BatchResult combining previous and new results.

        Raises:
            ValueError: If the job or checkpoint cannot be found.
        """
        job = self._persistence.load_job(job_id)
        if job is None:
            raise ValueError(f"Job not found: {job_id}")

        checkpoint = self._checkpoint_mgr.load_checkpoint(job_id)
        if checkpoint is None:
            raise ValueError(f"Checkpoint not found for job: {job_id}")

        # Determine which files need (re)processing
        files_to_process: list[Path] = list(checkpoint.pending_paths)

        # Check completed files for modifications
        modified_files: list[Path] = []
        for path in checkpoint.completed_paths:
            if self._checkpoint_mgr.has_file_changed(checkpoint, path):
                modified_files.append(path)
                logger.info("File modified since checkpoint, reprocessing: %s", path)

        files_to_process.extend(modified_files)

        # Remove modified files from completed list in checkpoint
        still_completed = [
            p for p in checkpoint.completed_paths if p not in modified_files
        ]

        # Update job state
        job.status = JobStatus.RUNNING
        job.updated = datetime.now(timezone.utc)
        self._persistence.save_job(job)

        # Update checkpoint to reflect re-queued files
        checkpoint = self._checkpoint_mgr.create_checkpoint(
            job_id=job_id,
            completed_files=still_completed,
            pending_files=files_to_process,
        )

        if not files_to_process:
            # Nothing to process, job is already complete
            job.status = JobStatus.COMPLETED
            job.updated = datetime.now(timezone.utc)
            self._persistence.save_job(job)
            return BatchResult(
                total=job.total_files,
                succeeded=len(still_completed),
                failed=0,
                results=[],
            )

        # Process remaining files
        result = self._process_and_checkpoint(
            job=job,
            files=files_to_process,
            process_fn=process_fn,
            checkpoint=checkpoint,
        )

        # Adjust totals to reflect the full job
        result = BatchResult(
            total=job.total_files,
            succeeded=len(still_completed) + result.succeeded,
            failed=result.failed,
            results=result.results,
            total_duration_ms=result.total_duration_ms,
            files_per_second=result.files_per_second,
        )
        return result

    def _process_and_checkpoint(
        self,
        job: JobState,
        files: list[Path],
        process_fn: Callable[[Path], Any],
        checkpoint: Checkpoint | None = None,
    ) -> BatchResult:
        """
        Process files using the parallel processor, checkpointing each result.

        Updates the job state and checkpoint after each file completes.
        On completion, marks the job as COMPLETED or FAILED depending on results.

        Args:
            job: The current job state.
            files: Files to process in this run.
            process_fn: Processing function.
            checkpoint: Optional in-memory checkpoint object to update.
                Batched persistence means in-memory updates between save intervals
                can be lost if the process crashes.

        Returns:
            BatchResult for this processing run.
        """
        results: list[FileResult] = []

        # Load checkpoint if not provided (fallback)
        if checkpoint is None:
            checkpoint = self._checkpoint_mgr.load_checkpoint(job.id)

        last_save_time = time.monotonic()
        files_since_save = 0

        try:
            for file_result in self._processor.process_batch_iter(
                files, process_fn
            ):
                results.append(file_result)

                if file_result.success:
                    # Update in-memory state
                    if checkpoint:
                        self._checkpoint_mgr.update_checkpoint_state(
                            checkpoint, file_result.path
                        )
                    job.completed_files += 1
                else:
                    job.failed_files += 1

                job.updated = datetime.now(timezone.utc)

                # Batched persistence: save every 5 seconds or 50 files
                files_since_save += 1
                now = time.monotonic()
                if (now - last_save_time) >= 5.0 or files_since_save >= 50:
                    self._persistence.save_job(job)
                    if checkpoint:
                        self._checkpoint_mgr.save_checkpoint(checkpoint)
                    last_save_time = now
                    files_since_save = 0

        except Exception as exc:
            logger.error("Job %s failed with error: %s", job.id, exc)
            job.status = JobStatus.FAILED
            job.error = str(exc)
            job.updated = datetime.now(timezone.utc)
            self._persistence.save_job(job)
            if checkpoint:
                self._checkpoint_mgr.save_checkpoint(checkpoint)
            raise

        # Determine final status
        if job.failed_files > 0 and job.completed_files == 0:
            job.status = JobStatus.FAILED
        else:
            job.status = JobStatus.COMPLETED
        job.updated = datetime.now(timezone.utc)
        self._persistence.save_job(job)
        if checkpoint:
            self._checkpoint_mgr.save_checkpoint(checkpoint)

        succeeded = sum(1 for r in results if r.success)
        failed = sum(1 for r in results if not r.success)

        return BatchResult(
            total=len(files),
            succeeded=succeeded,
            failed=failed,
            results=results,
        )
