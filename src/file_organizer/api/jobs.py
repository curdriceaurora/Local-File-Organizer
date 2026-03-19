"""In-memory job tracking for background API tasks."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, fields
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import Any, Literal
from uuid import uuid4

from file_organizer.api.realtime import realtime_manager

JobStateStatus = Literal["queued", "running", "completed", "failed"]


@dataclass
class JobState:
    """State record for a background API job."""

    job_id: str
    job_type: str
    status: JobStateStatus
    created_at: datetime
    updated_at: datetime
    result: dict[str, Any] | None = None
    error: str | None = None


_ACTIVE_STATUSES = {"queued", "running"}
_JOB_STORE: OrderedDict[str, JobState] = OrderedDict()
_JOB_STORE_LOCK = Lock()
_JOB_FIELDS = {field.name for field in fields(JobState)}
_MAX_JOBS = 1000
_JOB_TTL = timedelta(hours=24)


def _now() -> datetime:
    return datetime.now(UTC)


def _prune_jobs(now: datetime) -> None:
    cutoff = now - _JOB_TTL
    expired = [job_id for job_id, job in _JOB_STORE.items() if job.updated_at < cutoff]
    for job_id in expired:
        _JOB_STORE.pop(job_id, None)
    while len(_JOB_STORE) > _MAX_JOBS:
        _JOB_STORE.popitem(last=False)


def create_job(job_type: str) -> JobState:
    """Create a new background job and return its initial state."""
    job_id = uuid4().hex
    ts = _now()
    job = JobState(
        job_id=job_id,
        job_type=job_type,
        status="queued",
        created_at=ts,
        updated_at=ts,
    )
    with _JOB_STORE_LOCK:
        _JOB_STORE[job_id] = job
        _JOB_STORE.move_to_end(job_id)
        _prune_jobs(ts)
        payload = _build_job_payload(job, event_type="job.created")
    _notify_job_event(payload)
    return job


def get_job(job_id: str) -> JobState | None:
    """Return the job state for job_id, or None if not found."""
    with _JOB_STORE_LOCK:
        _prune_jobs(_now())
        job = _JOB_STORE.get(job_id)
        if job:
            _JOB_STORE.move_to_end(job_id)
        return job


def update_job(job_id: str, **updates: Any) -> JobState | None:
    """Apply keyword updates to a job and return the updated state."""
    with _JOB_STORE_LOCK:
        job = _JOB_STORE.get(job_id)
        if not job:
            return None
        invalid_keys = [key for key in updates if key not in _JOB_FIELDS]
        if invalid_keys:
            raise ValueError(f"Unknown job fields: {', '.join(invalid_keys)}")
        for key, value in updates.items():
            setattr(job, key, value)
        job.updated_at = _now()
        _JOB_STORE.move_to_end(job_id)
        _prune_jobs(job.updated_at)
        payload = _build_job_payload(job, event_type="job.updated")
    _notify_job_event(payload)
    return job


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
    return jobs[:safe_limit]


def job_count() -> int:
    """Return the count of currently active (queued or running) jobs."""
    with _JOB_STORE_LOCK:
        _prune_jobs(_now())
        return sum(1 for job in _JOB_STORE.values() if job.status in _ACTIVE_STATUSES)


def _build_job_payload(job: JobState, event_type: str) -> dict[str, Any]:
    return {
        "type": event_type,
        "job_id": job.job_id,
        "job_type": job.job_type,
        "status": job.status,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
        "error": job.error,
        "result": job.result,
    }


def _notify_job_event(payload: dict[str, Any]) -> None:
    realtime_manager.enqueue_event(payload, channel="jobs")
    job_id = payload.get("job_id")
    if job_id:
        realtime_manager.enqueue_event(payload, channel=f"job:{job_id}")
