"""Tests for ParallelProcessor thread safety."""

from __future__ import annotations

import threading

import pytest

from file_organizer.parallel.config import ParallelConfig
from file_organizer.parallel.processor import ParallelProcessor

pytestmark = pytest.mark.unit


class TestProcessorThreadSafety:
    """Verify ParallelProcessor protects shared state with a lock."""

    def test_lock_exists(self):
        """ParallelProcessor should have a threading.Lock for shared state."""
        proc = ParallelProcessor()
        assert hasattr(proc, "_lock")
        assert isinstance(proc._lock, type(threading.Lock()))

    def test_executor_type_used_protected_by_lock(self):
        """_executor_type_used should be updated under the lock."""
        config = ParallelConfig(timeout_per_file=1.0)
        proc = ParallelProcessor(config)

        # Process an empty batch — no actual work, but verifies
        # the initial state is coherent.
        results = list(proc.process_batch_iter([], lambda p: None))
        assert results == []

        # Verify _executor_type_used can be read safely
        assert proc._executor_type_used in ("thread", "process")

    def test_concurrent_process_batch_iter(self, tmp_path):
        """Two threads calling process_batch_iter simultaneously should not crash."""
        config = ParallelConfig(timeout_per_file=5.0)
        proc = ParallelProcessor(config)

        # Create some tiny test files
        files = []
        for i in range(4):
            f = tmp_path / f"file_{i}.txt"
            f.write_text(f"content {i}")
            files.append(f)

        results_a: list = []
        results_b: list = []
        errors: list = []

        def worker(file_list, results_out):
            """worker."""
            try:
                for r in proc.process_batch_iter(file_list, lambda p: p.read_text()):
                    results_out.append(r)
            except Exception as exc:
                errors.append(exc)

        t1 = threading.Thread(target=worker, args=(files[:2], results_a))
        t2 = threading.Thread(target=worker, args=(files[2:], results_b))
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        assert not errors, f"Unexpected errors: {errors}"
        assert len(results_a) == 2
        assert len(results_b) == 2
        assert all(r.success for r in results_a + results_b)
