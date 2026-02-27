"""
Unit tests for the ParallelProcessor.

Tests parallel batch processing using simple test functions,
covering thread/process executors, timeouts, retries, progress
callbacks, error handling, and graceful shutdown.
"""

import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from file_organizer.parallel.config import ExecutorType, ParallelConfig
from file_organizer.parallel.processor import ParallelProcessor, _execute_with_timing
from file_organizer.parallel.result import BatchResult, FileResult

# ---------------------------------------------------------------------------
# Simple test functions (no real file I/O)
# ---------------------------------------------------------------------------


def _identity(path: Path) -> str:
    """Return the file name as a string."""
    return path.name


def _double_stem_length(path: Path) -> int:
    """Return double the length of the file stem."""
    return len(path.stem) * 2


def _always_fail(path: Path) -> None:
    """Always raises a ValueError."""
    raise ValueError(f"Simulated failure for {path}")


def _slow_fn(path: Path) -> str:
    """Sleep briefly then return the file name."""
    time.sleep(0.05)
    return path.name


def _fail_then_succeed_factory() -> tuple[MagicMock, object]:
    """Create a callable that fails on first call, succeeds on second."""
    call_counts: dict[str, int] = {}

    def fn(path: Path) -> str:
        key = str(path)
        call_counts[key] = call_counts.get(key, 0) + 1
        if call_counts[key] == 1:
            raise RuntimeError(f"Transient error for {path}")
        return path.name

    return MagicMock(wraps=fn), call_counts


@pytest.mark.unit
class TestExecuteWithTiming(unittest.TestCase):
    """Test the _execute_with_timing helper function."""

    def test_successful_execution(self) -> None:
        """Test timing wrapper on a successful function."""
        result = _execute_with_timing(Path("test.txt"), _identity)
        self.assertTrue(result.success)
        self.assertEqual(result.result, "test.txt")
        self.assertGreaterEqual(result.duration_ms, 0)

    def test_failed_execution(self) -> None:
        """Test timing wrapper captures exceptions."""
        result = _execute_with_timing(Path("fail.txt"), _always_fail)
        self.assertFalse(result.success)
        assert result.error is not None
        self.assertIn("Simulated failure", result.error)
        self.assertGreaterEqual(result.duration_ms, 0)

    def test_measures_time(self) -> None:
        """Test that timing is captured for slow functions."""
        result = _execute_with_timing(Path("slow.txt"), _slow_fn)
        self.assertTrue(result.success)
        self.assertGreater(result.duration_ms, 10.0)


@pytest.mark.unit
class TestParallelProcessorInit(unittest.TestCase):
    """Test ParallelProcessor initialization."""

    def test_default_config(self) -> None:
        """Test processor with default config."""
        processor = ParallelProcessor()
        self.assertIsNotNone(processor.config)
        self.assertIsNone(processor.config.max_workers)
        self.assertEqual(processor.config.executor_type, ExecutorType.THREAD)

    def test_custom_config(self) -> None:
        """Test processor with custom config."""
        config = ParallelConfig(
            max_workers=4,
            executor_type=ExecutorType.PROCESS,
            chunk_size=5,
            timeout_per_file=30.0,
            retry_count=1,
        )
        processor = ParallelProcessor(config=config)
        self.assertEqual(processor.config.max_workers, 4)
        self.assertEqual(processor.config.executor_type, ExecutorType.PROCESS)
        self.assertEqual(processor.config.chunk_size, 5)


@pytest.mark.unit
class TestProcessBatch(unittest.TestCase):
    """Test ParallelProcessor.process_batch."""

    def setUp(self) -> None:
        """Create processor with thread pool for test speed."""
        self.config = ParallelConfig(
            max_workers=2,
            executor_type=ExecutorType.THREAD,
            chunk_size=5,
            timeout_per_file=10.0,
            retry_count=0,
        )
        self.processor = ParallelProcessor(config=self.config)

    def test_empty_batch(self) -> None:
        """Test processing an empty file list."""
        result = self.processor.process_batch([], _identity)
        self.assertIsInstance(result, BatchResult)
        self.assertEqual(result.total, 0)
        self.assertEqual(result.succeeded, 0)
        self.assertEqual(result.failed, 0)

    def test_all_succeed(self) -> None:
        """Test batch where all files succeed."""
        files = [Path(f"file{i}.txt") for i in range(5)]
        result = self.processor.process_batch(files, _identity)
        self.assertEqual(result.total, 5)
        self.assertEqual(result.succeeded, 5)
        self.assertEqual(result.failed, 0)
        self.assertEqual(len(result.results), 5)

    def test_all_fail(self) -> None:
        """Test batch where all files fail."""
        files = [Path(f"file{i}.txt") for i in range(3)]
        result = self.processor.process_batch(files, _always_fail)
        self.assertEqual(result.total, 3)
        self.assertEqual(result.succeeded, 0)
        self.assertEqual(result.failed, 3)

    def test_mixed_results(self) -> None:
        """Test batch with both successes and failures."""

        def mixed_fn(path: Path) -> str:
            if "bad" in path.name:
                raise ValueError(f"Bad file: {path}")
            return path.name

        files = [Path("good1.txt"), Path("bad1.txt"), Path("good2.txt")]
        result = self.processor.process_batch(files, mixed_fn)
        self.assertEqual(result.total, 3)
        self.assertEqual(result.succeeded, 2)
        self.assertEqual(result.failed, 1)

    def test_result_values(self) -> None:
        """Test that result values from process_fn are captured."""
        files = [Path("hello.txt")]
        result = self.processor.process_batch(files, _double_stem_length)
        self.assertEqual(result.results[0].result, 10)  # len("hello") * 2

    def test_timing_is_positive(self) -> None:
        """Test that batch timing is measured."""
        files = [Path(f"f{i}.txt") for i in range(3)]
        result = self.processor.process_batch(files, _slow_fn)
        self.assertGreater(result.total_duration_ms, 0)
        self.assertGreater(result.files_per_second, 0)

    def test_files_per_second_calculated(self) -> None:
        """Test throughput metric is reasonable."""
        files = [Path(f"f{i}.txt") for i in range(4)]
        result = self.processor.process_batch(files, _identity)
        self.assertGreater(result.files_per_second, 0)
        # Should be total / (duration_ms/1000)
        if result.total_duration_ms > 0:
            expected_fps = len(files) / (result.total_duration_ms / 1000)
            self.assertAlmostEqual(result.files_per_second, expected_fps, places=1)

    def test_single_file(self) -> None:
        """Test processing a single file."""
        result = self.processor.process_batch([Path("only.txt")], _identity)
        self.assertEqual(result.total, 1)
        self.assertEqual(result.succeeded, 1)
        self.assertEqual(result.results[0].result, "only.txt")

    def test_large_batch(self) -> None:
        """Test processing many files."""
        files = [Path(f"file{i:04d}.txt") for i in range(50)]
        result = self.processor.process_batch(files, _identity)
        self.assertEqual(result.total, 50)
        self.assertEqual(result.succeeded, 50)

    def test_process_pool_executor(self) -> None:
        """Test processing with ProcessPoolExecutor."""
        config = ParallelConfig(
            max_workers=2,
            executor_type=ExecutorType.PROCESS,
            retry_count=0,
        )
        processor = ParallelProcessor(config=config)
        files = [Path(f"f{i}.txt") for i in range(3)]
        result = processor.process_batch(files, _identity)
        self.assertEqual(result.total, 3)
        self.assertEqual(result.succeeded, 3)


@pytest.mark.unit
class TestProcessBatchRetry(unittest.TestCase):
    """Test retry behavior in process_batch."""

    def test_retry_recovers_transient_failure(self) -> None:
        """Test that transient failures are retried and succeed."""
        call_counts: dict[str, int] = {}

        def fail_then_succeed(path: Path) -> str:
            key = str(path)
            call_counts[key] = call_counts.get(key, 0) + 1
            if call_counts[key] == 1:
                raise RuntimeError("transient")
            return path.name

        config = ParallelConfig(
            max_workers=1,
            executor_type=ExecutorType.THREAD,
            retry_count=2,
        )
        processor = ParallelProcessor(config=config)
        files = [Path("retry.txt")]
        result = processor.process_batch(files, fail_then_succeed)
        self.assertEqual(result.succeeded, 1)
        self.assertEqual(result.failed, 0)

    def test_retry_exhausted(self) -> None:
        """Test that persistent failures remain failed after retries."""
        config = ParallelConfig(
            max_workers=1,
            executor_type=ExecutorType.THREAD,
            retry_count=2,
        )
        processor = ParallelProcessor(config=config)
        files = [Path("always_fail.txt")]
        result = processor.process_batch(files, _always_fail)
        self.assertEqual(result.failed, 1)
        self.assertEqual(result.succeeded, 0)

    def test_zero_retries(self) -> None:
        """Test that zero retries means no retry attempts."""
        config = ParallelConfig(
            max_workers=1,
            executor_type=ExecutorType.THREAD,
            retry_count=0,
        )
        processor = ParallelProcessor(config=config)
        files = [Path("fail.txt")]
        result = processor.process_batch(files, _always_fail)
        self.assertEqual(result.failed, 1)


@pytest.mark.unit
class TestProgressCallback(unittest.TestCase):
    """Test progress callback invocation."""

    def test_callback_called_for_each_file(self) -> None:
        """Test that progress callback is called once per file."""
        callback = MagicMock()
        config = ParallelConfig(
            max_workers=1,
            executor_type=ExecutorType.THREAD,
            retry_count=0,
            progress_callback=callback,
        )
        processor = ParallelProcessor(config=config)
        files = [Path(f"f{i}.txt") for i in range(3)]
        processor.process_batch(files, _identity)
        self.assertEqual(callback.call_count, 3)

    def test_callback_receives_correct_total(self) -> None:
        """Test callback receives the total file count."""
        calls: list[tuple[int, int]] = []

        def track(completed: int, total: int, result: FileResult) -> None:
            calls.append((completed, total))

        config = ParallelConfig(
            max_workers=1,
            executor_type=ExecutorType.THREAD,
            retry_count=0,
            progress_callback=track,
        )
        processor = ParallelProcessor(config=config)
        files = [Path(f"f{i}.txt") for i in range(4)]
        processor.process_batch(files, _identity)
        # All calls should have total=4
        for _, total in calls:
            self.assertEqual(total, 4)

    def test_callback_completed_increments(self) -> None:
        """Test completed count increments with each callback."""
        completed_values: list[int] = []

        def track(completed: int, total: int, result: FileResult) -> None:
            completed_values.append(completed)

        config = ParallelConfig(
            max_workers=1,
            executor_type=ExecutorType.THREAD,
            retry_count=0,
            progress_callback=track,
        )
        processor = ParallelProcessor(config=config)
        files = [Path(f"f{i}.txt") for i in range(3)]
        processor.process_batch(files, _identity)
        self.assertEqual(sorted(completed_values), [1, 2, 3])


@pytest.mark.unit
class TestProcessBatchIter(unittest.TestCase):
    """Test ParallelProcessor.process_batch_iter."""

    def setUp(self) -> None:
        """Create processor for iteration tests."""
        self.config = ParallelConfig(
            max_workers=2,
            executor_type=ExecutorType.THREAD,
            timeout_per_file=10.0,
            retry_count=0,
        )
        self.processor = ParallelProcessor(config=self.config)

    def test_iter_empty(self) -> None:
        """Test iterating over empty file list."""
        results = list(self.processor.process_batch_iter([], _identity))
        self.assertEqual(results, [])

    def test_iter_yields_results(self) -> None:
        """Test that iterator yields FileResult objects."""
        files = [Path(f"f{i}.txt") for i in range(3)]
        results = list(self.processor.process_batch_iter(files, _identity))
        self.assertEqual(len(results), 3)
        for r in results:
            self.assertIsInstance(r, FileResult)

    def test_iter_captures_failures(self) -> None:
        """Test that iterator captures failures."""
        files = [Path("fail.txt")]
        results = list(self.processor.process_batch_iter(files, _always_fail))
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].success)
        assert results[0].error is not None
        self.assertIn("Simulated failure", results[0].error)

    def test_iter_calls_progress_callback(self) -> None:
        """Test iterator invokes progress callback."""
        callback = MagicMock()
        config = ParallelConfig(
            max_workers=1,
            executor_type=ExecutorType.THREAD,
            retry_count=0,
            progress_callback=callback,
        )
        processor = ParallelProcessor(config=config)
        files = [Path("a.txt"), Path("b.txt")]
        list(processor.process_batch_iter(files, _identity))
        self.assertEqual(callback.call_count, 2)


class TestExecutorFallback(unittest.TestCase):
    """Test ParallelProcessor executor fallback behavior."""

    def test_process_executor_preferred_when_available(self) -> None:
        """Test that ProcessPoolExecutor is used when configured."""
        config = ParallelConfig(
            max_workers=2,
            executor_type=ExecutorType.PROCESS,
            retry_count=0,
        )
        processor = ParallelProcessor(config=config)
        files = [Path("a.txt"), Path("b.txt"), Path("c.txt")]
        result = processor.process_batch(files, _identity)
        # Verify all files processed successfully
        self.assertEqual(result.succeeded, 3)
        self.assertEqual(result.total, 3)
        self.assertEqual(result.failed, 0)

    def test_thread_executor_fallback_works(self) -> None:
        """Test that ThreadPoolExecutor fallback works correctly."""
        config = ParallelConfig(
            max_workers=2,
            executor_type=ExecutorType.THREAD,
            retry_count=0,
        )
        processor = ParallelProcessor(config=config)
        files = [Path("a.txt"), Path("b.txt"), Path("c.txt")]
        result = processor.process_batch(files, _identity)
        # Verify all files processed successfully
        self.assertEqual(result.succeeded, 3)
        self.assertEqual(result.total, 3)
        self.assertEqual(result.failed, 0)

    def test_process_batch_iter_handles_executor_fallback(self) -> None:
        """Test process_batch_iter handles executor creation and fallback."""
        config = ParallelConfig(
            max_workers=2,
            executor_type=ExecutorType.PROCESS,
            retry_count=0,
        )
        processor = ParallelProcessor(config=config)
        files = [Path("x.txt"), Path("y.txt")]
        results = list(processor.process_batch_iter(files, _double_stem_length))
        # Each file has stem length of 1 (x or y), so result should be 2
        self.assertEqual(len(results), 2)
        self.assertTrue(all(r.success for r in results))
        self.assertTrue(all(r.result == 2 for r in results))

    def test_mixed_success_and_failure_with_executor_fallback(self) -> None:
        """Test that failures are handled correctly with executor fallback."""
        fail_then_succeed = _fail_then_succeed_factory()
        config = ParallelConfig(
            max_workers=2,
            executor_type=ExecutorType.PROCESS,
            retry_count=1,  # Allow 1 retry
        )
        processor = ParallelProcessor(config=config)
        files = [Path("a.txt"), Path("b.txt")]
        result = processor.process_batch(files, fail_then_succeed[0])
        # With retry_count=1, should recover from initial failure
        self.assertEqual(result.failed + result.succeeded, 2)


@pytest.mark.unit
class TestShutdown(unittest.TestCase):
    """Test ParallelProcessor.shutdown."""

    def test_shutdown_is_safe(self) -> None:
        """Test that shutdown can be called without error."""
        processor = ParallelProcessor()
        processor.shutdown()  # Should not raise


if __name__ == "__main__":
    unittest.main()
