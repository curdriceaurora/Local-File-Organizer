"""Coverage tests for ResumableProcessor — targets uncovered branches."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.parallel.models import Checkpoint, JobState, JobStatus
from file_organizer.parallel.result import FileResult
from file_organizer.parallel.resume import ResumableProcessor

pytestmark = pytest.mark.unit


def _make_file_result(path: Path, success: bool = True) -> FileResult:
    return FileResult(
        path=path,
        success=success,
        result="ok" if success else None,
        error=None if success else "failed",
    )


@pytest.fixture()
def mock_persistence():
    return MagicMock()


@pytest.fixture()
def mock_checkpoint_mgr():
    mgr = MagicMock()
    mgr.create_checkpoint.return_value = MagicMock(
        spec=Checkpoint,
        completed_paths=[],
        pending_paths=[],
    )
    mgr.load_checkpoint.return_value = None
    return mgr


@pytest.fixture()
def processor(mock_persistence, mock_checkpoint_mgr):
    return ResumableProcessor(
        persistence=mock_persistence,
        checkpoint_mgr=mock_checkpoint_mgr,
    )


# ---------------------------------------------------------------------------
# process_with_resume
# ---------------------------------------------------------------------------


class TestProcessWithResume:
    def test_auto_generates_job_id(self, processor, tmp_path, mock_persistence):
        f = tmp_path / "a.txt"
        f.write_text("x")

        with patch.object(
            processor._processor,
            "process_batch_iter",
            return_value=[_make_file_result(f)],
        ):
            result = processor.process_with_resume([f], lambda p: "ok")

        assert result.succeeded == 1
        mock_persistence.save_job.assert_called()

    def test_explicit_job_id(self, processor, tmp_path, mock_persistence):
        f = tmp_path / "a.txt"
        f.write_text("x")

        with patch.object(
            processor._processor,
            "process_batch_iter",
            return_value=[_make_file_result(f)],
        ):
            result = processor.process_with_resume([f], lambda p: "ok", job_id="my-job")

        assert result.succeeded == 1


# ---------------------------------------------------------------------------
# resume_job
# ---------------------------------------------------------------------------


class TestResumeJob:
    def test_job_not_found_raises(self, processor, mock_persistence):
        mock_persistence.load_job.return_value = None
        with pytest.raises(ValueError, match="Job not found"):
            processor.resume_job("missing-job", lambda p: "ok")

    def test_checkpoint_not_found_raises(self, processor, mock_persistence, mock_checkpoint_mgr):
        mock_persistence.load_job.return_value = JobState(
            id="j1", status=JobStatus.RUNNING, total_files=1
        )
        mock_checkpoint_mgr.load_checkpoint.return_value = None
        with pytest.raises(ValueError, match="Checkpoint not found"):
            processor.resume_job("j1", lambda p: "ok")

    def test_resume_nothing_to_process(self, processor, mock_persistence, mock_checkpoint_mgr):
        job = JobState(id="j1", status=JobStatus.RUNNING, total_files=2)
        mock_persistence.load_job.return_value = job

        cp = MagicMock(spec=Checkpoint)
        cp.pending_paths = []
        cp.completed_paths = [Path("/a"), Path("/b")]
        mock_checkpoint_mgr.load_checkpoint.return_value = cp
        mock_checkpoint_mgr.has_file_changed.return_value = False
        mock_checkpoint_mgr.create_checkpoint.return_value = cp

        result = processor.resume_job("j1", lambda p: "ok")
        assert result.succeeded == 2
        assert result.failed == 0

    def test_resume_with_modified_files(
        self, processor, mock_persistence, mock_checkpoint_mgr, tmp_path
    ):
        f1 = tmp_path / "mod.txt"
        f1.write_text("modified")

        job = JobState(id="j1", status=JobStatus.RUNNING, total_files=1)
        mock_persistence.load_job.return_value = job

        cp = MagicMock(spec=Checkpoint)
        cp.pending_paths = []
        cp.completed_paths = [f1]
        mock_checkpoint_mgr.load_checkpoint.return_value = cp
        mock_checkpoint_mgr.has_file_changed.return_value = True

        new_cp = MagicMock(spec=Checkpoint)
        new_cp.completed_paths = []
        new_cp.pending_paths = [f1]
        mock_checkpoint_mgr.create_checkpoint.return_value = new_cp

        with patch.object(
            processor._processor,
            "process_batch_iter",
            return_value=[_make_file_result(f1)],
        ):
            result = processor.resume_job("j1", lambda p: "ok")

        assert result.succeeded >= 1


# ---------------------------------------------------------------------------
# _process_and_checkpoint
# ---------------------------------------------------------------------------


class TestProcessAndCheckpoint:
    def test_failed_files_set_failed_status(
        self, processor, mock_persistence, mock_checkpoint_mgr, tmp_path
    ):
        f = tmp_path / "bad.txt"
        f.write_text("x")

        job = JobState(id="j1", status=JobStatus.RUNNING, total_files=1)
        cp = MagicMock(spec=Checkpoint)
        mock_checkpoint_mgr.create_checkpoint.return_value = cp

        with patch.object(
            processor._processor,
            "process_batch_iter",
            return_value=[_make_file_result(f, success=False)],
        ):
            result = processor._process_and_checkpoint(
                job=job, files=[f], process_fn=lambda p: "ok", checkpoint=cp
            )

        assert result.failed == 1
        assert job.status == JobStatus.FAILED

    def test_exception_marks_job_failed(
        self, processor, mock_persistence, mock_checkpoint_mgr, tmp_path
    ):
        f = tmp_path / "err.txt"
        f.write_text("x")

        job = JobState(id="j1", status=JobStatus.RUNNING, total_files=1)
        cp = MagicMock(spec=Checkpoint)
        mock_checkpoint_mgr.create_checkpoint.return_value = cp

        with patch.object(
            processor._processor,
            "process_batch_iter",
            side_effect=RuntimeError("crash"),
        ):
            with pytest.raises(RuntimeError, match="crash"):
                processor._process_and_checkpoint(
                    job=job, files=[f], process_fn=lambda p: "ok", checkpoint=cp
                )

        assert job.status == JobStatus.FAILED

    def test_no_checkpoint_provided(
        self, processor, mock_persistence, mock_checkpoint_mgr, tmp_path
    ):
        f = tmp_path / "a.txt"
        f.write_text("x")

        job = JobState(id="j1", status=JobStatus.RUNNING, total_files=1)
        mock_checkpoint_mgr.load_checkpoint.return_value = MagicMock(spec=Checkpoint)

        with patch.object(
            processor._processor,
            "process_batch_iter",
            return_value=[_make_file_result(f)],
        ):
            result = processor._process_and_checkpoint(
                job=job, files=[f], process_fn=lambda p: "ok", checkpoint=None
            )

        assert result.succeeded == 1
