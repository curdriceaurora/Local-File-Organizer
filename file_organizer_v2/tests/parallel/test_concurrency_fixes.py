import time
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from file_organizer.parallel.checkpoint import Checkpoint
from file_organizer.parallel.config import ParallelConfig
from file_organizer.parallel.processor import FileResult, ParallelProcessor
from file_organizer.parallel.resume import ResumableProcessor


class TestConcurrencyFixes(unittest.TestCase):
    def test_checkpoint_batching_overhead(self) -> None:
        """Test that checkpoint saving is batched (Issue #292)."""
        # Setup mocks
        mock_persistence = MagicMock()
        mock_checkpoint_mgr = MagicMock()

        # Setup initial checkpoint
        initial_checkpoint = Checkpoint(
            job_id="test_job",
            completed_paths=[],
            pending_paths=[Path(f"file_{i}") for i in range(20)],
            file_hashes={},
            last_updated=datetime.now(),
        )
        mock_checkpoint_mgr.create_checkpoint.return_value = initial_checkpoint
        mock_checkpoint_mgr.load_checkpoint.return_value = initial_checkpoint

        # Setup mocked processor to simulate fast processing and verify save calls
        # process_batch_iter returns results. We mock it inside ResumableProcessor?
        # No, ResumableProcessor instantiates ParallelProcessor.
        # We can mock ParallelProcessor's process_batch_iter method.

        with patch("file_organizer.parallel.resume.ParallelProcessor") as MockProcessorCls:
            mock_proc_instance = MockProcessorCls.return_value

            # Make process_batch_iter yield 20 successes
            def fake_iter(files, fn):
                for p in files:
                    yield FileResult(path=p, success=True, result="ok")

            mock_proc_instance.process_batch_iter.side_effect = fake_iter

            processor = ResumableProcessor(
                config=ParallelConfig(max_workers=2),
                persistence=mock_persistence,
                checkpoint_mgr=mock_checkpoint_mgr,
            )

            # Run without crashing
            processor.process_with_resume(
                [Path(f"file_{i}") for i in range(20)], lambda x: x, job_id="test_job"
            )

            # Verification
            # create_checkpoint called once?
            # update_checkpoint_state called 20 times?
            self.assertEqual(mock_checkpoint_mgr.update_checkpoint_state.call_count, 20)

            # save_checkpoint should be called:
            # 1. Inside create_checkpoint (1 time)
            # 2. Inside process_with_resume (batched + final)
            # If batching works (every 50 files or 5s), with 20 files instantly,
            # only the final save should trigger (plus maybe one if timing is weird).
            # Total calls should be small (create + final + maybe 1 batch).
            # Definitely < 10.
            # Without batching, it would be 20 calls inside the loop + create = 21 calls.
            # With batching, it's create + final = 2 calls (if fast).

            save_calls = mock_checkpoint_mgr.save_checkpoint.call_count
            self.assertLess(save_calls, 10, "Should use batched checkpoints")
            self.assertGreaterEqual(save_calls, 1, "Should save at least once")

    def test_process_batch_iter_bounded_pending_futures(self) -> None:
        """Test that pending futures are bounded to avoid unbounded memory (Issue #293)."""
        config = ParallelConfig(max_workers=3)
        processor = ParallelProcessor(config=config)
        paths = [Path(f"batch_file_{i}") for i in range(50)]

        observed_pending_sizes: list[int] = []

        from concurrent.futures import wait as real_wait

        def tracked_wait(fs, *args, **kwargs):
            observed_pending_sizes.append(len(fs))
            return real_wait(fs, *args, **kwargs)

        def slow_task(_path: Path) -> str:
            time.sleep(0.01)
            return "ok"

        with patch("file_organizer.parallel.processor.wait", side_effect=tracked_wait):
            results = list(processor.process_batch_iter(paths, slow_task))

        self.assertEqual(len(results), len(paths))
        self.assertTrue(observed_pending_sizes)
        self.assertLessEqual(
            max(observed_pending_sizes),
            config.max_workers * 2,
            "Pending futures should be bounded to 2 * max_workers",
        )

    def test_zombie_task_timeout(self) -> None:
        """Test that timed-out tasks are cancelled and reported correctly (Issue #294)."""
        config = ParallelConfig(
            max_workers=2,
            timeout_per_file=0.1,  # Short timeout
            retry_count=0,  # Disable retries to speed up test
        )
        processor = ParallelProcessor(config=config)

        def slow_task(path: Path) -> str:
            time.sleep(0.5)
            return "done"

        # Using process_batch which calls _run_batch -> process_batch_iter
        filepath = Path("slow_file")
        results = processor.process_batch([filepath], slow_task)

        self.assertEqual(results.total, 1)
        self.assertEqual(results.failed, 1)
        res = results.results[0]
        self.assertFalse(res.success)
        self.assertIn("Timed out", str(res.error))

        # Must return close to timeout_per_file, not full task duration.
        self.assertLess(
            results.total_duration_ms,
            config.timeout_per_file * 1000 + 300,
            "Should finish close to timeout_per_file, not full task duration",
        )

    def test_process_batch_iter_bounded_futures_memory_usage(self) -> None:
        """Test that process_batch_iter uses bounded concurrency to avoid unbounded memory (Issue #293)."""
        # Use a small worker pool and many slow tasks; total time should scale with
        # len(paths) / max_workers if concurrency is bounded.
        config = ParallelConfig(
            max_workers=4,
        )
        processor = ParallelProcessor(config=config)

        per_file_sleep = 0.05
        num_files = 40
        paths = [Path(f"large_batch_file_{i}") for i in range(num_files)]

        def slow_task(_path: Path) -> str:
            time.sleep(per_file_sleep)
            return "ok"

        start = time.time()
        results = list(processor.process_batch_iter(paths, slow_task))
        duration = time.time() - start

        # All files should be processed.
        self.assertEqual(len(results), num_files)

        # If futures were unbounded (e.g., starting one thread per file), total duration
        # would be close to per_file_sleep. With bounded concurrency, duration should be
        # significantly larger, roughly scaling with num_files / max_workers.
        expected_min_duration = (num_files / config.max_workers) * per_file_sleep * 0.5
        self.assertGreater(
            duration,
            expected_min_duration,
            "process_batch_iter appears to run too many tasks concurrently, which risks unbounded memory usage",
        )

    def test_timeout_does_not_deadlock_with_queued_files(self) -> None:
        """Test that timeout handling aborts queued work instead of deadlocking."""
        config = ParallelConfig(
            max_workers=1,
            timeout_per_file=0.1,
            retry_count=0,
        )
        processor = ParallelProcessor(config=config)
        paths = [Path("slow_1"), Path("slow_2"), Path("slow_3")]

        def very_slow_task(_path: Path) -> str:
            time.sleep(0.5)
            return "done"

        results = processor.process_batch(paths, very_slow_task)

        self.assertEqual(results.total, 3)
        self.assertEqual(results.failed, 3)
        self.assertEqual(len(results.results), 3)
        self.assertLess(
            results.total_duration_ms,
            700,
            "Should abort queued/remaining work quickly after uncancellable timeout",
        )
        errors = [str(item.error) for item in results.results]
        self.assertTrue(any("Timed out" in err for err in errors))
        self.assertTrue(any("Aborted because another task" in err for err in errors))

    def test_timeout_poll_interval_scales_with_timeout(self) -> None:
        """Test polling interval scales with timeout to reduce timeout drift."""
        config = ParallelConfig(
            max_workers=1,
            timeout_per_file=0.1,
            retry_count=0,
        )
        processor = ParallelProcessor(config=config)
        paths = [Path("poll_interval_file")]
        observed_timeouts: list[float] = []

        from concurrent.futures import wait as real_wait

        def tracked_wait(fs, *args, **kwargs):
            timeout = kwargs.get("timeout")
            if isinstance(timeout, (int, float)):
                observed_timeouts.append(float(timeout))
            return real_wait(fs, *args, **kwargs)

        def short_task(_path: Path) -> str:
            time.sleep(0.02)
            return "ok"

        with patch("file_organizer.parallel.processor.wait", side_effect=tracked_wait):
            results = list(processor.process_batch_iter(paths, short_task))

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].success)
        self.assertTrue(observed_timeouts)
        self.assertLessEqual(
            max(observed_timeouts),
            0.011,
            "Expected timeout polling interval to scale down for short timeouts",
        )
