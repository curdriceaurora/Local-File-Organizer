"""Branch-coverage tests for ResumableProcessor.

Targets the 79 lines missing from the 16% baseline in
src/file_organizer/parallel/resume.py.  Every test class carries
@pytest.mark.integration as requested.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.parallel.models import Checkpoint, JobState, JobStatus
from file_organizer.parallel.result import FileResult
from file_organizer.parallel.resume import ResumableProcessor

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_file_result(path: Path, *, success: bool = True) -> FileResult:
    return FileResult(
        path=path,
        success=success,
        result="ok" if success else None,
        error=None if success else "simulated failure",
    )


def _make_checkpoint(
    job_id: str = "j1",
    completed: list[Path] | None = None,
    pending: list[Path] | None = None,
) -> MagicMock:
    cp = MagicMock(spec=Checkpoint)
    cp.job_id = job_id
    cp.completed_paths = list(completed or [])
    cp.pending_paths = list(pending or [])
    return cp


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_persistence() -> MagicMock:
    return MagicMock()


@pytest.fixture()
def mock_checkpoint_mgr() -> MagicMock:
    mgr = MagicMock()
    mgr.create_checkpoint.return_value = _make_checkpoint()
    mgr.load_checkpoint.return_value = None
    return mgr


@pytest.fixture()
def processor(mock_persistence: MagicMock, mock_checkpoint_mgr: MagicMock) -> ResumableProcessor:
    return ResumableProcessor(
        persistence=mock_persistence,
        checkpoint_mgr=mock_checkpoint_mgr,
    )


# ---------------------------------------------------------------------------
# process_with_resume — missing branches
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestProcessWithResumeBranches:
    """Covers process_with_resume branches not hit by existing tests."""

    def test_empty_file_list_succeeds_with_zero_counts(
        self, processor: ResumableProcessor, mock_persistence: MagicMock
    ) -> None:
        """Passing an empty file list yields total=0, succeeded=0, failed=0."""
        cp = _make_checkpoint()
        processor._checkpoint_mgr.create_checkpoint.return_value = cp

        with patch.object(processor._processor, "process_batch_iter", return_value=[]):
            result = processor.process_with_resume([], lambda p: "ok", job_id="empty-job")

        assert result.total == 0
        assert result.succeeded == 0
        assert result.failed == 0
        # job should have been saved at least once (on creation)
        mock_persistence.save_job.assert_called()

    def test_initial_job_state_has_running_status(
        self, processor: ResumableProcessor, mock_persistence: MagicMock, tmp_path: Path
    ) -> None:
        """Job is saved with RUNNING status before processing starts."""
        f = tmp_path / "a.txt"
        f.write_text("content")
        cp = _make_checkpoint()
        processor._checkpoint_mgr.create_checkpoint.return_value = cp

        saved_jobs: list[JobState] = []
        mock_persistence.save_job.side_effect = lambda j: saved_jobs.append(
            JobState(
                id=j.id,
                status=j.status,
                created=j.created,
                updated=j.updated,
                total_files=j.total_files,
            )
        )

        with patch.object(
            processor._processor,
            "process_batch_iter",
            return_value=[_make_file_result(f)],
        ):
            processor.process_with_resume([f], lambda p: "ok", job_id="status-job")

        first_save = saved_jobs[0]
        assert first_save.status == JobStatus.RUNNING
        assert first_save.total_files == 1

    def test_job_id_is_propagated_to_checkpoint(
        self, processor: ResumableProcessor, tmp_path: Path
    ) -> None:
        """create_checkpoint is called with the same job_id passed to process_with_resume."""
        f = tmp_path / "f.txt"
        f.write_text("x")
        cp = _make_checkpoint(job_id="my-explicit-id")
        processor._checkpoint_mgr.create_checkpoint.return_value = cp

        with patch.object(processor._processor, "process_batch_iter", return_value=[]):
            processor.process_with_resume([f], lambda p: "ok", job_id="my-explicit-id")

        processor._checkpoint_mgr.create_checkpoint.assert_called_once_with(
            job_id="my-explicit-id",
            completed_files=[],
            pending_files=[f],
        )


# ---------------------------------------------------------------------------
# resume_job — missing branches
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestResumeJobBranches:
    """Covers resume_job branches: still_completed count, partial resume."""

    def test_result_total_reflects_full_job_not_just_new_files(
        self,
        processor: ResumableProcessor,
        mock_persistence: MagicMock,
        mock_checkpoint_mgr: MagicMock,
        tmp_path: Path,
    ) -> None:
        """BatchResult.total equals job.total_files (full job), not just reprocessed count."""
        already_done = tmp_path / "done.txt"
        already_done.write_text("done")
        pending = tmp_path / "pending.txt"
        pending.write_text("pending")

        job = JobState(id="j1", status=JobStatus.RUNNING, total_files=2)
        mock_persistence.load_job.return_value = job

        cp = _make_checkpoint(
            job_id="j1",
            completed=[already_done],
            pending=[pending],
        )
        mock_checkpoint_mgr.load_checkpoint.return_value = cp
        mock_checkpoint_mgr.has_file_changed.return_value = False
        new_cp = _make_checkpoint(job_id="j1", completed=[already_done], pending=[pending])
        mock_checkpoint_mgr.create_checkpoint.return_value = new_cp

        with patch.object(
            processor._processor,
            "process_batch_iter",
            return_value=[_make_file_result(pending)],
        ):
            result = processor.resume_job("j1", lambda p: "ok")

        # total should be the full job total_files=2, not just the 1 new file
        assert result.total == 2
        # still_completed (1) + newly succeeded (1) = 2
        assert result.succeeded == 2
        assert result.failed == 0

    def test_resume_with_failed_file_included_in_failed_count(
        self,
        processor: ResumableProcessor,
        mock_persistence: MagicMock,
        mock_checkpoint_mgr: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Failed files in reprocessed batch are reflected in BatchResult.failed."""
        pending = tmp_path / "bad.txt"
        pending.write_text("x")

        job = JobState(id="j2", status=JobStatus.RUNNING, total_files=1)
        mock_persistence.load_job.return_value = job

        cp = _make_checkpoint(job_id="j2", completed=[], pending=[pending])
        mock_checkpoint_mgr.load_checkpoint.return_value = cp
        mock_checkpoint_mgr.has_file_changed.return_value = False
        new_cp = _make_checkpoint(job_id="j2", completed=[], pending=[pending])
        mock_checkpoint_mgr.create_checkpoint.return_value = new_cp

        with patch.object(
            processor._processor,
            "process_batch_iter",
            return_value=[_make_file_result(pending, success=False)],
        ):
            result = processor.resume_job("j2", lambda p: "ok")

        assert result.failed == 1
        assert result.succeeded == 0

    def test_resume_job_updates_status_to_running_before_processing(
        self,
        processor: ResumableProcessor,
        mock_persistence: MagicMock,
        mock_checkpoint_mgr: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Job status is set to RUNNING before delegating to _process_and_checkpoint."""
        f = tmp_path / "f.txt"
        f.write_text("x")

        job = JobState(id="j3", status=JobStatus.PAUSED, total_files=1)
        mock_persistence.load_job.return_value = job

        cp = _make_checkpoint(job_id="j3", completed=[], pending=[f])
        mock_checkpoint_mgr.load_checkpoint.return_value = cp
        mock_checkpoint_mgr.has_file_changed.return_value = False
        new_cp = _make_checkpoint(job_id="j3", completed=[], pending=[f])
        mock_checkpoint_mgr.create_checkpoint.return_value = new_cp

        saved_statuses: list[JobStatus] = []

        def capture_status(j: JobState) -> None:
            saved_statuses.append(j.status)

        mock_persistence.save_job.side_effect = capture_status

        with patch.object(
            processor._processor,
            "process_batch_iter",
            return_value=[_make_file_result(f)],
        ):
            processor.resume_job("j3", lambda p: "ok")

        # The first save after loading must be RUNNING (ordering matters)
        assert len(saved_statuses) > 0
        assert saved_statuses[0] == JobStatus.RUNNING

    def test_modified_files_are_re_added_to_pending(
        self,
        processor: ResumableProcessor,
        mock_persistence: MagicMock,
        mock_checkpoint_mgr: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Files detected as modified are moved from completed to pending for reprocessing."""
        modified = tmp_path / "changed.txt"
        modified.write_text("new content")
        unchanged = tmp_path / "stable.txt"
        unchanged.write_text("stable")

        job = JobState(id="j4", status=JobStatus.RUNNING, total_files=2)
        mock_persistence.load_job.return_value = job

        cp = _make_checkpoint(
            job_id="j4",
            completed=[modified, unchanged],
            pending=[],
        )
        mock_checkpoint_mgr.load_checkpoint.return_value = cp

        # modified has changed; unchanged has not
        mock_checkpoint_mgr.has_file_changed.side_effect = lambda ckpt, path: path == modified

        new_cp = _make_checkpoint(job_id="j4", completed=[unchanged], pending=[modified])
        mock_checkpoint_mgr.create_checkpoint.return_value = new_cp

        with patch.object(
            processor._processor,
            "process_batch_iter",
            return_value=[_make_file_result(modified)],
        ):
            result = processor.resume_job("j4", lambda p: "ok")

        # create_checkpoint should be called with unchanged as completed and modified as pending
        processor._checkpoint_mgr.create_checkpoint.assert_called_once_with(
            job_id="j4",
            completed_files=[unchanged],
            pending_files=[modified],
        )
        # total = full job = 2; still_completed (1 unchanged) + succeeded (1 modified) = 2
        assert result.total == 2
        assert result.succeeded == 2


# ---------------------------------------------------------------------------
# _process_and_checkpoint — missing branches
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestProcessAndCheckpointBranches:
    """Covers batched-save triggers and status transitions in _process_and_checkpoint."""

    def test_mixed_success_and_failure_marks_completed_not_failed(
        self, processor: ResumableProcessor, mock_persistence: MagicMock, tmp_path: Path
    ) -> None:
        """When completed_files > 0 and failed_files > 0, status is COMPLETED, not FAILED."""
        good = tmp_path / "good.txt"
        bad = tmp_path / "bad.txt"
        good.write_text("x")
        bad.write_text("x")

        job = JobState(id="j5", status=JobStatus.RUNNING, total_files=2)
        cp = _make_checkpoint(job_id="j5")

        with patch.object(
            processor._processor,
            "process_batch_iter",
            return_value=[
                _make_file_result(good, success=True),
                _make_file_result(bad, success=False),
            ],
        ):
            result = processor._process_and_checkpoint(
                job=job, files=[good, bad], process_fn=lambda p: "ok", checkpoint=cp
            )

        # FAILED status only when ALL files fail (completed_files == 0)
        assert job.status == JobStatus.COMPLETED
        assert result.succeeded == 1
        assert result.failed == 1

    def test_all_failed_marks_job_failed(
        self, processor: ResumableProcessor, mock_persistence: MagicMock, tmp_path: Path
    ) -> None:
        """When every file fails, job status is FAILED."""
        f1 = tmp_path / "f1.txt"
        f2 = tmp_path / "f2.txt"
        f1.write_text("x")
        f2.write_text("x")

        job = JobState(id="j6", status=JobStatus.RUNNING, total_files=2)
        cp = _make_checkpoint(job_id="j6")

        with patch.object(
            processor._processor,
            "process_batch_iter",
            return_value=[
                _make_file_result(f1, success=False),
                _make_file_result(f2, success=False),
            ],
        ):
            result = processor._process_and_checkpoint(
                job=job, files=[f1, f2], process_fn=lambda p: "ok", checkpoint=cp
            )

        assert job.status == JobStatus.FAILED
        assert result.failed == 2
        assert result.succeeded == 0

    def test_checkpoint_none_load_fallback_returns_none(
        self, processor: ResumableProcessor, mock_persistence: MagicMock, tmp_path: Path
    ) -> None:
        """When checkpoint=None and load_checkpoint returns None, the `if checkpoint:` guards
        inside the loop are False — processing still completes without error."""
        f = tmp_path / "a.txt"
        f.write_text("x")

        job = JobState(id="j7", status=JobStatus.RUNNING, total_files=1)
        # load_checkpoint returns None — no checkpoint to update
        processor._checkpoint_mgr.load_checkpoint.return_value = None

        with patch.object(
            processor._processor,
            "process_batch_iter",
            return_value=[_make_file_result(f)],
        ):
            result = processor._process_and_checkpoint(
                job=job, files=[f], process_fn=lambda p: "ok", checkpoint=None
            )

        assert result.succeeded == 1
        assert result.failed == 0
        # update_checkpoint_state must NOT have been called (checkpoint was None)
        processor._checkpoint_mgr.update_checkpoint_state.assert_not_called()

    def test_batched_save_triggered_by_file_count(
        self, processor: ResumableProcessor, mock_persistence: MagicMock, tmp_path: Path
    ) -> None:
        """Batched persistence fires when files_since_save reaches 50."""
        files = []
        for i in range(52):
            f = tmp_path / f"f{i:03d}.txt"
            f.write_text("x")
            files.append(f)

        job = JobState(id="j8", status=JobStatus.RUNNING, total_files=52)
        cp = _make_checkpoint(job_id="j8")

        file_results = [_make_file_result(f) for f in files]

        with patch.object(
            processor._processor,
            "process_batch_iter",
            return_value=file_results,
        ):
            result = processor._process_and_checkpoint(
                job=job, files=files, process_fn=lambda p: "ok", checkpoint=cp
            )

        # Mid-batch save should occur at file 50 plus a final save at completion
        # Total save_job calls must be > 1 (at least one mid-batch + one final)
        save_count = mock_persistence.save_job.call_count
        assert save_count >= 2
        assert result.succeeded == 52

    def test_batched_save_triggered_by_elapsed_time(
        self, processor: ResumableProcessor, mock_persistence: MagicMock, tmp_path: Path
    ) -> None:
        """Batched persistence fires when >= 5 seconds have elapsed since last save."""
        f1 = tmp_path / "slow1.txt"
        f2 = tmp_path / "slow2.txt"
        f1.write_text("x")
        f2.write_text("x")

        job = JobState(id="j9", status=JobStatus.RUNNING, total_files=2)
        cp = _make_checkpoint(job_id="j9")

        # Simulate time jumping forward so the elapsed >= 5.0 branch fires on f2
        time_values = iter([0.0, 6.0, 6.0])

        with patch("file_organizer.parallel.resume.time.monotonic", side_effect=time_values):
            with patch.object(
                processor._processor,
                "process_batch_iter",
                return_value=[_make_file_result(f1), _make_file_result(f2)],
            ):
                result = processor._process_and_checkpoint(
                    job=job, files=[f1, f2], process_fn=lambda p: "ok", checkpoint=cp
                )

        # Mid-batch save triggered by elapsed time + final save = >= 2 calls
        save_count = mock_persistence.save_job.call_count
        assert save_count >= 2
        assert result.succeeded == 2

    def test_exception_saves_checkpoint_before_reraise(
        self, processor: ResumableProcessor, mock_persistence: MagicMock, tmp_path: Path
    ) -> None:
        """On exception, checkpoint.save is called before the exception propagates."""
        f = tmp_path / "crash.txt"
        f.write_text("x")

        job = JobState(id="j10", status=JobStatus.RUNNING, total_files=1)
        cp = _make_checkpoint(job_id="j10")

        with patch.object(
            processor._processor,
            "process_batch_iter",
            side_effect=RuntimeError("batch crash"),
        ):
            with pytest.raises(RuntimeError, match="batch crash"):
                processor._process_and_checkpoint(
                    job=job, files=[f], process_fn=lambda p: "ok", checkpoint=cp
                )

        assert job.status == JobStatus.FAILED
        assert job.error == "batch crash"
        processor._checkpoint_mgr.save_checkpoint.assert_called_with(cp)

    def test_completed_files_counter_incremented_per_success(
        self, processor: ResumableProcessor, mock_persistence: MagicMock, tmp_path: Path
    ) -> None:
        """job.completed_files is incremented once per successful FileResult."""
        files = [tmp_path / f"f{i}.txt" for i in range(3)]
        for f in files:
            f.write_text("x")

        job = JobState(id="j11", status=JobStatus.RUNNING, total_files=3)
        cp = _make_checkpoint(job_id="j11")

        with patch.object(
            processor._processor,
            "process_batch_iter",
            return_value=[_make_file_result(f) for f in files],
        ):
            processor._process_and_checkpoint(
                job=job, files=files, process_fn=lambda p: "ok", checkpoint=cp
            )

        assert job.completed_files == 3
        assert job.failed_files == 0

    def test_failed_files_counter_incremented_per_failure(
        self, processor: ResumableProcessor, mock_persistence: MagicMock, tmp_path: Path
    ) -> None:
        """job.failed_files is incremented once per failed FileResult."""
        f = tmp_path / "bad.txt"
        f.write_text("x")

        job = JobState(id="j12", status=JobStatus.RUNNING, total_files=1)
        cp = _make_checkpoint(job_id="j12")

        with patch.object(
            processor._processor,
            "process_batch_iter",
            return_value=[_make_file_result(f, success=False)],
        ):
            processor._process_and_checkpoint(
                job=job, files=[f], process_fn=lambda p: "ok", checkpoint=cp
            )

        assert job.failed_files == 1
        assert job.completed_files == 0

    def test_update_checkpoint_state_called_per_success(
        self, processor: ResumableProcessor, mock_persistence: MagicMock, tmp_path: Path
    ) -> None:
        """update_checkpoint_state is called for each successful file result."""
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("x")
        f2.write_text("x")

        job = JobState(id="j13", status=JobStatus.RUNNING, total_files=2)
        cp = _make_checkpoint(job_id="j13")

        with patch.object(
            processor._processor,
            "process_batch_iter",
            return_value=[
                _make_file_result(f1, success=True),
                _make_file_result(f2, success=False),
            ],
        ):
            processor._process_and_checkpoint(
                job=job, files=[f1, f2], process_fn=lambda p: "ok", checkpoint=cp
            )

        # Only f1 succeeded — should be called exactly once with f1
        processor._checkpoint_mgr.update_checkpoint_state.assert_called_once_with(cp, f1)
        # f2 failed — update_checkpoint_state NOT called for it
        calls = processor._checkpoint_mgr.update_checkpoint_state.call_args_list
        assert len(calls) == 1
        assert calls[0].args[1] == f1


@pytest.mark.integration
class TestCheckpointNoneBranches:
    """Covers the checkpoint=None path in batched save and exception handler."""

    def test_batched_save_with_no_checkpoint_skips_save_checkpoint(
        self,
        processor: ResumableProcessor,
        mock_persistence: MagicMock,
        mock_checkpoint_mgr: MagicMock,
        tmp_path: Path,
    ) -> None:
        """When batched save triggers with checkpoint=None, only save_job is called.

        This covers the False branch at line 246 (if checkpoint:) inside the
        batched-persistence block that fires at files_since_save >= 50.
        """
        files = [tmp_path / f"f{i}.txt" for i in range(50)]
        for f in files:
            f.write_text("x")

        job = JobState(id="j1", status=JobStatus.RUNNING, total_files=50)
        mock_checkpoint_mgr.load_checkpoint.return_value = None

        batch_results = [_make_file_result(f, success=True) for f in files]

        with patch.object(
            processor._processor,
            "process_batch_iter",
            return_value=batch_results,
        ):
            result = processor._process_and_checkpoint(
                job=job,
                files=files,
                process_fn=lambda p: "ok",
                checkpoint=None,
            )

        assert result.succeeded == 50
        assert mock_persistence.save_job.call_count >= 2
        mock_checkpoint_mgr.save_checkpoint.assert_not_called()

    def test_exception_with_no_checkpoint_skips_save_checkpoint(
        self,
        processor: ResumableProcessor,
        mock_persistence: MagicMock,
        mock_checkpoint_mgr: MagicMock,
        tmp_path: Path,
    ) -> None:
        """When process_batch_iter raises with checkpoint=None, save_checkpoint is not called.

        This covers the False branch at line 257 (if checkpoint:) inside the
        exception handler.
        """
        f = tmp_path / "a.txt"
        f.write_text("x")

        job = JobState(id="j1", status=JobStatus.RUNNING, total_files=1)
        mock_checkpoint_mgr.load_checkpoint.return_value = None

        with patch.object(
            processor._processor,
            "process_batch_iter",
            side_effect=RuntimeError("crash"),
        ):
            with pytest.raises(RuntimeError, match="crash"):
                processor._process_and_checkpoint(
                    job=job,
                    files=[f],
                    process_fn=lambda p: "ok",
                    checkpoint=None,
                )

        assert job.status == JobStatus.FAILED
        mock_persistence.save_job.assert_called_with(job)
        mock_checkpoint_mgr.save_checkpoint.assert_not_called()

    def test_checkpoint_update_called_on_success_with_checkpoint(
        self,
        processor: ResumableProcessor,
        mock_checkpoint_mgr: MagicMock,
        tmp_path: Path,
    ) -> None:
        """When file succeeds and checkpoint is provided, update_checkpoint_state is called."""
        f = tmp_path / "a.txt"
        f.write_text("x")
        job = JobState(id="j1", status=JobStatus.RUNNING, total_files=1)
        cp = MagicMock(spec=Checkpoint)
        with patch.object(
            processor._processor,
            "process_batch_iter",
            return_value=[_make_file_result(f, success=True)],
        ):
            result = processor._process_and_checkpoint(
                job=job,
                files=[f],
                process_fn=lambda p: "ok",
                checkpoint=cp,
            )
        assert result.succeeded == 1
        mock_checkpoint_mgr.update_checkpoint_state.assert_called_once_with(cp, f)

    def test_exception_with_checkpoint_calls_save_checkpoint(
        self,
        processor,
        mock_persistence,
        mock_checkpoint_mgr,
        tmp_path,
    ) -> None:
        """When process_batch_iter raises and checkpoint is provided, save_checkpoint is called."""
        f = tmp_path / "a.txt"
        f.write_text("x")
        job = JobState(id="j1", status=JobStatus.RUNNING, total_files=1)
        cp = MagicMock(spec=Checkpoint)
        with patch.object(
            processor._processor,
            "process_batch_iter",
            side_effect=RuntimeError("crash"),
        ):
            with pytest.raises(RuntimeError, match="crash"):
                processor._process_and_checkpoint(
                    job=job,
                    files=[f],
                    process_fn=lambda p: "ok",
                    checkpoint=cp,
                )
        assert job.status == JobStatus.FAILED
        mock_checkpoint_mgr.save_checkpoint.assert_called_with(cp)

    def test_batched_save_with_checkpoint_calls_save_checkpoint(
        self,
        processor,
        mock_persistence,
        mock_checkpoint_mgr,
        tmp_path,
    ) -> None:
        """When batched save triggers with a real checkpoint, save_checkpoint is called."""
        files = [tmp_path / f"f{i}.txt" for i in range(50)]
        for f in files:
            f.write_text("x")
        job = JobState(id="j1", status=JobStatus.RUNNING, total_files=50)
        cp = MagicMock(spec=Checkpoint)
        batch_results = [_make_file_result(f, success=True) for f in files]
        with patch.object(
            processor._processor,
            "process_batch_iter",
            return_value=batch_results,
        ):
            result = processor._process_and_checkpoint(
                job=job,
                files=files,
                process_fn=lambda p: "ok",
                checkpoint=cp,
            )
        assert result.succeeded == 50
        assert mock_persistence.save_job.call_count >= 2
        assert mock_checkpoint_mgr.save_checkpoint.call_count >= 2
