"""Integration tests for parallel processing, analytics, config manager, and related modules."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.ci]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_file_result(path: Path, success: bool = True, error: str | None = None) -> Any:
    """Build a FileResult for use in mock returns."""
    from file_organizer.parallel.result import FileResult

    return FileResult(path=path, success=success, error=error, duration_ms=1.0)


def _make_batch_result(total: int = 1, succeeded: int = 1, failed: int = 0) -> Any:
    """Build a minimal BatchResult."""
    from file_organizer.parallel.result import BatchResult

    return BatchResult(total=total, succeeded=succeeded, failed=failed, results=[])


# ===========================================================================
# TestResumableProcessor
# ===========================================================================


class TestResumableProcessor:
    """Tests for file_organizer.parallel.resume.ResumableProcessor."""

    def test_process_with_resume_creates_job_state(self, tmp_path: Path) -> None:
        from file_organizer.parallel.resume import ResumableProcessor

        mock_persistence = MagicMock()
        mock_checkpoint_mgr = MagicMock()
        mock_processor = MagicMock()

        saved_jobs: list[Any] = []
        mock_persistence.save_job.side_effect = saved_jobs.append

        file1 = tmp_path / "a.txt"
        file1.write_text("content")

        mock_checkpoint_mgr.create_checkpoint.return_value = MagicMock(
            pending_paths=[], completed_paths=[]
        )
        mock_processor.process_batch_iter.return_value = iter(
            [_make_file_result(file1, success=True)]
        )

        rp = ResumableProcessor(
            persistence=mock_persistence,
            checkpoint_mgr=mock_checkpoint_mgr,
        )
        rp._processor = mock_processor

        rp.process_with_resume([file1], lambda p: "ok", job_id="test-job-1")

        assert len(saved_jobs) >= 1
        assert saved_jobs[0].id == "test-job-1"
        assert saved_jobs[0].total_files == 1

    def test_process_with_resume_autogenerates_job_id(self, tmp_path: Path) -> None:
        from file_organizer.parallel.resume import ResumableProcessor

        mock_persistence = MagicMock()
        mock_checkpoint_mgr = MagicMock()
        mock_processor = MagicMock()

        saved_ids: list[str] = []
        mock_persistence.save_job.side_effect = lambda j: saved_ids.append(j.id)
        mock_checkpoint_mgr.create_checkpoint.return_value = MagicMock(
            pending_paths=[], completed_paths=[]
        )
        mock_processor.process_batch_iter.return_value = iter([])

        rp = ResumableProcessor(
            persistence=mock_persistence,
            checkpoint_mgr=mock_checkpoint_mgr,
        )
        rp._processor = mock_processor

        rp.process_with_resume([], lambda p: "ok")

        assert len(saved_ids) >= 1
        assert len(saved_ids[0]) > 0

    def test_process_with_resume_returns_batch_result(self, tmp_path: Path) -> None:
        from file_organizer.parallel.result import BatchResult
        from file_organizer.parallel.resume import ResumableProcessor

        mock_persistence = MagicMock()
        mock_checkpoint_mgr = MagicMock()
        mock_processor = MagicMock()

        file1 = tmp_path / "b.txt"
        file1.write_text("hello")

        mock_checkpoint_mgr.create_checkpoint.return_value = MagicMock(
            pending_paths=[], completed_paths=[]
        )
        mock_processor.process_batch_iter.return_value = iter(
            [_make_file_result(file1, success=True)]
        )

        rp = ResumableProcessor(
            persistence=mock_persistence,
            checkpoint_mgr=mock_checkpoint_mgr,
        )
        rp._processor = mock_processor

        result = rp.process_with_resume([file1], lambda p: "ok", job_id="r1")

        assert isinstance(result, BatchResult)
        assert result.total == 1
        assert result.succeeded == 1

    def test_process_with_resume_counts_failures(self, tmp_path: Path) -> None:
        from file_organizer.parallel.resume import ResumableProcessor

        mock_persistence = MagicMock()
        mock_checkpoint_mgr = MagicMock()
        mock_processor = MagicMock()

        file1 = tmp_path / "bad.txt"
        file1.write_text("x")

        mock_checkpoint_mgr.create_checkpoint.return_value = MagicMock(
            pending_paths=[], completed_paths=[]
        )
        mock_processor.process_batch_iter.return_value = iter(
            [_make_file_result(file1, success=False, error="boom")]
        )

        rp = ResumableProcessor(
            persistence=mock_persistence,
            checkpoint_mgr=mock_checkpoint_mgr,
        )
        rp._processor = mock_processor

        result = rp.process_with_resume([file1], lambda p: None, job_id="fail-job")

        assert result.failed == 1
        assert result.succeeded == 0

    def test_resume_job_raises_when_job_missing(self) -> None:
        from file_organizer.parallel.resume import ResumableProcessor

        mock_persistence = MagicMock()
        mock_persistence.load_job.return_value = None
        mock_checkpoint_mgr = MagicMock()

        rp = ResumableProcessor(
            persistence=mock_persistence,
            checkpoint_mgr=mock_checkpoint_mgr,
        )

        with pytest.raises(ValueError, match="Job not found"):
            rp.resume_job("nonexistent-id", lambda p: "ok")

    def test_resume_job_raises_when_checkpoint_missing(self) -> None:
        from datetime import UTC, datetime

        from file_organizer.parallel.models import JobState, JobStatus
        from file_organizer.parallel.resume import ResumableProcessor

        mock_persistence = MagicMock()
        now = datetime.now(UTC)
        mock_persistence.load_job.return_value = JobState(
            id="j1",
            status=JobStatus.RUNNING,
            created=now,
            updated=now,
        )
        mock_checkpoint_mgr = MagicMock()
        mock_checkpoint_mgr.load_checkpoint.return_value = None

        rp = ResumableProcessor(
            persistence=mock_persistence,
            checkpoint_mgr=mock_checkpoint_mgr,
        )

        with pytest.raises(ValueError, match="Checkpoint not found"):
            rp.resume_job("j1", lambda p: "ok")

    def test_resume_job_skips_completed_files(self, tmp_path: Path) -> None:
        from datetime import UTC, datetime

        from file_organizer.parallel.models import Checkpoint, JobState, JobStatus
        from file_organizer.parallel.result import BatchResult
        from file_organizer.parallel.resume import ResumableProcessor

        now = datetime.now(UTC)
        file_done = tmp_path / "done.txt"
        file_done.write_text("done")

        mock_persistence = MagicMock()
        mock_persistence.load_job.return_value = JobState(
            id="j2",
            status=JobStatus.RUNNING,
            created=now,
            updated=now,
            total_files=1,
        )
        checkpoint = Checkpoint(
            job_id="j2",
            completed_paths=[file_done],
            pending_paths=[],
        )
        mock_checkpoint_mgr = MagicMock()
        mock_checkpoint_mgr.load_checkpoint.return_value = checkpoint
        mock_checkpoint_mgr.has_file_changed.return_value = False
        mock_checkpoint_mgr.create_checkpoint.return_value = checkpoint
        mock_processor = MagicMock()
        mock_processor.process_batch_iter.return_value = iter([])

        rp = ResumableProcessor(
            persistence=mock_persistence,
            checkpoint_mgr=mock_checkpoint_mgr,
        )
        rp._processor = mock_processor

        result = rp.resume_job("j2", lambda p: "ok")

        assert isinstance(result, BatchResult)
        assert result.succeeded == 1
        assert result.failed == 0

    def test_resume_job_reprocesses_modified_files(self, tmp_path: Path) -> None:
        from datetime import UTC, datetime

        from file_organizer.parallel.models import Checkpoint, JobState, JobStatus
        from file_organizer.parallel.resume import ResumableProcessor

        now = datetime.now(UTC)
        file_mod = tmp_path / "modified.txt"
        file_mod.write_text("modified content")

        mock_persistence = MagicMock()
        mock_persistence.load_job.return_value = JobState(
            id="j3",
            status=JobStatus.RUNNING,
            created=now,
            updated=now,
            total_files=1,
        )
        checkpoint = Checkpoint(
            job_id="j3",
            completed_paths=[file_mod],
            pending_paths=[],
        )
        new_checkpoint = Checkpoint(
            job_id="j3",
            completed_paths=[],
            pending_paths=[file_mod],
        )
        mock_checkpoint_mgr = MagicMock()
        mock_checkpoint_mgr.load_checkpoint.return_value = checkpoint
        mock_checkpoint_mgr.has_file_changed.return_value = True
        mock_checkpoint_mgr.create_checkpoint.return_value = new_checkpoint
        mock_processor = MagicMock()
        mock_processor.process_batch_iter.return_value = iter(
            [_make_file_result(file_mod, success=True)]
        )

        rp = ResumableProcessor(
            persistence=mock_persistence,
            checkpoint_mgr=mock_checkpoint_mgr,
        )
        rp._processor = mock_processor

        result = rp.resume_job("j3", lambda p: "ok")

        assert result.succeeded == 1
        mock_checkpoint_mgr.load_checkpoint.assert_called_once_with("j3")
        mock_checkpoint_mgr.has_file_changed.assert_called_once_with(checkpoint, file_mod)
        mock_checkpoint_mgr.create_checkpoint.assert_called_once_with(
            job_id="j3",
            completed_files=[],
            pending_files=[file_mod],
        )
        mock_processor.process_batch_iter.assert_called_once()
        files_arg, process_fn_arg = mock_processor.process_batch_iter.call_args.args
        assert files_arg == [file_mod]
        assert callable(process_fn_arg)

    def test_process_and_checkpoint_marks_job_completed(self, tmp_path: Path) -> None:
        from datetime import UTC, datetime

        from file_organizer.parallel.models import JobState, JobStatus
        from file_organizer.parallel.resume import ResumableProcessor

        now = datetime.now(UTC)
        f = tmp_path / "f.txt"
        f.write_text("x")

        saved_jobs: list[Any] = []
        mock_persistence = MagicMock()
        mock_persistence.save_job.side_effect = saved_jobs.append
        mock_checkpoint_mgr = MagicMock()
        mock_checkpoint_mgr.load_checkpoint.return_value = None
        mock_processor = MagicMock()
        mock_processor.process_batch_iter.return_value = iter([_make_file_result(f, success=True)])

        job = JobState(id="j4", status=JobStatus.RUNNING, created=now, updated=now, total_files=1)

        rp = ResumableProcessor(
            persistence=mock_persistence,
            checkpoint_mgr=mock_checkpoint_mgr,
        )
        rp._processor = mock_processor

        rp._process_and_checkpoint(job=job, files=[f], process_fn=lambda p: "ok")

        final_job = saved_jobs[-1]
        assert final_job.status == JobStatus.COMPLETED

    def test_process_and_checkpoint_marks_job_failed_on_exception(self, tmp_path: Path) -> None:
        from datetime import UTC, datetime

        from file_organizer.parallel.models import JobState, JobStatus
        from file_organizer.parallel.resume import ResumableProcessor

        now = datetime.now(UTC)
        f = tmp_path / "f.txt"
        f.write_text("x")

        saved_jobs: list[Any] = []
        mock_persistence = MagicMock()
        mock_persistence.save_job.side_effect = saved_jobs.append
        mock_checkpoint_mgr = MagicMock()
        mock_checkpoint_mgr.load_checkpoint.return_value = None
        mock_processor = MagicMock()
        mock_processor.process_batch_iter.side_effect = RuntimeError("crash")

        job = JobState(id="j5", status=JobStatus.RUNNING, created=now, updated=now, total_files=1)

        rp = ResumableProcessor(
            persistence=mock_persistence,
            checkpoint_mgr=mock_checkpoint_mgr,
        )
        rp._processor = mock_processor

        with pytest.raises(RuntimeError, match="crash"):
            rp._process_and_checkpoint(job=job, files=[f], process_fn=lambda p: None)

        failed_job = next(j for j in saved_jobs if j.status == JobStatus.FAILED)
        assert failed_job.error == "crash"

    def test_process_with_resume_empty_file_list(self) -> None:
        from file_organizer.parallel.result import BatchResult
        from file_organizer.parallel.resume import ResumableProcessor

        mock_persistence = MagicMock()
        mock_checkpoint_mgr = MagicMock()
        mock_processor = MagicMock()

        mock_checkpoint_mgr.create_checkpoint.return_value = MagicMock(
            pending_paths=[], completed_paths=[]
        )
        mock_processor.process_batch_iter.return_value = iter([])

        rp = ResumableProcessor(
            persistence=mock_persistence,
            checkpoint_mgr=mock_checkpoint_mgr,
        )
        rp._processor = mock_processor

        result = rp.process_with_resume([], lambda p: None, job_id="empty")

        assert isinstance(result, BatchResult)
        assert result.total == 0
        assert result.succeeded == 0

    def test_process_with_resume_updates_checkpoint_per_file(self, tmp_path: Path) -> None:
        from file_organizer.parallel.resume import ResumableProcessor

        mock_persistence = MagicMock()
        mock_checkpoint_mgr = MagicMock()
        mock_processor = MagicMock()

        checkpoint_mock = MagicMock(pending_paths=[], completed_paths=[])
        mock_checkpoint_mgr.create_checkpoint.return_value = checkpoint_mock

        files = []
        for i in range(3):
            f = tmp_path / f"f{i}.txt"
            f.write_text("content")
            files.append(f)

        mock_processor.process_batch_iter.return_value = iter(
            [_make_file_result(f, success=True) for f in files]
        )

        rp = ResumableProcessor(
            persistence=mock_persistence,
            checkpoint_mgr=mock_checkpoint_mgr,
        )
        rp._processor = mock_processor

        rp.process_with_resume(files, lambda p: "ok", job_id="multi")

        # update_checkpoint_state called once per successful file
        assert mock_checkpoint_mgr.update_checkpoint_state.call_count == 3

    def test_default_constructor_creates_internal_components(self) -> None:
        from file_organizer.parallel.checkpoint import CheckpointManager
        from file_organizer.parallel.persistence import JobPersistence
        from file_organizer.parallel.processor import ParallelProcessor
        from file_organizer.parallel.resume import ResumableProcessor

        rp = ResumableProcessor()

        assert isinstance(rp._processor, ParallelProcessor)
        assert isinstance(rp._persistence, JobPersistence)
        assert isinstance(rp._checkpoint_mgr, CheckpointManager)

    def test_process_with_resume_saves_job_at_end(self, tmp_path: Path) -> None:
        from file_organizer.parallel.models import JobStatus
        from file_organizer.parallel.resume import ResumableProcessor

        mock_persistence = MagicMock()
        mock_checkpoint_mgr = MagicMock()
        mock_processor = MagicMock()

        saved_statuses: list[str] = []
        mock_persistence.save_job.side_effect = lambda j: saved_statuses.append(str(j.status))
        mock_checkpoint_mgr.create_checkpoint.return_value = MagicMock(
            pending_paths=[], completed_paths=[]
        )
        mock_processor.process_batch_iter.return_value = iter([])

        rp = ResumableProcessor(
            persistence=mock_persistence,
            checkpoint_mgr=mock_checkpoint_mgr,
        )
        rp._processor = mock_processor

        rp.process_with_resume([], lambda p: None, job_id="save-test")

        # Last saved status should be COMPLETED
        assert saved_statuses[-1] == str(JobStatus.COMPLETED)

    def test_resume_job_pending_files_reprocessed(self, tmp_path: Path) -> None:
        from datetime import UTC, datetime

        from file_organizer.parallel.models import Checkpoint, JobState, JobStatus
        from file_organizer.parallel.resume import ResumableProcessor

        now = datetime.now(UTC)
        pending_file = tmp_path / "pending.txt"
        pending_file.write_text("data")

        mock_persistence = MagicMock()
        mock_persistence.load_job.return_value = JobState(
            id="j6",
            status=JobStatus.RUNNING,
            created=now,
            updated=now,
            total_files=1,
        )
        checkpoint = Checkpoint(
            job_id="j6",
            completed_paths=[],
            pending_paths=[pending_file],
        )
        mock_checkpoint_mgr = MagicMock()
        mock_checkpoint_mgr.load_checkpoint.return_value = checkpoint
        mock_checkpoint_mgr.create_checkpoint.return_value = checkpoint
        mock_processor = MagicMock()
        mock_processor.process_batch_iter.return_value = iter(
            [_make_file_result(pending_file, success=True)]
        )

        rp = ResumableProcessor(
            persistence=mock_persistence,
            checkpoint_mgr=mock_checkpoint_mgr,
        )
        rp._processor = mock_processor

        result = rp.resume_job("j6", lambda p: "ok")

        assert result.succeeded == 1
        mock_checkpoint_mgr.load_checkpoint.assert_called_once_with("j6")
        mock_checkpoint_mgr.create_checkpoint.assert_called_once_with(
            job_id="j6",
            completed_files=[],
            pending_files=[pending_file],
        )
        mock_processor.process_batch_iter.assert_called_once()
        files_arg, process_fn_arg = mock_processor.process_batch_iter.call_args.args
        assert files_arg == [pending_file]
        assert callable(process_fn_arg)

    def test_process_and_checkpoint_failed_all_marks_failed(self, tmp_path: Path) -> None:
        from datetime import UTC, datetime

        from file_organizer.parallel.models import JobState, JobStatus
        from file_organizer.parallel.resume import ResumableProcessor

        now = datetime.now(UTC)
        f = tmp_path / "fail.txt"
        f.write_text("x")

        saved_jobs: list[Any] = []
        mock_persistence = MagicMock()
        mock_persistence.save_job.side_effect = saved_jobs.append
        mock_checkpoint_mgr = MagicMock()
        mock_checkpoint_mgr.load_checkpoint.return_value = None
        mock_processor = MagicMock()
        mock_processor.process_batch_iter.return_value = iter(
            [_make_file_result(f, success=False, error="failed")]
        )

        job = JobState(id="jf", status=JobStatus.RUNNING, created=now, updated=now, total_files=1)

        rp = ResumableProcessor(
            persistence=mock_persistence,
            checkpoint_mgr=mock_checkpoint_mgr,
        )
        rp._processor = mock_processor

        rp._process_and_checkpoint(job=job, files=[f], process_fn=lambda p: None)

        final_job = saved_jobs[-1]
        assert final_job.status == JobStatus.FAILED

    def test_process_with_resume_mixed_results(self, tmp_path: Path) -> None:
        from file_organizer.parallel.resume import ResumableProcessor

        mock_persistence = MagicMock()
        mock_checkpoint_mgr = MagicMock()
        mock_processor = MagicMock()

        files = []
        results_iter = []
        for i in range(4):
            f = tmp_path / f"mix{i}.txt"
            f.write_text("x")
            files.append(f)
            success = i % 2 == 0
            results_iter.append(
                _make_file_result(f, success=success, error=None if success else "err")
            )

        mock_checkpoint_mgr.create_checkpoint.return_value = MagicMock(
            pending_paths=[], completed_paths=[]
        )
        mock_processor.process_batch_iter.return_value = iter(results_iter)

        rp = ResumableProcessor(
            persistence=mock_persistence,
            checkpoint_mgr=mock_checkpoint_mgr,
        )
        rp._processor = mock_processor

        result = rp.process_with_resume(files, lambda p: None, job_id="mix")

        assert result.succeeded == 2
        assert result.failed == 2
        assert result.total == 4

    def test_resume_job_adjusts_total_to_full_job(self, tmp_path: Path) -> None:
        from datetime import UTC, datetime

        from file_organizer.parallel.models import Checkpoint, JobState, JobStatus
        from file_organizer.parallel.resume import ResumableProcessor

        now = datetime.now(UTC)
        done_file = tmp_path / "done2.txt"
        done_file.write_text("x")
        pending_file = tmp_path / "pend2.txt"
        pending_file.write_text("y")

        mock_persistence = MagicMock()
        mock_persistence.load_job.return_value = JobState(
            id="j7",
            status=JobStatus.RUNNING,
            created=now,
            updated=now,
            total_files=2,
        )
        checkpoint = Checkpoint(
            job_id="j7",
            completed_paths=[done_file],
            pending_paths=[pending_file],
        )
        mock_checkpoint_mgr = MagicMock()
        mock_checkpoint_mgr.load_checkpoint.return_value = checkpoint
        mock_checkpoint_mgr.has_file_changed.return_value = False
        mock_checkpoint_mgr.create_checkpoint.return_value = checkpoint
        mock_processor = MagicMock()
        mock_processor.process_batch_iter.return_value = iter(
            [_make_file_result(pending_file, success=True)]
        )

        rp = ResumableProcessor(
            persistence=mock_persistence,
            checkpoint_mgr=mock_checkpoint_mgr,
        )
        rp._processor = mock_processor

        result = rp.resume_job("j7", lambda p: "ok")

        assert result.total == 2
        assert result.succeeded == 2

    def test_process_with_resume_saves_checkpoint_at_end(self, tmp_path: Path) -> None:
        from file_organizer.parallel.resume import ResumableProcessor

        mock_persistence = MagicMock()
        mock_checkpoint_mgr = MagicMock()
        mock_processor = MagicMock()

        checkpoint_mock = MagicMock(pending_paths=[], completed_paths=[])
        mock_checkpoint_mgr.create_checkpoint.return_value = checkpoint_mock
        mock_processor.process_batch_iter.return_value = iter([])

        rp = ResumableProcessor(
            persistence=mock_persistence,
            checkpoint_mgr=mock_checkpoint_mgr,
        )
        rp._processor = mock_processor

        rp.process_with_resume([], lambda p: None, job_id="ckpt-end")

        mock_checkpoint_mgr.save_checkpoint.assert_called_once_with(checkpoint_mock)

    def test_process_with_resume_sets_total_files_in_job(self, tmp_path: Path) -> None:
        from file_organizer.parallel.resume import ResumableProcessor

        mock_persistence = MagicMock()
        mock_checkpoint_mgr = MagicMock()
        mock_processor = MagicMock()

        captured: list[Any] = []
        mock_persistence.save_job.side_effect = captured.append
        mock_checkpoint_mgr.create_checkpoint.return_value = MagicMock(
            pending_paths=[], completed_paths=[]
        )
        mock_processor.process_batch_iter.return_value = iter([])

        files = [tmp_path / f"f{i}.txt" for i in range(5)]
        for f in files:
            f.write_text("x")

        rp = ResumableProcessor(
            persistence=mock_persistence,
            checkpoint_mgr=mock_checkpoint_mgr,
        )
        rp._processor = mock_processor

        rp.process_with_resume(files, lambda p: None, job_id="total-test")

        first_saved = captured[0]
        assert first_saved.total_files == 5

    def test_process_with_resume_job_id_passed_to_checkpoint_mgr(self, tmp_path: Path) -> None:
        from file_organizer.parallel.resume import ResumableProcessor

        mock_persistence = MagicMock()
        mock_checkpoint_mgr = MagicMock()
        mock_processor = MagicMock()

        checkpoint_mock = MagicMock(pending_paths=[], completed_paths=[])
        mock_checkpoint_mgr.create_checkpoint.return_value = checkpoint_mock
        mock_processor.process_batch_iter.return_value = iter([])

        rp = ResumableProcessor(
            persistence=mock_persistence,
            checkpoint_mgr=mock_checkpoint_mgr,
        )
        rp._processor = mock_processor

        rp.process_with_resume([], lambda p: None, job_id="cp-test")

        call_kwargs = mock_checkpoint_mgr.create_checkpoint.call_args
        assert call_kwargs.kwargs.get("job_id") == "cp-test" or (
            call_kwargs.args and call_kwargs.args[0] == "cp-test"
        )

    def test_process_with_resume_error_propagates(self, tmp_path: Path) -> None:
        from file_organizer.parallel.resume import ResumableProcessor

        mock_persistence = MagicMock()
        mock_checkpoint_mgr = MagicMock()
        mock_processor = MagicMock()

        mock_checkpoint_mgr.create_checkpoint.side_effect = RuntimeError("setup fail")

        rp = ResumableProcessor(
            persistence=mock_persistence,
            checkpoint_mgr=mock_checkpoint_mgr,
        )
        rp._processor = mock_processor

        with pytest.raises(RuntimeError, match="setup fail"):
            rp.process_with_resume([], lambda p: None, job_id="err-test")

    def test_batch_result_summary_includes_counts(self, tmp_path: Path) -> None:
        from file_organizer.parallel.result import BatchResult, FileResult

        r = FileResult(path=tmp_path / "a.txt", success=False, error="oops", duration_ms=5.0)
        br = BatchResult(total=2, succeeded=1, failed=1, results=[r])
        summary = br.summary()

        assert "2" in summary
        assert "1" in summary
        assert "oops" in summary

    def test_file_result_str_success(self, tmp_path: Path) -> None:
        from file_organizer.parallel.result import FileResult

        f = FileResult(path=tmp_path / "ok.txt", success=True, duration_ms=10.0)
        s = str(f)

        assert "OK" in s
        assert "ok.txt" in s

    def test_file_result_str_failure(self, tmp_path: Path) -> None:
        from file_organizer.parallel.result import FileResult

        f = FileResult(path=tmp_path / "bad.txt", success=False, error="no perm", duration_ms=2.0)
        s = str(f)

        assert "FAIL" in s
        assert "no perm" in s

    def test_batch_result_summary_with_many_failures(self, tmp_path: Path) -> None:
        from file_organizer.parallel.result import BatchResult, FileResult

        results = [
            FileResult(path=tmp_path / f"f{i}.txt", success=False, error=f"err{i}")
            for i in range(7)
        ]
        br = BatchResult(total=7, succeeded=0, failed=7, results=results)
        summary = br.summary()

        assert "and" in summary  # "... and N more"


# ===========================================================================
# TestAnalyticsService
# ===========================================================================


class TestAnalyticsService:
    """Tests for file_organizer.services.analytics.analytics_service.AnalyticsService."""

    def test_calculate_time_saved_returns_time_savings(self) -> None:
        from file_organizer.models.analytics import TimeSavings
        from file_organizer.services.analytics.analytics_service import AnalyticsService

        svc = AnalyticsService(
            storage_analyzer=MagicMock(),
            metrics_calculator=MagicMock(),
        )
        result = svc.calculate_time_saved(total_files=10, duplicates_removed=2)

        assert isinstance(result, TimeSavings)
        assert result.total_operations == 10

    def test_calculate_time_saved_zero_duplicates(self) -> None:
        from file_organizer.services.analytics.analytics_service import AnalyticsService

        svc = AnalyticsService(
            storage_analyzer=MagicMock(),
            metrics_calculator=MagicMock(),
        )
        result = svc.calculate_time_saved(total_files=5, duplicates_removed=0)

        assert result.total_operations == 5
        assert result.automated_operations == 5

    def test_calculate_time_saved_time_values_positive(self) -> None:
        from file_organizer.services.analytics.analytics_service import AnalyticsService

        svc = AnalyticsService(
            storage_analyzer=MagicMock(),
            metrics_calculator=MagicMock(),
        )
        result = svc.calculate_time_saved(total_files=100, duplicates_removed=10)

        assert result.manual_time_seconds >= 0
        assert result.automated_time_seconds >= 0
        assert result.estimated_time_saved_seconds >= 0

    def test_calculate_time_saved_manual_time_greater_than_automated(self) -> None:
        from file_organizer.services.analytics.analytics_service import AnalyticsService

        svc = AnalyticsService(
            storage_analyzer=MagicMock(),
            metrics_calculator=MagicMock(),
        )
        result = svc.calculate_time_saved(total_files=50, duplicates_removed=5)

        # manual time (30s/file + 60s/dup) >> automated time (1s/file)
        assert result.manual_time_seconds > result.automated_time_seconds

    def test_get_duplicate_stats_empty_groups(self) -> None:
        from file_organizer.models.analytics import DuplicateStats
        from file_organizer.services.analytics.analytics_service import AnalyticsService

        svc = AnalyticsService(
            storage_analyzer=MagicMock(),
            metrics_calculator=MagicMock(),
        )
        result = svc.get_duplicate_stats(duplicate_groups=[], total_size=1000)

        assert isinstance(result, DuplicateStats)
        assert result.total_duplicates == 0
        assert result.duplicate_groups == 0
        assert result.space_wasted == 0

    def test_get_duplicate_stats_counts_extra_copies(self, tmp_path: Path) -> None:
        from file_organizer.services.analytics.analytics_service import AnalyticsService

        f1 = tmp_path / "dup1.txt"
        f2 = tmp_path / "dup2.txt"
        f1.write_text("same")
        f2.write_text("same")

        groups = [{"files": [str(f1), str(f2)]}]

        svc = AnalyticsService(
            storage_analyzer=MagicMock(),
            metrics_calculator=MagicMock(),
        )
        result = svc.get_duplicate_stats(duplicate_groups=groups, total_size=10000)

        # 2 files in group → 1 duplicate (extra copy)
        assert result.total_duplicates == 1
        assert result.duplicate_groups == 1

    def test_get_duplicate_stats_ignores_singleton_groups(self, tmp_path: Path) -> None:
        from file_organizer.services.analytics.analytics_service import AnalyticsService

        f1 = tmp_path / "single.txt"
        f1.write_text("unique")

        groups = [{"files": [str(f1)]}]  # only one file — not a duplicate

        svc = AnalyticsService(
            storage_analyzer=MagicMock(),
            metrics_calculator=MagicMock(),
        )
        result = svc.get_duplicate_stats(duplicate_groups=groups, total_size=5000)

        assert result.total_duplicates == 0
        assert result.duplicate_groups == 0

    def test_get_duplicate_stats_space_wasted_nonzero_for_existing_files(
        self, tmp_path: Path
    ) -> None:
        from file_organizer.services.analytics.analytics_service import AnalyticsService

        f1 = tmp_path / "big1.bin"
        f2 = tmp_path / "big2.bin"
        content = b"X" * 1024
        f1.write_bytes(content)
        f2.write_bytes(content)

        groups = [{"files": [str(f1), str(f2)]}]

        svc = AnalyticsService(
            storage_analyzer=MagicMock(),
            metrics_calculator=MagicMock(),
        )
        result = svc.get_duplicate_stats(duplicate_groups=groups, total_size=2048)

        assert result.space_wasted == 1024
        assert result.space_recoverable == 1024

    def test_get_storage_stats_delegates_to_analyzer(self, tmp_path: Path) -> None:
        from file_organizer.models.analytics import StorageStats
        from file_organizer.services.analytics.analytics_service import AnalyticsService

        mock_analyzer = MagicMock()
        expected = StorageStats(
            total_size=500,
            organized_size=500,
            saved_size=0,
            file_count=5,
            directory_count=2,
        )
        mock_analyzer.analyze_directory.return_value = expected

        svc = AnalyticsService(storage_analyzer=mock_analyzer, metrics_calculator=MagicMock())
        result = svc.get_storage_stats(tmp_path)

        assert result is expected
        mock_analyzer.analyze_directory.assert_called_once_with(tmp_path, None)

    def test_get_storage_stats_passes_max_depth(self, tmp_path: Path) -> None:
        from file_organizer.models.analytics import StorageStats
        from file_organizer.services.analytics.analytics_service import AnalyticsService

        mock_analyzer = MagicMock()
        mock_analyzer.analyze_directory.return_value = StorageStats(
            total_size=0, organized_size=0, saved_size=0, file_count=0, directory_count=0
        )

        svc = AnalyticsService(storage_analyzer=mock_analyzer, metrics_calculator=MagicMock())
        svc.get_storage_stats(tmp_path, max_depth=3)

        mock_analyzer.analyze_directory.assert_called_once_with(tmp_path, 3)

    def test_get_quality_metrics_returns_quality_metrics(self, tmp_path: Path) -> None:
        from file_organizer.models.analytics import QualityMetrics
        from file_organizer.services.analytics.analytics_service import AnalyticsService

        f = tmp_path / "doc.txt"
        f.write_text("hello world")

        mock_analyzer = MagicMock()
        mock_analyzer.walk_directory.return_value = [f]
        mock_calc = MagicMock()
        mock_calc.measure_naming_compliance.return_value = 0.9
        mock_calc.calculate_quality_score.return_value = 85.0

        svc = AnalyticsService(storage_analyzer=mock_analyzer, metrics_calculator=mock_calc)
        result = svc.get_quality_metrics(tmp_path)

        assert isinstance(result, QualityMetrics)
        assert result.naming_compliance == 0.9

    def test_get_quality_metrics_structure_consistency_in_range(self, tmp_path: Path) -> None:
        from file_organizer.services.analytics.analytics_service import AnalyticsService

        # file in subdirectory → organized
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        f = subdir / "doc.txt"
        f.write_text("hello")

        mock_analyzer = MagicMock()
        mock_analyzer.walk_directory.return_value = [f]
        mock_calc = MagicMock()
        mock_calc.measure_naming_compliance.return_value = 1.0
        mock_calc.calculate_quality_score.return_value = 90.0

        svc = AnalyticsService(storage_analyzer=mock_analyzer, metrics_calculator=mock_calc)
        result = svc.get_quality_metrics(tmp_path)

        assert 0.0 <= result.structure_consistency <= 1.0

    def test_get_quality_metrics_metadata_completeness_known_extensions(
        self, tmp_path: Path
    ) -> None:
        from file_organizer.services.analytics.analytics_service import AnalyticsService

        # .txt is a known extension
        f = tmp_path / "readme.txt"
        f.write_text("content")

        mock_analyzer = MagicMock()
        mock_analyzer.walk_directory.return_value = [f]
        mock_calc = MagicMock()
        mock_calc.measure_naming_compliance.return_value = 1.0
        mock_calc.calculate_quality_score.return_value = 95.0

        svc = AnalyticsService(storage_analyzer=mock_analyzer, metrics_calculator=mock_calc)
        result = svc.get_quality_metrics(tmp_path)

        # readme.txt has known extension and non-numeric stem → completeness == 1.0
        assert result.metadata_completeness == 1.0

    def test_get_quality_metrics_empty_directory(self, tmp_path: Path) -> None:
        from file_organizer.services.analytics.analytics_service import AnalyticsService

        mock_analyzer = MagicMock()
        mock_analyzer.walk_directory.return_value = []
        mock_calc = MagicMock()
        mock_calc.measure_naming_compliance.return_value = 0.0
        mock_calc.calculate_quality_score.return_value = 0.0

        svc = AnalyticsService(storage_analyzer=mock_analyzer, metrics_calculator=mock_calc)
        result = svc.get_quality_metrics(tmp_path)

        assert result.quality_score == 0.0
        assert result.naming_compliance == 0.0

    def test_export_dashboard_json(self, tmp_path: Path) -> None:
        import json
        from datetime import UTC, datetime

        from file_organizer.models.analytics import (
            AnalyticsDashboard,
            DuplicateStats,
            FileDistribution,
            QualityMetrics,
            StorageStats,
            TimeSavings,
        )
        from file_organizer.services.analytics.analytics_service import AnalyticsService

        dashboard = AnalyticsDashboard(
            storage_stats=StorageStats(
                total_size=100, organized_size=100, saved_size=0, file_count=1, directory_count=1
            ),
            file_distribution=FileDistribution(total_files=1),
            duplicate_stats=DuplicateStats(
                total_duplicates=0, duplicate_groups=0, space_wasted=0, space_recoverable=0
            ),
            quality_metrics=QualityMetrics(
                quality_score=80.0,
                naming_compliance=0.8,
                structure_consistency=0.8,
                metadata_completeness=0.8,
                categorization_accuracy=0.8,
            ),
            time_savings=TimeSavings(
                total_operations=1,
                automated_operations=1,
                manual_time_seconds=30,
                automated_time_seconds=1,
                estimated_time_saved_seconds=29,
            ),
            generated_at=datetime.now(UTC),
        )

        out = tmp_path / "dashboard.json"
        svc = AnalyticsService(storage_analyzer=MagicMock(), metrics_calculator=MagicMock())
        svc.export_dashboard(dashboard, out, format="json")

        assert out.exists()
        data = json.loads(out.read_text())
        assert isinstance(data, dict)

    def test_export_dashboard_text(self, tmp_path: Path) -> None:
        from datetime import UTC, datetime

        from file_organizer.models.analytics import (
            AnalyticsDashboard,
            DuplicateStats,
            FileDistribution,
            QualityMetrics,
            StorageStats,
            TimeSavings,
        )
        from file_organizer.services.analytics.analytics_service import AnalyticsService

        dashboard = AnalyticsDashboard(
            storage_stats=StorageStats(
                total_size=500, organized_size=500, saved_size=0, file_count=3, directory_count=1
            ),
            file_distribution=FileDistribution(total_files=3),
            duplicate_stats=DuplicateStats(
                total_duplicates=0, duplicate_groups=0, space_wasted=0, space_recoverable=0
            ),
            quality_metrics=QualityMetrics(
                quality_score=75.0,
                naming_compliance=0.75,
                structure_consistency=0.75,
                metadata_completeness=0.75,
                categorization_accuracy=0.75,
            ),
            time_savings=TimeSavings(
                total_operations=3,
                automated_operations=3,
                manual_time_seconds=90,
                automated_time_seconds=3,
                estimated_time_saved_seconds=87,
            ),
            generated_at=datetime.now(UTC),
        )

        out = tmp_path / "dashboard.txt"
        svc = AnalyticsService(storage_analyzer=MagicMock(), metrics_calculator=MagicMock())
        svc.export_dashboard(dashboard, out, format="text")

        content = out.read_text()
        assert "STORAGE STATISTICS" in content
        assert "QUALITY METRICS" in content

    def test_export_dashboard_unsupported_format_raises(self, tmp_path: Path) -> None:
        from datetime import UTC, datetime

        from file_organizer.models.analytics import (
            AnalyticsDashboard,
            DuplicateStats,
            FileDistribution,
            QualityMetrics,
            StorageStats,
            TimeSavings,
        )
        from file_organizer.services.analytics.analytics_service import AnalyticsService

        dashboard = AnalyticsDashboard(
            storage_stats=StorageStats(
                total_size=0, organized_size=0, saved_size=0, file_count=0, directory_count=0
            ),
            file_distribution=FileDistribution(total_files=0),
            duplicate_stats=DuplicateStats(
                total_duplicates=0, duplicate_groups=0, space_wasted=0, space_recoverable=0
            ),
            quality_metrics=QualityMetrics(
                quality_score=0.0,
                naming_compliance=0.0,
                structure_consistency=0.0,
                metadata_completeness=0.0,
                categorization_accuracy=0.0,
            ),
            time_savings=TimeSavings(
                total_operations=0,
                automated_operations=0,
                manual_time_seconds=0,
                automated_time_seconds=0,
                estimated_time_saved_seconds=0,
            ),
            generated_at=datetime.now(UTC),
        )

        svc = AnalyticsService(storage_analyzer=MagicMock(), metrics_calculator=MagicMock())
        with pytest.raises(ValueError, match="Unsupported format"):
            svc.export_dashboard(dashboard, tmp_path / "out.xyz", format="csv")

    def test_generate_dashboard_calls_all_sub_methods(self, tmp_path: Path) -> None:
        from file_organizer.models.analytics import (
            AnalyticsDashboard,
            FileDistribution,
            StorageStats,
        )
        from file_organizer.services.analytics.analytics_service import AnalyticsService

        mock_analyzer = MagicMock()
        mock_analyzer.analyze_directory.return_value = StorageStats(
            total_size=100, organized_size=100, saved_size=0, file_count=2, directory_count=1
        )
        mock_analyzer.calculate_size_distribution.return_value = FileDistribution(total_files=2)
        mock_analyzer.walk_directory.return_value = []
        mock_calc = MagicMock()
        mock_calc.measure_naming_compliance.return_value = 0.8
        mock_calc.calculate_quality_score.return_value = 70.0

        svc = AnalyticsService(storage_analyzer=mock_analyzer, metrics_calculator=mock_calc)
        result = svc.generate_dashboard(tmp_path)

        assert isinstance(result, AnalyticsDashboard)
        assert result.storage_stats.file_count == 2
        mock_analyzer.analyze_directory.assert_called_once()
        mock_analyzer.calculate_size_distribution.assert_called_once()

    def test_generate_dashboard_with_duplicate_groups(self, tmp_path: Path) -> None:
        from file_organizer.models.analytics import FileDistribution, StorageStats
        from file_organizer.services.analytics.analytics_service import AnalyticsService

        f1 = tmp_path / "d1.txt"
        f2 = tmp_path / "d2.txt"
        f1.write_text("same")
        f2.write_text("same")

        mock_analyzer = MagicMock()
        mock_analyzer.analyze_directory.return_value = StorageStats(
            total_size=10, organized_size=10, saved_size=0, file_count=2, directory_count=0
        )
        mock_analyzer.calculate_size_distribution.return_value = FileDistribution(total_files=2)
        mock_analyzer.walk_directory.return_value = []
        mock_calc = MagicMock()
        mock_calc.measure_naming_compliance.return_value = 1.0
        mock_calc.calculate_quality_score.return_value = 100.0

        dup_groups = [{"files": [str(f1), str(f2)]}]

        svc = AnalyticsService(storage_analyzer=mock_analyzer, metrics_calculator=mock_calc)
        result = svc.generate_dashboard(tmp_path, duplicate_groups=dup_groups)

        assert result.duplicate_stats.total_duplicates == 1

    def test_get_duplicate_stats_tracks_by_type(self, tmp_path: Path) -> None:
        from file_organizer.services.analytics.analytics_service import AnalyticsService

        f1 = tmp_path / "img1.jpg"
        f2 = tmp_path / "img2.jpg"
        f1.write_bytes(b"img")
        f2.write_bytes(b"img")

        groups = [{"files": [str(f1), str(f2)]}]

        svc = AnalyticsService(storage_analyzer=MagicMock(), metrics_calculator=MagicMock())
        result = svc.get_duplicate_stats(duplicate_groups=groups, total_size=6)

        assert ".jpg" in result.by_type
        assert result.by_type[".jpg"] == 1

    def test_get_duplicate_stats_largest_group_populated(self, tmp_path: Path) -> None:
        from file_organizer.services.analytics.analytics_service import AnalyticsService

        files = []
        for i in range(3):
            f = tmp_path / f"triple{i}.bin"
            f.write_bytes(b"X" * 512)
            files.append(str(f))

        groups = [{"files": files}]

        svc = AnalyticsService(storage_analyzer=MagicMock(), metrics_calculator=MagicMock())
        result = svc.get_duplicate_stats(duplicate_groups=groups, total_size=1536)

        assert result.largest_duplicate_group is not None
        assert result.largest_duplicate_group["count"] == 3

    def test_default_constructor_creates_components(self) -> None:
        from file_organizer.services.analytics.analytics_service import AnalyticsService
        from file_organizer.services.analytics.metrics_calculator import MetricsCalculator
        from file_organizer.services.analytics.storage_analyzer import StorageAnalyzer

        svc = AnalyticsService()

        assert isinstance(svc.storage_analyzer, StorageAnalyzer)
        assert isinstance(svc.metrics_calculator, MetricsCalculator)

    def test_time_saved_exact_formula(self) -> None:
        from file_organizer.services.analytics.analytics_service import AnalyticsService

        svc = AnalyticsService(storage_analyzer=MagicMock(), metrics_calculator=MagicMock())
        result = svc.calculate_time_saved(total_files=10, duplicates_removed=2)

        # manual: 10*30 + 2*60 = 300 + 120 = 420
        # automated: 10
        assert result.manual_time_seconds == 420
        assert result.automated_time_seconds == 10
        assert result.estimated_time_saved_seconds == 410


# ===========================================================================
# TestIntentParser
# ===========================================================================


class TestIntentParser:
    """Tests for file_organizer.services.copilot.intent_parser.IntentParser."""

    def test_parse_empty_string_returns_unknown(self) -> None:
        from file_organizer.services.copilot.intent_parser import IntentParser
        from file_organizer.services.copilot.models import IntentType

        parser = IntentParser()
        intent = parser.parse("")

        assert intent.intent_type == IntentType.UNKNOWN
        assert intent.confidence == 0.0

    def test_parse_organize_keyword(self) -> None:
        from file_organizer.services.copilot.intent_parser import IntentParser
        from file_organizer.services.copilot.models import IntentType

        parser = IntentParser()
        intent = parser.parse("Please organize my files")

        assert intent.intent_type == IntentType.ORGANIZE
        assert intent.confidence > 0.0

    def test_parse_find_keyword(self) -> None:
        from file_organizer.services.copilot.intent_parser import IntentParser
        from file_organizer.services.copilot.models import IntentType

        parser = IntentParser()
        intent = parser.parse("find my documents")

        assert intent.intent_type == IntentType.FIND

    def test_parse_undo_keyword(self) -> None:
        from file_organizer.services.copilot.intent_parser import IntentParser
        from file_organizer.services.copilot.models import IntentType

        parser = IntentParser()
        intent = parser.parse("undo that action")

        assert intent.intent_type == IntentType.UNDO
        assert intent.confidence == 0.95

    def test_parse_redo_keyword(self) -> None:
        from file_organizer.services.copilot.intent_parser import IntentParser
        from file_organizer.services.copilot.models import IntentType

        parser = IntentParser()
        intent = parser.parse("redo")

        assert intent.intent_type == IntentType.REDO

    def test_parse_move_keyword(self) -> None:
        from file_organizer.services.copilot.intent_parser import IntentParser
        from file_organizer.services.copilot.models import IntentType

        parser = IntentParser()
        intent = parser.parse("move files to /tmp/dest")

        assert intent.intent_type == IntentType.MOVE

    def test_parse_rename_keyword(self) -> None:
        from file_organizer.services.copilot.intent_parser import IntentParser
        from file_organizer.services.copilot.models import IntentType

        parser = IntentParser()
        intent = parser.parse('rename this file to "new_name.txt"')

        assert intent.intent_type == IntentType.RENAME

    def test_parse_preview_keyword(self) -> None:
        from file_organizer.services.copilot.intent_parser import IntentParser
        from file_organizer.services.copilot.models import IntentType

        parser = IntentParser()
        intent = parser.parse("preview what will happen")

        assert intent.intent_type == IntentType.PREVIEW

    def test_parse_help_keyword(self) -> None:
        from file_organizer.services.copilot.intent_parser import IntentParser
        from file_organizer.services.copilot.models import IntentType

        parser = IntentParser()
        intent = parser.parse("help me please")

        assert intent.intent_type == IntentType.HELP

    def test_parse_status_keyword(self) -> None:
        from file_organizer.services.copilot.intent_parser import IntentParser
        from file_organizer.services.copilot.models import IntentType

        parser = IntentParser()
        intent = parser.parse("show me the status")

        assert intent.intent_type == IntentType.STATUS

    def test_parse_suggest_keyword(self) -> None:
        from file_organizer.services.copilot.intent_parser import IntentParser
        from file_organizer.services.copilot.models import IntentType

        parser = IntentParser()
        intent = parser.parse("suggest a better location")

        assert intent.intent_type == IntentType.SUGGEST

    def test_parse_unknown_text_returns_chat(self) -> None:
        from file_organizer.services.copilot.intent_parser import IntentParser
        from file_organizer.services.copilot.models import IntentType

        parser = IntentParser()
        intent = parser.parse("the weather is nice today")

        assert intent.intent_type == IntentType.CHAT
        assert intent.confidence == 0.3

    def test_parse_raw_text_preserved(self) -> None:
        from file_organizer.services.copilot.intent_parser import IntentParser

        parser = IntentParser()
        text = "Organize my Downloads folder"
        intent = parser.parse(text)

        assert intent.raw_text == text

    def test_parse_extracts_path_for_organize(self) -> None:
        from file_organizer.services.copilot.intent_parser import IntentParser

        parser = IntentParser()
        intent = parser.parse("organize /home/user/Downloads")

        assert "paths" in intent.parameters or "source" in intent.parameters

    def test_parse_extracts_quoted_strings(self) -> None:
        from file_organizer.services.copilot.intent_parser import IntentParser

        parser = IntentParser()
        intent = parser.parse('rename to "my new name"')

        assert "quoted_args" in intent.parameters
        assert "my new name" in intent.parameters["quoted_args"]

    def test_parse_extracts_new_name_for_rename(self) -> None:
        from file_organizer.services.copilot.intent_parser import IntentParser

        parser = IntentParser()
        intent = parser.parse('rename this to "report_final.pdf"')

        assert intent.parameters.get("new_name") == "report_final.pdf"

    def test_parse_find_extracts_query(self) -> None:
        from file_organizer.services.copilot.intent_parser import IntentParser

        parser = IntentParser()
        intent = parser.parse("find tax returns")

        assert "query" in intent.parameters
        assert "tax" in intent.parameters["query"]

    def test_parse_organize_dry_run_detected(self) -> None:
        from file_organizer.services.copilot.intent_parser import IntentParser

        parser = IntentParser()
        intent = parser.parse("organize with dry-run")

        assert intent.parameters.get("dry_run") is True

    def test_parse_move_extracts_source_and_destination(self) -> None:
        from file_organizer.services.copilot.intent_parser import IntentParser

        parser = IntentParser()
        intent = parser.parse("move /source/dir /destination/dir")

        assert "source" in intent.parameters
        assert "destination" in intent.parameters

    def test_intent_is_actionable_for_organize(self) -> None:
        from file_organizer.services.copilot.intent_parser import IntentParser

        parser = IntentParser()
        intent = parser.parse("organize my files")

        assert intent.is_actionable is True

    def test_intent_not_actionable_for_chat(self) -> None:
        from file_organizer.services.copilot.intent_parser import IntentParser

        parser = IntentParser()
        intent = parser.parse("hello there how are you doing")

        assert intent.is_actionable is False

    def test_intent_not_actionable_for_help(self) -> None:
        from file_organizer.services.copilot.intent_parser import IntentParser

        parser = IntentParser()
        intent = parser.parse("help please")

        assert intent.is_actionable is False

    def test_parse_is_case_insensitive(self) -> None:
        from file_organizer.services.copilot.intent_parser import IntentParser
        from file_organizer.services.copilot.models import IntentType

        parser = IntentParser()
        intent = parser.parse("ORGANIZE MY FILES PLEASE")

        assert intent.intent_type == IntentType.ORGANIZE

    def test_parse_relocate_maps_to_move(self) -> None:
        from file_organizer.services.copilot.intent_parser import IntentParser
        from file_organizer.services.copilot.models import IntentType

        parser = IntentParser()
        intent = parser.parse("relocate these files")

        assert intent.intent_type == IntentType.MOVE

    def test_parse_clean_up_maps_to_organize(self) -> None:
        from file_organizer.services.copilot.intent_parser import IntentParser
        from file_organizer.services.copilot.models import IntentType

        parser = IntentParser()
        intent = parser.parse("clean up my folder")

        assert intent.intent_type == IntentType.ORGANIZE

    def test_parse_dry_run_maps_to_preview(self) -> None:
        from file_organizer.services.copilot.intent_parser import IntentParser
        from file_organizer.services.copilot.models import IntentType

        parser = IntentParser()
        intent = parser.parse("do a dry run first")

        assert intent.intent_type == IntentType.PREVIEW

    def test_parse_statistics_maps_to_status(self) -> None:
        from file_organizer.services.copilot.intent_parser import IntentParser
        from file_organizer.services.copilot.models import IntentType

        parser = IntentParser()
        intent = parser.parse("show statistics")

        assert intent.intent_type == IntentType.STATUS

    def test_extract_quoted_strings_static_method(self) -> None:
        from file_organizer.services.copilot.intent_parser import IntentParser

        result = IntentParser._extract_quoted_strings("say \"hello\" and 'world'")

        assert "hello" in result
        assert "world" in result
        assert len(result) == 2

    def test_extract_paths_detects_unix_paths(self) -> None:
        from file_organizer.services.copilot.intent_parser import IntentParser

        result = IntentParser._extract_paths("move /home/user/docs")

        assert len(result) == 1
        assert "/home/user/docs" in result[0]


# ===========================================================================
# TestConfigManager
# ===========================================================================


class TestConfigManager:
    """Tests for file_organizer.config.manager.ConfigManager."""

    def test_load_returns_default_when_no_file(self, tmp_path: Path) -> None:
        from file_organizer.config.manager import ConfigManager
        from file_organizer.config.schema import AppConfig

        mgr = ConfigManager(config_dir=tmp_path)
        cfg = mgr.load()

        assert isinstance(cfg, AppConfig)
        assert cfg.profile_name == "default"

    def test_load_returns_defaults_for_missing_profile(self, tmp_path: Path) -> None:
        # Create file with different profile
        import yaml

        from file_organizer.config.manager import ConfigManager
        from file_organizer.config.schema import AppConfig

        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            yaml.dump({"profiles": {"production": {"version": "1.0"}}}),
            encoding="utf-8",
        )

        mgr = ConfigManager(config_dir=tmp_path)
        cfg = mgr.load("development")

        assert isinstance(cfg, AppConfig)
        assert cfg.profile_name == "development"

    def test_save_creates_config_file(self, tmp_path: Path) -> None:
        from file_organizer.config.manager import ConfigManager
        from file_organizer.config.schema import AppConfig

        mgr = ConfigManager(config_dir=tmp_path)
        cfg = AppConfig(profile_name="default", version="1.0")
        mgr.save(cfg)

        config_path = tmp_path / "config.yaml"
        assert config_path.exists()

    def test_save_and_load_roundtrip(self, tmp_path: Path) -> None:
        from file_organizer.config.manager import ConfigManager
        from file_organizer.config.schema import AppConfig

        mgr = ConfigManager(config_dir=tmp_path)
        cfg = AppConfig(
            profile_name="test",
            version="2.0",
            default_methodology="para",
            setup_completed=True,
        )
        mgr.save(cfg)

        loaded = mgr.load("test")

        assert loaded.version == "2.0"
        assert loaded.default_methodology == "para"
        assert loaded.setup_completed is True

    def test_save_preserves_other_profiles(self, tmp_path: Path) -> None:
        from file_organizer.config.manager import ConfigManager
        from file_organizer.config.schema import AppConfig

        mgr = ConfigManager(config_dir=tmp_path)
        cfg_a = AppConfig(profile_name="alpha")
        cfg_b = AppConfig(profile_name="beta")

        mgr.save(cfg_a)
        mgr.save(cfg_b)

        profiles = mgr.list_profiles()
        assert "alpha" in profiles
        assert "beta" in profiles

    def test_list_profiles_empty_when_no_file(self, tmp_path: Path) -> None:
        from file_organizer.config.manager import ConfigManager

        mgr = ConfigManager(config_dir=tmp_path)
        profiles = mgr.list_profiles()

        assert profiles == []

    def test_list_profiles_sorted(self, tmp_path: Path) -> None:
        from file_organizer.config.manager import ConfigManager
        from file_organizer.config.schema import AppConfig

        mgr = ConfigManager(config_dir=tmp_path)
        for name in ["zebra", "alpha", "middle"]:
            mgr.save(AppConfig(profile_name=name))

        profiles = mgr.list_profiles()
        assert profiles == sorted(profiles)

    def test_delete_profile_returns_true_when_found(self, tmp_path: Path) -> None:
        from file_organizer.config.manager import ConfigManager
        from file_organizer.config.schema import AppConfig

        mgr = ConfigManager(config_dir=tmp_path)
        mgr.save(AppConfig(profile_name="removeme"))

        result = mgr.delete_profile("removeme")

        assert result is True

    def test_delete_profile_removes_it_from_list(self, tmp_path: Path) -> None:
        from file_organizer.config.manager import ConfigManager
        from file_organizer.config.schema import AppConfig

        mgr = ConfigManager(config_dir=tmp_path)
        mgr.save(AppConfig(profile_name="gone"))
        mgr.delete_profile("gone")

        profiles = mgr.list_profiles()
        assert "gone" not in profiles

    def test_delete_profile_returns_false_when_missing(self, tmp_path: Path) -> None:
        from file_organizer.config.manager import ConfigManager

        mgr = ConfigManager(config_dir=tmp_path)
        result = mgr.delete_profile("nonexistent")

        assert result is False

    def test_config_dir_property(self, tmp_path: Path) -> None:
        from file_organizer.config.manager import ConfigManager

        mgr = ConfigManager(config_dir=tmp_path)

        assert mgr.config_dir == tmp_path

    def test_to_text_model_config_uses_text_model(self, tmp_path: Path) -> None:
        from file_organizer.config.manager import ConfigManager
        from file_organizer.config.schema import AppConfig, ModelPreset
        from file_organizer.models.base import ModelType

        mgr = ConfigManager(config_dir=tmp_path)
        cfg = AppConfig(models=ModelPreset(text_model="llama3:latest"))

        model_cfg = mgr.to_text_model_config(cfg)

        assert model_cfg.name == "llama3:latest"
        assert model_cfg.model_type == ModelType.TEXT

    def test_to_vision_model_config_uses_vision_model(self, tmp_path: Path) -> None:
        from file_organizer.config.manager import ConfigManager
        from file_organizer.config.schema import AppConfig, ModelPreset
        from file_organizer.models.base import ModelType

        mgr = ConfigManager(config_dir=tmp_path)
        cfg = AppConfig(models=ModelPreset(vision_model="llava:7b"))

        model_cfg = mgr.to_vision_model_config(cfg)

        assert model_cfg.name == "llava:7b"
        assert model_cfg.model_type == ModelType.VISION

    def test_config_to_dict_contains_required_keys(self, tmp_path: Path) -> None:
        from file_organizer.config.manager import ConfigManager
        from file_organizer.config.schema import AppConfig

        mgr = ConfigManager(config_dir=tmp_path)
        cfg = AppConfig()

        d = mgr.config_to_dict(cfg)

        assert "version" in d
        assert "models" in d
        assert "updates" in d

    def test_config_to_dict_excludes_none_module_overrides(self, tmp_path: Path) -> None:
        from file_organizer.config.manager import ConfigManager
        from file_organizer.config.schema import AppConfig

        mgr = ConfigManager(config_dir=tmp_path)
        cfg = AppConfig(watcher=None, daemon=None)

        d = mgr.config_to_dict(cfg)

        assert "watcher" not in d
        assert "daemon" not in d

    def test_config_to_dict_includes_set_module_overrides(self, tmp_path: Path) -> None:
        from file_organizer.config.manager import ConfigManager
        from file_organizer.config.schema import AppConfig

        mgr = ConfigManager(config_dir=tmp_path)
        cfg = AppConfig(watcher={"interval": 5})

        d = mgr.config_to_dict(cfg)

        assert "watcher" in d
        assert d["watcher"]["interval"] == 5

    def test_load_invalid_yaml_returns_default(self, tmp_path: Path) -> None:
        from file_organizer.config.manager import ConfigManager

        config_path = tmp_path / "config.yaml"
        config_path.write_text(":::invalid yaml:::", encoding="utf-8")

        mgr = ConfigManager(config_dir=tmp_path)
        cfg = mgr.load()

        assert cfg.profile_name == "default"

    def test_load_non_dict_yaml_returns_default(self, tmp_path: Path) -> None:
        from file_organizer.config.manager import ConfigManager

        config_path = tmp_path / "config.yaml"
        config_path.write_text("- item1\n- item2\n", encoding="utf-8")

        mgr = ConfigManager(config_dir=tmp_path)
        cfg = mgr.load()

        assert cfg.profile_name == "default"

    def test_to_parallel_config(self, tmp_path: Path) -> None:
        from file_organizer.config.manager import ConfigManager
        from file_organizer.config.schema import AppConfig
        from file_organizer.parallel.config import ParallelConfig

        mgr = ConfigManager(config_dir=tmp_path)
        cfg = AppConfig(parallel={})

        result = mgr.to_parallel_config(cfg)

        assert isinstance(result, ParallelConfig)
        assert result.executor_type is not None  # has a default executor type

    def test_save_creates_parent_directories(self, tmp_path: Path) -> None:
        from file_organizer.config.manager import ConfigManager
        from file_organizer.config.schema import AppConfig

        deep = tmp_path / "a" / "b" / "c"
        mgr = ConfigManager(config_dir=deep)
        mgr.save(AppConfig(profile_name="deep"))

        assert (deep / "config.yaml").exists()

    def test_list_profiles_returns_list_of_strings(self, tmp_path: Path) -> None:
        from file_organizer.config.manager import ConfigManager
        from file_organizer.config.schema import AppConfig

        mgr = ConfigManager(config_dir=tmp_path)
        mgr.save(AppConfig(profile_name="p1"))
        mgr.save(AppConfig(profile_name="p2"))

        profiles = mgr.list_profiles()
        assert len(profiles) == 2
        assert all(isinstance(p, str) for p in profiles)


# ===========================================================================
# TestInitializer
# ===========================================================================


class TestInitializer:
    """Tests for file_organizer.core.initializer module."""

    def test_init_text_processor_success(self) -> None:
        from file_organizer.core.initializer import init_text_processor
        from file_organizer.models.base import ModelConfig, ModelType

        mock_processor_instance = MagicMock()
        mock_processor_cls = MagicMock(return_value=mock_processor_instance)
        mock_console = MagicMock()

        config = MagicMock(spec=ModelConfig)
        config.model_type = ModelType.TEXT

        result = init_text_processor(config, mock_console, processor_cls=mock_processor_cls)

        assert result is mock_processor_instance
        mock_processor_instance.initialize.assert_called_once()

    def test_init_text_processor_returns_none_on_failure(self) -> None:
        from file_organizer.core.initializer import init_text_processor
        from file_organizer.models.base import ModelConfig

        def failing_cls(**kwargs: Any) -> Any:
            raise ConnectionError("Ollama unreachable")

        mock_console = MagicMock()
        config = MagicMock(spec=ModelConfig)

        result = init_text_processor(config, mock_console, processor_cls=failing_cls)

        assert result is None

    def test_init_text_processor_prints_on_success(self) -> None:
        from file_organizer.core.initializer import init_text_processor
        from file_organizer.models.base import ModelConfig

        mock_processor_instance = MagicMock()
        mock_processor_cls = MagicMock(return_value=mock_processor_instance)
        mock_console = MagicMock()
        config = MagicMock(spec=ModelConfig)

        init_text_processor(config, mock_console, processor_cls=mock_processor_cls)

        mock_console.print.assert_called_once()
        call_arg = mock_console.print.call_args[0][0]
        assert "Text model ready" in call_arg

    def test_init_text_processor_prints_warning_on_failure(self) -> None:
        from file_organizer.core.initializer import init_text_processor
        from file_organizer.models.base import ModelConfig

        mock_processor_cls = MagicMock(side_effect=RuntimeError("model missing"))
        mock_console = MagicMock()
        config = MagicMock(spec=ModelConfig)

        init_text_processor(config, mock_console, processor_cls=mock_processor_cls)

        mock_console.print.assert_called_once()
        call_arg = mock_console.print.call_args[0][0]
        assert "unavailable" in call_arg

    def test_init_text_processor_cleans_up_on_init_failure(self) -> None:
        from file_organizer.core.initializer import init_text_processor
        from file_organizer.models.base import ModelConfig

        mock_processor_instance = MagicMock()
        mock_processor_instance.initialize.side_effect = RuntimeError("init fail")
        mock_processor_cls = MagicMock(return_value=mock_processor_instance)
        mock_console = MagicMock()
        config = MagicMock(spec=ModelConfig)

        result = init_text_processor(config, mock_console, processor_cls=mock_processor_cls)

        assert result is None
        mock_processor_instance.cleanup.assert_called_once()

    def test_init_vision_processor_success(self) -> None:
        from file_organizer.core.initializer import init_vision_processor
        from file_organizer.models.base import ModelConfig

        mock_processor_instance = MagicMock()
        mock_processor_cls = MagicMock(return_value=mock_processor_instance)
        mock_console = MagicMock()
        config = MagicMock(spec=ModelConfig)

        result = init_vision_processor(config, mock_console, processor_cls=mock_processor_cls)

        assert result is mock_processor_instance
        mock_processor_instance.initialize.assert_called_once()

    def test_init_vision_processor_returns_none_on_failure(self) -> None:
        from file_organizer.core.initializer import init_vision_processor
        from file_organizer.models.base import ModelConfig

        mock_processor_cls = MagicMock(side_effect=OSError("no gpu"))
        mock_console = MagicMock()
        config = MagicMock(spec=ModelConfig)

        result = init_vision_processor(config, mock_console, processor_cls=mock_processor_cls)

        assert result is None

    def test_init_vision_processor_prints_on_success(self) -> None:
        from file_organizer.core.initializer import init_vision_processor
        from file_organizer.models.base import ModelConfig

        mock_processor_instance = MagicMock()
        mock_processor_cls = MagicMock(return_value=mock_processor_instance)
        mock_console = MagicMock()
        config = MagicMock(spec=ModelConfig)

        init_vision_processor(config, mock_console, processor_cls=mock_processor_cls)

        mock_console.print.assert_called_once()
        call_arg = mock_console.print.call_args[0][0]
        assert "Vision model ready" in call_arg

    def test_init_vision_processor_prints_warning_on_failure(self) -> None:
        from file_organizer.core.initializer import init_vision_processor
        from file_organizer.models.base import ModelConfig

        mock_processor_cls = MagicMock(side_effect=ImportError("no llava"))
        mock_console = MagicMock()
        config = MagicMock(spec=ModelConfig)

        init_vision_processor(config, mock_console, processor_cls=mock_processor_cls)

        call_arg = mock_console.print.call_args[0][0]
        assert "unavailable" in call_arg

    def test_init_vision_processor_cleans_up_on_init_failure(self) -> None:
        from file_organizer.core.initializer import init_vision_processor
        from file_organizer.models.base import ModelConfig

        mock_processor_instance = MagicMock()
        mock_processor_instance.initialize.side_effect = RuntimeError("vision fail")
        mock_processor_cls = MagicMock(return_value=mock_processor_instance)
        mock_console = MagicMock()
        config = MagicMock(spec=ModelConfig)

        result = init_vision_processor(config, mock_console, processor_cls=mock_processor_cls)

        assert result is None
        mock_processor_instance.cleanup.assert_called_once()

    def test_init_text_processor_cleanup_error_does_not_propagate(self) -> None:
        from file_organizer.core.initializer import init_text_processor
        from file_organizer.models.base import ModelConfig

        mock_processor_instance = MagicMock()
        mock_processor_instance.initialize.side_effect = RuntimeError("init fail")
        mock_processor_instance.cleanup.side_effect = RuntimeError("cleanup also fails")
        mock_processor_cls = MagicMock(return_value=mock_processor_instance)
        mock_console = MagicMock()
        config = MagicMock(spec=ModelConfig)

        # Should not raise despite cleanup failure
        result = init_text_processor(config, mock_console, processor_cls=mock_processor_cls)

        assert result is None

    def test_init_vision_processor_cleanup_error_does_not_propagate(self) -> None:
        from file_organizer.core.initializer import init_vision_processor
        from file_organizer.models.base import ModelConfig

        mock_processor_instance = MagicMock()
        mock_processor_instance.initialize.side_effect = RuntimeError("init fail")
        mock_processor_instance.cleanup.side_effect = RuntimeError("cleanup also fails")
        mock_processor_cls = MagicMock(return_value=mock_processor_instance)
        mock_console = MagicMock()
        config = MagicMock(spec=ModelConfig)

        result = init_vision_processor(config, mock_console, processor_cls=mock_processor_cls)

        assert result is None

    def test_init_text_processor_uses_default_class_when_none(self) -> None:
        from file_organizer.core.initializer import init_text_processor
        from file_organizer.models.base import ModelConfig
        from file_organizer.services import TextProcessor

        mock_console = MagicMock()
        config = MagicMock(spec=ModelConfig)

        with patch.object(TextProcessor, "__init__", side_effect=RuntimeError("no model")):
            result = init_text_processor(config, mock_console)

        assert result is None

    def test_init_vision_processor_uses_default_class_when_none(self) -> None:
        from file_organizer.core.initializer import init_vision_processor
        from file_organizer.models.base import ModelConfig
        from file_organizer.services import VisionProcessor

        mock_console = MagicMock()
        config = MagicMock(spec=ModelConfig)

        with patch.object(VisionProcessor, "__init__", side_effect=RuntimeError("no model")):
            result = init_vision_processor(config, mock_console)

        assert result is None


# ===========================================================================
# TestServiceFacade
# ===========================================================================


class TestServiceFacade:
    """Tests for file_organizer.api.service_facade.ServiceFacade."""

    def test_health_check_structure_for_ollama_provider(self) -> None:
        import asyncio

        from file_organizer.api.service_facade import ServiceFacade

        facade = ServiceFacade()

        with patch("file_organizer.api.service_facade.get_current_provider", return_value="ollama"):

            async def run() -> dict[str, Any]:
                facade._check_ollama = MagicMock(return_value=_awaitable(True))
                return await facade.health_check()

            result = asyncio.get_event_loop().run_until_complete(run())

        assert "status" in result
        assert "version" in result
        assert "provider" in result
        assert "ollama" in result

    def test_health_check_degraded_when_ollama_down(self) -> None:
        import asyncio

        from file_organizer.api.service_facade import ServiceFacade

        facade = ServiceFacade()

        with patch("file_organizer.api.service_facade.get_current_provider", return_value="ollama"):

            async def run() -> dict[str, Any]:
                facade._check_ollama = MagicMock(return_value=_awaitable(False))
                return await facade.health_check()

            result = asyncio.get_event_loop().run_until_complete(run())

        assert result["status"] == "degraded"
        assert result["ollama"] is False

    def test_health_check_includes_capabilities_when_ollama_down(self) -> None:
        import asyncio

        from file_organizer.api.service_facade import ServiceFacade

        facade = ServiceFacade()

        with patch("file_organizer.api.service_facade.get_current_provider", return_value="ollama"):

            async def run() -> dict[str, Any]:
                facade._check_ollama = MagicMock(return_value=_awaitable(False))
                return await facade.health_check()

            result = asyncio.get_event_loop().run_until_complete(run())

        assert "capabilities" in result
        assert "rule_based" in result["capabilities"]

    def test_health_check_openai_provider_status_unknown(self) -> None:
        import asyncio

        from file_organizer.api.service_facade import ServiceFacade

        facade = ServiceFacade()

        with patch("file_organizer.api.service_facade.get_current_provider", return_value="openai"):

            async def run() -> dict[str, Any]:
                return await facade.health_check()

            result = asyncio.get_event_loop().run_until_complete(run())

        assert result["status"] == "unknown"
        assert result["provider"] == "openai"

    def test_health_check_llama_cpp_provider_status_unknown(self) -> None:
        import asyncio

        from file_organizer.api.service_facade import ServiceFacade

        facade = ServiceFacade()

        with patch(
            "file_organizer.api.service_facade.get_current_provider", return_value="llama_cpp"
        ):

            async def run() -> dict[str, Any]:
                return await facade.health_check()

            result = asyncio.get_event_loop().run_until_complete(run())

        assert result["status"] == "unknown"

    def test_get_status_returns_required_keys(self) -> None:
        import asyncio

        from file_organizer.api.service_facade import ServiceFacade

        facade = ServiceFacade()

        async def run() -> dict[str, Any]:
            facade._check_ollama = MagicMock(return_value=_awaitable(False))
            return await facade.get_status()

        result = asyncio.get_event_loop().run_until_complete(run())

        assert "environment" in result
        assert "version" in result
        assert "auth_enabled" in result
        assert "ollama" in result

    def test_organize_files_returns_success_false_on_error(self) -> None:
        import asyncio

        from file_organizer.api.service_facade import ServiceFacade

        facade = ServiceFacade()

        with patch("file_organizer.core.organizer.FileOrganizer") as mock_organizer_cls:
            mock_organizer_cls.side_effect = RuntimeError("organizer broken")

            async def run() -> dict[str, Any]:
                return await facade.organize_files("/nonexistent/path")

            result = asyncio.get_event_loop().run_until_complete(run())

        assert result["success"] is False
        assert "error" in result

    def test_undo_last_operation_wraps_undo_manager(self) -> None:
        import asyncio

        from file_organizer.api.service_facade import ServiceFacade

        facade = ServiceFacade()

        with patch("file_organizer.undo.undo_manager.UndoManager") as mock_cls:
            mock_instance = MagicMock()
            mock_instance.undo_last_operation.return_value = False
            mock_cls.return_value = mock_instance

            async def run() -> dict[str, Any]:
                return await facade.undo_last_operation()

            result = asyncio.get_event_loop().run_until_complete(run())

        assert result["success"] is True
        assert result["data"]["undone"] is False

    def test_undo_last_operation_success_true_when_undone(self) -> None:
        import asyncio

        from file_organizer.api.service_facade import ServiceFacade

        facade = ServiceFacade()

        with patch("file_organizer.undo.undo_manager.UndoManager") as mock_cls:
            mock_instance = MagicMock()
            mock_instance.undo_last_operation.return_value = True
            mock_cls.return_value = mock_instance

            async def run() -> dict[str, Any]:
                return await facade.undo_last_operation()

            result = asyncio.get_event_loop().run_until_complete(run())

        assert result["data"]["undone"] is True

    def test_undo_last_operation_returns_error_on_exception(self) -> None:
        import asyncio

        from file_organizer.api.service_facade import ServiceFacade

        facade = ServiceFacade()

        with patch("file_organizer.undo.undo_manager.UndoManager") as mock_cls:
            mock_cls.side_effect = RuntimeError("undo failed")

            async def run() -> dict[str, Any]:
                return await facade.undo_last_operation()

            result = asyncio.get_event_loop().run_until_complete(run())

        assert result["success"] is False
        assert "error" in result

    def test_get_operation_history_returns_list(self) -> None:
        import asyncio

        from file_organizer.api.service_facade import ServiceFacade

        facade = ServiceFacade()

        with patch("file_organizer.history.tracker.OperationHistory") as mock_cls:
            mock_instance = MagicMock()
            mock_instance.get_recent_operations.return_value = []
            mock_cls.return_value = mock_instance

            async def run() -> dict[str, Any]:
                return await facade.get_operation_history(limit=5)

            result = asyncio.get_event_loop().run_until_complete(run())

        assert result["success"] is True
        assert result["data"]["operations"] == []

    def test_get_operation_history_error_on_exception(self) -> None:
        import asyncio

        from file_organizer.api.service_facade import ServiceFacade

        facade = ServiceFacade()

        with patch("file_organizer.history.tracker.OperationHistory") as mock_cls:
            mock_cls.side_effect = RuntimeError("history broken")

            async def run() -> dict[str, Any]:
                return await facade.get_operation_history()

            result = asyncio.get_event_loop().run_until_complete(run())

        assert result["success"] is False

    def test_get_daemon_status_returns_success(self) -> None:
        import asyncio

        from file_organizer.api.service_facade import ServiceFacade

        facade = ServiceFacade()
        mock_daemon = MagicMock()
        mock_daemon.is_running = False
        mock_daemon.uptime_seconds = 0.0
        mock_daemon.files_processed = 0
        facade._daemon_service = mock_daemon

        async def run() -> dict[str, Any]:
            return await facade.get_daemon_status()

        result = asyncio.get_event_loop().run_until_complete(run())

        assert result["success"] is True
        assert "running" in result["data"]
        assert result["data"]["running"] is False

    def test_start_daemon_returns_started_true(self) -> None:
        import asyncio

        from file_organizer.api.service_facade import ServiceFacade

        facade = ServiceFacade()
        mock_daemon = MagicMock()
        facade._daemon_service = mock_daemon

        async def run() -> dict[str, Any]:
            return await facade.start_daemon()

        result = asyncio.get_event_loop().run_until_complete(run())

        assert result["success"] is True
        assert result["data"]["started"] is True
        mock_daemon.start_background.assert_called_once()

    def test_stop_daemon_returns_stopped_true(self) -> None:
        import asyncio

        from file_organizer.api.service_facade import ServiceFacade

        facade = ServiceFacade()
        mock_daemon = MagicMock()
        facade._daemon_service = mock_daemon

        async def run() -> dict[str, Any]:
            return await facade.stop_daemon()

        result = asyncio.get_event_loop().run_until_complete(run())

        assert result["success"] is True
        assert result["data"]["stopped"] is True

    def test_get_model_status_returns_models_list(self) -> None:
        import asyncio

        from file_organizer.api.service_facade import ServiceFacade

        facade = ServiceFacade()

        with patch("file_organizer.models.model_manager.ModelManager") as mock_cls:
            mock_instance = MagicMock()
            mock_instance.list_models.return_value = []
            mock_cls.return_value = mock_instance

            async def run() -> dict[str, Any]:
                return await facade.get_model_status()

            result = asyncio.get_event_loop().run_until_complete(run())

        assert result["success"] is True
        assert "models" in result["data"]
        assert result["data"]["models"] == []

    def test_get_model_status_error_on_exception(self) -> None:
        import asyncio

        from file_organizer.api.service_facade import ServiceFacade

        facade = ServiceFacade()

        with patch("file_organizer.models.model_manager.ModelManager") as mock_cls:
            mock_cls.side_effect = RuntimeError("no manager")

            async def run() -> dict[str, Any]:
                return await facade.get_model_status()

            result = asyncio.get_event_loop().run_until_complete(run())

        assert result["success"] is False

    def test_find_duplicates_error_on_exception(self, tmp_path: Path) -> None:
        import asyncio

        from file_organizer.api.service_facade import ServiceFacade

        facade = ServiceFacade()

        with patch("file_organizer.services.deduplication.detector.DuplicateDetector") as mock_cls:
            mock_cls.side_effect = RuntimeError("dedup broken")

            async def run() -> dict[str, Any]:
                return await facade.find_duplicates(str(tmp_path / "scan"))

            result = asyncio.get_event_loop().run_until_complete(run())

        assert result["success"] is False
        assert "error" in result

    def test_get_daemon_service_lazy_init(self) -> None:
        from file_organizer.api.service_facade import ServiceFacade

        facade = ServiceFacade()
        assert facade._daemon_service is None

        with patch("file_organizer.daemon.service.DaemonService") as mock_cls:
            mock_cls.return_value = MagicMock()
            svc = facade._get_daemon_service()

        assert svc is not None
        assert facade._daemon_service is svc

    def test_get_daemon_service_cached_on_second_call(self) -> None:
        from file_organizer.api.service_facade import ServiceFacade

        facade = ServiceFacade()

        with patch("file_organizer.daemon.service.DaemonService") as mock_cls:
            first_instance = MagicMock()
            mock_cls.return_value = first_instance

            svc1 = facade._get_daemon_service()
            svc2 = facade._get_daemon_service()

        assert svc1 is svc2
        assert mock_cls.call_count == 1

    def test_check_ollama_returns_false_on_connection_error(self) -> None:
        import asyncio

        from file_organizer.api.service_facade import ServiceFacade

        facade = ServiceFacade()

        with patch("urllib.request.urlopen", side_effect=OSError("refused")):

            async def run() -> bool:
                return await facade._check_ollama()

            result = asyncio.get_event_loop().run_until_complete(run())

        assert result is False

    def test_health_check_ollama_ok_gives_ok_status(self) -> None:
        import asyncio

        from file_organizer.api.service_facade import ServiceFacade

        facade = ServiceFacade()

        with patch("file_organizer.api.service_facade.get_current_provider", return_value="ollama"):

            async def run() -> dict[str, Any]:
                facade._check_ollama = MagicMock(return_value=_awaitable(True))
                return await facade.health_check()

            result = asyncio.get_event_loop().run_until_complete(run())

        assert result["status"] == "ok"
        assert result["ollama"] is True


# ---------------------------------------------------------------------------
# Async helper
# ---------------------------------------------------------------------------


async def _awaitable(value: Any) -> Any:
    """Return a value from an async context for use in mock return values."""
    return value
