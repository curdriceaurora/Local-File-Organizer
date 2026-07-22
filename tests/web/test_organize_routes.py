"""Unit tests for web organize_routes helpers.

Tests presentation helpers, plan-store operations, job metadata, job views,
and lifecycle adaptation.
"""

from __future__ import annotations

from datetime import UTC, datetime
from threading import Timer
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.api.exceptions import ApiError
from file_organizer.core.lifecycle import JobStatus, RecoveryAction
from file_organizer.web.organize_routes import (
    ORGANIZE_MAX_DELAY_MIN,
    ORGANIZE_METHODOLOGIES,
    _cancel_scheduled_job,
    _normalize_methodology,
    _parse_delay_minutes,
    _status_progress,
)

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# _parse_delay_minutes
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestParseDelayMinutes:
    """Test the _parse_delay_minutes helper."""

    def test_none_returns_default(self):
        """Verifies None input returns the default delay of 0."""
        assert _parse_delay_minutes(None) == 0

    def test_empty_string_returns_default(self):
        """Verifies an empty string returns the default delay of 0."""
        assert _parse_delay_minutes("") == 0

    def test_whitespace_returns_default(self):
        """Verifies a whitespace-only string returns the default delay of 0."""
        assert _parse_delay_minutes("   ") == 0

    def test_valid_integer(self):
        """Verifies a valid integer string is parsed correctly."""
        assert _parse_delay_minutes("10") == 10

    def test_zero(self):
        """Verifies the string '0' parses to zero delay."""
        assert _parse_delay_minutes("0") == 0

    def test_max_boundary(self):
        """Verifies the maximum allowed delay value is accepted."""
        result = _parse_delay_minutes(str(ORGANIZE_MAX_DELAY_MIN))
        assert result == ORGANIZE_MAX_DELAY_MIN

    def test_non_numeric_raises(self):
        """Verifies a non-numeric string raises ApiError 400 with the expected error code."""
        with pytest.raises(ApiError) as exc_info:
            _parse_delay_minutes("abc")
        assert exc_info.value.status_code == 400
        assert "invalid_schedule_delay" in exc_info.value.error

    def test_negative_raises(self):
        """Verifies a negative delay string raises ApiError 400."""
        with pytest.raises(ApiError) as exc_info:
            _parse_delay_minutes("-1")
        assert exc_info.value.status_code == 400

    def test_over_max_raises(self):
        """Verifies a delay exceeding the maximum raises ApiError."""
        with pytest.raises(ApiError):
            _parse_delay_minutes(str(ORGANIZE_MAX_DELAY_MIN + 1))

    def test_float_string_raises(self):
        """Verifies a float string raises ApiError."""
        with pytest.raises(ApiError):
            _parse_delay_minutes("1.5")


# ---------------------------------------------------------------------------
# _normalize_methodology
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestNormalizeMethodology:
    """Test the _normalize_methodology helper."""

    def test_known_methodology(self):
        """Verifies canonical methodology names are returned unchanged."""
        assert _normalize_methodology("para") == "para"
        assert _normalize_methodology("jd") == "jd"
        assert _normalize_methodology("none") == "none"

    def test_legacy_aliases_map_to_canonical(self):
        """Pre-unification web values should map to their canonical equivalent."""
        assert _normalize_methodology("johnny_decimal") == "jd"
        assert _normalize_methodology("content_based") == "none"

    def test_none_returns_default(self):
        """Verifies None input falls back to the default 'none' methodology."""
        assert _normalize_methodology(None) == "none"

    def test_empty_string_returns_default(self):
        """Verifies an empty string falls back to the default methodology."""
        assert _normalize_methodology("") == "none"

    def test_unknown_returns_default(self):
        """Verifies an unrecognised methodology name falls back to the default.

        ``date_based`` was a web-only dropdown option with no organizer
        implementation behind it anywhere in the codebase, so it is not a
        recognized alias either — it falls back like any other unknown value.
        """
        assert _normalize_methodology("unknown_method") == "none"
        assert _normalize_methodology("date_based") == "none"

    def test_case_insensitive(self):
        """Verifies methodology names are matched case-insensitively."""
        assert _normalize_methodology("PARA") == "para"

    def test_whitespace_trimmed(self):
        """Verifies leading/trailing whitespace is stripped before matching."""
        assert _normalize_methodology("  para  ") == "para"


# ---------------------------------------------------------------------------
# _status_progress
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestStatusProgress:
    """Test the _status_progress helper."""

    def test_queued(self):
        """Verifies 'queued' status maps to 5% progress."""
        assert _status_progress("queued") == 5

    def test_running(self):
        """Verifies 'running' status maps to 65% progress."""
        assert _status_progress("running") == 65

    def test_completed(self):
        """Verifies 'completed' status maps to 100% progress."""
        assert _status_progress("completed") == 100

    def test_failed(self):
        """Verifies 'failed' status maps to 100% progress."""
        assert _status_progress("failed") == 100

    def test_unknown(self):
        """Verifies an unrecognised status maps to 0% progress."""
        assert _status_progress("something_else") == 0

    def test_empty(self):
        """Verifies an empty string status maps to 0% progress."""
        assert _status_progress("") == 0


# ---------------------------------------------------------------------------
# _job_report_payload
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestJobReportPayload:
    """Test the _job_report_payload helper."""

    def test_extracts_all_keys(self):
        """Verifies the payload contains expected job keys and excludes unknown keys."""
        from file_organizer.web.organize_routes import _job_report_payload

        job = {
            "job_id": "j1",
            "status": "completed",
            "created_at": "2025-01-01",
            "updated_at": "2025-01-02",
            "methodology": "para",
            "input_dir": "/in",
            "output_dir": "/out",
            "dry_run": False,
            "processed_files": 10,
            "total_files": 12,
            "failed_files": 2,
            "skipped_files": 0,
            "error": None,
            "result": {"organized_structure": {}},
            "extra_key": "ignored",
        }
        payload = _job_report_payload(job)
        assert payload["job_id"] == "j1"
        assert payload["methodology"] == "para"
        assert "extra_key" not in payload
        assert payload["processed_files"] == 10


# ---------------------------------------------------------------------------
# Plan store operations
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPlanStore:
    """Test _store_organize_plan, _get_organize_plan, _delete_organize_plan."""

    def test_store_and_get(self):
        """Verifies a plan can be stored, retrieved by ID, and then deleted."""
        from file_organizer.web.organize_routes import (
            _ORGANIZE_PLAN_STORE,
            _delete_organize_plan,
            _get_organize_plan,
            _store_organize_plan,
        )

        record = _store_organize_plan({"input_dir": "/tmp", "files": []})  # noqa: test-hardcoded-paths
        plan_id = record["plan_id"]
        assert plan_id in _ORGANIZE_PLAN_STORE

        retrieved = _get_organize_plan(plan_id)
        assert retrieved is not None
        assert retrieved["input_dir"] == "/tmp"  # noqa: test-hardcoded-paths

        _delete_organize_plan(plan_id)
        assert _get_organize_plan(plan_id) is None

    def test_get_missing_plan(self):
        """Verifies retrieving a non-existent plan ID returns None."""
        from file_organizer.web.organize_routes import _get_organize_plan

        assert _get_organize_plan("nonexistent-id") is None

    def test_delete_missing_plan(self):
        """Verifies deleting a non-existent plan ID does not raise."""
        from file_organizer.web.organize_routes import _delete_organize_plan

        # Should not raise
        _delete_organize_plan("nonexistent-id")

    def test_prune_oldest(self):
        """Verifies that storing beyond the plan limit prunes the store to within bounds."""
        from file_organizer.web.organize_routes import (
            _ORGANIZE_PLAN_STORE,
            ORGANIZE_PLAN_LIMIT,
            _store_organize_plan,
        )

        # Store more than the limit
        original_size = len(_ORGANIZE_PLAN_STORE)
        for i in range(ORGANIZE_PLAN_LIMIT + 5):
            _store_organize_plan({"idx": i})

        assert len(_ORGANIZE_PLAN_STORE) <= ORGANIZE_PLAN_LIMIT + original_size

        # Cleanup
        _ORGANIZE_PLAN_STORE.clear()


# ---------------------------------------------------------------------------
# Job metadata operations
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestJobMetadata:
    """Test _set_job_metadata, _get_job_metadata."""

    def test_set_and_get(self):
        """Verifies job metadata can be stored and retrieved by job ID."""
        from file_organizer.web.organize_routes import (
            _JOB_METADATA,
            _get_job_metadata,
            _set_job_metadata,
        )

        # Mock get_job so _prune_job_metadata doesn't remove our test entry
        with patch("file_organizer.web.organize_routes.get_job", return_value=MagicMock()):
            _set_job_metadata("test-job-1", {"methodology": "para"})
        result = _get_job_metadata("test-job-1")
        assert result["methodology"] == "para"

        # Cleanup
        _JOB_METADATA.pop("test-job-1", None)

    def test_get_missing(self):
        """Verifies retrieving metadata for a non-existent job returns an empty dict."""
        from file_organizer.web.organize_routes import _get_job_metadata

        result = _get_job_metadata("nonexistent-job")
        assert result == {}

    def test_returns_copy(self):
        """Verifies _get_job_metadata returns a copy so mutations do not affect the store."""
        from file_organizer.web.organize_routes import (
            _JOB_METADATA,
            _get_job_metadata,
            _set_job_metadata,
        )

        with patch("file_organizer.web.organize_routes.get_job", return_value=MagicMock()):
            _set_job_metadata("test-job-2", {"key": "val"})
        copy1 = _get_job_metadata("test-job-2")
        copy1["mutated"] = True
        copy2 = _get_job_metadata("test-job-2")
        assert "mutated" not in copy2

        # Cleanup
        _JOB_METADATA.pop("test-job-2", None)


# ---------------------------------------------------------------------------
# _prune_job_metadata
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPruneJobMetadata:
    """Test _prune_job_metadata."""

    def test_prune_removes_stale(self):
        """Verifies that jobs not found via get_job are removed from the metadata store."""
        from file_organizer.web.organize_routes import (
            _JOB_METADATA,
            _prune_job_metadata,
        )

        _JOB_METADATA["stale-job-x"] = {"something": True}

        with patch("file_organizer.web.organize_routes.get_job", return_value=None):
            _prune_job_metadata(force=True)

        assert "stale-job-x" not in _JOB_METADATA

    def test_prune_keeps_valid(self):
        """Verifies that jobs still found via get_job are retained in the metadata store."""
        from file_organizer.web.organize_routes import (
            _JOB_METADATA,
            _prune_job_metadata,
        )

        _JOB_METADATA["valid-job-y"] = {"something": True}
        mock_job = MagicMock()

        with patch("file_organizer.web.organize_routes.get_job", return_value=mock_job):
            _prune_job_metadata(force=True)

        assert "valid-job-y" in _JOB_METADATA
        # Cleanup
        _JOB_METADATA.pop("valid-job-y", None)


# ---------------------------------------------------------------------------
# _build_job_view
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBuildJobView:
    """Test _build_job_view."""

    def test_returns_none_for_missing_job(self):
        """Verifies _build_job_view returns None when the job does not exist."""
        from file_organizer.web.organize_routes import _build_job_view

        with patch("file_organizer.web.organize_routes.get_job", return_value=None):
            result = _build_job_view("no-such-job")
        assert result is None

    def test_builds_view_completed(self):
        """Verifies a completed job view includes correct progress, methodology, and terminal flags."""
        from file_organizer.web.organize_routes import _build_job_view

        mock_job = MagicMock()
        mock_job.job_id = "job-1"
        mock_job.status = "completed"
        mock_job.result = {
            "processed_files": 10,
            "total_files": 12,
            "failed_files": 2,
            "skipped_files": 0,
        }
        mock_job.created_at = datetime(2025, 1, 1, tzinfo=UTC)
        mock_job.updated_at = datetime(2025, 1, 2, tzinfo=UTC)
        mock_job.error = None
        mock_job.scheduled_for = None
        mock_job.transaction_id = "txn-1"
        mock_job.recovery_action = RecoveryAction.ROLLBACK
        mock_job.revision = 1

        with (
            patch("file_organizer.web.organize_routes.get_job", return_value=mock_job),
            patch(
                "file_organizer.web.organize_routes._get_job_metadata",
                return_value={
                    "methodology": "para",
                    "input_dir": "/in",
                    "output_dir": "/out",
                    "dry_run": False,
                },
            ),
        ):
            view = _build_job_view("job-1")

        assert view is not None
        assert view["job_id"] == "job-1"
        assert view["status"] == "completed"
        assert view["progress_percent"] == 100
        assert view["methodology"] == "para"
        assert view["can_rollback"] is True
        assert view["is_terminal"] is True

    def test_builds_view_running(self):
        """Verifies a running job view reports partial progress and is not marked terminal."""
        from file_organizer.web.organize_routes import _build_job_view

        mock_job = MagicMock()
        mock_job.job_id = "job-2"
        mock_job.status = "running"
        mock_job.result = {
            "processed_files": 5,
            "total_files": 10,
            "failed_files": 0,
            "skipped_files": 0,
        }
        mock_job.created_at = datetime(2025, 1, 1, tzinfo=UTC)
        mock_job.updated_at = datetime(2025, 1, 2, tzinfo=UTC)
        mock_job.error = None
        mock_job.scheduled_for = None
        mock_job.transaction_id = None
        mock_job.recovery_action = RecoveryAction.NONE
        mock_job.revision = 1

        with (
            patch("file_organizer.web.organize_routes.get_job", return_value=mock_job),
            patch("file_organizer.web.organize_routes._get_job_metadata", return_value={}),
        ):
            view = _build_job_view("job-2")

        assert view is not None
        assert view["status"] == "running"
        assert view["progress_percent"] >= 50
        assert view["is_terminal"] is False

    def test_builds_view_scheduled(self):
        """Verifies a queued/scheduled job view exposes can_cancel as True."""
        from file_organizer.web.organize_routes import _build_job_view

        mock_job = MagicMock()
        mock_job.job_id = "job-3"
        mock_job.status = "scheduled"
        mock_job.result = None
        mock_job.created_at = datetime(2025, 1, 1, tzinfo=UTC)
        mock_job.updated_at = datetime(2025, 1, 2, tzinfo=UTC)
        mock_job.error = None
        mock_job.scheduled_for = datetime(2025, 1, 1, 1, tzinfo=UTC)
        mock_job.transaction_id = None
        mock_job.recovery_action = RecoveryAction.NONE
        mock_job.revision = 0

        with (
            patch("file_organizer.web.organize_routes.get_job", return_value=mock_job),
            patch(
                "file_organizer.web.organize_routes._get_job_metadata",
                return_value={
                    "schedule_delay_minutes": 30,
                    "scheduled_for": "2025-01-01T01:00:00Z",
                },
            ),
        ):
            view = _build_job_view("job-3")

        assert view is not None
        assert view["can_cancel"] is True

    def test_builds_view_queued_as_cancellable(self):
        """Queued work can be cancelled before the background task starts."""
        from file_organizer.web.organize_routes import _build_job_view

        mock_job = MagicMock()
        mock_job.job_id = "job-queued"
        mock_job.status = JobStatus.QUEUED
        mock_job.result = None
        mock_job.created_at = datetime(2025, 1, 1, tzinfo=UTC)
        mock_job.updated_at = datetime(2025, 1, 1, tzinfo=UTC)
        mock_job.error = None
        mock_job.scheduled_for = None
        mock_job.transaction_id = None
        mock_job.recovery_action = RecoveryAction.NONE
        mock_job.revision = 0

        with (
            patch("file_organizer.web.organize_routes.get_job", return_value=mock_job),
            patch("file_organizer.web.organize_routes._get_job_metadata", return_value={}),
        ):
            view = _build_job_view("job-queued")

        assert view is not None
        assert view["can_cancel"] is True


# ---------------------------------------------------------------------------
# _list_organize_jobs
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestListOrganizeJobs:
    """Test _list_organize_jobs."""

    def test_empty_list(self):
        """Verifies an empty job list is returned when no jobs exist."""
        from file_organizer.web.organize_routes import _list_organize_jobs

        with patch("file_organizer.web.organize_routes.list_jobs", return_value=[]):
            result = _list_organize_jobs()
        assert result == []

    def test_status_filter(self):
        """Verifies only jobs matching the requested status filter are returned."""
        from file_organizer.web.organize_routes import _list_organize_jobs

        job1 = MagicMock()
        job1.job_id = "j1"
        job1.status = "completed"
        job2 = MagicMock()
        job2.job_id = "j2"
        job2.status = "failed"

        with (
            patch("file_organizer.web.organize_routes.list_jobs", return_value=[job1, job2]),
            patch("file_organizer.web.organize_routes._build_job_view") as mock_view,
        ):
            mock_view.return_value = {"status": "completed"}
            result = _list_organize_jobs(status_filter="completed")

        # Only job1 should match the filter
        assert len(result) == 1  # only job1 passes status_filter='completed'; job2 is 'failed'

    def test_all_filter(self):
        """Verifies all jobs are returned when status_filter is 'all'."""
        from file_organizer.web.organize_routes import _list_organize_jobs

        job1 = MagicMock()
        job1.job_id = "j1"
        job1.status = "completed"

        with (
            patch("file_organizer.web.organize_routes.list_jobs", return_value=[job1]),
            patch(
                "file_organizer.web.organize_routes._build_job_view",
                return_value={"status": "completed"},
            ),
        ):
            result = _list_organize_jobs(status_filter="all")

        assert len(result) == 1


# ---------------------------------------------------------------------------
# _build_organize_stats
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBuildOrganizeStats:
    """Test _build_organize_stats."""

    def test_empty_stats(self):
        """Verifies stats with no jobs returns zeroed totals and 0.0 success rate."""
        from file_organizer.web.organize_routes import _build_organize_stats

        with patch("file_organizer.web.organize_routes._list_organize_jobs", return_value=[]):
            stats = _build_organize_stats()

        assert stats["total_jobs"] == 0
        assert stats["success_rate"] == 0.0
        assert stats["total_files"] == 0

    def test_with_jobs(self):
        """Verifies stats correctly aggregate counts, file totals, success rate, and methodology breakdown."""
        from file_organizer.web.organize_routes import _build_organize_stats

        jobs = [
            {"status": "completed", "processed_files": 10, "methodology_label": "PARA"},
            {"status": "completed", "processed_files": 5, "methodology_label": "PARA"},
            {"status": "failed", "processed_files": 0, "methodology_label": "Content-Based"},
        ]

        with patch("file_organizer.web.organize_routes._list_organize_jobs", return_value=jobs):
            stats = _build_organize_stats()

        assert stats["total_jobs"] == 3
        assert stats["completed_jobs"] == 2
        assert stats["failed_jobs"] == 1
        assert stats["total_files"] == 15
        assert stats["success_rate"] == pytest.approx(66.666, rel=0.01)
        assert stats["methodology_counts"]["PARA"] == 2


# ---------------------------------------------------------------------------
# _cancel_scheduled_job
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCancelScheduledJob:
    """Test _cancel_scheduled_job."""

    def test_cancel_existing_timer(self):
        """Verifies cancelling an existing scheduled job cancels the timer and removes it from the store."""
        from file_organizer.web.organize_routes import _SCHEDULED_TIMERS

        mock_timer = MagicMock(spec=Timer)
        _SCHEDULED_TIMERS["cancel-test"] = mock_timer

        result = _cancel_scheduled_job("cancel-test")

        assert result is True
        mock_timer.cancel.assert_called_once()
        assert "cancel-test" not in _SCHEDULED_TIMERS

    def test_cancel_nonexistent_timer(self):
        """Verifies cancelling a job with no scheduled timer returns False."""
        result = _cancel_scheduled_job("nonexistent-timer")
        assert result is False


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestModuleConstants:
    """Verify module-level constants are sensible."""

    def test_methodologies_dict(self):
        """Verifies the methodologies dict is exactly the canonical vocabulary.

        ``date_based`` was removed: it was a web-only dropdown option with no
        organizer implementation behind it anywhere in the codebase (#1538).
        """
        assert set(ORGANIZE_METHODOLOGIES) == {"none", "para", "jd"}

    def test_max_delay(self):
        """Verifies ORGANIZE_MAX_DELAY_MIN is positive and equals 7 days in minutes."""
        from file_organizer.web.organize_routes import ORGANIZE_MAX_DELAY_MIN

        assert ORGANIZE_MAX_DELAY_MIN > 0

        assert ORGANIZE_MAX_DELAY_MIN == 7 * 24 * 60
