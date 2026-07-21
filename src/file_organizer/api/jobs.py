"""In-memory job tracking for background API tasks."""

from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass, field, fields, replace
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import Any
from uuid import uuid4

from file_organizer.api.realtime import realtime_manager
from file_organizer.core.errors import DomainError, DomainErrorCode
from file_organizer.core.lifecycle import (
    ACTIVE_JOB_STATUSES,
    JobProgress,
    JobSnapshot,
    JobStatus,
    RecoveryAction,
    create_job_snapshot,
    transition_job,
)

JobStateStatus = JobStatus


@dataclass
class JobState:
    """Backward-compatible API view of the canonical lifecycle snapshot."""

    job_id: str
    job_type: str
    status: JobStatus
    created_at: datetime
    updated_at: datetime
    result: dict[str, Any] | None = None
    error: str | None = None
    error_code: DomainErrorCode | None = None
    error_retryable: bool = False
    error_details: dict[str, Any] = field(default_factory=dict)
    revision: int = 0
    idempotency_key: str | None = None
    scheduled_for: datetime | None = None
    progress: JobProgress = field(default_factory=JobProgress)
    transaction_id: str | None = None
    recovery_action: RecoveryAction = RecoveryAction.NONE

    @classmethod
    def from_snapshot(cls, snapshot: JobSnapshot) -> JobState:
        """Build the compatibility view from an immutable domain snapshot."""
        return cls(
            job_id=snapshot.job_id,
            job_type=snapshot.job_type,
            status=snapshot.status,
            created_at=snapshot.created_at,
            updated_at=snapshot.updated_at,
            result=deepcopy(snapshot.result),
            error=snapshot.error.message if snapshot.error is not None else None,
            error_code=snapshot.error.code if snapshot.error is not None else None,
            error_retryable=snapshot.error.retryable if snapshot.error is not None else False,
            error_details=deepcopy(snapshot.error.details) if snapshot.error is not None else {},
            revision=snapshot.revision,
            idempotency_key=snapshot.idempotency_key,
            scheduled_for=snapshot.scheduled_for,
            progress=snapshot.progress,
            transaction_id=snapshot.transaction_id,
            recovery_action=snapshot.recovery_action,
        )

    def to_snapshot(self) -> JobSnapshot:
        """Return the canonical immutable snapshot represented by this view."""
        domain_error = None
        if self.error is not None:
            domain_error = DomainError(
                self.error_code or DomainErrorCode.EXECUTION_FAILED,
                self.error,
                retryable=self.error_retryable,
                details=deepcopy(self.error_details),
            )
        return JobSnapshot(
            job_id=self.job_id,
            job_type=self.job_type,
            status=self.status,
            created_at=self.created_at,
            updated_at=self.updated_at,
            revision=self.revision,
            idempotency_key=self.idempotency_key,
            scheduled_for=self.scheduled_for,
            progress=self.progress,
            transaction_id=self.transaction_id,
            recovery_action=self.recovery_action,
            result=deepcopy(self.result),
            error=domain_error,
        )


_ACTIVE_STATUSES = ACTIVE_JOB_STATUSES
_JOB_STORE: OrderedDict[str, JobState] = OrderedDict()
_IDEMPOTENCY_INDEX: dict[tuple[str, str], str] = {}
_JOB_STORE_LOCK = Lock()
_JOB_FIELDS = {field.name for field in fields(JobState)}
_MAX_JOBS = 1000
_JOB_TTL = timedelta(hours=24)


def _now() -> datetime:
    """Return the current UTC time as a timezone-aware datetime."""
    return datetime.now(UTC)


def _prune_jobs(now: datetime) -> None:
    """Remove completed jobs older than the configured retention window."""
    cutoff = now - _JOB_TTL
    expired = [job_id for job_id, job in _JOB_STORE.items() if job.updated_at < cutoff]
    for job_id in expired:
        removed = _JOB_STORE.pop(job_id, None)
        if removed is not None and removed.idempotency_key is not None:
            _IDEMPOTENCY_INDEX.pop((removed.job_type, removed.idempotency_key), None)
    while len(_JOB_STORE) > _MAX_JOBS:
        _, removed = _JOB_STORE.popitem(last=False)
        if removed.idempotency_key is not None:
            _IDEMPOTENCY_INDEX.pop((removed.job_type, removed.idempotency_key), None)


def create_job(
    job_type: str,
    *,
    idempotency_key: str | None = None,
    scheduled_for: datetime | None = None,
) -> JobState:
    """Create a new background job and return its initial state."""
    ts = _now()
    with _JOB_STORE_LOCK:
        if idempotency_key is not None:
            existing_id = _IDEMPOTENCY_INDEX.get((job_type, idempotency_key))
            if existing_id is not None and existing_id in _JOB_STORE:
                return deepcopy(_JOB_STORE[existing_id])
        snapshot = create_job_snapshot(
            job_id=uuid4().hex,
            job_type=job_type,
            now=ts,
            idempotency_key=idempotency_key,
            scheduled_for=scheduled_for,
        )
        job = JobState.from_snapshot(snapshot)
        _JOB_STORE[job.job_id] = job
        _JOB_STORE.move_to_end(job.job_id)
        if idempotency_key is not None:
            _IDEMPOTENCY_INDEX[(job_type, idempotency_key)] = job.job_id
        _prune_jobs(ts)
        payload = _build_job_payload(job, event_type="job.created")
    _notify_job_event(payload)
    return deepcopy(job)


def get_job(job_id: str) -> JobState | None:
    """Return the job state for job_id, or None if not found."""
    with _JOB_STORE_LOCK:
        _prune_jobs(_now())
        job = _JOB_STORE.get(job_id)
        if job:
            _JOB_STORE.move_to_end(job_id)
        return deepcopy(job) if job is not None else None


def update_job(job_id: str, **updates: Any) -> JobState | None:
    """Apply keyword updates to a job and return the updated state."""
    with _JOB_STORE_LOCK:
        job = _JOB_STORE.get(job_id)
        if not job:
            return None
        expected_revision = updates.pop("expected_revision", None)
        invalid_keys = [key for key in updates if key not in _JOB_FIELDS]
        if invalid_keys:
            raise ValueError(f"Unknown job fields: {', '.join(invalid_keys)}")
        status = updates.pop("status", None)
        now = _now()
        if status is not None:
            error_text = updates.pop("error", None)
            error_code = updates.pop("error_code", None)
            error_retryable = bool(updates.pop("error_retryable", False))
            error_details = updates.pop("error_details", None)
            domain_error = None
            if error_text is not None:
                domain_error = DomainError(
                    DomainErrorCode(error_code or DomainErrorCode.EXECUTION_FAILED),
                    str(error_text),
                    retryable=error_retryable,
                    details=deepcopy(error_details),
                )
            snapshot = transition_job(
                job.to_snapshot(),
                status,
                now=now,
                expected_revision=expected_revision,
                progress=updates.pop("progress", None),
                transaction_id=updates.pop("transaction_id", None),
                recovery_action=updates.pop("recovery_action", None),
                result=updates.pop("result", None),
                error=domain_error,
            )
            job = JobState.from_snapshot(snapshot)
        else:
            if expected_revision is not None and expected_revision != job.revision:
                raise DomainError(
                    DomainErrorCode.STALE_JOB_REVISION,
                    "Job state changed before this mutation could be applied.",
                    retryable=True,
                    details={"expected": expected_revision, "actual": job.revision},
                )
            job = replace(job, updated_at=now, revision=job.revision + 1, **updates)
        _JOB_STORE[job_id] = job
        _JOB_STORE.move_to_end(job_id)
        _prune_jobs(job.updated_at)
        payload = _build_job_payload(job, event_type="job.updated")
    _notify_job_event(payload)
    return deepcopy(job)


def list_jobs(
    *,
    job_type: str | None = None,
    statuses: set[JobStateStatus] | None = None,
    limit: int = 100,
) -> list[JobState]:
    """List tracked jobs, newest first."""
    safe_limit = max(1, min(limit, _MAX_JOBS))
    with _JOB_STORE_LOCK:
        _prune_jobs(_now())
        jobs = list(_JOB_STORE.values())
    if job_type is not None:
        jobs = [job for job in jobs if job.job_type == job_type]
    if statuses is not None:
        jobs = [job for job in jobs if job.status in statuses]
    jobs.sort(key=lambda job: job.updated_at, reverse=True)
    return deepcopy(jobs[:safe_limit])


def job_count() -> int:
    """Return the count of currently active (queued or running) jobs."""
    with _JOB_STORE_LOCK:
        _prune_jobs(_now())
        return sum(1 for job in _JOB_STORE.values() if job.status in _ACTIVE_STATUSES)


def _build_job_payload(job: JobState, event_type: str) -> dict[str, Any]:
    """Serialize a Job into a dict suitable for JSON responses and websocket broadcasts."""
    return {
        "type": event_type,
        "job_id": job.job_id,
        "job_type": job.job_type,
        "status": job.status,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
        "revision": job.revision,
        "scheduled_for": job.scheduled_for.isoformat() if job.scheduled_for else None,
        "progress": {
            "total": job.progress.total,
            "completed": job.progress.completed,
            "failed": job.progress.failed,
            "skipped": job.progress.skipped,
            "percent": job.progress.percent,
        },
        "transaction_id": job.transaction_id,
        "recovery_action": job.recovery_action.value,
        "error_code": job.error_code.value if job.error_code is not None else None,
        "error_retryable": job.error_retryable,
        "error_details": deepcopy(job.error_details),
        "error": job.error,
        "result": job.result,
    }


def _notify_job_event(payload: dict[str, Any]) -> None:
    """Enqueue a websocket event describing a job state transition."""
    realtime_manager.enqueue_event(payload, channel="jobs")
    job_id = payload.get("job_id")
    if job_id:
        realtime_manager.enqueue_event(payload, channel=f"job:{job_id}")
