"""Unit tests for parallel processing data models.

Tests JobStatus, JobState, JobSummary, and Checkpoint dataclasses,
including serialization (to_dict) and deserialization (from_dict).
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime
from pathlib import Path

import pytest

from file_organizer.parallel.models import (
    Checkpoint,
    JobState,
    JobStatus,
    JobSummary,
)


@pytest.mark.unit
class TestJobStatus(unittest.TestCase):
    """Test cases for JobStatus enum."""

    def test_enum_values(self) -> None:
        """Test that JobStatus has the expected string values."""
        self.assertEqual(JobStatus.PENDING, "pending")
        self.assertEqual(JobStatus.RUNNING, "running")
        self.assertEqual(JobStatus.PAUSED, "paused")
        self.assertEqual(JobStatus.COMPLETED, "completed")
        self.assertEqual(JobStatus.FAILED, "failed")

    def test_string_comparison(self) -> None:
        """Test that JobStatus compares equal to its string value."""
        self.assertEqual(JobStatus.PENDING, "pending")
        self.assertEqual(str(JobStatus.RUNNING), "running")

    def test_all_members(self) -> None:
        """Test that all expected members exist."""
        members = {m.value for m in JobStatus}
        expected = {"pending", "running", "paused", "completed", "failed"}
        self.assertEqual(members, expected)

    def test_from_string(self) -> None:
        """Test creating JobStatus from string value."""
        self.assertEqual(JobStatus("pending"), JobStatus.PENDING)
        self.assertEqual(JobStatus("failed"), JobStatus.FAILED)

    def test_invalid_status_raises(self) -> None:
        """Test that invalid status string raises ValueError."""
        with self.assertRaises(ValueError):
            JobStatus("invalid")


@pytest.mark.unit
class TestJobState(unittest.TestCase):
    """Test cases for JobState dataclass."""

    def test_defaults(self) -> None:
        """Test default field values."""
        job = JobState(id="test-1")
        self.assertEqual(job.id, "test-1")
        self.assertEqual(job.status, JobStatus.PENDING)
        self.assertEqual(job.total_files, 0)
        self.assertEqual(job.completed_files, 0)
        self.assertEqual(job.failed_files, 0)
        self.assertEqual(job.config, {})
        self.assertIsNone(job.error)
        self.assertIsInstance(job.created, datetime)
        self.assertIsInstance(job.updated, datetime)

    def test_custom_values(self) -> None:
        """Test creating with custom values."""
        now = datetime.now(UTC)
        job = JobState(
            id="custom-1",
            status=JobStatus.RUNNING,
            created=now,
            updated=now,
            total_files=100,
            completed_files=42,
            failed_files=3,
            config={"workers": 4},
            error=None,
        )
        self.assertEqual(job.total_files, 100)
        self.assertEqual(job.completed_files, 42)
        self.assertEqual(job.config, {"workers": 4})

    def test_to_dict(self) -> None:
        """Test serializing JobState to dictionary."""
        now = datetime(2026, 1, 15, 10, 30, 0, tzinfo=UTC)
        job = JobState(
            id="ser-1",
            status=JobStatus.COMPLETED,
            created=now,
            updated=now,
            total_files=10,
            completed_files=10,
            failed_files=0,
            config={"key": "val"},
            error=None,
        )
        d = job.to_dict()
        self.assertEqual(d["id"], "ser-1")
        self.assertEqual(d["status"], "completed")
        self.assertEqual(d["total_files"], 10)
        self.assertEqual(d["completed_files"], 10)
        self.assertEqual(d["failed_files"], 0)
        self.assertEqual(d["config"], {"key": "val"})
        self.assertIsNone(d["error"])
        self.assertIn("2026-01-15", str(d["created"]))

    def test_to_dict_with_error(self) -> None:
        """Test serializing JobState with an error field."""
        job = JobState(
            id="err-1",
            status=JobStatus.FAILED,
            error="disk full",
        )
        d = job.to_dict()
        self.assertEqual(d["error"], "disk full")
        self.assertEqual(d["status"], "failed")

    def test_from_dict(self) -> None:
        """Test deserializing JobState from dictionary."""
        now = datetime(2026, 2, 1, 12, 0, 0, tzinfo=UTC)
        data = {
            "id": "deser-1",
            "status": "running",
            "created": now.isoformat(),
            "updated": now.isoformat(),
            "total_files": 50,
            "completed_files": 25,
            "failed_files": 2,
            "config": {"max_workers": 8},
            "error": None,
        }
        job = JobState.from_dict(data)
        self.assertEqual(job.id, "deser-1")
        self.assertEqual(job.status, JobStatus.RUNNING)
        self.assertEqual(job.total_files, 50)
        self.assertEqual(job.completed_files, 25)
        self.assertEqual(job.failed_files, 2)
        self.assertEqual(job.config, {"max_workers": 8})
        self.assertIsNone(job.error)

    def test_from_dict_with_error(self) -> None:
        """Test deserializing JobState with a non-None error."""
        now = datetime.now(UTC)
        data = {
            "id": "err-deser",
            "status": "failed",
            "created": now.isoformat(),
            "updated": now.isoformat(),
            "error": "something broke",
        }
        job = JobState.from_dict(data)
        self.assertEqual(job.error, "something broke")

    def test_from_dict_missing_optional_fields(self) -> None:
        """Test deserializing with missing optional fields uses defaults."""
        now = datetime.now(UTC)
        data = {
            "id": "minimal",
            "status": "pending",
            "created": now.isoformat(),
            "updated": now.isoformat(),
        }
        job = JobState.from_dict(data)
        self.assertEqual(job.total_files, 0)
        self.assertEqual(job.completed_files, 0)
        self.assertEqual(job.failed_files, 0)
        self.assertEqual(job.config, {})
        self.assertIsNone(job.error)

    def test_roundtrip_to_from_dict(self) -> None:
        """Test that to_dict -> from_dict produces equivalent state."""
        now = datetime(2026, 3, 1, 8, 0, 0, tzinfo=UTC)
        original = JobState(
            id="roundtrip",
            status=JobStatus.PAUSED,
            created=now,
            updated=now,
            total_files=200,
            completed_files=150,
            failed_files=10,
            config={"batch_size": 16},
            error="paused by user",
        )
        restored = JobState.from_dict(original.to_dict())
        self.assertEqual(restored.id, original.id)
        self.assertEqual(restored.status, original.status)
        self.assertEqual(restored.total_files, original.total_files)
        self.assertEqual(restored.completed_files, original.completed_files)
        self.assertEqual(restored.failed_files, original.failed_files)
        self.assertEqual(restored.config, original.config)
        self.assertEqual(restored.error, original.error)

    def test_from_dict_missing_id_raises(self) -> None:
        """Test that missing 'id' key raises KeyError."""
        with self.assertRaises(KeyError):
            JobState.from_dict({"status": "pending"})

    def test_from_dict_invalid_status_raises(self) -> None:
        """Test that invalid status value raises ValueError."""
        now = datetime.now(UTC).isoformat()
        with self.assertRaises(ValueError):
            JobState.from_dict(
                {
                    "id": "bad",
                    "status": "nonexistent",
                    "created": now,
                    "updated": now,
                }
            )


@pytest.mark.unit
class TestJobSummary(unittest.TestCase):
    """Test cases for JobSummary dataclass."""

    def test_from_job_state_with_progress(self) -> None:
        """Test creating summary from a job with progress."""
        job = JobState(
            id="sum-1",
            status=JobStatus.RUNNING,
            total_files=200,
            completed_files=100,
        )
        summary = JobSummary.from_job_state(job)
        self.assertEqual(summary.id, "sum-1")
        self.assertEqual(summary.status, JobStatus.RUNNING)
        self.assertAlmostEqual(summary.progress_percent, 50.0)

    def test_from_job_state_zero_total(self) -> None:
        """Test creating summary when total_files is zero."""
        job = JobState(id="empty", status=JobStatus.PENDING, total_files=0)
        summary = JobSummary.from_job_state(job)
        self.assertAlmostEqual(summary.progress_percent, 0.0)

    def test_from_job_state_completed(self) -> None:
        """Test creating summary from a fully completed job."""
        job = JobState(
            id="done",
            status=JobStatus.COMPLETED,
            total_files=50,
            completed_files=50,
        )
        summary = JobSummary.from_job_state(job)
        self.assertAlmostEqual(summary.progress_percent, 100.0)

    def test_from_job_state_preserves_created(self) -> None:
        """Test that summary preserves the job's creation time."""
        created = datetime(2026, 1, 1, tzinfo=UTC)
        job = JobState(id="time-test", created=created)
        summary = JobSummary.from_job_state(job)
        self.assertEqual(summary.created, created)

    def test_progress_rounding(self) -> None:
        """Test that progress is rounded to one decimal place."""
        job = JobState(
            id="rounding",
            status=JobStatus.RUNNING,
            total_files=3,
            completed_files=1,
        )
        summary = JobSummary.from_job_state(job)
        # 1/3 * 100 = 33.333... -> 33.3
        self.assertAlmostEqual(summary.progress_percent, 33.3, places=1)


@pytest.mark.unit
class TestCheckpoint(unittest.TestCase):
    """Test cases for Checkpoint dataclass."""

    def test_defaults(self) -> None:
        """Test default field values."""
        ckpt = Checkpoint(job_id="ckpt-1")
        self.assertEqual(ckpt.job_id, "ckpt-1")
        self.assertEqual(ckpt.completed_paths, [])
        self.assertEqual(ckpt.pending_paths, [])
        self.assertEqual(ckpt.file_hashes, {})
        self.assertIsInstance(ckpt.last_updated, datetime)

    def test_with_paths(self) -> None:
        """Test creating checkpoint with file paths."""
        completed = [Path("/a/b.txt"), Path("/c/d.txt")]
        pending = [Path("/e/f.txt")]
        ckpt = Checkpoint(
            job_id="paths-test",
            completed_paths=completed,
            pending_paths=pending,
            file_hashes={"/a/b.txt": "abc123", "/c/d.txt": "def456"},
        )
        self.assertEqual(len(ckpt.completed_paths), 2)
        self.assertEqual(len(ckpt.pending_paths), 1)
        self.assertEqual(len(ckpt.file_hashes), 2)

    def test_to_dict(self) -> None:
        """Test serializing Checkpoint to dictionary."""
        now = datetime(2026, 6, 15, 14, 0, 0, tzinfo=UTC)
        ckpt = Checkpoint(
            job_id="ser-ckpt",
            completed_paths=[Path("/done/a.txt")],
            pending_paths=[Path("/todo/b.txt"), Path("/todo/c.txt")],
            file_hashes={"/done/a.txt": "hash-a"},
            last_updated=now,
        )
        d = ckpt.to_dict()
        self.assertEqual(d["job_id"], "ser-ckpt")
        self.assertEqual(d["completed_paths"], ["/done/a.txt"])
        self.assertEqual(d["pending_paths"], ["/todo/b.txt", "/todo/c.txt"])
        self.assertEqual(d["file_hashes"], {"/done/a.txt": "hash-a"})
        self.assertIn("2026-06-15", str(d["last_updated"]))

    def test_to_dict_empty_paths(self) -> None:
        """Test serializing checkpoint with no paths."""
        ckpt = Checkpoint(job_id="empty-ckpt")
        d = ckpt.to_dict()
        self.assertEqual(d["completed_paths"], [])
        self.assertEqual(d["pending_paths"], [])
        self.assertEqual(d["file_hashes"], {})

    def test_from_dict(self) -> None:
        """Test deserializing Checkpoint from dictionary."""
        now = datetime(2026, 7, 1, 12, 0, 0, tzinfo=UTC)
        data = {
            "job_id": "deser-ckpt",
            "completed_paths": ["/x/a.txt"],
            "pending_paths": ["/x/b.txt", "/x/c.txt"],
            "file_hashes": {"/x/a.txt": "hash-a"},
            "last_updated": now.isoformat(),
        }
        ckpt = Checkpoint.from_dict(data)
        self.assertEqual(ckpt.job_id, "deser-ckpt")
        self.assertEqual(ckpt.completed_paths, [Path("/x/a.txt")])
        self.assertEqual(len(ckpt.pending_paths), 2)
        self.assertEqual(ckpt.file_hashes, {"/x/a.txt": "hash-a"})

    def test_from_dict_missing_optional_fields(self) -> None:
        """Test deserializing with missing optional fields uses defaults."""
        now = datetime.now(UTC)
        data = {
            "job_id": "minimal-ckpt",
            "last_updated": now.isoformat(),
        }
        ckpt = Checkpoint.from_dict(data)
        self.assertEqual(ckpt.completed_paths, [])
        self.assertEqual(ckpt.pending_paths, [])
        self.assertEqual(ckpt.file_hashes, {})

    def test_roundtrip_to_from_dict(self) -> None:
        """Test that to_dict -> from_dict produces equivalent checkpoint."""
        now = datetime(2026, 8, 1, 10, 0, 0, tzinfo=UTC)
        original = Checkpoint(
            job_id="roundtrip-ckpt",
            completed_paths=[Path("/a.txt"), Path("/b.txt")],
            pending_paths=[Path("/c.txt")],
            file_hashes={"/a.txt": "h1", "/b.txt": "h2"},
            last_updated=now,
        )
        restored = Checkpoint.from_dict(original.to_dict())
        self.assertEqual(restored.job_id, original.job_id)
        self.assertEqual(restored.completed_paths, original.completed_paths)
        self.assertEqual(restored.pending_paths, original.pending_paths)
        self.assertEqual(restored.file_hashes, original.file_hashes)

    def test_from_dict_missing_job_id_raises(self) -> None:
        """Test that missing 'job_id' key raises KeyError."""
        with self.assertRaises(KeyError):
            Checkpoint.from_dict(
                {
                    "last_updated": datetime.now(UTC).isoformat(),
                }
            )

    def test_lists_are_independent_across_instances(self) -> None:
        """Test that default mutable fields are independent."""
        ckpt1 = Checkpoint(job_id="a")
        ckpt2 = Checkpoint(job_id="b")
        ckpt1.completed_paths.append(Path("/x.txt"))
        self.assertEqual(len(ckpt2.completed_paths), 0)

    def test_file_hashes_independent_across_instances(self) -> None:
        """Test that file_hashes dicts are independent."""
        ckpt1 = Checkpoint(job_id="c")
        ckpt2 = Checkpoint(job_id="d")
        ckpt1.file_hashes["key"] = "val"
        self.assertEqual(len(ckpt2.file_hashes), 0)


if __name__ == "__main__":
    unittest.main()
