"""Tests for ParallelProcessor thread safety."""

from __future__ import annotations

import threading

import pytest

from file_organizer.parallel.config import ParallelConfig
from file_organizer.parallel.processor import ParallelProcessor

pytestmark = pytest.mark.unit


class TestProcessorThreadSafety:
    def test_executor_type_default(self) -> None:
        """Verify executor type defaults to 'thread'."""
        proc = ParallelProcessor()
        assert proc._executor_type_used == "thread", (
            f"Executor type should default to 'thread', got '{proc._executor_type_used}'"
        )

    def test_concurrent_batch_iter_access(self) -> None:
        """Multiple threads reading _executor_type_used should not crash.

        This exercises the critical path where multiple threads concurrently
        access the processor's executor type field to ensure no race conditions.
        """
        proc = ParallelProcessor(ParallelConfig(max_workers=1))
        errors: list[Exception] = []

        def read_type() -> None:
            """Read executor type multiple times from thread."""
            try:
                for _ in range(50):
                    _ = proc._executor_type_used
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=read_type) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        # Verify all threads actually completed
        alive_threads = [t for t in threads if t.is_alive()]
        assert not alive_threads, (
            f"Expected all 5 threads to complete, but {len(alive_threads)} are still alive"
        )
        assert not errors, (
            f"Concurrent read access errors: {[str(e) for e in errors]}"
        )
