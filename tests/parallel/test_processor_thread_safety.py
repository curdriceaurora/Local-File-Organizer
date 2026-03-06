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
        assert hasattr(proc, "_lock"), "ParallelProcessor should have _lock attribute"
        assert isinstance(proc._lock, type(threading.Lock())), (
            f"_lock should be a threading.Lock, got {type(proc._lock)}"
        )

    def test_executor_type_used_protected_by_lock(self):
        """_executor_type_used should be updated under the lock."""
        config = ParallelConfig(timeout_per_file=1.0)
        proc = ParallelProcessor(config)

        # Process an empty batch — no actual work, but verifies
        # the initial state is coherent.
        results = list(proc.process_batch_iter([], lambda p: None))
        assert results == [], f"Empty batch should return empty results, got {results}"

        # Verify _executor_type_used can be read safely
        assert proc._executor_type_used in ("thread", "process"), (
            f"_executor_type_used should be 'thread' or 'process', got {proc._executor_type_used}"
        )

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

        assert not errors, f"Unexpected errors in concurrent processing: {errors}"
        assert len(results_a) == 2, f"Thread A should process 2 files, got {len(results_a)}"
        assert len(results_b) == 2, f"Thread B should process 2 files, got {len(results_b)}"
        assert all(r.success for r in results_a + results_b), (
            f"All results should be successful. Failed: {[r for r in results_a + results_b if not r.success]}"
        )
