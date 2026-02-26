"""
Unit tests for ResumableProcessor.

Tests resumable batch processing including fresh runs, resume after
interruption, hash mismatch detection, and error handling.
"""

from __future__ import annotations
import pytest

import unittest
from pathlib import Path

from file_organizer.parallel.checkpoint import CheckpointManager
from file_organizer.parallel.config import ExecutorType, ParallelConfig
from file_organizer.parallel.models import JobState, JobStatus
from file_organizer.parallel.persistence import JobPersistence
from file_organizer.parallel.resume import ResumableProcessor


def _identity(path: Path) -> str:
    """Return the file name as a string."""
    return path.name


def _always_fail(path: Path) -> None:
    """Always raises a ValueError."""
    raise ValueError(f"Simulated failure for {path}")


@pytest.mark.unit
class TestProcessWithResume(unittest.TestCase):
    """Test ResumableProcessor.process_with_resume."""

    def setUp(self) -> None:
        """Set up temp directory and processor."""
        import tempfile

        self._tmpdir = tempfile.mkdtemp()
        self.tmp_path = Path(self._tmpdir)
        self.jobs_dir = self.tmp_path / "jobs"
        self.ckpt_dir = self.tmp_path / "checkpoints"

        self.config = ParallelConfig(
            max_workers=1,
            executor_type=ExecutorType.THREAD,
            retry_count=0,
        )
        self.persistence = JobPersistence(jobs_dir=self.jobs_dir)
        self.checkpoint_mgr = CheckpointManager(checkpoints_dir=self.ckpt_dir)
        self.processor = ResumableProcessor(
            config=self.config,
            persistence=self.persistence,
            checkpoint_mgr=self.checkpoint_mgr,
        )

    def tearDown(self) -> None:
        """Clean up temp directory."""
        import shutil

        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_process_creates_job_state(self) -> None:
        """Test that processing creates a persisted job state."""
        files = [self.tmp_path / f"f{i}.txt" for i in range(3)]
        for f in files:
            f.write_text(f.name, encoding="utf-8")

        result = self.processor.process_with_resume(files, _identity, job_id="job-1")
        self.assertEqual(result.succeeded, 3)

        job = self.persistence.load_job("job-1")
        self.assertIsNotNone(job)
        assert job is not None
        self.assertEqual(job.status, JobStatus.COMPLETED)

    def test_process_creates_checkpoint(self) -> None:
        """Test that processing creates a checkpoint."""
        files = [self.tmp_path / "check.txt"]
        files[0].write_text("check", encoding="utf-8")

        self.processor.process_with_resume(files, _identity, job_id="ckpt-job")
        ckpt = self.checkpoint_mgr.load_checkpoint("ckpt-job")
        self.assertIsNotNone(ckpt)

    def test_process_auto_generates_job_id(self) -> None:
        """Test that omitting job_id auto-generates one."""
        f = self.tmp_path / "auto.txt"
        f.write_text("auto", encoding="utf-8")

        result = self.processor.process_with_resume([f], _identity)
        self.assertEqual(result.succeeded, 1)

        jobs = self.persistence.list_jobs()
        self.assertEqual(len(jobs), 1)

    def test_process_empty_file_list(self) -> None:
        """Test processing with no files."""
        result = self.processor.process_with_resume([], _identity, job_id="empty")
        self.assertEqual(result.total, 0)
        self.assertEqual(result.succeeded, 0)

    def test_process_all_fail_marks_failed(self) -> None:
        """Test that all failures marks job as FAILED."""
        files = [self.tmp_path / f"fail{i}.txt" for i in range(2)]
        for f in files:
            f.write_text(f.name, encoding="utf-8")

        result = self.processor.process_with_resume(files, _always_fail, job_id="all-fail")
        self.assertEqual(result.failed, 2)

        job = self.persistence.load_job("all-fail")
        assert job is not None
        self.assertEqual(job.status, JobStatus.FAILED)

    def test_process_mixed_results(self) -> None:
        """Test processing with some successes and some failures."""

        def mixed_fn(path: Path) -> str:
            if "bad" in path.name:
                raise ValueError("bad file")
            return path.name

        files = [
            self.tmp_path / "good.txt",
            self.tmp_path / "bad.txt",
        ]
        for f in files:
            f.write_text(f.name, encoding="utf-8")

        result = self.processor.process_with_resume(files, mixed_fn, job_id="mixed")
        self.assertEqual(result.succeeded, 1)
        self.assertEqual(result.failed, 1)

        job = self.persistence.load_job("mixed")
        assert job is not None
        # Has some succeeded, so COMPLETED (not all failures)
        self.assertEqual(job.status, JobStatus.COMPLETED)


@pytest.mark.unit
class TestResumeJob(unittest.TestCase):
    """Test ResumableProcessor.resume_job."""

    def setUp(self) -> None:
        """Set up temp directory and processor."""
        import tempfile

        self._tmpdir = tempfile.mkdtemp()
        self.tmp_path = Path(self._tmpdir)
        self.jobs_dir = self.tmp_path / "jobs"
        self.ckpt_dir = self.tmp_path / "checkpoints"

        self.config = ParallelConfig(
            max_workers=1,
            executor_type=ExecutorType.THREAD,
            retry_count=0,
        )
        self.persistence = JobPersistence(jobs_dir=self.jobs_dir)
        self.checkpoint_mgr = CheckpointManager(checkpoints_dir=self.ckpt_dir)
        self.processor = ResumableProcessor(
            config=self.config,
            persistence=self.persistence,
            checkpoint_mgr=self.checkpoint_mgr,
        )

    def tearDown(self) -> None:
        """Clean up temp directory."""
        import shutil

        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_resume_nonexistent_job_raises(self) -> None:
        """Test that resuming a missing job raises ValueError."""
        with self.assertRaises(ValueError):
            self.processor.resume_job("no-such-job", _identity)

    def test_resume_no_checkpoint_raises(self) -> None:
        """Test that resuming without checkpoint raises ValueError."""
        job = JobState(
            id="no-ckpt",
            status=JobStatus.PAUSED,
            total_files=5,
        )
        self.persistence.save_job(job)
        with self.assertRaises(ValueError):
            self.processor.resume_job("no-ckpt", _identity)

    def test_resume_processes_only_pending(self) -> None:
        """Test that resume skips already-completed files."""
        f1 = self.tmp_path / "done.txt"
        f2 = self.tmp_path / "pending.txt"
        f1.write_text("done", encoding="utf-8")
        f2.write_text("pending", encoding="utf-8")

        # Create a job with f1 completed and f2 pending
        job = JobState(
            id="resume-partial",
            status=JobStatus.PAUSED,
            total_files=2,
            completed_files=1,
        )
        self.persistence.save_job(job)

        self.checkpoint_mgr.create_checkpoint(
            job_id="resume-partial",
            completed_files=[f1],
            pending_files=[f2],
        )

        processed_files: list[str] = []

        def tracking_fn(path: Path) -> str:
            processed_files.append(path.name)
            return path.name

        result = self.processor.resume_job("resume-partial", tracking_fn)

        # Only f2 should be processed
        self.assertEqual(processed_files, ["pending.txt"])
        # But total should reflect the full job
        self.assertEqual(result.total, 2)
        self.assertEqual(result.succeeded, 2)  # 1 previous + 1 new

    def test_resume_reprocesses_modified_files(self) -> None:
        """Test that modified files are reprocessed on resume."""
        f1 = self.tmp_path / "modified.txt"
        f2 = self.tmp_path / "still_pending.txt"
        f1.write_text("original", encoding="utf-8")
        f2.write_text("pending", encoding="utf-8")

        # Create job and checkpoint with f1 completed
        job = JobState(
            id="hash-mismatch",
            status=JobStatus.PAUSED,
            total_files=2,
            completed_files=1,
        )
        self.persistence.save_job(job)

        self.checkpoint_mgr.create_checkpoint(
            job_id="hash-mismatch",
            completed_files=[f1],
            pending_files=[f2],
        )

        # Modify f1 after checkpoint
        f1.write_text("MODIFIED CONTENT", encoding="utf-8")

        processed_files: list[str] = []

        def tracking_fn(path: Path) -> str:
            processed_files.append(path.name)
            return path.name

        self.processor.resume_job("hash-mismatch", tracking_fn)

        # Both files should be processed (f1 modified, f2 pending)
        self.assertEqual(len(processed_files), 2)
        self.assertIn("modified.txt", processed_files)
        self.assertIn("still_pending.txt", processed_files)

    def test_resume_all_completed_no_changes(self) -> None:
        """Test resuming when all files are already done and unchanged."""
        f1 = self.tmp_path / "complete.txt"
        f1.write_text("done", encoding="utf-8")

        job = JobState(
            id="all-done",
            status=JobStatus.PAUSED,
            total_files=1,
            completed_files=1,
        )
        self.persistence.save_job(job)

        self.checkpoint_mgr.create_checkpoint(
            job_id="all-done",
            completed_files=[f1],
            pending_files=[],
        )

        result = self.processor.resume_job("all-done", _identity)
        self.assertEqual(result.total, 1)
        self.assertEqual(result.succeeded, 1)

        job = self.persistence.load_job("all-done")
        assert job is not None
        self.assertEqual(job.status, JobStatus.COMPLETED)

    def test_resume_updates_job_status(self) -> None:
        """Test that resume updates the final job status."""
        f1 = self.tmp_path / "resume_status.txt"
        f1.write_text("content", encoding="utf-8")

        job = JobState(
            id="status-update",
            status=JobStatus.PAUSED,
            total_files=1,
        )
        self.persistence.save_job(job)

        self.checkpoint_mgr.create_checkpoint(
            job_id="status-update",
            completed_files=[],
            pending_files=[f1],
        )

        self.processor.resume_job("status-update", _identity)

        final_job = self.persistence.load_job("status-update")
        assert final_job is not None
        self.assertEqual(final_job.status, JobStatus.COMPLETED)

    def test_full_workflow_process_then_resume(self) -> None:
        """Test a complete workflow: process, simulate interrupt, resume."""
        # Create files
        files = [self.tmp_path / f"wf{i}.txt" for i in range(4)]
        for f in files:
            f.write_text(f.name, encoding="utf-8")

        call_count = {"n": 0}

        def partial_fail(path: Path) -> str:
            call_count["n"] += 1
            # Fail on file wf2.txt and wf3.txt on first run
            if "wf2" in path.name or "wf3" in path.name:
                raise ValueError(f"Temporary failure for {path.name}")
            return path.name

        # First run: wf0 and wf1 succeed, wf2 and wf3 fail
        result = self.processor.process_with_resume(files, partial_fail, job_id="workflow")
        self.assertEqual(result.succeeded, 2)
        self.assertEqual(result.failed, 2)

        # For resume: now all files succeed
        self.processor.resume_job("workflow", _identity)

        # wf2 and wf3 were pending, should be processed now
        # Plus wf0 and wf1 are already completed
        final_job = self.persistence.load_job("workflow")
        assert final_job is not None
        self.assertEqual(final_job.status, JobStatus.COMPLETED)


if __name__ == "__main__":
    unittest.main()
