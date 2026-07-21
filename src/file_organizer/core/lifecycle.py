"""Canonical job, scheduling, cancellation, and recovery contracts."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any

from file_organizer._compat import StrEnum
from file_organizer.core.errors import DomainError, DomainErrorCode


class JobStatus(StrEnum):
    """Stable lifecycle states exposed by every organization adapter."""

    SCHEDULED = "scheduled"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RECOVERY_REQUIRED = "recovery_required"
    ROLLING_BACK = "rolling_back"
    ROLLED_BACK = "rolled_back"


class RecoveryAction(StrEnum):
    """Canonical next action after incomplete or failed work."""

    NONE = "none"
    RETRY = "retry"
    ROLLBACK = "rollback"
    MANUAL = "manual"


TERMINAL_JOB_STATUSES = frozenset(
    {
        JobStatus.COMPLETED,
        JobStatus.PARTIAL,
        JobStatus.FAILED,
        JobStatus.CANCELLED,
        JobStatus.RECOVERY_REQUIRED,
        JobStatus.ROLLED_BACK,
    }
)

ACTIVE_JOB_STATUSES = frozenset(
    {
        JobStatus.SCHEDULED,
        JobStatus.QUEUED,
        JobStatus.RUNNING,
        JobStatus.ROLLING_BACK,
    }
)

LEGAL_JOB_TRANSITIONS: dict[JobStatus, frozenset[JobStatus]] = {
    JobStatus.SCHEDULED: frozenset({JobStatus.RUNNING, JobStatus.CANCELLED, JobStatus.FAILED}),
    JobStatus.QUEUED: frozenset(
        {
            JobStatus.RUNNING,
            JobStatus.COMPLETED,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
        }
    ),
    JobStatus.RUNNING: frozenset(
        {
            JobStatus.COMPLETED,
            JobStatus.PARTIAL,
            JobStatus.FAILED,
            JobStatus.RECOVERY_REQUIRED,
        }
    ),
    JobStatus.PARTIAL: frozenset(
        {JobStatus.QUEUED, JobStatus.ROLLING_BACK, JobStatus.RECOVERY_REQUIRED}
    ),
    JobStatus.FAILED: frozenset(
        {JobStatus.QUEUED, JobStatus.ROLLING_BACK, JobStatus.RECOVERY_REQUIRED}
    ),
    JobStatus.RECOVERY_REQUIRED: frozenset(
        {JobStatus.QUEUED, JobStatus.ROLLING_BACK, JobStatus.FAILED}
    ),
    JobStatus.COMPLETED: frozenset({JobStatus.ROLLING_BACK}),
    JobStatus.ROLLING_BACK: frozenset(
        {JobStatus.ROLLED_BACK, JobStatus.RECOVERY_REQUIRED, JobStatus.FAILED}
    ),
    JobStatus.CANCELLED: frozenset(),
    JobStatus.ROLLED_BACK: frozenset(),
}


@dataclass(frozen=True, slots=True)
class JobProgress:
    """Monotonic progress counters for one job revision."""

    total: int = 0
    completed: int = 0
    failed: int = 0
    skipped: int = 0

    def __post_init__(self) -> None:
        """Reject negative or internally inconsistent counters."""
        counters = (self.total, self.completed, self.failed, self.skipped)
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in counters
        ):
            raise ValueError("Job progress counters must be non-negative integers")
        if self.completed + self.failed + self.skipped > self.total:
            raise ValueError("Job progress counters exceed total")

    @property
    def percent(self) -> float:
        """Return completion progress as a stable percentage."""
        if self.total == 0:
            return 0.0
        done = self.completed + self.failed + self.skipped
        return round((done / self.total) * 100.0, 1)


@dataclass(frozen=True, slots=True)
class JobSnapshot:
    """Immutable serialized state for background organization work."""

    job_id: str
    job_type: str
    status: JobStatus
    created_at: datetime
    updated_at: datetime
    revision: int = 0
    idempotency_key: str | None = None
    scheduled_for: datetime | None = None
    progress: JobProgress = field(default_factory=JobProgress)
    transaction_id: str | None = None
    recovery_action: RecoveryAction = RecoveryAction.NONE
    result: dict[str, Any] | None = None
    error: DomainError | None = None

    def __post_init__(self) -> None:
        """Validate scheduling and timestamp invariants."""
        if not self.job_id or not self.job_type:
            raise ValueError("job_id and job_type must not be empty")
        if self.revision < 0:
            raise ValueError("revision must be non-negative")
        if self.created_at.tzinfo is None or self.updated_at.tzinfo is None:
            raise ValueError("job timestamps must be timezone-aware")
        if self.scheduled_for is not None and self.scheduled_for.tzinfo is None:
            raise ValueError("scheduled_for must be timezone-aware")
        if self.status == JobStatus.SCHEDULED and self.scheduled_for is None:
            raise ValueError("scheduled jobs require scheduled_for")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must not precede created_at")

    def to_dict(self) -> dict[str, Any]:
        """Serialize the lifecycle snapshot for persistence or transport."""
        return {
            "job_id": self.job_id,
            "job_type": self.job_type,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "revision": self.revision,
            "idempotency_key": self.idempotency_key,
            "scheduled_for": (
                self.scheduled_for.isoformat() if self.scheduled_for is not None else None
            ),
            "progress": {
                "total": self.progress.total,
                "completed": self.progress.completed,
                "failed": self.progress.failed,
                "skipped": self.progress.skipped,
                "percent": self.progress.percent,
            },
            "transaction_id": self.transaction_id,
            "recovery_action": self.recovery_action.value,
            "result": self.result,
            "error": self.error.to_dict() if self.error is not None else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JobSnapshot:
        """Restore a validated snapshot from persisted canonical state."""
        progress = dict(data.get("progress", {}))
        raw_error = data.get("error")
        return cls(
            job_id=str(data["job_id"]),
            job_type=str(data["job_type"]),
            status=JobStatus(data["status"]),
            created_at=datetime.fromisoformat(str(data["created_at"])),
            updated_at=datetime.fromisoformat(str(data["updated_at"])),
            revision=int(data.get("revision", 0)),
            idempotency_key=(
                str(data["idempotency_key"]) if data.get("idempotency_key") is not None else None
            ),
            scheduled_for=(
                datetime.fromisoformat(str(data["scheduled_for"]))
                if data.get("scheduled_for") is not None
                else None
            ),
            progress=JobProgress(
                total=int(progress.get("total", 0)),
                completed=int(progress.get("completed", 0)),
                failed=int(progress.get("failed", 0)),
                skipped=int(progress.get("skipped", 0)),
            ),
            transaction_id=(
                str(data["transaction_id"]) if data.get("transaction_id") is not None else None
            ),
            recovery_action=RecoveryAction(data.get("recovery_action", "none")),
            result=dict(data["result"]) if data.get("result") is not None else None,
            error=DomainError.from_dict(dict(raw_error)) if raw_error is not None else None,
        )


def create_job_snapshot(
    *,
    job_id: str,
    job_type: str,
    now: datetime | None = None,
    idempotency_key: str | None = None,
    scheduled_for: datetime | None = None,
) -> JobSnapshot:
    """Create a queued or one-shot scheduled lifecycle snapshot."""
    timestamp = now or datetime.now(UTC)
    if scheduled_for is not None and scheduled_for.tzinfo is None:
        raise ValueError("scheduled_for must be timezone-aware")
    status = JobStatus.SCHEDULED if scheduled_for is not None else JobStatus.QUEUED
    return JobSnapshot(
        job_id=job_id,
        job_type=job_type,
        status=status,
        created_at=timestamp,
        updated_at=timestamp,
        idempotency_key=idempotency_key,
        scheduled_for=scheduled_for,
    )


def transition_job(
    job: JobSnapshot,
    target: JobStatus | str,
    *,
    now: datetime | None = None,
    expected_revision: int | None = None,
    progress: JobProgress | None = None,
    transaction_id: str | None = None,
    recovery_action: RecoveryAction | str | None = None,
    result: dict[str, Any] | None = None,
    error: DomainError | None = None,
) -> JobSnapshot:
    """Apply one legal compare-and-swap lifecycle transition."""
    target_status = JobStatus(target)
    if expected_revision is not None and expected_revision != job.revision:
        raise DomainError(
            DomainErrorCode.STALE_JOB_REVISION,
            "Job state changed before this mutation could be applied.",
            retryable=True,
            details={"expected": expected_revision, "actual": job.revision},
        )
    if target_status == job.status:
        raise DomainError(
            DomainErrorCode.INVALID_JOB_TRANSITION,
            f"Duplicate job transition to {target_status.value} is not allowed.",
            details={"from": job.status.value, "to": target_status.value},
        )
    if target_status not in LEGAL_JOB_TRANSITIONS[job.status]:
        raise DomainError(
            DomainErrorCode.INVALID_JOB_TRANSITION,
            f"Cannot transition job from {job.status.value} to {target_status.value}.",
            details={"from": job.status.value, "to": target_status.value},
        )
    next_progress = progress or job.progress
    if (
        next_progress.completed < job.progress.completed
        or next_progress.failed < job.progress.failed
        or next_progress.skipped < job.progress.skipped
    ):
        raise DomainError(
            DomainErrorCode.CONFLICT,
            "Job progress cannot move backwards.",
        )
    next_recovery = (
        RecoveryAction(recovery_action)
        if recovery_action is not None
        else _default_recovery_action(target_status)
    )
    return replace(
        job,
        status=target_status,
        updated_at=now or datetime.now(UTC),
        revision=job.revision + 1,
        progress=next_progress,
        transaction_id=transaction_id or job.transaction_id,
        recovery_action=next_recovery,
        result=result if result is not None else job.result,
        error=error,
    )


def _default_recovery_action(status: JobStatus) -> RecoveryAction:
    """Return the default recovery directive for a lifecycle state."""
    if status in {JobStatus.PARTIAL, JobStatus.FAILED}:
        return RecoveryAction.RETRY
    if status == JobStatus.RECOVERY_REQUIRED:
        return RecoveryAction.MANUAL
    return RecoveryAction.NONE
