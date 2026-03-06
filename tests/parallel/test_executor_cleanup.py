"""Tests for executor factory cleanup on fallback."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.parallel.executor import create_executor

pytestmark = [pytest.mark.unit, pytest.mark.ci]


class TestExecutorFactoryCleanup:
    """Verify ProcessPoolExecutor fallback cleans up partial state."""

    def test_process_executor_fallback_to_thread(self):
        """When ProcessPoolExecutor raises, a ThreadPoolExecutor is returned."""
        with patch(
            "file_organizer.parallel.executor.ProcessPoolExecutor",
            side_effect=RuntimeError("spawn failed"),
        ):
            executor, etype = create_executor("process", max_workers=2)
            try:
                assert isinstance(executor, ThreadPoolExecutor)
                assert etype == "thread"
            finally:
                executor.shutdown(wait=False)

    def test_process_executor_partial_init_cleanup(self):
        """If ProcessPoolExecutor partially initialises then raises, shutdown is called."""
        partial_executor = MagicMock()

        # Patch constructor to return a mock, but make logger.info raise
        # only on the first call (the ProcessPoolExecutor creation log),
        # so we trigger the except block with process_executor already assigned.
        with patch(
            "file_organizer.parallel.executor.ProcessPoolExecutor",
            return_value=partial_executor,
        ):
            call_count = 0

            def info_side_effect(*args, **kwargs):
                """info_side_effect."""
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise RuntimeError("simulated post-init failure")

            with patch("file_organizer.parallel.executor.logger") as mock_logger:
                mock_logger.info.side_effect = info_side_effect
                executor, etype = create_executor("process", max_workers=2)
                try:
                    assert isinstance(executor, ThreadPoolExecutor)
                    assert etype == "thread"
                    partial_executor.shutdown.assert_called_once_with(wait=False)
                finally:
                    executor.shutdown(wait=False)

    def test_thread_executor_direct(self):
        """executor_type='thread' returns ThreadPoolExecutor directly."""
        executor, etype = create_executor("thread", max_workers=2)
        try:
            assert isinstance(executor, ThreadPoolExecutor)
            assert etype == "thread"
        finally:
            executor.shutdown(wait=False)
