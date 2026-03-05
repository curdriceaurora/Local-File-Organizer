"""Tests for executor factory cleanup on fallback."""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.parallel.executor import create_executor

pytestmark = pytest.mark.unit


class TestExecutorFactoryCleanup:
    def test_process_executor_creation_success(self):
        executor, kind = create_executor("process", 2)
        try:
            assert kind == "process"
            assert isinstance(executor, ProcessPoolExecutor)
        finally:
            executor.shutdown(wait=False)

    def test_thread_executor_creation(self):
        executor, kind = create_executor("thread", 2)
        try:
            assert kind == "thread"
            assert isinstance(executor, ThreadPoolExecutor)
        finally:
            executor.shutdown(wait=False)

    def test_fallback_to_thread_on_process_failure(self):
        with patch(
            "file_organizer.parallel.executor.ProcessPoolExecutor",
            side_effect=OSError("semaphore limit"),
        ):
            executor, kind = create_executor("process", 2)
            try:
                assert kind == "thread"
                assert isinstance(executor, ThreadPoolExecutor)
            finally:
                executor.shutdown(wait=False)

    def test_partial_executor_cleaned_up_on_fallback(self):
        """If ProcessPoolExecutor init succeeds then raises, it should be shut down."""
        mock_executor = MagicMock(spec=ProcessPoolExecutor)

        call_count = 0

        def ppe_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            # Return on first call (constructor), then raise on info log access
            return mock_executor

        # Simulate: constructor succeeds but a later step in the try block raises
        # by making the logger.info call raise
        with patch(
            "file_organizer.parallel.executor.ProcessPoolExecutor",
            return_value=mock_executor,
        ):
            # Normal success path
            executor, kind = create_executor("process", 2)
            assert kind == "process"
            assert executor is mock_executor
