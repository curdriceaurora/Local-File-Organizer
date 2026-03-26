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

            if any(self._is_non_retryable_failure(result) for result in failed):
                results.extend(failed)
                remaining = []
                break

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

        exec_instance, owns_executor = self._setup_executor(executor)
        cleanup_state = {"force_nonblocking_shutdown": False}
        try:
            yield from self._process_with_executor(
                exec_instance,
                files,
                process_fn,
                owns_executor,
                cleanup_state,
            )
        finally:
            self._cleanup_executor(
                exec_instance,
                owns_executor,
                cleanup_state["force_nonblocking_shutdown"],
            )

    def _setup_executor(
        self, executor: ThreadPoolExecutor | ProcessPoolExecutor | None
    ) -> tuple[ThreadPoolExecutor | ProcessPoolExecutor, bool]:
        """Set up executor for batch processing.

        Args:
            executor: Optional existing executor to reuse.

        Returns:
            Tuple of (executor instance, owns_executor flag).
        """
        owns_executor = executor is None
        if owns_executor:
            max_workers = self._config.max_workers or os.cpu_count() or 1
            executor_type = (
                "process" if self._config.executor_type == ExecutorType.PROCESS else "thread"
            )
            exec_instance, exec_type = create_executor(executor_type, max_workers)
            with self._lock:
                self._executor_type_used = exec_type
        else:
            assert executor is not None
            exec_instance = executor
        return exec_instance, owns_executor

    @staticmethod
    def _is_non_retryable_failure(result: FileResult) -> bool:
        """Return whether a failed result should stop retries for the batch."""
        return result.non_retryable

    def _process_with_executor(
        self,
        exec_instance: ThreadPoolExecutor | ProcessPoolExecutor,
        files: list[Path],
        process_fn: Callable[[Path], Any],
        owns_executor: bool,
        cleanup_state: dict[str, bool],
    ) -> Iterator[FileResult]:
        """Core processing loop with timeout handling.

        Args:
            exec_instance: Executor to use for processing.
            files: Files to process.
            process_fn: Function to apply to each file.
            owns_executor: Whether we own the executor and should handle shutdown.
            cleanup_state: Per-iterator shutdown state shared with cleanup.

        Yields:
            FileResult for each completed file.
        """
        total = len(files)
        completed_count = 0
        max_workers = self._config.max_workers or os.cpu_count() or 1

        # Calculate limits for backpressure control
        if self._config.prefetch_depth == 0:
            limit = 1
        else:
            limit = max_workers * self._config.prefetch_depth
        submit_round = min(limit, self._config.chunk_size)
        timeout = self._config.timeout_per_file
        poll_interval = min(0.05, max(0.005, timeout / 10.0))

        # State tracking
        pending: set[Future[FileResult]] = set()
        future_paths: dict[Future[FileResult], Path] = {}
        future_started: dict[Future[FileResult], float | None] = {}
        iterator = iter(files)
        iterator_exhausted = False

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
            done, _ = wait(pending, timeout=poll_interval, return_when=FIRST_COMPLETED)

            # Process completed tasks
            for future in done:
                pending.remove(future)
                path = future_paths.pop(future)
                future_started.pop(future, None)

                try:
                    file_result = future.result()
                except Exception as exc:
                    file_result = FileResult(path=path, success=False, error=str(exc))

                yield finalize_result(file_result)
                submit_round_of_work()

            # Check for and handle timeouts
            timeout_handling = self._handle_timeouts(
                pending,
                future_paths,
                future_started,
                timeout,
                poll_interval,
                finalize_result,
            )
            if timeout_handling is not None:
                should_abort, timeout_results = timeout_handling
                if not should_abort:
                    yield from timeout_results
                    submit_round_of_work()
                    continue

                cleanup_state["force_nonblocking_shutdown"] = owns_executor
                yield from timeout_results
                # Abort remaining files from iterator
                for remaining_path in iterator:
                    yield finalize_result(
                        FileResult(
                            path=remaining_path,
                            success=False,
                            error="Aborted because another task exceeded timeout "
                            "and could not be cancelled",
                            non_retryable=True,
                        )
                    )
                return

            submit_round_of_work()

    def _handle_timeouts(
        self,
        pending: set[Future[FileResult]],
        future_paths: dict[Future[FileResult], Path],
        future_started: dict[Future[FileResult], float | None],
        timeout: float,
        poll_interval: float,
        finalize_result: Callable[[FileResult], FileResult],
    ) -> tuple[bool, list[FileResult]] | None:
        """Check for and handle timed-out tasks.

        Args:
            pending: Set of pending futures.
            future_paths: Mapping of futures to file paths.
            future_started: Mapping of futures to start times.
            timeout: Timeout threshold in seconds.
            poll_interval: Polling interval for drift compensation.
            owns_executor: Whether we own the executor.
            finalize_result: Function to finalize results.

        Returns:
            None if no timeout was handled, or tuple of
            (should_abort_processing, finalized_results_to_yield).
        """
        now = time.monotonic()

        # Mark tasks as started when they begin running
        for future in pending:
            if future_started[future] is None and future.running():
                future_started[future] = now - poll_interval

        # Check for timeouts
        for future in list(pending):
            start_time = future_started[future]
            if start_time is None:
                continue

            if (now - start_time) > timeout:
                path = future_paths[future]
                cancelled = future.cancel()
                if cancelled:
                    pending.remove(future)
                    del future_paths[future]
                    del future_started[future]
                    timed_out_result = finalize_result(
                        FileResult(
                            path=path,
                            success=False,
                            error=f"Timed out after {timeout}s",
                        )
                    )
                    return (False, [timed_out_result])

                if future.done():
                    pending.remove(future)
                    completed_path = future_paths.pop(future)
                    future_started.pop(future, None)
                    try:
                        completed_result = finalize_result(future.result())
                    except Exception as exc:
                        completed_result = finalize_result(
                            FileResult(path=completed_path, success=False, error=str(exc))
                        )
                    return (False, [completed_result])

                abort_results = self._abort_remaining_work(
                    pending,
                    future_paths,
                    future_started,
                    finalize_result,
                    timed_out_future=future,
                    timeout=timeout,
                )
                return (True, abort_results)

        return None

    def _abort_remaining_work(
        self,
        pending: set[Future[FileResult]],
        future_paths: dict[Future[FileResult], Path],
        future_started: dict[Future[FileResult], float | None],
        finalize_result: Callable[[FileResult], FileResult],
        timed_out_future: Future[FileResult] | None = None,
        timeout: float | None = None,
    ) -> list[FileResult]:
        """Abort all remaining pending work due to uncancellable timeout.

        Args:
            pending: Set of pending futures to abort.
            future_paths: Mapping of futures to file paths.
            future_started: Mapping of futures to start times.
            finalize_result: Function to finalize results.
            timed_out_future: Future that exceeded the timeout and could not be cancelled.
            timeout: Timeout threshold used for the timed-out future, if known.

        Returns:
            List of FileResult for aborted tasks.
        """
        abort_error = "Aborted because another task exceeded timeout and could not be cancelled"
        aborted_results = []

        for other in list(pending):
            pending.remove(other)
            other_path = future_paths.pop(other)
            future_started.pop(other, None)

            if other is timed_out_future:
                result = finalize_result(
                    FileResult(
                        path=other_path,
                        success=False,
                        error=(
                            f"Timed out after {timeout}s and could not be cancelled"
                            if timeout is not None
                            else abort_error
                        ),
                        non_retryable=True,
                    )
                )
                aborted_results.append(result)
                continue

            if other.done():
                try:
                    result = finalize_result(other.result())
                except Exception as exc:
                    result = finalize_result(
                        FileResult(path=other_path, success=False, error=str(exc))
                    )
                aborted_results.append(result)
                continue

            other.cancel()
            result = finalize_result(
                FileResult(
                    path=other_path,
                    success=False,
                    error=abort_error,
                    non_retryable=True,
                )
            )
            aborted_results.append(result)

        return aborted_results

    def _cleanup_executor(
        self,
        exec_instance: ThreadPoolExecutor | ProcessPoolExecutor,
        owns_executor: bool,
        force_shutdown: bool,
    ) -> None:
        """Clean up executor after processing.

        Args:
            exec_instance: Executor to clean up.
            owns_executor: Whether we own the executor.
            force_shutdown: Whether to shut down without waiting.
        """
        if owns_executor:
            exec_instance.shutdown(
                wait=not force_shutdown,
                cancel_futures=force_shutdown,
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
