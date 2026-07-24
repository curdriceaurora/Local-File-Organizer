"""Integration tests for JobRepository against a real SQLite DB."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import file_organizer.api.db_models  # noqa: F401 — registers models with Base
from file_organizer.api.auth_models import Base
from file_organizer.api.repositories.job_repo import JobRepository
from file_organizer.core.errors import DomainError, DomainErrorCode

pytestmark = [pytest.mark.integration, pytest.mark.ci]


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)


class TestJobRepositoryCreate:
    def test_create_with_defaults(self, db_session: Session) -> None:
        job = JobRepository.create(db_session, "/input", "/output")
        db_session.flush()
        assert job.id is not None
        assert job.input_dir == "/input"
        assert job.output_dir == "/output"
        assert job.job_type == "organize"
        assert job.methodology == "content_based"
        assert job.dry_run is False
        assert job.workspace_id is None
        assert job.owner_id is None

    def test_create_with_all_options(self, db_session: Session) -> None:
        job = JobRepository.create(
            db_session,
            "/in",
            "/out",
            workspace_id="ws-1",
            owner_id="user-1",
            job_type="dedupe",
            methodology="para",
            dry_run=True,
        )
        db_session.flush()
        assert job.workspace_id == "ws-1"
        assert job.owner_id == "user-1"
        assert job.job_type == "dedupe"
        assert job.methodology == "para"
        assert job.dry_run is True

    def test_multiple_jobs_get_distinct_ids(self, db_session: Session) -> None:
        j1 = JobRepository.create(db_session, "/a", "/b")
        j2 = JobRepository.create(db_session, "/c", "/d")
        db_session.flush()
        assert j1.id != j2.id

    def test_idempotency_key_returns_existing_job(self, db_session: Session) -> None:
        first = JobRepository.create(
            db_session,
            "/a",
            "/b",
            idempotency_key="request-1",
        )
        second = JobRepository.create(
            db_session,
            "/different",
            "/different-output",
            idempotency_key="request-1",
        )

        assert second.id == first.id
        assert second.input_dir == "/a"


class TestJobRepositoryGetById:
    def test_returns_job_when_exists(self, db_session: Session) -> None:
        created = JobRepository.create(db_session, "/in", "/out")
        db_session.flush()
        fetched = JobRepository.get_by_id(db_session, created.id)
        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.input_dir == "/in"

    def test_returns_none_for_unknown_id(self, db_session: Session) -> None:
        result = JobRepository.get_by_id(db_session, "does-not-exist")
        assert result is None


class TestJobRepositoryListJobs:
    def test_lists_all_jobs(self, db_session: Session) -> None:
        j1 = JobRepository.create(db_session, "/a", "/b")
        j2 = JobRepository.create(db_session, "/c", "/d")
        db_session.flush()
        jobs = JobRepository.list_jobs(db_session)
        assert len(jobs) == 2
        ids = {j.id for j in jobs}
        assert j1.id in ids
        assert j2.id in ids

    def test_filter_by_owner_id(self, db_session: Session) -> None:
        JobRepository.create(db_session, "/a", "/b", owner_id="alice")
        JobRepository.create(db_session, "/c", "/d", owner_id="bob")
        db_session.flush()
        alice_jobs = JobRepository.list_jobs(db_session, owner_id="alice")
        assert len(alice_jobs) == 1
        assert alice_jobs[0].owner_id == "alice"

    def test_filter_by_status(self, db_session: Session) -> None:
        j = JobRepository.create(db_session, "/in", "/out")
        db_session.flush()
        JobRepository.update_status(db_session, j.id, "running")
        db_session.flush()
        running = JobRepository.list_jobs(db_session, status="running")
        assert len(running) == 1
        assert running[0].id == j.id

    def test_limit_respected(self, db_session: Session) -> None:
        for _ in range(5):
            JobRepository.create(db_session, "/in", "/out")
        db_session.flush()
        jobs = JobRepository.list_jobs(db_session, limit=2)
        assert len(jobs) == 2


class TestJobRepositoryUpdateStatus:
    def test_transitions_status(self, db_session: Session) -> None:
        job = JobRepository.create(db_session, "/in", "/out")
        db_session.flush()
        updated = JobRepository.update_status(db_session, job.id, "running")
        db_session.flush()
        assert updated is not None
        assert updated.status == "running"
        assert updated.error is None

    def test_sets_error_on_failure(self, db_session: Session) -> None:
        job = JobRepository.create(db_session, "/in", "/out")
        db_session.flush()
        updated = JobRepository.update_status(
            db_session,
            job.id,
            "failed",
            error="disk full",
            error_code="execution_failed",
            error_retryable=True,
            error_details={"device": "output"},
        )
        db_session.flush()
        assert updated is not None
        assert updated.status == "failed"
        assert updated.error == "disk full"
        assert updated.error_code == "execution_failed"
        assert updated.error_retryable is True
        assert updated.error_details_json == '{"device": "output"}'

    def test_returns_none_for_unknown_id(self, db_session: Session) -> None:
        result = JobRepository.update_status(db_session, "ghost-id", "running")
        assert result is None

    def test_stale_session_cannot_overwrite_newer_revision(self) -> None:
        engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        with Session(engine) as setup:
            job = JobRepository.create(setup, "/in", "/out")
            setup.commit()
            job_id = job.id

        with Session(engine) as winner, Session(engine) as stale:
            winner_job = JobRepository.get_by_id(winner, job_id)
            stale_job = JobRepository.get_by_id(stale, job_id)
            assert winner_job is not None and stale_job is not None

            JobRepository.update_status(winner, job_id, "running")
            winner.commit()

            with pytest.raises(DomainError) as exc_info:
                JobRepository.update_status(stale, job_id, "failed")

        assert exc_info.value.code == DomainErrorCode.STALE_JOB_REVISION
        Base.metadata.drop_all(engine)

    def test_rollback_states_preserve_prior_error_fields(self, db_session: Session) -> None:
        job = JobRepository.create(db_session, "/in", "/out")
        db_session.flush()
        JobRepository.update_status(db_session, job.id, "running")
        db_session.flush()
        JobRepository.update_status(
            db_session,
            job.id,
            "failed",
            error="disk full",
            error_code="execution_failed",
            error_retryable=True,
            error_details={"device": "output"},
        )
        db_session.flush()
        rolling_back = JobRepository.update_status(db_session, job.id, "rolling_back")
        db_session.flush()
        assert rolling_back is not None
        assert rolling_back.error == "disk full"
        assert rolling_back.error_code == "execution_failed"
        assert rolling_back.error_retryable is True
        assert rolling_back.error_details_json == '{"device": "output"}'
        rolled_back = JobRepository.update_status(db_session, rolling_back.id, "rolled_back")
        db_session.flush()
        assert rolled_back is not None
        assert rolled_back.error == "disk full"
        assert rolled_back.error_code == "execution_failed"
        assert rolled_back.error_retryable is True
        assert rolled_back.error_details_json == '{"device": "output"}'

        job2 = JobRepository.create(db_session, "/in2", "/out2")
        db_session.flush()
        JobRepository.update_status(db_session, job2.id, "running")
        db_session.flush()
        JobRepository.update_status(
            db_session,
            job2.id,
            "failed",
            error="disk full",
            error_code="execution_failed",
            error_retryable=True,
            error_details={"device": "output"},
        )
        db_session.flush()
        rolling_back2 = JobRepository.update_status(db_session, job2.id, "rolling_back")
        db_session.flush()
        recovery = JobRepository.update_status(
            db_session, rolling_back2.id, "recovery_required"
        )
        db_session.flush()
        assert recovery is not None
        assert recovery.error == "disk full"
        assert recovery.error_code == "execution_failed"
        assert recovery.error_retryable is True
        assert recovery.error_details_json == '{"device": "output"}'


class TestJobRepositoryUpdateResult:
    def test_updates_counters(self, db_session: Session) -> None:
        job = JobRepository.create(db_session, "/in", "/out")
        db_session.flush()
        updated = JobRepository.update_result(
            db_session,
            job.id,
            total_files=10,
            processed_files=9,
            failed_files=1,
            skipped_files=0,
        )
        db_session.flush()
        assert updated.total_files == 10
        assert updated.processed_files == 9
        assert updated.failed_files == 1
        assert updated.skipped_files == 0

    def test_partial_update_preserves_other_counters(self, db_session: Session) -> None:
        job = JobRepository.create(db_session, "/in", "/out")
        db_session.flush()
        JobRepository.update_result(db_session, job.id, total_files=5)
        db_session.flush()
        JobRepository.update_result(db_session, job.id, processed_files=3)
        db_session.flush()
        refreshed = JobRepository.get_by_id(db_session, job.id)
        assert refreshed is not None
        assert refreshed.total_files == 5
        assert refreshed.processed_files == 3
        assert refreshed.failed_files == 0
        assert refreshed.skipped_files == 0

    def test_returns_none_for_unknown_id(self, db_session: Session) -> None:
        result = JobRepository.update_result(db_session, "ghost-id", total_files=1)
        assert result is None
