"""Parallel file processor using concurrent.futures.

This module provides the main ParallelProcessor class that orchestrates
batch file processing across thread or process pools with timeout handling,
retry logic, progress reporting, and graceful shutdown.
"""

from __future__ import annotations

import logging
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
from typing import Any, cast

from file_organizer.parallel.config import ExecutorType, ParallelConfig
from file_organizer.parallel.executor import create_executor
from file_organizer.parallel.result import BatchResult, FileResult

logger = logging.getLogger(__name__)


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
        return cast(ProcessPoolExecutor | ThreadPoolExecutor, exec_instance), bool(owns_executor)

    @staticmethod
    def _is_non_retryable_failure(result: FileResult) -> bool:
        """Return whether a failed result should stop retries for the batch."""
        return result.non_retryable

    @staticmethod
    def _collect_result(future: Future[FileResult], path: Path) -> FileResult:
        """Extract a FileResult from a completed future, wrapping exceptions."""
        try:
            return future.result()
        except Exception as exc:
            return FileResult(path=path, success=False, error=str(exc))

    def _process_with_executor(  # noqa: C901 — complexity from nested state-tracking closures
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
        # Queue time is tracked separately: if a task never gets a worker thread
        # within `timeout` seconds of submission, all workers are saturated by
        # abandoned tasks and we must abort to avoid an infinite hang.
        future_queued_at: dict[Future[FileResult], float] = {}
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
                future_queued_at[future] = time.monotonic()
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
                future_queued_at.pop(future, None)
                yield finalize_result(self._collect_result(future, path))
                submit_round_of_work()

            saturation = self._check_pool_saturation(
                pending,
                future_paths,
                future_started,
                future_queued_at,
                timeout,
                finalize_result,
            )
            if saturation is not None:
                cleanup_state["force_nonblocking_shutdown"] = owns_executor
                yield from saturation
                # #432 follow-up: unsubmitted files at the iterator tail are
                # never-started by definition; flag them retryable so the
                # dispatcher's sequential pass picks them up. Without this, a
                # saturation with N in-flight + M unsubmitted still mass-fails
                # the M tail for the same reason the in-flight retry was meant
                # to fix.
                for remaining_path in iterator:
                    yield finalize_result(
                        FileResult(
                            path=remaining_path,
                            success=False,
                            error="Aborted: worker pool saturated by hung tasks",
                            non_retryable=False,
                        )
                    )
                return

            # Check for running-task timeouts
            timeout_handling = self._handle_timeouts(
                pending,
                future_paths,
                future_started,
                future_queued_at,
                timeout,
                poll_interval,
                finalize_result,
            )
            if timeout_handling is not None:
                should_abort, needs_nonblocking, timeout_results = timeout_handling
                if needs_nonblocking:
                    cleanup_state["force_nonblocking_shutdown"] = owns_executor
                if not should_abort:
                    yield from timeout_results
                    submit_round_of_work()
                    continue

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

    def _check_pool_saturation(
        self,
        pending: set[Future[FileResult]],
        future_paths: dict[Future[FileResult], Path],
        future_started: dict[Future[FileResult], float | None],
        future_queued_at: dict[Future[FileResult], float],
        timeout: float,
        finalize_result: Callable[[FileResult], FileResult],
    ) -> list[FileResult] | None:
        """Detect and handle worker-pool saturation caused by abandoned tasks.

        Returns a list of finalized error results for all pending tasks if the
        pool is saturated (all pending tasks queued for > 2 × timeout without
        starting), or None if the pool is healthy.  The 2× multiplier gives
        temporarily-busy pools (abandoned tasks that finish in O(timeout)) time
        to free a slot before declaring permanent saturation.
        """
        if not pending:
            return None
        now = time.monotonic()
        # Only futures that have never started (future_started[f] is None) AND
        # have been queued for longer than 2×timeout count as stalled. Futures
        # already picked up by a worker have a float start time and are excluded.
        stalled = [
            f
            for f in pending
            if future_started.get(f) is None
            and not f.running()
            and (now - future_queued_at.get(f, now)) > timeout * 2
        ]
        if not stalled:
            return None
        logger.warning(
            "Worker pool saturated: %d queued tasks waited > %.0fs without "
            "starting. Aborting remaining work. "
            "Hint: raise `--timeout-per-file` (#396) or lower `--workers` "
            "(#408) — on low-memory hardware running large vision models, "
            "concurrent slots often exhaust unified memory and trigger this "
            "saturation path.",
            len(stalled),
            timeout * 2,
        )
        results: list[FileResult] = []
        for f in list(pending):
            # #432: distinguish never-started tasks (collateral, should be
            # retryable in a degraded mode) from in-flight tasks (truly hung —
            # don't retry). The dispatcher's image path scans for
            # ``non_retryable=False`` saturation aborts and reruns them
            # sequentially so a 2-3 hung-image case doesn't collateral-fail
            # every untried file in the batch.
            never_started = future_started.get(f) is None and not f.running()
            f.cancel()
            abort_path = future_paths.pop(f)
            future_started.pop(f, None)
            future_queued_at.pop(f, None)
            pending.discard(f)
            results.append(
                finalize_result(
                    FileResult(
                        path=abort_path,
                        success=False,
                        error="Aborted: worker pool saturated by hung tasks",
                        non_retryable=not never_started,
                    )
                )
            )
        return results

    def _handle_timeouts(
        self,
        pending: set[Future[FileResult]],
        future_paths: dict[Future[FileResult], Path],
        future_started: dict[Future[FileResult], float | None],
        future_queued_at: dict[Future[FileResult], float],
        timeout: float,
        poll_interval: float,
        finalize_result: Callable[[FileResult], FileResult],
    ) -> tuple[bool, bool, list[FileResult]] | None:
        """Check for and handle timed-out tasks.

        ``non_retryable=True`` is set **only** on the uncancellable-running
        branch — where ``future.cancel()`` returned ``False`` because a thread
        is actively executing the task. Retrying such a task would submit a
        new future while the original thread is still running, risking resource
        exhaustion. Futures that were cancelled successfully (task never
        started) do *not* receive ``non_retryable=True`` and may be retried
        by the caller.

        Args:
            pending: Set of pending futures.
            future_paths: Mapping of futures to file paths.
            future_started: Mapping of futures to start times.
            future_queued_at: Mapping of futures to submission times.
            timeout: Timeout threshold in seconds.
            poll_interval: Polling interval for drift compensation.
            finalize_result: Function to finalize results.

        Returns:
            None if no timeout was handled, or a 3-tuple of
            (should_abort_processing, needs_nonblocking_shutdown,
            finalized_results_to_yield).

            should_abort_processing=True means drain the iterator and stop.
            needs_nonblocking_shutdown=True means set force_nonblocking_shutdown
            so the executor does not hang waiting for a stuck thread.
        """
        now = time.monotonic()

        # Mark tasks as started when they begin running
        for future in pending:
            if future_started[future] is None and future.running():
                future_started[future] = now - poll_interval

        # Check for running-task timeouts
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
                    future_queued_at.pop(future, None)
                    timed_out_result = finalize_result(
                        FileResult(
                            path=path,
                            success=False,
                            error=f"Timed out after {timeout}s",
                        )
                    )
                    return (False, False, [timed_out_result])

                if future.done():
                    # Task completed in the narrow window between cancel() and
                    # done() — a race that only occurs on some OS schedulers
                    # (commonly macOS).  Preserve the actual result rather than
                    # reporting a phantom timeout: the backdated
                    # ``future_started[future] = now - poll_interval`` (above)
                    # can trip the elapsed-time check up to ``poll_interval``
                    # seconds early, so a task that genuinely finished within
                    # the configured timeout was otherwise being reported as
                    # ``non_retryable=True`` and discarding its actual return
                    # value.
                    pending.remove(future)
                    del future_paths[future]
                    del future_started[future]
                    future_queued_at.pop(future, None)
                    try:
                        race_result = future.result()
                    except Exception as exc:
                        # The task completed but raised — surface the real
                        # exception text rather than a timeout.
                        race_result = finalize_result(
                            FileResult(path=path, success=False, error=str(exc))
                        )
                    else:
                        race_result = finalize_result(race_result)
                    return (False, False, [race_result])

                # Task is running and cannot be cancelled.  Abandon it —
                # remove from tracking so other files continue normally.
                # The thread will finish on its own (Ollama will eventually
                # respond); we set needs_nonblocking_shutdown so the executor
                # doesn't hang on cleanup waiting for it.
                logger.warning(
                    "Task for %s timed out after %.0fs and could not be cancelled "
                    "(thread still running in background); continuing with remaining files",
                    path,
                    timeout,
                )
                pending.remove(future)
                del future_paths[future]
                del future_started[future]
                future_queued_at.pop(future, None)
                abandoned_result = finalize_result(
                    FileResult(
                        path=path,
                        success=False,
                        error=f"Timed out after {timeout}s",
                        non_retryable=True,
                    )
                )
                # The abandoned thread still occupies the worker slot until it
                # exits naturally.  Reset the saturation-detection clock for all
                # remaining queued futures so the 2×timeout guard doesn't fire
                # while that thread is still winding down.
                _reset_time = time.monotonic()
                for _remaining in pending:
                    future_queued_at[_remaining] = _reset_time
                return (False, True, [abandoned_result])

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
