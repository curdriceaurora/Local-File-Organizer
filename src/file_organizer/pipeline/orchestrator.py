"""Pipeline orchestrator for auto-organization.

Coordinates file discovery (via watcher or batch), routing, processing,
and organization into a cohesive pipeline.  Supports composable stages
via :class:`~file_organizer.interfaces.PipelineStage`.
"""

from __future__ import annotations

import contextlib
import logging
import threading
import time
from collections.abc import Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import wait as futures_wait
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from file_organizer.interfaces.pipeline import PipelineStage, StageContext
from file_organizer.optimization.batch_sizer import AdaptiveBatchSizer
from file_organizer.optimization.buffer_pool import BufferPool
from file_organizer.optimization.memory_limiter import MemoryLimiter
from file_organizer.optimization.resource_monitor import ResourceMonitor
from file_organizer.utils.safe_copy import safe_copy2

from .config import PipelineConfig
from .processor_pool import (
    BaseProcessor,
    ProcessorPool,
    ProcessorResult,
    normalize_processor_result,
)
from .resource_aware_executor import BUFFER_KEY as _BUFFER_KEY
from .resource_aware_executor import ResourceAwareExecutor
from .router import FileRouter, ProcessorType

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProcessingResult:
    """Result of processing a single file through the pipeline.

    Attributes:
        file_path: Original path of the processed file.
        success: Whether processing completed without errors.
        category: The folder/category name assigned to the file.
        destination: The target path where the file was (or would be) placed.
        duration_ms: Processing time in milliseconds.
        error: Error message if processing failed, None otherwise.
        processor_type: The processor type that handled the file.
        dry_run: Whether this was a dry-run (no files actually moved).
    """

    file_path: Path
    success: bool
    category: str = ""
    destination: Path | None = None
    duration_ms: float = 0.0
    error: str | None = None
    processor_type: ProcessorType = ProcessorType.UNKNOWN
    dry_run: bool = True


@dataclass
class PipelineStats:
    """Cumulative statistics for pipeline operations.

    Attributes:
        total_processed: Total files that went through the pipeline.
        successful: Number of files processed successfully.
        failed: Number of files that failed processing.
        skipped: Number of files skipped (unsupported, filtered).
        total_duration_ms: Total processing time in milliseconds.
    """

    total_processed: int = 0
    successful: int = 0
    failed: int = 0
    skipped: int = 0
    total_duration_ms: float = 0.0


class PipelineOrchestrator:
    """Orchestrates the auto-organization pipeline.

    Connects file discovery to processing and organization.  Supports
    both batch mode (process a list of files) and watch mode (react
    to file-system events in real-time).

    The orchestrator can operate in two modes:

    1. **Stage-based** (new): supply a ``stages`` list of
       :class:`~file_organizer.interfaces.PipelineStage` instances.
       Each file flows through the stages in order.
    2. **Legacy** (default): uses the built-in router, processor pool,
       and ``_process_with_processor`` / ``_organize_file`` helpers
       for backward compatibility.

    Dry-run mode is enabled by default for safety.  Files are only
    moved when both ``dry_run=False`` and ``auto_organize=True`` in
    config.

    Example::

        from file_organizer.pipeline.stages import (
            PreprocessorStage, AnalyzerStage,
            PostprocessorStage, WriterStage,
        )
        config = PipelineConfig(
            output_directory=Path("organized"),
            dry_run=True,
        )
        pipeline = PipelineOrchestrator(
            config,
            stages=[
                PreprocessorStage(),
                AnalyzerStage(),
                PostprocessorStage(output_directory=config.output_directory),
                WriterStage(),
            ],
        )
        result = pipeline.process_file(Path("document.pdf"))
    """

    def __init__(
        self,
        config: PipelineConfig | None = None,
        stages: Sequence[PipelineStage] | None = None,
        prefetch_depth: int = 2,
        prefetch_stages: int = 1,
        memory_limiter: MemoryLimiter | None = None,
        batch_sizer: AdaptiveBatchSizer | None = None,
        buffer_pool: BufferPool | None = None,
        resource_monitor: ResourceMonitor | None = None,
        memory_pressure_threshold_percent: float = 85.0,
    ) -> None:
        """Initialize the pipeline orchestrator.

        Args:
            config: Pipeline configuration.  Uses safe defaults if *None*.
            stages: Optional list of composable pipeline stages.
                When provided, ``process_file`` delegates to these stages
                instead of the legacy router/pool path.
            prefetch_depth: Number of files to pre-process in parallel
                using I/O threads while the current file's compute stages
                run.  Set to 0 to disable prefetch (sequential fallback).
                Defaults to 2.
            prefetch_stages: Requested number of leading stages to treat
                as I/O stages.  For thread-safety, the current
                implementation caps the effective prefetched stage count
                at 1, so only the first stage (typically
                :class:`~file_organizer.pipeline.stages.PreprocessorStage`)
                runs in the prefetch thread pool; remaining stages run on
                the calling thread.  Values greater than 1 currently log
                a warning and are treated as 1.  Defaults to 1.
            memory_limiter: Optional limiter that gates whether a new
                prefetch slot may be opened.  When ``limiter.check()``
                returns *False*, no new prefetch futures are submitted
                until memory is available.
            batch_sizer: Optional adaptive batch sizer used by
                ``process_batch`` to chunk large inputs based on estimated
                memory budget. When omitted, a default
                :class:`~file_organizer.optimization.batch_sizer.AdaptiveBatchSizer`
                is used.
            buffer_pool: Optional shared byte-buffer pool used to reduce
                allocation churn across file processing.
            resource_monitor: Optional monitor used to detect memory pressure
                and trigger buffer-pool resizing.
            memory_pressure_threshold_percent: Threshold passed to
                ``resource_monitor.should_evict()`` for proactive buffer-pool
                shrink decisions. Must be between 0 and 100.
        """
        if not 0.0 <= memory_pressure_threshold_percent <= 100.0:
            raise ValueError(
                "memory_pressure_threshold_percent must be between 0 and 100, "
                f"got {memory_pressure_threshold_percent}"
            )

        self.config = config or PipelineConfig()
        self.router = FileRouter()
        self.processor_pool = ProcessorPool()
        self.stats = PipelineStats()
        self._stats_lock = threading.Lock()
        self._stages: list[PipelineStage] = list(stages) if stages else []
        # Stages retired by ``set_stages()`` while still potentially holding open
        # resources (e.g. SafeDir fds). They become unreachable from
        # ``self._stages`` but their ``close()`` must still run, so track them
        # here and close them in ``stop()`` alongside the current stages (#1286).
        self._retired_stages: list[PipelineStage] = []

        self._prefetch_depth = max(0, prefetch_depth)
        self._prefetch_stages = max(0, prefetch_stages)
        self._memory_limiter = memory_limiter
        self._batch_sizer = batch_sizer or AdaptiveBatchSizer()
        self._buffer_pool: BufferPool | None = buffer_pool
        # Dedicated lock for lazy buffer-pool init. Must NOT be ``self._lock``:
        # a worker initializing the pool mid-shutdown would otherwise block on
        # the lifecycle lock that ``stop()`` holds while draining, stalling the
        # drain until timeout and wrongly skipping stage close (#1285 review).
        self._buffer_pool_lock = threading.Lock()
        self._resource_monitor = resource_monitor or ResourceMonitor()
        self._memory_pressure_threshold_percent = memory_pressure_threshold_percent

        # D2 seam (WP-4.3, #1233): prefetch + I/O-compute overlap moved into
        # ``ResourceAwareExecutor``. The orchestrator builds it from the same
        # resource collaborators it holds so the prefetch path shares one
        # buffer pool, memory limiter, and resource monitor with the
        # orchestrator's own adaptive-batching helpers (which existing tests
        # exercise directly via ``self._resource_monitor`` / ``self._buffer_pool``).
        self._resource_executor = ResourceAwareExecutor(
            prefetch_depth=prefetch_depth,
            prefetch_stages=prefetch_stages,
            memory_limiter=memory_limiter,
            buffer_pool=buffer_pool,
            resource_monitor=self._resource_monitor,
            memory_pressure_threshold_percent=memory_pressure_threshold_percent,
        )

        self._running = False
        self._lock = threading.Lock()
        self._monitor: Any = None
        self._watch_thread: threading.Thread | None = None
        self._executor = ThreadPoolExecutor(
            max_workers=self.config.max_concurrent,
        )
        # In-flight watch-mode ``process_file`` futures. Tracked so ``stop()``
        # can drain workers before closing stage-owned resources (WP-4.3,
        # #1233): ``self._executor.shutdown(wait=False)`` lets already-submitted
        # work keep running, so closing a stage's fd while a worker is still in
        # ``stage.process()`` would race. Draining first makes the stage-close
        # loop safe.
        self._watch_futures: set[Future[Any]] = set()
        # Done-callbacks discard futures from worker threads while stop()
        # snapshots the set, so every add/discard/snapshot must hold this lock
        # to avoid "set changed size during iteration" (#1285 review).
        self._watch_futures_lock = threading.Lock()
        # Guards the stage-close loop so a repeated stop() does not double-close
        # stage resources. Reset on start() for a reused orchestrator.
        self._stages_closed = False
        # Set when stop() shut the executor down but the watch-worker drain timed
        # out, so processor-pool cleanup must be deferred (a still-running legacy
        # watch worker may hold a pool processor). A later stop() retries cleanup
        # once the drain succeeds. ProcessorPool.cleanup() is idempotent.
        self._pending_pool_cleanup = False

    # ------------------------------------------------------------------
    # Stage management
    # ------------------------------------------------------------------

    @property
    def stages(self) -> list[PipelineStage]:
        """Return the current stage list (mutable copy)."""
        return list(self._stages)

    @property
    def buffer_pool(self) -> BufferPool:
        """Return the orchestrator's shared buffer pool."""
        if self._buffer_pool is None:
            with self._buffer_pool_lock:
                if self._buffer_pool is None:
                    self._buffer_pool = BufferPool()
        return self._buffer_pool

    def set_stages(self, stages: Sequence[PipelineStage]) -> None:
        """Replace the stage list at runtime (thread-safe).

        Args:
            stages: New ordered list of pipeline stages.
        """
        with self._lock:
            # Preserve the outgoing stages so their close() is not lost: once
            # replaced they are unreachable from self._stages, but they may hold
            # open fds. stop() closes them (under the same drain-safety as the
            # current stages) and then clears the retired list (#1286).
            # Skip retiring when the outgoing stages were already closed
            # (``_stages_closed``): their close() already ran, so re-queuing them
            # would double-close on the next stop().
            if not self._stages_closed:
                # Only retire stages actually being dropped. A stage carried
                # over into the new list (e.g. ``[a]`` -> ``set_stages([a, b])``)
                # stays current and must NOT also be queued for close, or its
                # close() would run twice on stop() — once via the retired loop
                # and once via the current-stages loop (#1289 review). Compare
                # by identity since stages need not be hashable/comparable.
                retained_ids = {id(s) for s in stages}
                self._retired_stages.extend(s for s in self._stages if id(s) not in retained_ids)
            self._stages = list(stages)
            # Purge any reinstalled stage from the retired list: a stage that was
            # dropped earlier and is now present in the new list is current
            # again, so it must be closed via the current-stages loop only, not
            # also via the retired loop (e.g. [a] -> [b] -> [a]) (#1289 review).
            current_ids = {id(s) for s in self._stages}
            self._retired_stages = [s for s in self._retired_stages if id(s) not in current_ids]
            # Newly installed stages may hold their own fds; allow stop() to
            # close them even if a previous stage list was already closed
            # (e.g. batch → set_stages → batch without start()) (#1285 review).
            self._stages_closed = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the pipeline, including watch mode if configured.

        When watch_config is set, starts a background thread that
        polls the file monitor for events and processes them.

        Raises:
            RuntimeError: If the pipeline is already running.
        """
        with self._lock:
            if self._running:
                raise RuntimeError("Pipeline is already running")

            self._running = True
            # Fresh lifecycle: stages may be (re)opened, so allow close again.
            self._stages_closed = False

            # Start file monitor if watch config is provided
            if self.config.watch_config is not None:
                self._start_watch_mode()

            logger.info(
                "Pipeline started (dry_run=%s, auto_organize=%s)",
                self.config.dry_run,
                self.config.auto_organize,
            )

    def stop(self) -> None:
        """Stop the pipeline and clean up resources.

        Stops the file monitor (if running), cleans up processors,
        and resets pipeline state. Safe to call even if not running.
        """
        with self._lock:
            was_running = self._running
            if was_running:
                self._running = False

                # Stop file monitor
                if self._monitor is not None:
                    self._monitor.stop()
                    self._monitor = None

                # Wait for watch thread
                if self._watch_thread is not None:
                    self._watch_thread.join(timeout=5.0)
                    self._watch_thread = None

                # Clean up executor
                self._executor.shutdown(wait=False)

                # Defer processor-pool cleanup until after a successful watch-worker
                # drain below: an in-flight legacy watch worker may still be holding
                # a pool processor, and releasing it now reintroduces the same race
                # the stage-close drain fixes (#1291 review).
                self._pending_pool_cleanup = True

            # Close stage-owned resources (e.g. SafeDir fds) only once it is safe
            # — i.e. no watch-mode worker can still be inside ``stage.process()``.
            # This check runs on EVERY path, not just the running branch, because
            # (a) batch-only callers (``process_batch`` without ``start()``) still
            # hold stage resources, and (b) a previous timed-out ``stop()`` leaves
            # ``_running`` false while ``_watch_futures`` may still hold running
            # work — a second ``stop()`` must re-check rather than blindly close
            # and reintroduce the closed-fd race (#1285 review). Completed futures
            # remove themselves via the done-callback, so this only waits on work
            # that is genuinely still in flight. The bounded wait mirrors the
            # watch-thread join so a stuck/long worker cannot hang shutdown.
            safe_to_close = True
            with self._watch_futures_lock:
                pending = set(self._watch_futures)
            if pending:
                _, not_done = futures_wait(pending, timeout=5.0)
                if not_done:
                    # A worker is still running past the timeout. Closing a
                    # stage's fd now could pull it out from under that worker, so
                    # skip the close loop entirely rather than race; any held fd
                    # is reclaimed at process exit. The alternative (unbounded
                    # wait) risks hanging stop() on a stuck model-backed worker.
                    safe_to_close = False
                    logger.warning(
                        "%d watch worker(s) still running after %.1fs drain timeout; "
                        "skipping stage close to avoid a closed-fd race",
                        len(not_done),
                        5.0,
                    )

            if safe_to_close:
                # The drain succeeded (or there was nothing in flight), so no
                # watch worker can still be using a pool processor: run any
                # deferred processor-pool cleanup now (idempotent if already done).
                if self._pending_pool_cleanup:
                    self.processor_pool.cleanup()
                    self._pending_pool_cleanup = False
                self._close_stages()

            if was_running:
                logger.info("Pipeline stopped")

    def _close_stages(self) -> None:
        """Release resources held by stages (e.g. SafeDir file descriptors).

        WP-4.3 (#1233): the ``getattr`` guard makes this a safe no-op for stages
        that do not define ``close()`` (this repo's stages currently hold no
        fds). Idempotent via ``_stages_closed`` so a repeated ``stop()`` does
        not double-close; ``start()`` resets the guard for a reused orchestrator.

        Retired stages (replaced via ``set_stages()`` while still holding open
        resources) are closed here too and then cleared, so their ``close()`` is
        not lost when they fall out of ``self._stages`` (#1286). This runs only
        when the caller deemed it safe to close (the watch-worker drain
        succeeded), so retired stages are never closed out from under a worker
        that might still be using them — a timed-out drain leaves them in
        ``_retired_stages`` for a later ``stop()``.
        """
        # Close retired stages first, then drop them. This is gated by the same
        # drain check as the current stages (the caller only invokes us when
        # ``safe_to_close``), and clearing the list keeps a repeated ``stop()``
        # from double-closing them.
        for stage in self._retired_stages:
            close_fn = getattr(stage, "close", None)
            if close_fn is not None:
                with contextlib.suppress(Exception):
                    close_fn()
        self._retired_stages.clear()

        if self._stages_closed:
            return
        self._stages_closed = True
        for stage in self._stages:
            close_fn = getattr(stage, "close", None)
            if close_fn is not None:
                with contextlib.suppress(Exception):
                    close_fn()

    def _on_watch_future_done(self, future: Future[Any]) -> None:
        """Discard a completed watch-mode future under the lock.

        Runs from executor worker threads, so it must hold the same lock that
        guards ``stop()``'s snapshot and ``_watch_loop``'s add (#1285 review).

        A watch future that finished with an exception would otherwise vanish
        silently (its ``process_file`` failure is never awaited), so observe and
        log it. The exception is read OUTSIDE the lock to avoid holding the
        ``stop()`` lock during logging.
        """
        with self._watch_futures_lock:
            self._watch_futures.discard(future)
        if not future.cancelled():
            exc = future.exception()
            if exc is not None:
                logger.error("Watch-mode file processing failed: %s", exc)

    # ------------------------------------------------------------------
    # Processing
    # ------------------------------------------------------------------

    def process_file(self, file_path: Path, trusted_root: Path | None = None) -> ProcessingResult:
        """Process a single file through the pipeline.

        If ``stages`` were provided, each stage is executed in order.
        Otherwise, falls back to the legacy router/pool path.

        Args:
            file_path: Path to the file to process.
            trusted_root: Optional trusted root directory for anchored reads.

        Returns:
            ProcessingResult with processing outcome and metadata.
        """
        stages = self._stages  # snapshot once; set_stages() may replace list concurrently
        if stages:
            return self._process_file_staged(file_path, stages, trusted_root=trusted_root)
        return self._process_file_legacy(file_path)

    def process_batch(self, files: list[Path]) -> list[ProcessingResult]:
        """Process a batch of files through the pipeline.

        When stages are configured, ``prefetch_depth > 0``,
        ``prefetch_stages > 0``, and ``len(files) > 1``, the first
        configured stage may be run in a background thread pool so that I/O
        for file *N+1* overlaps with compute for file *N*. Values of
        ``prefetch_stages`` greater than 1 currently log a warning and are
        effectively capped to 1 for thread-safety. Otherwise files are
        processed sequentially.

        Args:
            files: List of file paths to process.

        Returns:
            List of ProcessingResult instances, one per file, in order.
        """
        if not files:
            return []

        # Snapshot once; set_stages() may replace self._stages concurrently.
        stages = self._stages
        overhead_per_file = self.buffer_pool.buffer_size if stages else 0
        file_sizes = [self._safe_file_size(path) for path in files]
        batch_size = max(
            1,
            self._batch_sizer.calculate_batch_size(
                file_sizes,
                # BufferPool allocates at least ``buffer_size`` per file and may
                # allocate larger buffers for oversized files; using the base
                # pool buffer size here keeps sizing conservative and stable.
                overhead_per_file=overhead_per_file,
            ),
        )

        results: list[ProcessingResult] = []

        if stages and self._prefetch_depth > 0 and self._prefetch_stages > 0 and len(files) > 1:
            # Keep prefetch behavior deterministic (Issue #713 contracts) while
            # still applying proactive memory feedback to the shared buffer pool.
            results = self._process_batch_prefetch(files, stages)
            self._rebalance_buffer_pool()
            return results

        index = 0
        while index < len(files):
            upper = min(index + batch_size, len(files))
            batch_files = files[index:upper]
            chunk_start_rss = self._safe_current_rss()
            results.extend(self._process_batch_chunk(batch_files, stages))
            self._rebalance_buffer_pool()

            if upper < len(files):
                chunk_end_rss = self._safe_current_rss()
                chunk_rss_delta = max(0, chunk_end_rss - chunk_start_rss)
                adjusted = self._batch_sizer.adjust_from_feedback(
                    chunk_rss_delta,
                    len(batch_files),
                )
                batch_size = max(1, adjusted)
            index = upper

        return results

    @property
    def is_running(self) -> bool:
        """Return True if the pipeline is currently running."""
        return self._running

    def _safe_file_size(self, file_path: Path) -> int:
        """Return file size in bytes, or 0 when unavailable."""
        try:
            return file_path.stat().st_size
        except OSError:
            logger.debug("Unable to stat %s for adaptive batching", file_path, exc_info=True)
            return 0

    def _safe_current_rss(self) -> int:
        """Return current process RSS in bytes, or 0 when unavailable."""
        try:
            return self._resource_monitor.get_memory_usage().rss
        except (OSError, RuntimeError, ValueError):
            logger.debug("Unable to read current RSS for adaptive batching", exc_info=True)
            return 0

    def _rebalance_buffer_pool(self) -> None:
        """Resize buffer pool in response to memory pressure and utilization."""
        pool = self._buffer_pool
        if pool is None:
            return

        try:
            under_pressure = self._resource_monitor.should_evict(
                threshold_percent=self._memory_pressure_threshold_percent,
            )
        except (OSError, RuntimeError, ValueError):
            logger.debug("Failed to evaluate memory pressure for buffer pool", exc_info=True)
            return

        if under_pressure:
            target = max(pool.initial_buffers, pool.in_use_count)
            new_size = pool.resize(target)
            logger.info(
                "Memory pressure detected; resized buffer pool to %d buffers (target=%d)",
                new_size,
                target,
            )
            return

        if pool.utilization >= 0.9 and pool.total_buffers < pool.max_buffers:
            growth_step = max(1, pool.initial_buffers // 2)
            target = min(pool.max_buffers, pool.total_buffers + growth_step)
            new_size = pool.resize(target)
            logger.debug("Increased buffer pool capacity to %d buffers", new_size)

    def _process_batch_chunk(
        self,
        files: list[Path],
        stages: list[PipelineStage],
    ) -> list[ProcessingResult]:
        """Process one adaptive batch chunk while preserving file order."""
        if stages:
            return [self._process_file_staged(path, stages) for path in files]
        return [self._process_file_legacy(path) for path in files]

    # ------------------------------------------------------------------
    # Stage-based processing (new)
    # ------------------------------------------------------------------

    def _run_stages(self, context: StageContext, stages: list[PipelineStage]) -> StageContext:
        """Run *context* through *stages*, stopping at the first error.

        Each stage is wrapped in a try/except so that an unexpected
        exception is recorded on the context rather than crashing the
        caller.  A stage returning ``None`` is treated as a failure.
        Already-failed contexts are passed through without re-running.

        Args:
            context: The pipeline context to thread through stages.
            stages: Ordered list of stages to execute.

        Returns:
            The final context after all stages have run (or after the
            first failure).
        """
        for stage in stages:
            if context.failed:
                break
            try:
                returned = stage.process(context)
            except Exception as exc:  # Intentional catch-all: stages are user-provided
                logger.exception("Stage %s raised for %s", stage.name, context.file_path)
                context.error = str(exc)
                break
            if returned is None:
                logger.error("Stage %s returned None for %s", stage.name, context.file_path)
                context.error = f"Stage {stage.name!r} returned None"
                break
            context = returned
        return context

    def _finalize_result(self, context: StageContext, start_time: float) -> ProcessingResult:
        """Convert a completed context into a ProcessingResult and update stats.

        Args:
            context: The final pipeline context after all stages ran.
            start_time: ``time.monotonic()`` timestamp from before stage
                execution began (used to compute ``duration_ms``).

        Returns:
            A :class:`ProcessingResult` reflecting the context state.
        """
        duration_ms = (time.monotonic() - start_time) * 1000
        processor_type = context.extra.get("analyzer.processor_type", ProcessorType.UNKNOWN)

        with self._stats_lock:
            self.stats.total_processed += 1
            self.stats.total_duration_ms += duration_ms
            if context.failed:
                self.stats.failed += 1
            else:
                self.stats.successful += 1

        self._notify(context.file_path, not context.failed)

        return ProcessingResult(
            file_path=context.file_path,
            success=not context.failed,
            category=context.category,
            destination=context.destination,
            duration_ms=duration_ms,
            error=context.error,
            processor_type=processor_type,
            dry_run=context.dry_run,
        )

    def _make_context(self, file_path: Path, trusted_root: Path | None = None) -> StageContext:
        """Create a fresh :class:`StageContext` for *file_path*.

        Centralises the ``dry_run`` derivation so all three entry points
        (``_process_file_staged``, the prefetch priming loop, and the
        prefetch fallback path) stay in sync.
        """
        return StageContext(
            file_path=file_path,
            dry_run=not self.config.should_move_files,
            trusted_root=trusted_root,
        )

    def _acquire_buffer(self, file_path: Path) -> bytearray | None:
        """Acquire a reusable buffer for processing *file_path*."""
        file_size = self._safe_file_size(file_path)
        pool = self.buffer_pool
        requested = max(pool.buffer_size, file_size)
        try:
            return pool.acquire(size=requested)
        except (MemoryError, RuntimeError, ValueError, TimeoutError):
            logger.warning("Failed to acquire buffer for %s", file_path, exc_info=True)
            return None

    def _release_buffer(self, file_path: Path, buffer: bytearray | None) -> None:
        """Release a previously acquired processing buffer, if any."""
        if buffer is None:
            return
        pool = self.buffer_pool
        try:
            pool.release(buffer)
        except (ValueError, RuntimeError):
            logger.warning("Failed to release buffer for %s", file_path, exc_info=True)

    def _process_file_staged(
        self, file_path: Path, stages: list[PipelineStage], trusted_root: Path | None = None
    ) -> ProcessingResult:
        """Run *file_path* through the configured stages."""
        start_time = time.monotonic()
        buffer = self._acquire_buffer(file_path)
        try:
            context = self._make_context(file_path, trusted_root=trusted_root)
            if buffer is not None:
                context.extra[_BUFFER_KEY] = buffer
            context = self._run_stages(context, stages)
            return self._finalize_result(context, start_time)
        finally:
            self._release_buffer(file_path, buffer)

    def _process_batch_prefetch(
        self, files: list[Path], stages: list[PipelineStage]
    ) -> list[ProcessingResult]:
        """Process a batch with I/O-compute overlap via the resource executor.

        The prefetch + I/O-compute-overlap loop moved to
        :meth:`ResourceAwareExecutor.run_prefetched_batch` in D2
        (WP-4.3, #1233). This thin wrapper preserves the orchestrator's
        historical ``process_batch`` entry point and contract while
        delegating the actual prefetch mechanics to the executor.

        The executor is driven with the orchestrator's collaborators
        (``_run_stages``, ``_make_context``, ``_finalize_result``) so
        stats accounting, dry-run derivation, and error semantics are
        unchanged. The orchestrator's resolved buffer pool is shared with
        the executor first so both sides acquire/release from one pool.

        Args:
            files: Ordered list of file paths to process.
            stages: Snapshot of the stage list taken by the caller.

        Returns:
            List of :class:`ProcessingResult` instances in the same
            order as *files*.
        """
        # Share the orchestrator's (possibly lazily-built) buffer pool with
        # the executor so prefetch acquire/release hits the same pool the
        # adaptive-batching path and existing tests inspect.
        self._resource_executor.buffer_pool = self.buffer_pool
        return self._resource_executor.run_prefetched_batch(
            files=files,
            stages=stages,
            run_stages=self._run_stages,
            make_context=self._make_context,
            finalize_result=self._finalize_result,
        )

    # ------------------------------------------------------------------
    # Legacy processing (backward compatible)
    # ------------------------------------------------------------------

    def _process_file_legacy(self, file_path: Path) -> ProcessingResult:
        """Original monolithic processing path."""
        start_time = time.monotonic()
        # Validate file exists
        if not file_path.exists():
            return ProcessingResult(
                file_path=file_path,
                success=False,
                error=f"File not found: {file_path}",
                dry_run=self.config.dry_run,
            )

        if not file_path.is_file():
            return ProcessingResult(
                file_path=file_path,
                success=False,
                error=f"Not a file: {file_path}",
                dry_run=self.config.dry_run,
            )

        # Check if extension is supported
        if not self.config.is_supported(file_path):
            duration_ms = (time.monotonic() - start_time) * 1000
            with self._stats_lock:
                self.stats.skipped += 1
            return ProcessingResult(
                file_path=file_path,
                success=False,
                error=f"Unsupported file extension: {file_path.suffix}",
                duration_ms=duration_ms,
                dry_run=self.config.dry_run,
            )

        # Route to processor
        processor_type = self.router.route(file_path)

        if processor_type == ProcessorType.UNKNOWN:
            duration_ms = (time.monotonic() - start_time) * 1000
            with self._stats_lock:
                self.stats.skipped += 1
            return ProcessingResult(
                file_path=file_path,
                success=False,
                error="No processor available for this file type",
                processor_type=processor_type,
                duration_ms=duration_ms,
                dry_run=self.config.dry_run,
            )

        # Get processor from pool
        processor = self.processor_pool.get_processor(processor_type)

        if processor is None:
            duration_ms = (time.monotonic() - start_time) * 1000
            with self._stats_lock:
                self.stats.failed += 1
            return ProcessingResult(
                file_path=file_path,
                success=False,
                error=f"Failed to initialize {processor_type.value} processor",
                processor_type=processor_type,
                duration_ms=duration_ms,
                dry_run=self.config.dry_run,
            )

        # Process the file
        try:
            result = self._process_with_processor(file_path, processor, processor_type)
            duration_ms = (time.monotonic() - start_time) * 1000

            # Build destination path
            category = result.get("category", "uncategorized")
            filename = result.get("filename", file_path.stem)
            destination = self.config.output_directory / category / f"{filename}{file_path.suffix}"

            # Organize file if configured
            if self.config.should_move_files:
                self._organize_file(file_path, destination)

            # Update stats
            with self._stats_lock:
                self.stats.total_processed += 1
                self.stats.successful += 1
                self.stats.total_duration_ms += duration_ms

            processing_result = ProcessingResult(
                file_path=file_path,
                success=True,
                category=category,
                destination=destination,
                duration_ms=duration_ms,
                processor_type=processor_type,
                dry_run=self.config.dry_run,
            )

            self._notify(file_path, True)
            return processing_result

        except Exception as e:  # Intentional catch-all: processor.process_file is user-provided
            duration_ms = (time.monotonic() - start_time) * 1000
            with self._stats_lock:
                self.stats.total_processed += 1
                self.stats.failed += 1
                self.stats.total_duration_ms += duration_ms

            logger.exception("Failed to process %s", file_path)

            self._notify(file_path, False)
            return ProcessingResult(
                file_path=file_path,
                success=False,
                error=str(e),
                processor_type=processor_type,
                duration_ms=duration_ms,
                dry_run=self.config.dry_run,
            )

    def _notify(self, file_path: Path, success: bool) -> None:
        """Fire the notification callback, swallowing exceptions."""
        if self.config.notification_callback is not None:
            try:
                self.config.notification_callback(file_path, success)
            except Exception:  # Intentional catch-all: callback is user-provided
                logger.exception("Notification callback failed for %s", file_path)

    def _process_with_processor(
        self,
        file_path: Path,
        processor: BaseProcessor,
        processor_type: ProcessorType,
    ) -> ProcessorResult:
        """Process a file and return normalised ``{category, filename}`` dict.

        Args:
            file_path: Path to the file to process.
            processor: The processor instance to use.
            processor_type: The type of processor (for logging).

        Returns:
            Dictionary with 'category' and 'filename' keys.

        Raises:
            RuntimeError: If the processor reports an error.
        """
        raw = processor.process_file(file_path)
        return normalize_processor_result(file_path, raw)

    def _organize_file(self, source: Path, destination: Path) -> None:
        """Move or copy a file to its destination.

        Creates the destination directory if needed.

        Args:
            source: Source file path.
            destination: Destination file path.
        """
        destination.parent.mkdir(parents=True, exist_ok=True)

        # Handle duplicate filenames
        final_dest = destination
        counter = 1
        while final_dest.exists():
            stem = destination.stem
            suffix = destination.suffix
            final_dest = destination.parent / f"{stem}_{counter}{suffix}"
            counter += 1

        safe_copy2(source, final_dest, self.config.output_directory)
        logger.info("Organized %s -> %s", source, final_dest)

    def _start_watch_mode(self) -> None:
        """Start the file monitor and watch thread."""
        from file_organizer.watcher import FileMonitor

        self._monitor = FileMonitor(config=self.config.watch_config)
        self._monitor.start()

        self._watch_thread = threading.Thread(
            target=self._watch_loop,
            name="pipeline-watcher",
            daemon=True,
        )
        self._watch_thread.start()
        logger.info("Watch mode started")

    def _watch_loop(self) -> None:
        """Background loop that polls the monitor for events and processes them.

        Uses a thread pool executor to process files without blocking
        the event loop.
        """
        while self._running and self._monitor is not None:
            try:
                events = self._monitor.get_events(max_size=self.config.max_concurrent)

                for event in events:
                    if event.is_directory:
                        continue

                    try:
                        # Find which watch directory this event's path lives
                        # under. ``trusted_root`` is resolved before use:
                        # SafeDir.open_root() refuses a symlinked root outright,
                        # so a configured watch directory that is itself a
                        # symlink (e.g. macOS /tmp -> /private/tmp) must be
                        # anchored on its real target, not the symlink path.
                        trusted_root = None
                        if self.config.watch_config and self.config.watch_config.watch_directories:
                            for d in self.config.watch_config.watch_directories:
                                try:
                                    event.path.relative_to(d)
                                    trusted_root = d.resolve()
                                    break
                                except ValueError:
                                    try:
                                        event.path.resolve().relative_to(d.resolve())
                                        trusted_root = d.resolve()
                                        break
                                    except ValueError:
                                        continue

                        # Submit to executor to avoid blocking the watch loop.
                        # Track the future so stop() can drain in-flight work
                        # before closing stage-owned resources.
                        if trusted_root is not None:
                            future = self._executor.submit(
                                self.process_file, event.path, trusted_root=trusted_root
                            )
                        else:
                            future = self._executor.submit(self.process_file, event.path)
                        with self._watch_futures_lock:
                            self._watch_futures.add(future)
                        # Register the discard outside the lock: if the future
                        # already completed, the callback fires inline here and
                        # would otherwise re-enter the non-reentrant lock.
                        future.add_done_callback(self._on_watch_future_done)
                    except (RuntimeError, OSError):
                        logger.exception("Error processing %s", event.path)

            except (RuntimeError, OSError):
                logger.exception("Error in watch loop")

            # Small sleep to avoid busy-waiting
            time.sleep(0.5)
