"""
Unit tests for the executor factory module.

Tests the create_executor function including ProcessPoolExecutor to
ThreadPoolExecutor fallback behavior.
"""

import unittest
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from unittest.mock import patch

from file_organizer.parallel.executor import create_executor


class TestCreateExecutor(unittest.TestCase):
    """Test create_executor factory function."""

    def test_create_thread_executor(self) -> None:
        """Test creating a ThreadPoolExecutor."""
        executor, executor_type = create_executor("thread", max_workers=4)
        try:
            self.assertIsInstance(executor, ThreadPoolExecutor)
            self.assertEqual(executor_type, "thread")
        finally:
            executor.shutdown(wait=False)

    def test_create_process_executor_success(self) -> None:
        """Test creating a ProcessPoolExecutor successfully."""
        executor, executor_type = create_executor("process", max_workers=2)
        try:
            self.assertIsInstance(executor, ProcessPoolExecutor)
            self.assertEqual(executor_type, "process")
        finally:
            executor.shutdown(wait=False)

    def test_process_executor_fallback_on_error(self) -> None:
        """Test that ProcessPoolExecutor falls back to ThreadPoolExecutor on error."""
        with patch(
            "file_organizer.parallel.executor.ProcessPoolExecutor",
            side_effect=RuntimeError("ProcessPoolExecutor not available"),
        ):
            executor, executor_type = create_executor("process", max_workers=4)
            try:
                # Should fall back to ThreadPoolExecutor
                self.assertIsInstance(executor, ThreadPoolExecutor)
                self.assertEqual(executor_type, "thread")
            finally:
                executor.shutdown(wait=False)

    def test_thread_executor_explicit(self) -> None:
        """Test explicitly requesting ThreadPoolExecutor."""
        executor, executor_type = create_executor("thread", max_workers=4)
        try:
            self.assertIsInstance(executor, ThreadPoolExecutor)
            self.assertEqual(executor_type, "thread")
        finally:
            executor.shutdown(wait=False)

    def test_executor_with_custom_worker_count(self) -> None:
        """Test creating executor with custom worker count."""
        executor, executor_type = create_executor("thread", max_workers=8)
        try:
            self.assertIsInstance(executor, ThreadPoolExecutor)
            # Verify executor can execute tasks
            future = executor.submit(lambda: 42)
            result = future.result(timeout=5)
            self.assertEqual(result, 42)
        finally:
            executor.shutdown(wait=False)

    def test_process_executor_fallback_logs_warning(self) -> None:
        """Test that fallback logs a warning."""
        with patch(
            "file_organizer.parallel.executor.ProcessPoolExecutor",
            side_effect=OSError("Multiprocessing not supported"),
        ):
            with patch("file_organizer.parallel.executor.logger") as mock_logger:
                executor, executor_type = create_executor("process", max_workers=2)
                try:
                    # Verify warning was logged
                    mock_logger.warning.assert_called_once()
                    call_args = mock_logger.warning.call_args[0]
                    self.assertIn("ProcessPoolExecutor", call_args[0])
                    self.assertIn("Falling back", call_args[0])
                finally:
                    executor.shutdown(wait=False)

    def test_process_executor_fallback_logs_info(self) -> None:
        """Test that successful creation logs info."""
        with patch("file_organizer.parallel.executor.logger") as mock_logger:
            executor, executor_type = create_executor("process", max_workers=2)
            try:
                # Verify info was logged for ProcessPoolExecutor creation
                info_calls = list(mock_logger.info.call_args_list)
                self.assertTrue(
                    any("ProcessPoolExecutor" in str(call) for call in info_calls)
                )
            finally:
                executor.shutdown(wait=False)


class TestExecutorTypeReporting(unittest.TestCase):
    """Test that create_executor accurately reports executor type."""

    def test_returns_correct_type_for_thread(self) -> None:
        """Test that thread executor type is correctly reported."""
        executor, executor_type = create_executor("thread", max_workers=2)
        try:
            self.assertEqual(executor_type, "thread")
        finally:
            executor.shutdown(wait=False)

    def test_returns_correct_type_for_process(self) -> None:
        """Test that process executor type is correctly reported."""
        executor, executor_type = create_executor("process", max_workers=2)
        try:
            if isinstance(executor, ProcessPoolExecutor):
                self.assertEqual(executor_type, "process")
            else:
                # Fallback occurred
                self.assertEqual(executor_type, "thread")
        finally:
            executor.shutdown(wait=False)

    def test_returns_correct_type_on_fallback(self) -> None:
        """Test that correct type is returned when fallback occurs."""
        with patch(
            "file_organizer.parallel.executor.ProcessPoolExecutor",
            side_effect=RuntimeError("Cannot create process executor"),
        ):
            executor, executor_type = create_executor("process", max_workers=2)
            try:
                self.assertIsInstance(executor, ThreadPoolExecutor)
                self.assertEqual(executor_type, "thread")
            finally:
                executor.shutdown(wait=False)


if __name__ == "__main__":
    unittest.main()
