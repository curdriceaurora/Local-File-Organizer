"""
Unit tests for JobPersistence.

Tests CRUD operations for JSON-based job state storage, including
save, load, list, delete, filtering, and error handling.
"""

from __future__ import annotations

import json
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from file_organizer.parallel.models import JobState, JobStatus, JobSummary
from file_organizer.parallel.persistence import JobPersistence


class TestJobPersistenceInit(unittest.TestCase):
    """Test JobPersistence initialization."""

    def test_default_jobs_dir(self) -> None:
        """Test that default directory is under home."""
        persistence = JobPersistence()
        self.assertEqual(persistence.jobs_dir, Path.home() / ".file-organizer" / "jobs")

    def test_custom_jobs_dir(self, tmp_path: Path | None = None) -> None:
        """Test that custom directory is used."""
        custom = Path("/tmp/test-jobs")
        persistence = JobPersistence(jobs_dir=custom)
        self.assertEqual(persistence.jobs_dir, custom)


class TestSaveAndLoadJob(unittest.TestCase):
    """Test saving and loading job state."""

    def setUp(self) -> None:
        """Set up a temporary directory for tests."""
        import tempfile

        self._tmpdir = tempfile.mkdtemp()
        self.jobs_dir = Path(self._tmpdir) / "jobs"
        self.persistence = JobPersistence(jobs_dir=self.jobs_dir)

    def tearDown(self) -> None:
        """Clean up temp directory."""
        import shutil

        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_save_creates_directory(self) -> None:
        """Test that save_job creates the jobs directory."""
        self.assertFalse(self.jobs_dir.exists())
        job = JobState(id="job-1", total_files=5)
        self.persistence.save_job(job)
        self.assertTrue(self.jobs_dir.exists())

    def test_save_creates_json_file(self) -> None:
        """Test that save_job creates a JSON file."""
        job = JobState(id="job-2", total_files=10)
        self.persistence.save_job(job)
        path = self.jobs_dir / "job-2.json"
        self.assertTrue(path.exists())

    def test_save_and_load_roundtrip(self) -> None:
        """Test that a job can be saved and loaded back identically."""
        now = datetime.now(UTC)
        job = JobState(
            id="roundtrip-1",
            status=JobStatus.RUNNING,
            created=now,
            updated=now,
            total_files=100,
            completed_files=42,
            failed_files=3,
            config={"max_workers": 4},
        )
        self.persistence.save_job(job)
        loaded = self.persistence.load_job("roundtrip-1")
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded.id, "roundtrip-1")
        self.assertEqual(loaded.status, JobStatus.RUNNING)
        self.assertEqual(loaded.total_files, 100)
        self.assertEqual(loaded.completed_files, 42)
        self.assertEqual(loaded.failed_files, 3)
        self.assertEqual(loaded.config, {"max_workers": 4})

    def test_save_overwrites_existing(self) -> None:
        """Test that saving again overwrites the previous state."""
        job = JobState(id="overwrite-1", status=JobStatus.PENDING, total_files=5)
        self.persistence.save_job(job)

        job.status = JobStatus.COMPLETED
        job.completed_files = 5
        self.persistence.save_job(job)

        loaded = self.persistence.load_job("overwrite-1")
        assert loaded is not None
        self.assertEqual(loaded.status, JobStatus.COMPLETED)
        self.assertEqual(loaded.completed_files, 5)

    def test_load_nonexistent_returns_none(self) -> None:
        """Test that loading a nonexistent job returns None."""
        result = self.persistence.load_job("does-not-exist")
        self.assertIsNone(result)

    def test_load_corrupted_json_returns_none(self) -> None:
        """Test that corrupted JSON files return None."""
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        path = self.jobs_dir / "corrupt.json"
        path.write_text("not valid json {{{", encoding="utf-8")
        result = self.persistence.load_job("corrupt")
        self.assertIsNone(result)

    def test_load_missing_fields_returns_none(self) -> None:
        """Test that JSON missing required fields returns None."""
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        path = self.jobs_dir / "incomplete.json"
        path.write_text(json.dumps({"id": "incomplete"}), encoding="utf-8")
        result = self.persistence.load_job("incomplete")
        self.assertIsNone(result)

    def test_save_with_error_field(self) -> None:
        """Test saving and loading a job with an error message."""
        job = JobState(
            id="error-job",
            status=JobStatus.FAILED,
            error="Something went wrong",
        )
        self.persistence.save_job(job)
        loaded = self.persistence.load_job("error-job")
        assert loaded is not None
        self.assertEqual(loaded.error, "Something went wrong")
        self.assertEqual(loaded.status, JobStatus.FAILED)

    def test_save_with_none_error(self) -> None:
        """Test saving a job with no error preserves None."""
        job = JobState(id="no-error", status=JobStatus.COMPLETED)
        self.persistence.save_job(job)
        loaded = self.persistence.load_job("no-error")
        assert loaded is not None
        self.assertIsNone(loaded.error)


class TestListJobs(unittest.TestCase):
    """Test listing persisted jobs."""

    def setUp(self) -> None:
        """Set up temp directory and persistence."""
        import tempfile

        self._tmpdir = tempfile.mkdtemp()
        self.jobs_dir = Path(self._tmpdir) / "jobs"
        self.persistence = JobPersistence(jobs_dir=self.jobs_dir)

    def tearDown(self) -> None:
        """Clean up temp directory."""
        import shutil

        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_list_empty_directory(self) -> None:
        """Test listing when no jobs directory exists."""
        result = self.persistence.list_jobs()
        self.assertEqual(result, [])

    def test_list_all_jobs(self) -> None:
        """Test listing all jobs without filter."""
        for i in range(3):
            job = JobState(
                id=f"list-{i}",
                status=JobStatus.COMPLETED,
                total_files=10,
                completed_files=10,
            )
            self.persistence.save_job(job)

        result = self.persistence.list_jobs()
        self.assertEqual(len(result), 3)
        for summary in result:
            self.assertIsInstance(summary, JobSummary)

    def test_list_with_status_filter(self) -> None:
        """Test listing jobs filtered by status."""
        self.persistence.save_job(JobState(id="pending-1", status=JobStatus.PENDING))
        self.persistence.save_job(JobState(id="running-1", status=JobStatus.RUNNING))
        self.persistence.save_job(JobState(id="completed-1", status=JobStatus.COMPLETED))

        pending = self.persistence.list_jobs(status=JobStatus.PENDING)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].id, "pending-1")

        running = self.persistence.list_jobs(status=JobStatus.RUNNING)
        self.assertEqual(len(running), 1)
        self.assertEqual(running[0].id, "running-1")

    def test_list_skips_corrupted_files(self) -> None:
        """Test that corrupted files are skipped during listing."""
        self.persistence.save_job(JobState(id="good-job", status=JobStatus.COMPLETED))
        # Create a corrupted file
        corrupt_path = self.jobs_dir / "bad-job.json"
        corrupt_path.write_text("{{invalid json", encoding="utf-8")

        result = self.persistence.list_jobs()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, "good-job")

    def test_list_sorted_newest_first(self) -> None:
        """Test that listed jobs are sorted by creation time (newest first)."""
        from datetime import timedelta

        base = datetime(2026, 1, 1, tzinfo=UTC)

        for i in range(3):
            job = JobState(
                id=f"sorted-{i}",
                status=JobStatus.COMPLETED,
                created=base + timedelta(hours=i),
                updated=base + timedelta(hours=i),
            )
            self.persistence.save_job(job)

        result = self.persistence.list_jobs()
        ids = [s.id for s in result]
        self.assertEqual(ids, ["sorted-2", "sorted-1", "sorted-0"])


class TestDeleteJob(unittest.TestCase):
    """Test deleting persisted jobs."""

    def setUp(self) -> None:
        """Set up temp directory and persistence."""
        import tempfile

        self._tmpdir = tempfile.mkdtemp()
        self.jobs_dir = Path(self._tmpdir) / "jobs"
        self.persistence = JobPersistence(jobs_dir=self.jobs_dir)

    def tearDown(self) -> None:
        """Clean up temp directory."""
        import shutil

        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_delete_existing_job(self) -> None:
        """Test deleting an existing job returns True."""
        job = JobState(id="delete-me")
        self.persistence.save_job(job)
        result = self.persistence.delete_job("delete-me")
        self.assertTrue(result)
        self.assertFalse((self.jobs_dir / "delete-me.json").exists())

    def test_delete_nonexistent_job(self) -> None:
        """Test deleting a nonexistent job returns False."""
        result = self.persistence.delete_job("nope")
        self.assertFalse(result)

    def test_delete_then_load_returns_none(self) -> None:
        """Test that loading a deleted job returns None."""
        job = JobState(id="gone")
        self.persistence.save_job(job)
        self.persistence.delete_job("gone")
        self.assertIsNone(self.persistence.load_job("gone"))


class TestJobExists(unittest.TestCase):
    """Test job existence checks."""

    def setUp(self) -> None:
        """Set up temp directory and persistence."""
        import tempfile

        self._tmpdir = tempfile.mkdtemp()
        self.jobs_dir = Path(self._tmpdir) / "jobs"
        self.persistence = JobPersistence(jobs_dir=self.jobs_dir)

    def tearDown(self) -> None:
        """Clean up temp directory."""
        import shutil

        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_exists_for_saved_job(self) -> None:
        """Test that job_exists returns True after saving."""
        job = JobState(id="exists-1")
        self.persistence.save_job(job)
        self.assertTrue(self.persistence.job_exists("exists-1"))

    def test_not_exists_for_unsaved_job(self) -> None:
        """Test that job_exists returns False for unknown job."""
        self.assertFalse(self.persistence.job_exists("phantom"))


class TestJobPersistenceAtomicWrites(unittest.TestCase):
    """Test atomic write behavior for job persistence."""

    def setUp(self) -> None:
        """Set up temp directory and persistence."""
        import tempfile

        self._tmpdir = tempfile.mkdtemp()
        self.jobs_dir = Path(self._tmpdir) / "jobs"
        self.persistence = JobPersistence(jobs_dir=self.jobs_dir)

    def tearDown(self) -> None:
        """Clean up temp directory."""
        import shutil

        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_save_job_uses_temp_file_then_replace(self) -> None:
        """Test save_job writes temp file before replacing target."""
        job = JobState(id="atomic-job-1", status=JobStatus.RUNNING, total_files=5)
        job_path = self.jobs_dir / "atomic-job-1.json"

        original_replace = Path.replace
        saw_temp_file_before_replace = False

        def wrapped_replace(path_self: Path, target: Path) -> Path:
            nonlocal saw_temp_file_before_replace
            if path_self.suffix == ".tmp":
                saw_temp_file_before_replace = path_self.exists()
            return original_replace(path_self, target)

        with patch.object(Path, "replace", autospec=True, side_effect=wrapped_replace):
            self.persistence.save_job(job)

        self.assertTrue(saw_temp_file_before_replace)
        self.assertTrue(job_path.exists())
        self.assertFalse(job_path.with_suffix(".tmp").exists())

    def test_temp_file_cleaned_up_after_successful_write(self) -> None:
        """Test temporary files are created during writes and cleaned up after."""
        job = JobState(id="atomic-job-2", status=JobStatus.RUNNING, total_files=5)
        temp_path = self.jobs_dir / "atomic-job-2.tmp"
        job_path = self.jobs_dir / "atomic-job-2.json"

        original_write_text = Path.write_text
        temp_file_was_created = False

        def track_temp_write(path_self: Path, data: str, encoding: str = "utf-8") -> int:
            nonlocal temp_file_was_created
            if path_self.suffix == ".tmp":
                temp_file_was_created = True
            return original_write_text(path_self, data, encoding=encoding)

        with patch.object(Path, "write_text", autospec=True, side_effect=track_temp_write):
            self.persistence.save_job(job)

        # Verify temp file was created during save
        self.assertTrue(temp_file_was_created)
        # Verify the final file exists and temp file does not
        self.assertTrue(job_path.exists())
        self.assertFalse(temp_path.exists())

        # Verify we can read back the data correctly
        loaded = self.persistence.load_job("atomic-job-2")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.id, "atomic-job-2")
        self.assertEqual(loaded.status, JobStatus.RUNNING)

    def test_temp_file_cleaned_up_after_write_failure(self) -> None:
        """Test temporary files are cleaned up after failed writes."""
        job = JobState(id="atomic-job-3", status=JobStatus.PENDING, total_files=10)
        job_path = self.jobs_dir / "atomic-job-3.json"
        temp_path = job_path.with_suffix(".tmp")

        original_replace = Path.replace

        def failing_replace(path_self: Path, target: Path) -> Path:
            # Let write_text succeed so temp file is created, then fail on replace
            if path_self.suffix == ".tmp":
                raise OSError("simulated replace failure")
            return original_replace(path_self, target)

        with patch.object(Path, "replace", autospec=True, side_effect=failing_replace):
            with self.assertRaises(OSError):
                self.persistence.save_job(job)

        # Verify temp file was cleaned up even though replace failed
        self.assertFalse(temp_path.exists())
        # And the job file was never created
        self.assertFalse(job_path.exists())

    def test_failed_save_does_not_corrupt_existing_file(self) -> None:
        """Test failed save operations don't corrupt existing job files."""
        job = JobState(id="atomic-job-4", status=JobStatus.PENDING, total_files=10)
        self.persistence.save_job(job)
        job_path = self.jobs_dir / "atomic-job-4.json"
        original_contents = job_path.read_text(encoding="utf-8")

        original_replace = Path.replace

        def failing_replace(path_self: Path, target: Path) -> Path:
            # Let write_text succeed so temp file is created, then fail on replace
            if path_self.suffix == ".tmp":
                raise OSError("simulated replace failure")
            return original_replace(path_self, target)

        updated_job = JobState(
            id="atomic-job-4",
            status=JobStatus.COMPLETED,
            total_files=10,
            completed_files=10,
        )

        with patch.object(Path, "replace", autospec=True, side_effect=failing_replace):
            with self.assertRaises(OSError):
                self.persistence.save_job(updated_job)

        self.assertEqual(
            job_path.read_text(encoding="utf-8"),
            original_contents,
            "Existing job file should remain intact on failed save",
        )
        self.assertFalse(job_path.with_suffix(".tmp").exists())


if __name__ == "__main__":
    unittest.main()
