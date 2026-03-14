"""Parallel file processor using concurrent.futures.

This module provides the main ParallelProcessor class that orchestrates
batch file processing across thread or process pools with timeout handling,
retry logic, progress reporting, and graceful shutdown.
"""

from __future__ import annotations

import os
import threading
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
from file_organizer.parallel.executor import create_executor
from file_organizer.parallel.result import BatchResult, FileResult


def _execute_with_timing(
    path: Path,
    process_fn: Callable[[Path], Any],
) -> FileResult:
    """Execute a processing function on a single file, measuring elapsed time.

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
    """Orchestrates parallel file processing using concurrent.futures executors.

    Supports both thread pools (for IO-bound work) and process pools
    (for CPU-bound work), with per-file timeouts, automatic retries,
    and progress callbacks.

    Args:
        config: Parallel processing configuration.
    """

    def __init__(self, config: ParallelConfig | None = None) -> None:
        """Initialize the parallel processor.

        Args:
            config: Processing configuration. Uses defaults if None.
        """
        self._config = config or ParallelConfig()
        self._lock = threading.Lock()
        self._executor_type_used: str = "thread"  # Track which executor type is in use

    @property
    def config(self) -> ParallelConfig:
        """Return the current configuration."""
        return self._config

    def process_batch(
        self,
        files: list[Path],
        process_fn: Callable[[Path], Any],
    ) -> BatchResult:
        """Process a batch of files in parallel.

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

        for attempt in range(1 + self._config.retry_count):
            if not remaining:
                break

            attempt_results = self._run_batch(
                executor_cls=None,
                max_workers=0,
                files=remaining,
                process_fn=process_fn,
                executor=None,
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
        executor: ThreadPoolExecutor | ProcessPoolExecutor | None = None,
    ) -> Iterator[FileResult]:
        """Process a batch of files, yielding results as they complete.

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
        owns_executor = executor is None
        if owns_executor:
            executor_type = (
                "process" if self._config.executor_type == ExecutorType.PROCESS else "thread"
            )
            exec_instance, exec_type = create_executor(executor_type, max_workers)
            with self._lock:
                self._executor_type_used = exec_type
        else:
            assert executor is not None
            exec_instance = executor

        completed_count = 0
        total = len(files)

        # Use a bounded set of futures to control memory usage (backpressure).
        # ``prefetch_depth`` controls how far ahead we queue work per worker.
        # Depth 0 is an explicit no-prefetch mode with sequential submit/consume.
        if self._config.prefetch_depth == 0:
            limit = 1
        else:
            limit = max_workers * self._config.prefetch_depth
        submit_round = min(limit, self._config.chunk_size)
        timeout = self._config.timeout_per_file
        # Poll more frequently for short timeouts to reduce timeout-detection drift.
        poll_interval = min(0.05, max(0.005, timeout / 10.0))
        pending: set[Future[FileResult]] = set()
        # Track scheduling metadata for timeout handling.
        future_paths: dict[Future[FileResult], Path] = {}
        future_started: dict[Future[FileResult], float | None] = {}
        force_nonblocking_shutdown = False

        iterator = iter(files)
        iterator_exhausted = False

        try:

            def submit_next() -> bool:
                """Submit next file if available."""
                nonlocal iterator_exhausted
                if iterator_exhausted:
                    return False
                try:
                    path = next(iterator)
                    future = exec_instance.submit(_execute_with_timing, path, process_fn)
                    pending.add(future)
                    future_paths[future] = path
                    future_started[future] = None
                    return True
                except StopIteration:
                    iterator_exhausted = True
                    return False

            def submit_round_of_work() -> None:
                """Submit up to chunk_size new tasks while respecting pending limit."""
                submitted = 0
                while len(pending) < limit and submitted < submit_round:
                    if not submit_next():
                        break
                    submitted += 1

            def finalize_result(file_result: FileResult) -> FileResult:
                """Update progress counters/callback and return result for yielding."""
                nonlocal completed_count
                completed_count += 1
                if self._config.progress_callback:
                    self._config.progress_callback(completed_count, total, file_result)
                return file_result

            # Initial fill
            submit_round_of_work()

            while pending:
                # Wait for completion or timeout check
                # We use a short timeout to periodically check for stale tasks
                # Interval scales with timeout_per_file to keep detection accurate.
                done, _ = wait(
                    pending,
                    timeout=poll_interval,
                    return_when=FIRST_COMPLETED,
                )

                # 1. Process completed tasks
                for future in done:
                    pending.remove(future)
                    path = future_paths.pop(future)
                    future_started.pop(future, None)

                    try:
                        file_result = future.result()
                    except Exception as exc:
                        # Should be captured by _execute_with_timing, but safety net
                        file_result = FileResult(path=path, success=False, error=str(exc))

                    yield finalize_result(file_result)
                    submit_round_of_work()

                # 2. Check for timed-out tasks
                now = time.monotonic()
                # Mark tasks as started when the executor reports they are running.
                for future in pending:
                    if future_started[future] is None and future.running():
                        # Compensate for polling interval so timeout accounting
                        # does not drift late by up to one poll tick.
                        future_started[future] = now - poll_interval

                # Check running tasks (those in pending but not in done)
                # We iterate a copy because we might modify pending
                for future in list(pending):
                    start_time = future_started[future]
                    if start_time is None:
                        continue
                    path = future_paths[future]
                    if (now - start_time) > timeout:
                        # Report timeout immediately so callers are not blocked
                        # by uncancellable tasks continuing in the background.
                        cancelled = future.cancel()
                        if owns_executor and not cancelled:
                            force_nonblocking_shutdown = True
                        pending.remove(future)
                        del future_paths[future]
                        del future_started[future]

                        file_result = FileResult(
                            path=path,
                            success=False,
                            error=f"Timed out after {timeout}s",
                        )
                        yield finalize_result(file_result)

                        if not cancelled:
                            # The task is already running and cannot be cancelled.
                            # Fail fast: mark all remaining queued/unscheduled files
                            # as aborted so callers do not deadlock waiting for work
                            # that cannot begin while worker slots remain occupied.
                            abort_error = (
                                "Aborted because another task exceeded timeout "
                                "and could not be cancelled"
                            )
                            for other in list(pending):
                                pending.remove(other)
                                other_path = future_paths.pop(other)
                                future_started.pop(other, None)
                                other.cancel()
                                yield finalize_result(
                                    FileResult(
                                        path=other_path,
                                        success=False,
                                        error=abort_error,
                                    )
                                )

                            for remaining_path in iterator:
                                yield finalize_result(
                                    FileResult(
                                        path=remaining_path,
                                        success=False,
                                        error=abort_error,
                                    )
                                )
                            return

                        submit_round_of_work()
        finally:
            if owns_executor:
                exec_instance.shutdown(
                    wait=not force_nonblocking_shutdown,
                    cancel_futures=force_nonblocking_shutdown,
                )

    def _run_batch(
        self,
        executor_cls: type[ThreadPoolExecutor] | type[ProcessPoolExecutor] | None,
        max_workers: int,
        files: list[Path],
        process_fn: Callable[[Path], Any],
        executor: ThreadPoolExecutor | ProcessPoolExecutor | None = None,
    ) -> list[FileResult]:
        """Submit files to the executor and collect all results.

        Wrapper around process_batch_iter.

        Args:
            executor_cls: Deprecated - parameter is not used. See create_executor().
            max_workers: Deprecated - parameter is not used. See create_executor().
            files: Files to process in this batch.
            process_fn: Processing function.
            executor: Optional executor to use.

        Returns:
            List of FileResult for each submitted file.
        """
        # Delegate to process_batch_iter which handles bounding and timeouts correctly
        return list(self.process_batch_iter(files, process_fn, executor=executor))

    def shutdown(self) -> None:
        """Clean up any resources.

        Currently a no-op since executors are used as context managers,
        but provided for forward compatibility.
        """
