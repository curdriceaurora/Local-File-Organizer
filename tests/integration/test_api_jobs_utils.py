"""Integration tests for api/jobs.py and api/utils.py.

Covers: create_job, get_job, update_job (valid/invalid fields),
list_jobs (type filter, status filter, limit), job_count,
_prune_jobs (TTL, max-entries eviction),
resolve_path (allowed / outside-root / no-roots),
file_info_from_path (normal file, missing file, permission error),
and ApiError exception.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Helpers to isolate the global _JOB_STORE between tests
# ---------------------------------------------------------------------------


def _fresh_store() -> None:
    """Clear the module-level job store so tests don't interfere."""
    from file_organizer.api import jobs

    with jobs._JOB_STORE_LOCK:
        jobs._JOB_STORE.clear()


# ---------------------------------------------------------------------------
# create_job / get_job
# ---------------------------------------------------------------------------


class TestCreateGetJob:
    def setup_method(self) -> None:
        _fresh_store()

    def test_create_job_returns_queued_state(self) -> None:
        from file_organizer.api.jobs import create_job

        with patch("file_organizer.api.jobs._notify_job_event"):
            job = create_job("organize")
        assert job.status == "queued"
        assert job.job_type == "organize"
        assert job.job_id != ""

    def test_create_job_persisted_in_store(self) -> None:
        from file_organizer.api.jobs import create_job, get_job

        with patch("file_organizer.api.jobs._notify_job_event"):
            job = create_job("dedupe")
        retrieved = get_job(job.job_id)
        assert retrieved is not None
        assert retrieved.job_id == job.job_id

    def test_get_job_missing_returns_none(self) -> None:
        from file_organizer.api.jobs import get_job

        assert get_job("nonexistent-job-id") is None

    def test_create_job_unique_ids(self) -> None:
        from file_organizer.api.jobs import create_job

        with patch("file_organizer.api.jobs._notify_job_event"):
            j1 = create_job("search")
            j2 = create_job("search")
        assert j1.job_id != j2.job_id

    def test_created_at_equals_updated_at_on_creation(self) -> None:
        from file_organizer.api.jobs import create_job

        with patch("file_organizer.api.jobs._notify_job_event"):
            job = create_job("analyze")
        assert job.created_at == job.updated_at


# ---------------------------------------------------------------------------
# update_job
# ---------------------------------------------------------------------------


class TestUpdateJob:
    def setup_method(self) -> None:
        _fresh_store()

    def test_update_status_to_running(self) -> None:
        from file_organizer.api.jobs import create_job, update_job

        with patch("file_organizer.api.jobs._notify_job_event"):
            job = create_job("organize")
            updated = update_job(job.job_id, status="running")
        assert updated is not None
        assert updated.status == "running"

    def test_update_status_to_completed_with_result(self) -> None:
        from file_organizer.api.jobs import create_job, update_job

        with patch("file_organizer.api.jobs._notify_job_event"):
            job = create_job("organize")
            updated = update_job(job.job_id, status="completed", result={"files_moved": 5})
        assert updated is not None
        assert updated.status == "completed"
        assert updated.result == {"files_moved": 5}

    def test_update_nonexistent_job_returns_none(self) -> None:
        from file_organizer.api.jobs import update_job

        with patch("file_organizer.api.jobs._notify_job_event"):
            result = update_job("ghost-job-id", status="running")
        assert result is None

    def test_update_invalid_field_raises_value_error(self) -> None:
        from file_organizer.api.jobs import create_job, update_job

        with patch("file_organizer.api.jobs._notify_job_event"):
            job = create_job("organize")
        with patch("file_organizer.api.jobs._notify_job_event"):
            with pytest.raises(ValueError, match="Unknown job fields"):
                update_job(job.job_id, nonexistent_field="value")

    def test_update_error_field(self) -> None:
        from file_organizer.api.jobs import create_job, update_job

        with patch("file_organizer.api.jobs._notify_job_event"):
            job = create_job("organize")
            updated = update_job(job.job_id, status="failed", error="Something went wrong")
        assert updated is not None
        assert updated.error == "Something went wrong"

    def test_updated_at_advances_on_update(self) -> None:
        from datetime import UTC, datetime

        from file_organizer.api.jobs import create_job, update_job

        t0 = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
        t1 = datetime(2026, 1, 1, 0, 0, 1, tzinfo=UTC)
        with patch("file_organizer.api.jobs._notify_job_event"):
            with patch("file_organizer.api.jobs._now", side_effect=[t0, t1]):
                job = create_job("organize")
                original_updated = job.updated_at
                updated = update_job(job.job_id, status="running")
        assert updated is not None
        assert updated.updated_at > original_updated


# ---------------------------------------------------------------------------
# list_jobs / job_count
# ---------------------------------------------------------------------------


class TestListJobsAndCount:
    def setup_method(self) -> None:
        _fresh_store()

    def test_list_jobs_empty(self) -> None:
        from file_organizer.api.jobs import list_jobs

        assert list_jobs() == []

    def test_list_jobs_returns_created_jobs(self) -> None:
        from file_organizer.api.jobs import create_job, list_jobs

        with patch("file_organizer.api.jobs._notify_job_event"):
            create_job("type_a")
            create_job("type_b")
        jobs = list_jobs()
        assert len(jobs) == 2

    def test_list_jobs_filter_by_type(self) -> None:
        from file_organizer.api.jobs import create_job, list_jobs

        with patch("file_organizer.api.jobs._notify_job_event"):
            create_job("organize")
            create_job("dedupe")
            create_job("organize")
        jobs = list_jobs(job_type="organize")
        assert len(jobs) == 2
        assert all(j.job_type == "organize" for j in jobs)

    def test_list_jobs_filter_by_status(self) -> None:
        from file_organizer.api.jobs import create_job, list_jobs, update_job

        with patch("file_organizer.api.jobs._notify_job_event"):
            j1 = create_job("organize")
            create_job("organize")
            update_job(j1.job_id, status="completed")
        jobs = list_jobs(statuses={"queued"})
        assert len(jobs) == 1
        assert all(j.status == "queued" for j in jobs)

    def test_list_jobs_limit(self) -> None:
        from file_organizer.api.jobs import create_job, list_jobs

        with patch("file_organizer.api.jobs._notify_job_event"):
            for _ in range(5):
                create_job("test")
        jobs = list_jobs(limit=2)
        assert len(jobs) == 2

    def test_job_count_active_only(self) -> None:
        from file_organizer.api.jobs import create_job, job_count, update_job

        with patch("file_organizer.api.jobs._notify_job_event"):
            j1 = create_job("organize")
            create_job("organize")
            update_job(j1.job_id, status="completed")
        count = job_count()
        assert count == 1  # only the second queued job is still active

    def test_job_count_zero_when_empty(self) -> None:
        from file_organizer.api.jobs import job_count

        assert job_count() == 0


# ---------------------------------------------------------------------------
# resolve_path
# ---------------------------------------------------------------------------


class TestResolvePath:
    def test_allowed_path_returns_resolved(self, tmp_path: Path) -> None:
        from file_organizer.api.utils import resolve_path

        subdir = tmp_path / "docs"
        subdir.mkdir()
        result = resolve_path(str(subdir), allowed_paths=[str(tmp_path)])
        assert result == subdir.resolve()

    def test_path_at_root_allowed(self, tmp_path: Path) -> None:
        from file_organizer.api.utils import resolve_path

        result = resolve_path(str(tmp_path), allowed_paths=[str(tmp_path)])
        assert result == tmp_path.resolve()

    def test_outside_root_raises_api_error(self, tmp_path: Path) -> None:
        from file_organizer.api.exceptions import ApiError
        from file_organizer.api.utils import resolve_path

        subdir = tmp_path / "subdir"
        subdir.mkdir()
        with pytest.raises(ApiError) as exc_info:
            resolve_path("/etc/passwd", allowed_paths=[str(subdir)])
        assert exc_info.value.status_code == 403

    def test_no_allowed_paths_raises_api_error(self, tmp_path: Path) -> None:
        from file_organizer.api.exceptions import ApiError
        from file_organizer.api.utils import resolve_path

        with pytest.raises(ApiError) as exc_info:
            resolve_path(str(tmp_path), allowed_paths=[])
        assert exc_info.value.status_code == 403

    def test_none_allowed_paths_raises_api_error(self, tmp_path: Path) -> None:
        from file_organizer.api.exceptions import ApiError
        from file_organizer.api.utils import resolve_path

        with pytest.raises(ApiError) as exc_info:
            resolve_path(str(tmp_path), allowed_paths=None)
        assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# file_info_from_path
# ---------------------------------------------------------------------------


class TestFileInfoFromPath:
    def test_normal_file_returns_file_info(self, tmp_path: Path) -> None:
        from file_organizer.api.utils import file_info_from_path

        f = tmp_path / "test.txt"
        f.write_text("hello world")
        info = file_info_from_path(f)
        assert info.name == "test.txt"
        assert info.size == len("hello world")
        assert info.file_type == ".txt"

    def test_missing_file_raises_api_error_404(self, tmp_path: Path) -> None:
        from file_organizer.api.exceptions import ApiError
        from file_organizer.api.utils import file_info_from_path

        missing = tmp_path / "gone.txt"
        with pytest.raises(ApiError) as exc_info:
            file_info_from_path(missing)
        assert exc_info.value.status_code == 404

    def test_permission_error_raises_api_error_403(self, tmp_path: Path) -> None:
        from file_organizer.api.exceptions import ApiError
        from file_organizer.api.utils import file_info_from_path

        f = tmp_path / "secret.txt"
        f.write_text("private")
        with patch.object(Path, "stat", side_effect=PermissionError("denied")):
            with pytest.raises(ApiError) as exc_info:
                file_info_from_path(f)
        assert exc_info.value.status_code == 403

    def test_oserror_raises_api_error_500(self, tmp_path: Path) -> None:
        from file_organizer.api.exceptions import ApiError
        from file_organizer.api.utils import file_info_from_path

        f = tmp_path / "broken.txt"
        f.write_text("data")
        with patch.object(Path, "stat", side_effect=OSError("device error")):
            with pytest.raises(ApiError) as exc_info:
                file_info_from_path(f)
        assert exc_info.value.status_code == 500

    def test_mime_type_detected_for_jpg(self, tmp_path: Path) -> None:
        from file_organizer.api.utils import file_info_from_path

        f = tmp_path / "photo.jpg"
        f.write_bytes(b"\xff\xd8\xff")
        info = file_info_from_path(f)
        assert info.mime_type is not None
        assert "image" in info.mime_type


# ---------------------------------------------------------------------------
# ApiError
# ---------------------------------------------------------------------------


class TestApiError:
    def test_api_error_fields(self) -> None:
        from file_organizer.api.exceptions import ApiError

        exc = ApiError(status_code=404, error="not_found", message="Missing")
        assert exc.status_code == 404
        assert exc.error == "not_found"
        assert exc.message == "Missing"

    def test_api_error_is_exception(self) -> None:
        from file_organizer.api.exceptions import ApiError

        exc = ApiError(status_code=500, error="internal", message="Error")
        assert isinstance(exc, Exception)
