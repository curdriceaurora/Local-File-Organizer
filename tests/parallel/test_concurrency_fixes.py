import threading
import time
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.parallel.checkpoint import Checkpoint
from file_organizer.parallel.config import ParallelConfig
from file_organizer.parallel.processor import FileResult, ParallelProcessor
from file_organizer.parallel.resume import ResumableProcessor


@pytest.mark.ci
@pytest.mark.unit
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
            last_updated=datetime.now(UTC),
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
            threading.Event().wait(timeout=0.01)
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
            threading.Event().wait(timeout=0.5)
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
            threading.Event().wait(timeout=per_file_sleep)
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
        """Timed-out tasks are abandoned; remaining files continue and terminate."""
        # timeout=0.5s → saturation threshold = 2x0.5s = 1.0s.
        # Task duration 0.8s keeps slow_3's max queue time (≈0.3s) well below 1.0s,
        # so the saturation guard must NOT trigger — each task times out individually.
        # Margins are deliberately wide (0.3s stuck-time vs 1.0s threshold) to
        # absorb the thread-scheduling variance seen on macOS GitHub Actions runners.
        config = ParallelConfig(
            max_workers=1,
            timeout_per_file=0.5,
            retry_count=0,
        )
        processor = ParallelProcessor(config=config)
        paths = [Path("slow_1"), Path("slow_2"), Path("slow_3")]

        def very_slow_task(_path: Path) -> str:
            threading.Event().wait(timeout=0.8)
            return "done"

        results = processor.process_batch(paths, very_slow_task)

        self.assertEqual(results.total, 3)
        self.assertEqual(results.failed, 3)
        self.assertEqual(len(results.results), 3)
        # Each file runs and times out individually — no cascade abort.
        # With max_workers=1 and 3x0.5s timeouts, total is ~1.5s.
        self.assertLess(
            results.total_duration_ms,
            4000,
            "Should terminate within reasonable time even with repeated timeouts",
        )
        errors = [str(item.error) for item in results.results]
        # Every file must report its own timeout, not a cascade-abort message.
        self.assertTrue(all("Timed out" in err for err in errors))

    def test_uncancellable_timeout_is_not_retried(self) -> None:
        """Timed-out tasks are non-retryable: each file runs exactly once."""
        # timeout=0.5s keeps saturation threshold (1.0s) well above task duration (0.8s).
        # Margins deliberately wide to absorb macOS GitHub Actions thread-scheduling variance.
        config = ParallelConfig(
            max_workers=1,
            timeout_per_file=0.5,
            retry_count=2,
        )
        processor = ParallelProcessor(config=config)
        call_count = 0

        def very_slow_task(_path: Path) -> str:
            nonlocal call_count
            call_count += 1
            threading.Event().wait(timeout=0.8)
            return "done"

        paths = [Path("slow_1"), Path("slow_2")]
        results = processor.process_batch(paths, very_slow_task)

        # With retry_count=2, a retried file would be called up to 3 times.
        # Each file should run exactly once (non_retryable prevents retry).
        self.assertEqual(call_count, len(paths))
        self.assertEqual(results.failed, 2)
        self.assertTrue(all("Timed out" in str(item.error) for item in results.results))

    def test_saturated_pool_aborts_queued_tasks(self) -> None:
        """Queued tasks abort when the pool is permanently saturated by hung tasks.

        Uses genuinely infinite tasks (Event.wait() with no timeout) to simulate
        worker threads that never complete.  The saturation guard should fire after
        2 x timeout_per_file and fail remaining queued tasks without hanging.
        """
        stop_event = threading.Event()

        config = ParallelConfig(
            max_workers=1,
            timeout_per_file=0.1,
            retry_count=0,
        )
        processor = ParallelProcessor(config=config)
        paths = [Path("hung_1"), Path("queued_2")]

        def hung_task(_path: Path) -> str:
            stop_event.wait()  # blocks until the event is set
            return "done"

        try:
            results = processor.process_batch(paths, hung_task)
        finally:
            stop_event.set()  # unblock the hung thread so the pool shuts down

        self.assertEqual(results.total, 2)
        self.assertEqual(results.failed, 2)
        # hung_1 should report a timeout; queued_2 must report pool saturation.
        by_path = {r.path: str(r.error) for r in results.results}
        self.assertTrue(
            "Timed out" in by_path.get(Path("hung_1"), "")
            or "saturated" in by_path.get(Path("hung_1"), ""),
            f"hung_1 should have a timeout/saturation error, got: {by_path.get(Path('hung_1'))}",
        )
        self.assertIn(
            "saturated",
            by_path.get(Path("queued_2"), ""),
            f"queued_2 must report pool saturation, got: {by_path.get(Path('queued_2'))}",
        )

    def test_slow_progressing_pool_does_not_trip_saturation(self) -> None:
        """#1288: a degraded-but-progressing pool must not false-trip saturation.

        With ``max_workers=1`` and several tasks that each complete just under
        ``timeout_per_file``, later files sit queued while earlier ones drain
        sequentially. A queued file's wall-clock age can exceed 2xtimeout even
        though the pool is making steady progress. The saturation guard must
        measure *continuous no-progress* time — reset on every healthy
        completion — so it does NOT fire here and ALL files complete.
        """
        timeout = 0.2
        config = ParallelConfig(
            max_workers=1,
            timeout_per_file=timeout,
            retry_count=0,
        )
        processor = ParallelProcessor(config=config)
        # Six files drained one-at-a-time: total ≈ 6 x 0.1s = 0.6s. Without the
        # per-completion reset, the last queued file would age well past
        # 2xtimeout (0.4s) and false-trip saturation before it ever runs.
        paths = [Path(f"slow_progress_{i}") for i in range(6)]

        def slow_but_completes(_path: Path) -> str:
            # Completes in ~half the timeout, so each task is healthy.
            threading.Event().wait(timeout=timeout * 0.5)
            return "ok"

        results = processor.process_batch(paths, slow_but_completes)

        self.assertEqual(results.total, len(paths))
        self.assertEqual(
            results.succeeded,
            len(paths),
            f"all files should complete on a progressing pool, got: "
            f"{[(str(r.path), r.success, r.error) for r in results.results]}",
        )
        self.assertEqual(results.failed, 0)
        self.assertFalse(
            any("saturated" in str(r.error) for r in results.results),
            "a steadily-progressing pool must not report saturation",
        )

    def test_saturation_guard_keys_off_recent_queue_time(self) -> None:
        """#1288 (unit): ``_check_pool_saturation`` keys off ``future_queued_at``.

        A never-started queued future whose ``future_queued_at`` was *recently*
        refreshed (as the main loop does on every healthy completion) must NOT
        be flagged as saturated, even though it has technically existed for a
        long time. This pins the contract that the reset on healthy completion
        relies on: saturation is measured from the last refreshed queue time,
        not absolute age.
        """
        config = ParallelConfig(max_workers=1, timeout_per_file=0.1, retry_count=0)
        processor = ParallelProcessor(config=config)

        never_started = MagicMock()
        never_started.running.return_value = False

        pending = {never_started}
        future_paths = {never_started: Path("queued")}
        future_started: dict[object, float | None] = {never_started: None}
        now = time.monotonic()
        # Simulate a clock that was just refreshed by a healthy completion.
        future_queued_at = {never_started: now}

        result = processor._check_pool_saturation(
            pending,  # type: ignore[arg-type]
            future_paths,  # type: ignore[arg-type]
            future_started,  # type: ignore[arg-type]
            future_queued_at,  # type: ignore[arg-type]
            config.timeout_per_file,
            lambda r: r,
        )
        self.assertIsNone(result, "recently-refreshed queue time must not trip saturation")

        # Conversely, an un-refreshed clock older than 2xtimeout DOES trip it,
        # proving the reset is what prevents the false positive.
        future_queued_at[never_started] = now - (config.timeout_per_file * 2 + 1.0)
        stale_result = processor._check_pool_saturation(
            pending,  # type: ignore[arg-type]
            future_paths,  # type: ignore[arg-type]
            future_started,  # type: ignore[arg-type]
            future_queued_at,  # type: ignore[arg-type]
            config.timeout_per_file,
            lambda r: r,
        )
        self.assertIsNotNone(stale_result, "stale queue time beyond 2xtimeout must trip saturation")

    def test_retryable_saturation_survives_non_retryable_peer(self) -> None:
        """#1287: a queued never-started saturation file (retryable) must still be
        retried even when a non-retryable hung peer fails in the same attempt.

        Old behaviour stopped on the first non-retryable failure before
        collecting retryable ones, stranding the queued file as a failure
        without ever running it — a residual cascade.
        """
        stop_event = threading.Event()
        config = ParallelConfig(max_workers=1, timeout_per_file=0.1, retry_count=1)
        processor = ParallelProcessor(config=config)

        def task(path: Path) -> str:
            if path.name == "hung_1":
                stop_event.wait()  # never completes during the test
            return "done"  # queued_2 succeeds once it actually runs (on retry)

        try:
            results = processor.process_batch([Path("hung_1"), Path("queued_2")], task)
        finally:
            stop_event.set()  # unblock the leaked thread so the pool shuts down

        by_path = {r.path: r for r in results.results}
        # The hung peer is a final failure (non-retryable)...
        self.assertFalse(by_path[Path("hung_1")].success)
        # ...but the queued file was retried alone and succeeded — not stranded.
        self.assertTrue(
            by_path[Path("queued_2")].success,
            f"queued_2 should have been retried, got: {by_path[Path('queued_2')]}",
        )

    def test_timeout_result_records_elapsed_duration(self) -> None:
        """#1287: a timed-out task records its elapsed duration (~timeout) rather
        than the 0.0 default, so the dispatcher's fallback ``inference_ms`` (and
        the p95/p99 sample) reflect the real worst-case latency of a hung call.
        """
        config = ParallelConfig(max_workers=1, timeout_per_file=0.2, retry_count=0)
        processor = ParallelProcessor(config=config)

        def very_slow_task(_path: Path) -> str:
            threading.Event().wait(timeout=2.0)
            return "done"

        results = processor.process_batch([Path("slow")], very_slow_task)

        self.assertEqual(results.failed, 1)
        item = results.results[0]
        self.assertIn("Timed out", str(item.error))
        # Elapsed reflects the real wait (≈ timeout), not the 0.0 default.
        self.assertGreaterEqual(item.duration_ms, config.timeout_per_file * 1000 * 0.5)

    def test_saturated_pool_warning_includes_tuning_hint(self) -> None:
        """#435: the saturation warning surfaces the tuning hint inline.

        Operators don't discover ``--timeout-per-file`` / ``--workers``
        until something breaks badly; the warning that fires when the
        pool aborts must point at those knobs so the next run can be
        tuned without a maintainer round-trip.
        """
        stop_event = threading.Event()
        config = ParallelConfig(max_workers=1, timeout_per_file=0.1, retry_count=0)
        processor = ParallelProcessor(config=config)

        def hung_task(_path: Path) -> str:
            stop_event.wait()
            return "done"

        captured: list[str] = []

        def fake_warning(msg: str, *args: object, **_kw: object) -> None:
            # stdlib logging-style: msg is a format string with %d / %s substitutions
            try:
                captured.append(msg % args)
            except TypeError:
                captured.append(msg)

        from file_organizer.parallel import processor as processor_mod

        with patch.object(processor_mod.logger, "warning", side_effect=fake_warning):
            try:
                processor.process_batch([Path("hung_1"), Path("queued_2")], hung_task)
            finally:
                stop_event.set()

        saturated = [line for line in captured if "saturated" in line.lower()]
        self.assertTrue(saturated, f"expected a saturation warning, got: {captured}")
        self.assertTrue(
            any("--timeout-per-file" in line for line in saturated),
            f"saturation warning should mention --timeout-per-file: {saturated}",
        )
        self.assertTrue(
            any("--workers" in line for line in saturated),
            f"saturation warning should mention --workers: {saturated}",
        )

    def test_error_message_does_not_control_retry_policy(self) -> None:
        """Regular failures containing the abort phrase should still be retried."""
        config = ParallelConfig(
            max_workers=1,
            retry_count=1,
        )
        processor = ParallelProcessor(config=config)
        call_count = 0

        def flaky_task(_path: Path) -> str:
            nonlocal call_count
            call_count += 1
            raise RuntimeError("plugin said could not be cancelled")

        results = processor.process_batch([Path("one.txt")], flaky_task)

        self.assertEqual(call_count, 2)
        self.assertEqual(results.failed, 1)

    def test_force_shutdown_flag_is_local_per_iterator(self) -> None:
        """One iterator's abort state should not leak into a later healthy batch."""
        config = ParallelConfig(
            max_workers=1,
            timeout_per_file=0.1,
            retry_count=0,
        )
        processor = ParallelProcessor(config=config)

        def very_slow_task(_path: Path) -> str:
            threading.Event().wait(timeout=0.3)
            return "done"

        first_results = list(processor.process_batch_iter([Path("slow.txt")], very_slow_task))
        self.assertTrue(any(result.non_retryable for result in first_results))

        with patch("concurrent.futures.thread.ThreadPoolExecutor.shutdown") as mock_shutdown:
            second_results = list(
                processor.process_batch_iter([Path("fast.txt")], lambda _path: "ok")
            )

        self.assertEqual(len(second_results), 1)
        self.assertTrue(second_results[0].success)
        self.assertTrue(mock_shutdown.called)
        force_shutdown_values = {
            call.kwargs.get("cancel_futures") for call in mock_shutdown.call_args_list
        }
        self.assertIn(False, force_shutdown_values)

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
            threading.Event().wait(timeout=0.02)
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
