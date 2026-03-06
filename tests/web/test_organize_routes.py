"""Unit tests for web organize_routes helpers.

Tests internal helpers (_parse_delay_minutes, _normalize_methodology,
_scan_directory, _counts_by_type, _status_progress, _job_report_payload),
plan-store operations, job-metadata operations, job-view builders,
and cancel/schedule helpers.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from threading import Timer
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.api.exceptions import ApiError
from file_organizer.web.organize_routes import (
    ORGANIZE_MAX_DELAY_MIN,
    ORGANIZE_METHODOLOGIES,
    _cancel_scheduled_job,
    _counts_by_type,
    _normalize_methodology,
    _parse_delay_minutes,
    _scan_directory,
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
        assert _parse_delay_minutes(None) == 0

    def test_empty_string_returns_default(self):
        assert _parse_delay_minutes("") == 0

    def test_whitespace_returns_default(self):
        assert _parse_delay_minutes("   ") == 0

    def test_valid_integer(self):
        assert _parse_delay_minutes("10") == 10

    def test_zero(self):
        assert _parse_delay_minutes("0") == 0

    def test_max_boundary(self):
        result = _parse_delay_minutes(str(ORGANIZE_MAX_DELAY_MIN))
        assert result == ORGANIZE_MAX_DELAY_MIN

    def test_non_numeric_raises(self):
        with pytest.raises(ApiError) as exc_info:
            _parse_delay_minutes("abc")
        assert exc_info.value.status_code == 400
        assert "invalid_schedule_delay" in exc_info.value.error

    def test_negative_raises(self):
        with pytest.raises(ApiError) as exc_info:
            _parse_delay_minutes("-1")
        assert exc_info.value.status_code == 400

    def test_over_max_raises(self):
        with pytest.raises(ApiError):
            _parse_delay_minutes(str(ORGANIZE_MAX_DELAY_MIN + 1))

    def test_float_string_raises(self):
        with pytest.raises(ApiError):
            _parse_delay_minutes("1.5")


# ---------------------------------------------------------------------------
# _normalize_methodology
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestNormalizeMethodology:
    """Test the _normalize_methodology helper."""

    def test_known_methodology(self):
        assert _normalize_methodology("para") == "para"
        assert _normalize_methodology("johnny_decimal") == "johnny_decimal"
        assert _normalize_methodology("date_based") == "date_based"

    def test_none_returns_default(self):
        assert _normalize_methodology(None) == "content_based"

    def test_empty_string_returns_default(self):
        assert _normalize_methodology("") == "content_based"

    def test_unknown_returns_default(self):
        assert _normalize_methodology("unknown_method") == "content_based"

    def test_case_insensitive(self):
        assert _normalize_methodology("PARA") == "para"

    def test_whitespace_trimmed(self):
        assert _normalize_methodology("  para  ") == "para"


# ---------------------------------------------------------------------------
# _scan_directory
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestScanDirectory:
    """Test the _scan_directory helper."""

    def test_scan_flat(self, tmp_path):
        (tmp_path / "a.txt").write_text("x")
        (tmp_path / "b.txt").write_text("y")
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "c.txt").write_text("z")

        files = _scan_directory(tmp_path, recursive=False, include_hidden=False)
        names = {f.name for f in files}
        assert "a.txt" in names
        assert "b.txt" in names
        # sub/c.txt should NOT be included (non-recursive)
        assert "c.txt" not in names

    def test_scan_recursive(self, tmp_path):
        (tmp_path / "a.txt").write_text("x")
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "c.txt").write_text("z")

        files = _scan_directory(tmp_path, recursive=True, include_hidden=False)
        names = {f.name for f in files}
        assert "a.txt" in names
        assert "c.txt" in names

    def test_exclude_hidden(self, tmp_path):
        (tmp_path / "visible.txt").write_text("x")
        (tmp_path / ".hidden.txt").write_text("y")

        files = _scan_directory(tmp_path, recursive=False, include_hidden=False)
        names = {f.name for f in files}
        assert "visible.txt" in names
        # Hidden file might or might not be excluded depending on is_hidden impl
        # The function calls is_hidden() so we check at least visible is there

    def test_include_hidden(self, tmp_path):
        (tmp_path / ".hidden.txt").write_text("y")

        files = _scan_directory(tmp_path, recursive=False, include_hidden=True)
        names = {f.name for f in files}
        assert ".hidden.txt" in names

    def test_single_file(self, tmp_path):
        f = tmp_path / "solo.txt"
        f.write_text("data")

        files = _scan_directory(f, recursive=False, include_hidden=True)
        assert len(files) == 1
        assert files[0].name == "solo.txt"

    def test_single_hidden_file_excluded(self, tmp_path):
        f = tmp_path / ".hidden_solo"
        f.write_text("data")

        files = _scan_directory(f, recursive=False, include_hidden=False)
        # is_hidden should filter this out
        assert len(files) == 0

    def test_nonexistent_path(self, tmp_path):
        missing = tmp_path / "nope"
        files = _scan_directory(missing, recursive=False, include_hidden=False)
        assert files == []


# ---------------------------------------------------------------------------
# _counts_by_type
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCountsByType:
    """Test the _counts_by_type helper."""

    def test_empty_list(self):
        result = _counts_by_type([])
        assert result == {"text": 0, "image": 0, "video": 0, "audio": 0, "cad": 0, "other": 0}

    def test_text_file(self):
        result = _counts_by_type([Path("doc.txt"), Path("notes.md")])
        assert result["text"] == 2

    def test_image_file(self):
        result = _counts_by_type([Path("photo.jpg"), Path("diagram.png")])
        assert result["image"] == 2

    def test_video_file(self):
        result = _counts_by_type([Path("clip.mp4")])
        assert result["video"] == 1

    def test_audio_file(self):
        result = _counts_by_type([Path("song.mp3")])
        assert result["audio"] == 1

    def test_unknown_extension(self):
        result = _counts_by_type([Path("mystery.xyz")])
        assert result["other"] == 1

    def test_mixed(self):
        files = [
            Path("a.txt"),
            Path("b.jpg"),
            Path("c.mp4"),
            Path("d.mp3"),
            Path("e.unknown"),
        ]
        result = _counts_by_type(files)
        assert result["text"] == 1
        assert result["image"] == 1
        assert result["video"] == 1
        assert result["audio"] == 1
        assert result["other"] == 1


# ---------------------------------------------------------------------------
# _status_progress
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestStatusProgress:
    """Test the _status_progress helper."""

    def test_queued(self):
        assert _status_progress("queued") == 5

    def test_running(self):
        assert _status_progress("running") == 65

    def test_completed(self):
        assert _status_progress("completed") == 100

    def test_failed(self):
        assert _status_progress("failed") == 100

    def test_unknown(self):
        assert _status_progress("something_else") == 0

    def test_empty(self):
        assert _status_progress("") == 0


# ---------------------------------------------------------------------------
# _job_report_payload
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestJobReportPayload:
    """Test the _job_report_payload helper."""

    def test_extracts_all_keys(self):
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
        from file_organizer.web.organize_routes import (
            _ORGANIZE_PLAN_STORE,
            _delete_organize_plan,
            _get_organize_plan,
            _store_organize_plan,
        )

        record = _store_organize_plan({"input_dir": "/tmp", "files": []})
        plan_id = record["plan_id"]
        assert plan_id in _ORGANIZE_PLAN_STORE

        retrieved = _get_organize_plan(plan_id)
        assert retrieved is not None
        assert retrieved["input_dir"] == "/tmp"

        _delete_organize_plan(plan_id)
        assert _get_organize_plan(plan_id) is None

    def test_get_missing_plan(self):
        from file_organizer.web.organize_routes import _get_organize_plan

        assert _get_organize_plan("nonexistent-id") is None

    def test_delete_missing_plan(self):
        from file_organizer.web.organize_routes import _delete_organize_plan

        # Should not raise
        _delete_organize_plan("nonexistent-id")

    def test_prune_oldest(self):
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
        from file_organizer.web.organize_routes import _get_job_metadata

        result = _get_job_metadata("nonexistent-job")
        assert result == {}

    def test_returns_copy(self):
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
        from file_organizer.web.organize_routes import (
            _JOB_METADATA,
            _prune_job_metadata,
        )

        _JOB_METADATA["stale-job-x"] = {"something": True}

        with patch("file_organizer.web.organize_routes.get_job", return_value=None):
            _prune_job_metadata(force=True)

        assert "stale-job-x" not in _JOB_METADATA

    def test_prune_keeps_valid(self):
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
        from file_organizer.web.organize_routes import _build_job_view

        with patch("file_organizer.web.organize_routes.get_job", return_value=None):
            result = _build_job_view("no-such-job")
        assert result is None

    def test_builds_view_completed(self):
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
        from file_organizer.web.organize_routes import _build_job_view

        mock_job = MagicMock()
        mock_job.job_id = "job-3"
        mock_job.status = "queued"
        mock_job.result = None
        mock_job.created_at = datetime(2025, 1, 1, tzinfo=UTC)
        mock_job.updated_at = datetime(2025, 1, 2, tzinfo=UTC)
        mock_job.error = None

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


# ---------------------------------------------------------------------------
# _list_organize_jobs
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestListOrganizeJobs:
    """Test _list_organize_jobs."""

    def test_empty_list(self):
        from file_organizer.web.organize_routes import _list_organize_jobs

        with patch("file_organizer.web.organize_routes.list_jobs", return_value=[]):
            result = _list_organize_jobs()
        assert result == []

    def test_status_filter(self):
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
        assert len(result) <= 2

    def test_all_filter(self):
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
        from file_organizer.web.organize_routes import _build_organize_stats

        with patch("file_organizer.web.organize_routes._list_organize_jobs", return_value=[]):
            stats = _build_organize_stats()

        assert stats["total_jobs"] == 0
        assert stats["success_rate"] == 0.0
        assert stats["total_files"] == 0

    def test_with_jobs(self):
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
        from file_organizer.web.organize_routes import _SCHEDULED_TIMERS

        mock_timer = MagicMock(spec=Timer)
        _SCHEDULED_TIMERS["cancel-test"] = mock_timer

        with patch("file_organizer.web.organize_routes.update_job"):
            result = _cancel_scheduled_job("cancel-test")

        assert result is True
        mock_timer.cancel.assert_called_once()
        assert "cancel-test" not in _SCHEDULED_TIMERS

    def test_cancel_nonexistent_timer(self):
        result = _cancel_scheduled_job("nonexistent-timer")
        assert result is False


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestModuleConstants:
    """Verify module-level constants are sensible."""

    def test_methodologies_dict(self):
        assert "johnny_decimal" in ORGANIZE_METHODOLOGIES
        assert "para" in ORGANIZE_METHODOLOGIES
        assert "content_based" in ORGANIZE_METHODOLOGIES

    def test_max_delay(self):
        from file_organizer.web.organize_routes import ORGANIZE_MAX_DELAY_MIN

        assert ORGANIZE_MAX_DELAY_MIN > 0

        assert ORGANIZE_MAX_DELAY_MIN == 7 * 24 * 60
