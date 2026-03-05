"""Tests for file_organizer.api.repositories.job_repo."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from file_organizer.api.db_models import OrganizationJob
from file_organizer.api.repositories.job_repo import JobRepository

pytestmark = pytest.mark.unit


class TestJobRepositoryCreate:
    """Tests for JobRepository.create."""

    def test_create_with_defaults(self):
        session = MagicMock(spec=Session)

        JobRepository.create(session, "/input", "/output")

        session.add.assert_called_once()
        session.flush.assert_called_once()
        added = session.add.call_args[0][0]
        assert isinstance(added, OrganizationJob)
        assert added.input_dir == "/input"
        assert added.output_dir == "/output"
        assert added.job_type == "organize"
        assert added.methodology == "content_based"
        assert added.dry_run is False
        assert added.workspace_id is None
        assert added.owner_id is None

    def test_create_with_all_options(self):
        session = MagicMock(spec=Session)

        JobRepository.create(
            session,
            "/in",
            "/out",
            workspace_id="ws-1",
            owner_id="user-1",
            job_type="dedupe",
            methodology="para",
            dry_run=True,
        )

        added = session.add.call_args[0][0]
        assert added.workspace_id == "ws-1"
        assert added.owner_id == "user-1"
        assert added.job_type == "dedupe"
        assert added.methodology == "para"
        assert added.dry_run is True


class TestJobRepositoryGetById:
    """Tests for JobRepository.get_by_id."""

    def test_get_existing_job(self):
        session = MagicMock(spec=Session)
        job = MagicMock(spec=OrganizationJob)
        session.get.return_value = job

        result = JobRepository.get_by_id(session, "job-1")
        assert result is job
        session.get.assert_called_once_with(OrganizationJob, "job-1")

    def test_get_nonexistent_returns_none(self):
        session = MagicMock(spec=Session)
        session.get.return_value = None

        result = JobRepository.get_by_id(session, "missing")
        assert result is None


class TestJobRepositoryListJobs:
    """Tests for JobRepository.list_jobs."""

    def _make_session(self, results=None):
        session = MagicMock(spec=Session)
        query = MagicMock()
        session.query.return_value = query
        query.filter.return_value = query
        query.order_by.return_value = query
        query.limit.return_value = query
        query.all.return_value = results or []
        return session

    def test_list_no_filters(self):
        jobs = [MagicMock(spec=OrganizationJob)]
        session = self._make_session(results=jobs)

        result = JobRepository.list_jobs(session)
        assert result == jobs

    def test_list_with_owner_filter(self):
        session = self._make_session()
        JobRepository.list_jobs(session, owner_id="user-1")
        # filter should have been called for owner_id
        session.query.return_value.filter.assert_called()

    def test_list_with_status_filter(self):
        session = self._make_session()
        JobRepository.list_jobs(session, status="running")
        session.query.return_value.filter.assert_called()

    def test_list_with_custom_limit(self):
        session = self._make_session()
        JobRepository.list_jobs(session, limit=10)
        session.query.return_value.order_by.return_value.limit.assert_called_with(10)


class TestJobRepositoryUpdateStatus:
    """Tests for JobRepository.update_status."""

    def test_update_status_existing_job(self):
        session = MagicMock(spec=Session)
        job = MagicMock(spec=OrganizationJob)
        session.get.return_value = job

        result = JobRepository.update_status(session, "job-1", "running")
        assert result is job
        assert job.status == "running"
        assert job.error is None
        session.flush.assert_called_once()

    def test_update_status_with_error(self):
        session = MagicMock(spec=Session)
        job = MagicMock(spec=OrganizationJob)
        session.get.return_value = job

        JobRepository.update_status(session, "job-1", "failed", error="OOM")
        assert job.status == "failed"
        assert job.error == "OOM"

    def test_update_status_not_found(self):
        session = MagicMock(spec=Session)
        session.get.return_value = None

        result = JobRepository.update_status(session, "missing", "running")
        assert result is None
        session.flush.assert_not_called()


class TestJobRepositoryUpdateResult:
    """Tests for JobRepository.update_result."""

    def test_update_all_counters(self):
        session = MagicMock(spec=Session)
        job = MagicMock(spec=OrganizationJob)
        session.get.return_value = job

        result = JobRepository.update_result(
            session,
            "job-1",
            total_files=100,
            processed_files=90,
            failed_files=5,
            skipped_files=5,
            result_json='{"summary": "done"}',
        )
        assert result is job
        assert job.total_files == 100
        assert job.processed_files == 90
        assert job.failed_files == 5
        assert job.skipped_files == 5
        assert job.result_json == '{"summary": "done"}'
        session.flush.assert_called_once()

    def test_update_partial_counters(self):
        session = MagicMock(spec=Session)
        job = MagicMock(spec=OrganizationJob)
        job.total_files = 50
        job.processed_files = 10
        session.get.return_value = job

        JobRepository.update_result(session, "job-1", processed_files=20)
        assert job.processed_files == 20
        # total_files should NOT have been reassigned (None arg skipped)
        assert job.total_files == 50

    def test_update_result_not_found(self):
        session = MagicMock(spec=Session)
        session.get.return_value = None

        result = JobRepository.update_result(session, "missing", total_files=10)
        assert result is None
        session.flush.assert_not_called()
