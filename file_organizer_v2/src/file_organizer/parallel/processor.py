"""
Parallel file processor using concurrent.futures.

This module provides the main ParallelProcessor class that orchestrates
batch file processing across thread or process pools with timeout handling,
retry logic, progress reporting, and graceful shutdown.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Iterator
from concurrent.futures import (
    FIRST_COMPLETED,
    Future,
    ProcessPoolExecutor,
    ThreadPoolExecutor,
    wait,
)
from pathlib import Path
from typing import Any

from file_organizer.parallel.config import ExecutorType, ParallelConfig
from file_organizer.parallel.result import BatchResult, FileResult


def _execute_with_timing(
    path: Path,
    process_fn: Callable[[Path], Any],
) -> FileResult:
    """
    Execute a processing function on a single file, measuring elapsed time.

    This is a module-level function so it can be pickled for use with
    ProcessPoolExecutor.

    Args:
        path: File path to process.
        process_fn: Function that accepts a Path and returns a result.

    Returns:
        FileResult with success/failure status and timing.
    """
    start = time.perf_counter()
    try:
        result = process_fn(path)
        elapsed_ms = (time.perf_counter() - start) * 1000
        return FileResult(
            path=path,
            success=True,
            result=result,
            duration_ms=elapsed_ms,
        )
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - start) * 1000
        return FileResult(
            path=path,
            success=False,
            error=str(exc),
            duration_ms=elapsed_ms,
        )


class ParallelProcessor:
    """
    Orchestrates parallel file processing using concurrent.futures executors.

    Supports both thread pools (for IO-bound work) and process pools
    (for CPU-bound work), with per-file timeouts, automatic retries,
    and progress callbacks.

    Args:
        config: Parallel processing configuration.
    """

    def __init__(self, config: ParallelConfig | None = None) -> None:
        """
        Initialize the parallel processor.

        Args:
            config: Processing configuration. Uses defaults if None.
        """
        self._config = config or ParallelConfig()

    @property
    def config(self) -> ParallelConfig:
        """Return the current configuration."""
        return self._config

    def process_batch(
        self,
        files: list[Path],
        process_fn: Callable[[Path], Any],
    ) -> BatchResult:
        """
        Process a batch of files in parallel.

        Submits files to the configured executor pool and collects results.
        Failed files are retried up to config.retry_count times.

        Args:
            files: List of file paths to process.
            process_fn: Function to apply to each file path.

        Returns:
            BatchResult with aggregated counts and per-file results.
        """
        if not files:
            return BatchResult()

        batch_start = time.perf_counter()
        results: list[FileResult] = []
        remaining = list(files)

        max_workers = self._config.max_workers or os.cpu_count() or 1
        executor_cls = self._get_executor_class()

        # Create executor once for the whole batch + retries
        with executor_cls(max_workers=max_workers) as executor:
            for attempt in range(1 + self._config.retry_count):
                if not remaining:
                    break

                attempt_results = self._run_batch(
                    executor_cls=executor_cls,
                    max_workers=max_workers,
                    files=remaining,
                    process_fn=process_fn,
                    executor=executor,
                )

                succeeded = [r for r in attempt_results if r.success]
                failed = [r for r in attempt_results if not r.success]

                results.extend(succeeded)

                # On last attempt, include failures in results
                if attempt == self._config.retry_count:
                    results.extend(failed)
                else:
                    # Retry only the failures
                    remaining = [r.path for r in failed]

        batch_elapsed_ms = (time.perf_counter() - batch_start) * 1000
        succeeded_count = sum(1 for r in results if r.success)
        failed_count = sum(1 for r in results if not r.success)
        fps = (len(files) / (batch_elapsed_ms / 1000)) if batch_elapsed_ms > 0 else 0.0

        return BatchResult(
            total=len(files),
            succeeded=succeeded_count,
            failed=failed_count,
            results=results,
            total_duration_ms=batch_elapsed_ms,
            files_per_second=fps,
        )

    def process_batch_iter(
        self,
        files: list[Path],
        process_fn: Callable[[Path], Any],
        executor: Any | None = None,
    ) -> Iterator[FileResult]:
        """
        Process a batch of files, yielding results as they complete.

        Unlike process_batch, this returns results incrementally via an
        iterator, which is useful for streaming progress updates.

        Note: This method does not retry failures. Use process_batch for
        automatic retries.

        Args:
            files: List of file paths to process.
            process_fn: Function to apply to each file path.
            executor: Optional executor instance to reuse. If None, a new
                executor specific to this batch is created and shut down
                upon completion.

        Yields:
            FileResult for each completed file, in completion order.
        """
        if not files:
            return

        max_workers = self._config.max_workers or os.cpu_count() or 1
        
        # If executor is provided, we don't own it (no-op context manager).
        # If not provided, we create one and own it (standard context manager).
        if executor is None:
            executor_cls = self._get_executor_class()
            executor_ctx = executor_cls(max_workers=max_workers)
        else:
            # Simple context manager that does nothing on exit
            class NoOpContext_Executor:
                def __enter__(self): return executor
                def __exit__(self, *args): pass
            executor_ctx = NoOpContext_Executor()

        completed_count = 0
        total = len(files)

        # Use a bounded set of futures to control memory usage (backpressure)
        # Limit to 2x workers to keep pipeline full but not overflow memory
        limit = max_workers * 2
        pending: set[Future[FileResult]] = set()
        # Track start time for timeout handling: Future -> (Path, start_time)
        future_metadata: dict[Future[FileResult], tuple[Path, float]] = {}

        iterator = iter(files)

        with executor_ctx as exec_instance:

            def submit_next() -> bool:
                """Submit next file if available."""
                try:
                    path = next(iterator)
                    future = exec_instance.submit(_execute_with_timing, path, process_fn)
                    pending.add(future)
                    future_metadata[future] = (path, time.monotonic())
                    return True
                except StopIteration:
                    return False

            # Initial fill
            while len(pending) < limit:
                if not submit_next():
                    break

            while pending:
                # Wait for completion or timeout check
                # We use a short timeout to periodically check for stale tasks
                # Using 0.05s ensures responsive timeout detection
                done, _ = wait(pending, timeout=0.05, return_when=FIRST_COMPLETED)

                # 1. Process completed tasks
                for future in done:
                    pending.remove(future)
                    path, _ = future_metadata.pop(future)

                    try:
                        file_result = future.result()
                    except Exception as exc:
                        # Should be captured by _execute_with_timing, but safety net
                        file_result = FileResult(
                            path=path, success=False, error=str(exc)
                        )

                    completed_count += 1
                    if self._config.progress_callback:
                        self._config.progress_callback(
                            completed_count, total, file_result
                        )

                    yield file_result
                    submit_next()

                # 2. Check for timed-out tasks
                now = time.monotonic()
                timeout = self._config.timeout_per_file

                # Check running tasks (those in pending but not in done)
                # We iterate a copy because we might modify pending
                for future in list(pending):
                    path, start_time = future_metadata[future]
                    if (now - start_time) > timeout:
                        # Task timed out
                        future.cancel()  # Attempt to cancel (fixes zombie tasks if not started)
                        pending.remove(future)
                        del future_metadata[future]

                        file_result = FileResult(
                            path=path,
                            success=False,
                            error=f"Timed out after {timeout}s",
                        )

                        completed_count += 1
                        if self._config.progress_callback:
                            self._config.progress_callback(
                                completed_count, total, file_result
                            )

                        yield file_result
                        submit_next()

    def _get_executor_class(
        self,
    ) -> type[ThreadPoolExecutor] | type[ProcessPoolExecutor]:
        """
        Return the executor class based on configuration.

        Returns:
            ThreadPoolExecutor or ProcessPoolExecutor class.
        """
        if self._config.executor_type == ExecutorType.PROCESS:
            return ProcessPoolExecutor
        return ThreadPoolExecutor

    def _run_batch(
        self,
        executor_cls: type[ThreadPoolExecutor] | type[ProcessPoolExecutor],
        max_workers: int,
        files: list[Path],
        process_fn: Callable[[Path], Any],
        executor: Any | None = None,
    ) -> list[FileResult]:
        """
        Submit files to the executor and collect all results.

        Wrapper around process_batch_iter.

        Args:
            executor_cls: Ignored (uses config).
            max_workers: Ignored (uses config).
            files: Files to process in this batch.
            process_fn: Processing function.
            executor: Optional executor to use.

        Returns:
            List of FileResult for each submitted file.
        """
        # Delegate to process_batch_iter which handles bounding and timeouts correctly
        return list(
            self.process_batch_iter(files, process_fn, executor=executor)
        )

    def shutdown(self) -> None:
        """
        Clean up any resources.

        Currently a no-op since executors are used as context managers,
        but provided for forward compatibility.
        """
