"""Tests for canonical errors and organization job lifecycle semantics."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest

from file_organizer.api import jobs as api_jobs
from file_organizer.core.errors import (
    DomainError,
    DomainErrorCode,
    optional_feature_unavailable,
)
from file_organizer.core.lifecycle import (
    JobProgress,
    JobSnapshot,
    JobStatus,
    RecoveryAction,
    create_job_snapshot,
    transition_job,
)

pytestmark = [pytest.mark.unit, pytest.mark.ci]


def _now() -> datetime:
    return datetime(2026, 7, 21, 12, tzinfo=UTC)


def test_scheduled_partial_recovery_lifecycle_round_trips() -> None:
    scheduled_for = _now() + timedelta(hours=1)
    scheduled = create_job_snapshot(
        job_id="job-1",
        job_type="organize",
        now=_now(),
        scheduled_for=scheduled_for,
    )
    running = transition_job(scheduled, JobStatus.RUNNING, now=scheduled_for)
    partial = transition_job(
        running,
        JobStatus.PARTIAL,
        now=scheduled_for + timedelta(minutes=1),
        progress=JobProgress(total=2, completed=1, failed=1),
        transaction_id="txn-1",
        recovery_action=RecoveryAction.ROLLBACK,
        result={"processed_files": 1, "failed_files": 1},
    )
    rolling_back = transition_job(partial, JobStatus.ROLLING_BACK)
    rolled_back = transition_job(rolling_back, JobStatus.ROLLED_BACK)

    assert rolled_back.revision == 4
    assert rolled_back.transaction_id == "txn-1"
    assert rolled_back.progress.percent == 100.0
    assert JobSnapshot.from_dict(rolled_back.to_dict()) == rolled_back


def test_rollback_preserves_original_failure_evidence() -> None:
    queued = create_job_snapshot(job_id="job-1", job_type="organize", now=_now())
    running = transition_job(queued, JobStatus.RUNNING)
    failure = DomainError(
        DomainErrorCode.EXECUTION_FAILED,
        "Destination write failed.",
        details={"path": "/output/report.txt"},
    )
    failed = transition_job(running, JobStatus.FAILED, error=failure)

    rolling_back = transition_job(failed, JobStatus.ROLLING_BACK)
    rolled_back = transition_job(rolling_back, JobStatus.ROLLED_BACK)

    assert rolling_back.error is failure
    assert rolled_back.error is failure
    assert rolled_back.error.to_dict()["details"] == {"path": "/output/report.txt"}
    assert transition_job(failed, JobStatus.QUEUED).error is None


def test_duplicate_and_illegal_transitions_have_stable_errors() -> None:
    queued = create_job_snapshot(job_id="job-1", job_type="organize", now=_now())

    with pytest.raises(DomainError) as duplicate:
        transition_job(queued, JobStatus.QUEUED)
    assert duplicate.value.code == DomainErrorCode.INVALID_JOB_TRANSITION

    completed = transition_job(queued, JobStatus.COMPLETED)
    with pytest.raises(DomainError) as illegal:
        transition_job(completed, JobStatus.RUNNING)
    assert illegal.value.to_dict() == {
        "code": "invalid_job_transition",
        "message": "Cannot transition job from completed to running.",
        "retryable": False,
        "details": {"from": "completed", "to": "running"},
    }


def test_stale_revision_and_progress_regression_are_rejected() -> None:
    queued = create_job_snapshot(job_id="job-1", job_type="organize", now=_now())
    running = transition_job(
        queued,
        JobStatus.RUNNING,
        progress=JobProgress(total=2, completed=1),
    )

    with pytest.raises(DomainError) as stale:
        transition_job(running, JobStatus.COMPLETED, expected_revision=0)
    assert stale.value.code == DomainErrorCode.STALE_JOB_REVISION
    assert stale.value.retryable is True

    with pytest.raises(DomainError, match="cannot move backwards"):
        transition_job(
            running,
            JobStatus.COMPLETED,
            progress=JobProgress(total=2, completed=0),
        )


def test_optional_feature_error_is_transport_neutral() -> None:
    error = optional_feature_unavailable("transcription", "Install the audio extra.")

    assert DomainError.from_dict(error.to_dict()).to_dict() == {
        "code": "optional_feature_unavailable",
        "message": "Install the audio extra.",
        "retryable": False,
        "details": {"feature": "transcription"},
    }


def test_api_job_idempotency_is_safe_under_concurrent_creation() -> None:
    with api_jobs._JOB_STORE_LOCK:
        api_jobs._JOB_STORE.clear()
        api_jobs._IDEMPOTENCY_INDEX.clear()

    def create() -> str:
        return api_jobs.create_job("organize", idempotency_key="request-1").job_id

    with ThreadPoolExecutor(max_workers=8) as executor:
        job_ids = list(executor.map(lambda _: create(), range(32)))

    assert len(set(job_ids)) == 1
    assert len(api_jobs.list_jobs(job_type="organize")) == 1


def test_api_job_compare_and_swap_rejects_lost_update() -> None:
    with api_jobs._JOB_STORE_LOCK:
        api_jobs._JOB_STORE.clear()
        api_jobs._IDEMPOTENCY_INDEX.clear()
    job = api_jobs.create_job("organize")
    running = api_jobs.update_job(
        job.job_id,
        status=JobStatus.RUNNING,
        expected_revision=job.revision,
    )

    assert running is not None
    with pytest.raises(DomainError) as stale:
        api_jobs.update_job(
            job.job_id,
            status=JobStatus.FAILED,
            error="late failure",
            expected_revision=job.revision,
        )
    assert stale.value.code == DomainErrorCode.STALE_JOB_REVISION


def test_api_job_preserves_domain_error_evidence() -> None:
    with api_jobs._JOB_STORE_LOCK:
        api_jobs._JOB_STORE.clear()
        api_jobs._IDEMPOTENCY_INDEX.clear()
    job = api_jobs.create_job("organize")

    failed = api_jobs.update_job(
        job.job_id,
        status=JobStatus.FAILED,
        error="Install the audio extra.",
        error_code=DomainErrorCode.OPTIONAL_FEATURE_UNAVAILABLE,
        error_retryable=False,
        error_details={"feature": "transcription"},
    )

    assert failed is not None
    assert failed.to_snapshot().error is not None
    assert failed.to_snapshot().error.to_dict() == {
        "code": "optional_feature_unavailable",
        "message": "Install the audio extra.",
        "retryable": False,
        "details": {"feature": "transcription"},
    }
