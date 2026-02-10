"""In-memory job tracking for background API tasks."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

JobStateStatus = Literal["queued", "running", "completed", "failed"]


@dataclass
class JobState:
    job_id: str
    job_type: str
    status: JobStateStatus
    created_at: datetime
    updated_at: datetime
    result: dict[str, Any] | None = None
    error: str | None = None


_JOB_STORE: dict[str, JobState] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_job(job_type: str) -> JobState:
    job_id = uuid4().hex
    job = JobState(
        job_id=job_id,
        job_type=job_type,
        status="queued",
        created_at=_now(),
        updated_at=_now(),
    )
    _JOB_STORE[job_id] = job
    return job


def get_job(job_id: str) -> JobState | None:
    return _JOB_STORE.get(job_id)


def update_job(job_id: str, **updates: Any) -> JobState | None:
    job = _JOB_STORE.get(job_id)
    if not job:
        return None
    for key, value in updates.items():
        setattr(job, key, value)
    job.updated_at = _now()
    return job


def job_count() -> int:
    return len(_JOB_STORE)
