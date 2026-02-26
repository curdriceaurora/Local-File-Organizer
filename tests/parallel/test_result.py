"""
Unit tests for parallel processing result dataclasses.

Tests FileResult and BatchResult data structures, summary generation,
and string representations.
"""

import unittest
from pathlib import Path

import pytest

from file_organizer.parallel.result import BatchResult, FileResult


@pytest.mark.unit
class TestFileResult(unittest.TestCase):
    """Test cases for FileResult dataclass."""

    def test_successful_result(self) -> None:
        """Test creating a successful file result."""
        result = FileResult(
            path=Path("test.txt"),
            success=True,
            result="processed",
            duration_ms=150.5,
        )
        self.assertTrue(result.success)
        self.assertEqual(result.result, "processed")
        self.assertIsNone(result.error)
        self.assertAlmostEqual(result.duration_ms, 150.5)

    def test_failed_result(self) -> None:
        """Test creating a failed file result."""
        result = FileResult(
            path=Path("bad.txt"),
            success=False,
            error="File not found",
            duration_ms=5.0,
        )
        self.assertFalse(result.success)
        self.assertIsNone(result.result)
        self.assertEqual(result.error, "File not found")

    def test_str_success(self) -> None:
        """Test string representation of successful result."""
        result = FileResult(
            path=Path("file.txt"),
            success=True,
            duration_ms=42.0,
        )
        text = str(result)
        self.assertIn("OK", text)
        self.assertIn("file.txt", text)
        self.assertIn("42.0ms", text)

    def test_str_failure(self) -> None:
        """Test string representation of failed result."""
        result = FileResult(
            path=Path("broken.txt"),
            success=False,
            error="permission denied",
            duration_ms=1.0,
        )
        text = str(result)
        self.assertIn("FAIL", text)
        self.assertIn("broken.txt", text)
        self.assertIn("permission denied", text)

    def test_default_values(self) -> None:
        """Test default field values."""
        result = FileResult(path=Path("x.txt"), success=True)
        self.assertIsNone(result.result)
        self.assertIsNone(result.error)
        self.assertEqual(result.duration_ms, 0.0)

    def test_result_with_complex_return(self) -> None:
        """Test storing complex objects as result."""
        data = {"key": "value", "count": 42}
        result = FileResult(
            path=Path("data.json"),
            success=True,
            result=data,
            duration_ms=10.0,
        )
        self.assertEqual(result.result, {"key": "value", "count": 42})

    def test_result_preserves_path_type(self) -> None:
        """Test that path remains a Path object."""
        result = FileResult(path=Path("/tmp/file.txt"), success=True)
        self.assertIsInstance(result.path, Path)

    def test_result_with_zero_duration(self) -> None:
        """Test result with zero duration."""
        result = FileResult(
            path=Path("fast.txt"),
            success=True,
            result=None,
            duration_ms=0.0,
        )
        self.assertEqual(result.duration_ms, 0.0)
        self.assertIn("0.0ms", str(result))

    def test_result_with_large_duration(self) -> None:
        """Test result with large duration value."""
        result = FileResult(
            path=Path("slow.bin"),
            success=True,
            duration_ms=120000.0,
        )
        self.assertAlmostEqual(result.duration_ms, 120000.0)

    def test_result_error_none_when_success(self) -> None:
        """Test that error is None on success by default."""
        result = FileResult(path=Path("ok.txt"), success=True, result=42)
        self.assertIsNone(result.error)


@pytest.mark.unit
class TestBatchResult(unittest.TestCase):
    """Test cases for BatchResult dataclass."""

    def test_empty_batch(self) -> None:
        """Test default empty batch result."""
        batch = BatchResult()
        self.assertEqual(batch.total, 0)
        self.assertEqual(batch.succeeded, 0)
        self.assertEqual(batch.failed, 0)
        self.assertEqual(batch.results, [])
        self.assertEqual(batch.total_duration_ms, 0.0)
        self.assertEqual(batch.files_per_second, 0.0)

    def test_all_succeeded(self) -> None:
        """Test batch where all files succeeded."""
        results = [
            FileResult(path=Path(f"file{i}.txt"), success=True, duration_ms=10.0) for i in range(5)
        ]
        batch = BatchResult(
            total=5,
            succeeded=5,
            failed=0,
            results=results,
            total_duration_ms=100.0,
            files_per_second=50.0,
        )
        self.assertEqual(batch.total, 5)
        self.assertEqual(batch.succeeded, 5)
        self.assertEqual(batch.failed, 0)

    def test_mixed_results(self) -> None:
        """Test batch with both successes and failures."""
        results = [
            FileResult(path=Path("good.txt"), success=True, duration_ms=10.0),
            FileResult(
                path=Path("bad.txt"),
                success=False,
                error="corrupt",
                duration_ms=5.0,
            ),
        ]
        batch = BatchResult(
            total=2,
            succeeded=1,
            failed=1,
            results=results,
            total_duration_ms=50.0,
            files_per_second=40.0,
        )
        self.assertEqual(batch.succeeded, 1)
        self.assertEqual(batch.failed, 1)

    def test_summary_all_success(self) -> None:
        """Test summary output when all files succeed."""
        results = [
            FileResult(path=Path("a.txt"), success=True, duration_ms=10.0),
        ]
        batch = BatchResult(
            total=1,
            succeeded=1,
            failed=0,
            results=results,
            total_duration_ms=10.0,
            files_per_second=100.0,
        )
        summary = batch.summary()
        self.assertIn("Batch complete: 1 files", summary)
        self.assertIn("Succeeded: 1", summary)
        self.assertIn("Failed: 0", summary)
        self.assertNotIn("Failures:", summary)

    def test_summary_with_failures(self) -> None:
        """Test summary includes failure details."""
        results = [
            FileResult(
                path=Path("fail.txt"),
                success=False,
                error="timeout",
                duration_ms=60000.0,
            ),
        ]
        batch = BatchResult(
            total=1,
            succeeded=0,
            failed=1,
            results=results,
            total_duration_ms=60000.0,
            files_per_second=0.02,
        )
        summary = batch.summary()
        self.assertIn("Failed: 1", summary)
        self.assertIn("Failures:", summary)
        self.assertIn("fail.txt", summary)
        self.assertIn("timeout", summary)

    def test_summary_truncates_many_failures(self) -> None:
        """Test summary only shows first 5 failures."""
        results = [
            FileResult(
                path=Path(f"fail{i}.txt"),
                success=False,
                error=f"error {i}",
                duration_ms=1.0,
            )
            for i in range(8)
        ]
        batch = BatchResult(
            total=8,
            succeeded=0,
            failed=8,
            results=results,
            total_duration_ms=100.0,
            files_per_second=80.0,
        )
        summary = batch.summary()
        self.assertIn("... and 3 more", summary)

    def test_str_delegates_to_summary(self) -> None:
        """Test that __str__ returns the same as summary()."""
        batch = BatchResult(
            total=3,
            succeeded=3,
            failed=0,
            total_duration_ms=30.0,
            files_per_second=100.0,
        )
        self.assertEqual(str(batch), batch.summary())

    def test_files_per_second_calculation(self) -> None:
        """Test throughput metric storage."""
        batch = BatchResult(
            total=100,
            succeeded=100,
            failed=0,
            total_duration_ms=2000.0,
            files_per_second=50.0,
        )
        self.assertAlmostEqual(batch.files_per_second, 50.0)

    def test_batch_results_list_independent(self) -> None:
        """Test that results list is independent across instances."""
        batch1 = BatchResult()
        batch2 = BatchResult()
        batch1.results.append(FileResult(path=Path("a.txt"), success=True))
        self.assertEqual(len(batch2.results), 0)

    def test_summary_throughput_formatting(self) -> None:
        """Test throughput value is formatted to 2 decimal places."""
        batch = BatchResult(
            total=3,
            succeeded=3,
            failed=0,
            total_duration_ms=100.0,
            files_per_second=33.33333,
        )
        summary = batch.summary()
        self.assertIn("33.33 files/sec", summary)


if __name__ == "__main__":
    unittest.main()
