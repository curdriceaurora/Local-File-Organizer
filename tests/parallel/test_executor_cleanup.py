"""Tests for executor factory fallback behavior."""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from unittest.mock import patch

import pytest

from file_organizer.parallel.executor import create_executor

pytestmark = pytest.mark.unit


class TestExecutorFactory:
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
