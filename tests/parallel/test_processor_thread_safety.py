"""Tests for ParallelProcessor thread safety (executor_type_used lock)."""

from __future__ import annotations

import threading

import pytest

from file_organizer.parallel.config import ParallelConfig
from file_organizer.parallel.processor import ParallelProcessor

pytestmark = pytest.mark.unit


class TestProcessorThreadSafety:
    def test_executor_type_lock_exists(self):
        proc = ParallelProcessor()
        assert hasattr(proc, "_executor_type_lock")
        assert isinstance(proc._executor_type_lock, type(threading.Lock()))

    def test_executor_type_default(self):
        proc = ParallelProcessor()
        assert proc._executor_type_used == "thread"

    def test_concurrent_batch_iter_access(self):
        """Multiple threads reading _executor_type_used should not crash."""
        proc = ParallelProcessor(ParallelConfig(max_workers=1))
        errors: list[Exception] = []

        def read_type() -> None:
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

        assert not errors
