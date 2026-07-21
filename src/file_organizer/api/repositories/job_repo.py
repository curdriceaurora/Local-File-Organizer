"""Repository for :class:`~file_organizer.api.db_models.OrganizationJob` CRUD."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from file_organizer.api.db_models import OrganizationJob
from file_organizer.core.errors import DomainError, DomainErrorCode
from file_organizer.core.lifecycle import (
    LEGAL_JOB_TRANSITIONS,
    JobStatus,
    RecoveryAction,
)


class JobRepository:
    """Data-access layer for organization jobs."""

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    @staticmethod
    def create(
        session: Session,
        input_dir: str,
        output_dir: str,
        *,
        workspace_id: str | None = None,
        owner_id: str | None = None,
        job_type: str = "organize",
        methodology: str = "content_based",
        dry_run: bool = False,
        idempotency_key: str | None = None,
        scheduled_for: datetime | None = None,
    ) -> OrganizationJob:
        """Create and persist a new organization job.

        Args:
            session: Active SQLAlchemy session.
            input_dir: Source directory for the job.
            output_dir: Destination directory for the job.
            workspace_id: Optional workspace foreign key.
            owner_id: Optional user foreign key.
            job_type: Job type label (default ``"organize"``).
            methodology: Organization methodology name.
            dry_run: Whether the job is a dry run.
            idempotency_key: Optional caller key used to return an existing job.
            scheduled_for: Optional one-shot execution time.

        Returns:
            The newly created :class:`OrganizationJob` instance.
        """
        if idempotency_key is not None:
            existing = (
                session.query(OrganizationJob)
                .filter(
                    OrganizationJob.job_type == job_type,
                    OrganizationJob.idempotency_key == idempotency_key,
                )
                .one_or_none()
            )
            if existing is not None:
                return existing

        job = OrganizationJob()
        job.input_dir = input_dir
        job.output_dir = output_dir
        job.workspace_id = workspace_id
        job.owner_id = owner_id
        job.job_type = job_type
        job.methodology = methodology
        job.dry_run = dry_run
        job.status = "scheduled" if scheduled_for is not None else "queued"
        job.idempotency_key = idempotency_key
        job.scheduled_for = scheduled_for
        job.revision = 0
        job.recovery_action = RecoveryAction.NONE.value
        if idempotency_key is None:
            session.add(job)
            session.flush()
            return job

        try:
            # Isolate the insert so a concurrent unique-key winner does not
            # invalidate the caller's outer transaction.
            with session.begin_nested():
                session.add(job)
                session.flush()
        except IntegrityError:
            existing = (
                session.query(OrganizationJob)
                .filter(
                    OrganizationJob.job_type == job_type,
                    OrganizationJob.idempotency_key == idempotency_key,
                )
                .one_or_none()
            )
            if existing is None:
                raise
            return existing
        return job

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    @staticmethod
    def get_by_id(session: Session, job_id: str) -> OrganizationJob | None:
        """Return a single job by primary key, or ``None``."""
        return session.get(OrganizationJob, job_id)

    @staticmethod
    def list_jobs(
        session: Session,
        *,
        owner_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[OrganizationJob]:
        """Return jobs matching the optional filters, newest first.

        Args:
            session: Active SQLAlchemy session.
            owner_id: Filter to jobs owned by this user.
            status: Filter to jobs with this status string.
            limit: Maximum number of results (default 50).

        Returns:
            A list of :class:`OrganizationJob` instances.
        """
        query = session.query(OrganizationJob)
        if owner_id is not None:
            query = query.filter(OrganizationJob.owner_id == owner_id)
        if status is not None:
            query = query.filter(OrganizationJob.status == status)
        return query.order_by(OrganizationJob.created_at.desc()).limit(limit).all()

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    @staticmethod
    def update_status(
        session: Session,
        job_id: str,
        status: str,
        error: str | None = None,
        *,
        expected_revision: int | None = None,
        error_code: str | None = None,
        error_retryable: bool = False,
        error_details: dict[str, object] | None = None,
        transaction_id: str | None = None,
        recovery_action: RecoveryAction | str | None = None,
    ) -> OrganizationJob | None:
        """Transition a job to a new status.

        Args:
            session: Active SQLAlchemy session.
            job_id: Primary key of the job.
            status: New status string.
            error: Optional error message (typically set when status is ``"failed"``).
            expected_revision: Optional compare-and-swap revision guard.
            error_code: Stable domain error code associated with ``error``.
            error_retryable: Whether retrying the same operation may succeed.
            error_details: Structured transport-neutral error evidence.
            transaction_id: History transaction associated with execution.
            recovery_action: Canonical next recovery action.

        Returns:
            The updated :class:`OrganizationJob`, or ``None`` if not found.
        """
        job = session.get(OrganizationJob, job_id)
        if job is None:
            return None
        current = JobStatus(job.status)
        target = JobStatus(status)
        if target == current or target not in LEGAL_JOB_TRANSITIONS[current]:
            raise DomainError(
                DomainErrorCode.INVALID_JOB_TRANSITION,
                f"Cannot transition job from {current.value} to {target.value}.",
                details={"from": current.value, "to": target.value},
            )
        if expected_revision is not None and expected_revision != job.revision:
            raise DomainError(
                DomainErrorCode.STALE_JOB_REVISION,
                "Job state changed before this mutation could be applied.",
                retryable=True,
                details={"expected": expected_revision, "actual": job.revision},
            )
        job.status = target.value
        job.error = error
        job.error_code = error_code
        job.error_retryable = error_retryable
        job.error_details_json = (
            json.dumps(error_details, sort_keys=True) if error_details is not None else None
        )
        job.transaction_id = transaction_id or job.transaction_id
        if recovery_action is not None:
            job.recovery_action = RecoveryAction(recovery_action).value
        elif target in {JobStatus.PARTIAL, JobStatus.FAILED}:
            job.recovery_action = RecoveryAction.RETRY.value
        elif target == JobStatus.RECOVERY_REQUIRED:
            job.recovery_action = RecoveryAction.MANUAL.value
        else:
            job.recovery_action = RecoveryAction.NONE.value
        prior_revision = job.revision
        job.revision = prior_revision + 1
        job.updated_at = datetime.now(UTC)
        try:
            session.flush()
        except StaleDataError as exc:
            raise DomainError(
                DomainErrorCode.STALE_JOB_REVISION,
                "Job state changed before this mutation could be applied.",
                retryable=True,
                details={"expected": prior_revision},
            ) from exc
        return job

    @staticmethod
    def update_result(
        session: Session,
        job_id: str,
        *,
        total_files: int | None = None,
        processed_files: int | None = None,
        failed_files: int | None = None,
        skipped_files: int | None = None,
        result_json: str | None = None,
    ) -> OrganizationJob | None:
        """Update result counters and/or the JSON result blob.

        Only non-``None`` arguments are applied.

        Returns:
            The updated :class:`OrganizationJob`, or ``None`` if not found.
        """
        job = session.get(OrganizationJob, job_id)
        if job is None:
            return None

        if total_files is not None:
            job.total_files = total_files
        if processed_files is not None:
            job.processed_files = processed_files
        if failed_files is not None:
            job.failed_files = failed_files
        if skipped_files is not None:
            job.skipped_files = skipped_files
        if result_json is not None:
            job.result_json = result_json

        prior_revision = job.revision
        job.revision = prior_revision + 1
        job.updated_at = datetime.now(UTC)
        try:
            session.flush()
        except StaleDataError as exc:
            raise DomainError(
                DomainErrorCode.STALE_JOB_REVISION,
                "Job state changed before this mutation could be applied.",
                retryable=True,
                details={"expected": prior_revision},
            ) from exc
        return job
