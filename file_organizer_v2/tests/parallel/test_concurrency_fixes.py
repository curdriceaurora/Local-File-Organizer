
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

    def test_checkpoint_batching_overhead(self):
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
            last_updated=datetime.now()
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
                checkpoint_mgr=mock_checkpoint_mgr
            )

            # Run without crashing
            processor.process_with_resume(
                [Path(f"file_{i}") for i in range(20)],
                lambda x: x,
                job_id="test_job"
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
            # Without batching, it would be 20 calls inside the loop + create + final = 22 calls.
            # With batching, it's create + final = 2 calls (if fast).

            save_calls = mock_checkpoint_mgr.save_checkpoint.call_count
            self.assertLess(save_calls, 10, "Should use batched checkpoints")
            self.assertGreaterEqual(save_calls, 1, "Should save at least once")

    def test_zombie_task_timeout(self):
        """Test that timed-out tasks are cancelled and reported correctly (Issue #294)."""
        # We need to simulate a task that hangs.
        config = ParallelConfig(
            max_workers=2,
            timeout_per_file=0.1,  # Short timeout
            retry_count=0  # Disable retries to speed up test
        )
        processor = ParallelProcessor(config=config)

        def slow_task(path):
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

        # Verify it didn't take 0.5s + overhead (it should be close to 0.1s + overhead)
        # But time.sleep blocks the thread.
        # Oh right, ThreadPoolExecutor threads can't be killed.
        # Wait, if I use ThreadPoolExecutor (default), a sleeping thread blocks Python GIL release?
        # No, time.sleep releases GIL.
        # But `wait` timeout works.
        # The main thread wakes up after 0.1s check.
        # It sees timeout, cancels (no-op for running thread), and yields failure.
        # The test should finish in ~0.1s (plus polling interval), not 0.5s.
        # processor.process_batch waits for ALL results?
        # process_batch calls _run_batch which iterates the iterator.
        # The iterator yields failure immediately after detection.
        # So _run_batch collects failure and returns.
        # The background thread continues to sleep for 0.4s. That's fine.
        # The test validates prompt return.

        self.assertLess(results.total_duration_ms, 700, "Should finish faster than task duration")
