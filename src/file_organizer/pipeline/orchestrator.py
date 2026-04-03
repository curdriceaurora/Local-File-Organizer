"""Pipeline orchestrator for auto-organization.

Coordinates file discovery (via watcher or batch), routing, processing,
and organization into a cohesive pipeline.  Supports composable stages
via :class:`~file_organizer.interfaces.PipelineStage`.
"""

from __future__ import annotations

import logging
import shutil
import threading
import time
from collections.abc import Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from file_organizer.interfaces.pipeline import PipelineStage, StageContext
from file_organizer.optimization.batch_sizer import AdaptiveBatchSizer
from file_organizer.optimization.buffer_pool import BufferPool
from file_organizer.optimization.memory_limiter import MemoryLimiter
from file_organizer.optimization.resource_monitor import ResourceMonitor

from .config import PipelineConfig
from .processor_pool import (
    BaseProcessor,
    ProcessorPool,
    ProcessorResult,
    normalize_processor_result,
)
from .router import FileRouter, ProcessorType

logger = logging.getLogger(__name__)
_BUFFER_KEY = "pipeline.buffer"


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

        self._prefetch_depth = max(0, prefetch_depth)
        self._prefetch_stages = max(0, prefetch_stages)
        self._memory_limiter = memory_limiter
        self._batch_sizer = batch_sizer or AdaptiveBatchSizer()
        self._buffer_pool: BufferPool | None = buffer_pool
        self._resource_monitor = resource_monitor or ResourceMonitor()
        self._memory_pressure_threshold_percent = memory_pressure_threshold_percent

        self._running = False
        self._lock = threading.Lock()
        self._monitor: Any = None
        self._watch_thread: threading.Thread | None = None
        self._executor = ThreadPoolExecutor(
            max_workers=self.config.max_concurrent,
        )

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
            with self._lock:
                if self._buffer_pool is None:
                    self._buffer_pool = BufferPool()
        return self._buffer_pool

    def set_stages(self, stages: Sequence[PipelineStage]) -> None:
        """Replace the stage list at runtime (thread-safe).

        Args:
            stages: New ordered list of pipeline stages.
        """
        with self._lock:
            self._stages = list(stages)

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
            if not self._running:
                return

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

            # Clean up processors
            self.processor_pool.cleanup()

            logger.info("Pipeline stopped")

    # ------------------------------------------------------------------
    # Processing
    # ------------------------------------------------------------------

    def process_file(self, file_path: Path) -> ProcessingResult:
        """Process a single file through the pipeline.

        If ``stages`` were provided, each stage is executed in order.
        Otherwise, falls back to the legacy router/pool path.

        Args:
            file_path: Path to the file to process.

        Returns:
            ProcessingResult with processing outcome and metadata.
        """
        stages = self._stages  # snapshot once; set_stages() may replace list concurrently
        if stages:
            return self._process_file_staged(file_path, stages)
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

        if stages and self._prefetch_depth > 0 and self._prefetch_stages > 0 and len(files) > 1:
            # Keep prefetch behavior deterministic (Issue #713 contracts) while
            # still applying proactive memory feedback to the shared buffer pool.
            results = self._process_batch_prefetch(files, stages)
            self._rebalance_buffer_pool()
            return results

        results: list[ProcessingResult] = []
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

    def _make_context(self, file_path: Path) -> StageContext:
        """Create a fresh :class:`StageContext` for *file_path*.

        Centralises the ``dry_run`` derivation so all three entry points
        (``_process_file_staged``, the prefetch priming loop, and the
        prefetch fallback path) stay in sync.
        """
        return StageContext(
            file_path=file_path,
            dry_run=not self.config.should_move_files,
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
        self, file_path: Path, stages: list[PipelineStage]
    ) -> ProcessingResult:
        """Run *file_path* through the configured stages."""
        start_time = time.monotonic()
        buffer = self._acquire_buffer(file_path)
        try:
            context = self._make_context(file_path)
            if buffer is not None:
                context.extra[_BUFFER_KEY] = buffer
            context = self._run_stages(context, stages)
            return self._finalize_result(context, start_time)
        finally:
            self._release_buffer(file_path, buffer)

    def _process_batch_prefetch(
        self, files: list[Path], stages: list[PipelineStage]
    ) -> list[ProcessingResult]:
        """Process a batch with I/O-compute overlap via a prefetch queue.

        Splits *stages* at ``effective_prefetch_stages`` (capped at 1 for
        thread-safety — shared components such as ``ProcessorPool`` are not
        safe for concurrent initialisation): the I/O stages are submitted to
        a dedicated :class:`~concurrent.futures.ThreadPoolExecutor` for
        upcoming files while the compute stages run on the calling thread for
        the current file.

        At most ``self._prefetch_depth`` I/O futures are outstanding at
        any time.  If a ``memory_limiter`` is configured, no new futures
        are opened when ``limiter.check()`` returns *False*.

        An error in a prefetched file's I/O stages does not crash the
        batch; a failed :class:`~file_organizer.interfaces.StageContext`
        is returned and the compute stages are still attempted (they will
        short-circuit on ``context.failed``).

        Per-file ``ProcessingResult.duration_ms`` is measured from the
        moment the I/O future is *submitted* (not when it completes), so
        the reported wall-clock time covers prefetched I/O latency as well
        as compute time.  For files that fall through to the sequential
        inline path (no outstanding future), timing starts just before
        ``_run_io`` is called.

        Args:
            files: Ordered list of file paths to process.
            stages: Snapshot of the stage list taken by the caller.

        Returns:
            List of :class:`ProcessingResult` instances in the same
            order as *files*.
        """
        # Cap at 1: stages beyond the first (e.g. AnalyzerStage) rely on
        # shared components (ProcessorPool) that are not thread-safe for
        # concurrent initialisation.
        effective_prefetch_stages = min(self._prefetch_stages, 1)
        if self._prefetch_stages > 1:
            logger.warning(
                "prefetch_stages=%d is not fully supported; "
                "capping effective prefetch stages to %d for thread-safety",
                self._prefetch_stages,
                effective_prefetch_stages,
            )
        io_stages = stages[:effective_prefetch_stages]
        compute_stages = stages[effective_prefetch_stages:]

        def _run_io(idx: int) -> tuple[StageContext, bytearray | None]:
            file_path = files[idx]
            buffer = self._acquire_buffer(file_path)
            try:
                ctx = self._make_context(file_path)
                if buffer is not None:
                    ctx.extra[_BUFFER_KEY] = buffer
                io_ctx = self._run_stages(ctx, io_stages)
                if buffer is not None:
                    io_ctx.extra[_BUFFER_KEY] = buffer
                return io_ctx, buffer
            except Exception:  # Intentional catch-all: ensures buffer cleanup on any stage error
                self._release_buffer(file_path, buffer)
                raise

        futures: dict[int, tuple[Future[tuple[StageContext, bytearray | None]], float]] = {}
        results: list[ProcessingResult] = []

        with ThreadPoolExecutor(max_workers=self._prefetch_depth) as io_exec:
            # Prime the queue with the first prefetch_depth files.
            for i in range(min(self._prefetch_depth, len(files))):
                if self._memory_limiter is not None and not self._memory_limiter.check():
                    logger.warning("Prefetch depth capped at %d due to memory limit", i)
                    break
                futures[i] = (io_exec.submit(_run_io, i), time.monotonic())

            for i in range(len(files)):
                # Enqueue the next lookahead file as we consume one slot.
                next_i = i + self._prefetch_depth
                if next_i < len(files) and next_i not in futures:
                    if self._memory_limiter is None or self._memory_limiter.check():
                        futures[next_i] = (io_exec.submit(_run_io, next_i), time.monotonic())

                # Retrieve the prefetched I/O context (or compute inline).
                if i in futures:
                    future, start_time = futures.pop(i)
                    try:
                        ctx, buffer = future.result()
                    except (
                        Exception
                    ) as exc:  # Intentional catch-all: future can raise any stage error
                        logger.warning(
                            "Prefetch future failed for %s: %s",
                            files[i],
                            exc,
                            exc_info=True,
                        )
                        ctx = self._make_context(files[i])
                        ctx.error = str(exc)
                        buffer = None
                else:
                    start_time = time.monotonic()
                    ctx, buffer = _run_io(i)

                # Run compute stages on the calling thread.
                try:
                    ctx = self._run_stages(ctx, compute_stages)
                    results.append(self._finalize_result(ctx, start_time))
                finally:
                    self._release_buffer(files[i], buffer)
                    ctx.extra.pop(_BUFFER_KEY, None)

        return results

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

        shutil.copy2(source, final_dest)
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
                        # Submit to executor to avoid blocking the watch loop
                        self._executor.submit(self.process_file, event.path)
                    except (RuntimeError, OSError):
                        logger.exception("Error processing %s", event.path)

            except (RuntimeError, OSError):
                logger.exception("Error in watch loop")

            # Small sleep to avoid busy-waiting
            time.sleep(0.5)
