"""Repository for :class:`~file_organizer.api.db_models.OrganizationJob` CRUD."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from file_organizer.api.db_models import OrganizationJob


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

        Returns:
            The newly created :class:`OrganizationJob` instance.
        """
        job = OrganizationJob()
        job.input_dir = input_dir
        job.output_dir = output_dir
        job.workspace_id = workspace_id
        job.owner_id = owner_id
        job.job_type = job_type
        job.methodology = methodology
        job.dry_run = dry_run
        session.add(job)
        session.flush()
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
    ) -> OrganizationJob | None:
        """Transition a job to a new status.

        Args:
            session: Active SQLAlchemy session.
            job_id: Primary key of the job.
            status: New status string.
            error: Optional error message (typically set when status is ``"failed"``).

        Returns:
            The updated :class:`OrganizationJob`, or ``None`` if not found.
        """
        job = session.get(OrganizationJob, job_id)
        if job is None:
            return None
        job.status = status
        job.error = error
        job.updated_at = datetime.now(UTC)
        session.flush()
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

        job.updated_at = datetime.now(UTC)
        session.flush()
        return job
