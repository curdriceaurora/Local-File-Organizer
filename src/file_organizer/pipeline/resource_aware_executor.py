"""Resource-aware execution primitives for the pipeline orchestrator.

Epic D.pipeline (hardening roadmap #157 — D2): the pre-D2 orchestrator
owned prefetch, memory limiting, and buffer-pool rebalancing inline
alongside stage routing. That mixed two concerns in one ~900-line class
and made the resource-handling surface hard to test in isolation.

This module extracts the resource-aware surface into a single class
that the orchestrator holds and delegates to. The orchestrator retains
stage management, the legacy routing path, watch-mode lifecycle, and
statistics; ``ResourceAwareExecutor`` owns:

- the shared :class:`~file_organizer.optimization.buffer_pool.BufferPool` (lazy init)
- buffer acquire/release per file
- memory-pressure-driven buffer-pool rebalancing
- the I/O + compute-overlap batch prefetch loop

The prefetch method takes its orchestrator-specific collaborators
(stage runner, context factory, result finalizer) as callbacks so the
executor stays agnostic of
:class:`~file_organizer.pipeline.orchestrator.ProcessingResult`
and the orchestrator's statistics.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import TypeVar

from file_organizer.interfaces.pipeline import PipelineStage, StageContext
from file_organizer.optimization.buffer_pool import BufferPool
from file_organizer.optimization.memory_limiter import MemoryLimiter
from file_organizer.optimization.resource_monitor import ResourceMonitor

logger = logging.getLogger(__name__)

# Key under which the per-file buffer is stashed on StageContext.extra —
# kept here so the orchestrator and executor share one source of truth.
BUFFER_KEY = "pipeline.buffer"

_ResultT = TypeVar("_ResultT")
# ``run_prefetched_batch`` internal: index → (future, submitted_at_monotonic)
_FutureMap = dict[int, tuple["Future[tuple[StageContext, bytearray | None]]", float]]


class ResourceAwareExecutor:
    """Owns prefetch + memory limiting + buffer rebalancing.

    Constructed once per
    :class:`~file_organizer.pipeline.orchestrator.PipelineOrchestrator`
    and held as a private attribute. All resource-dependent arguments that
    used to live on the orchestrator constructor are accepted here and
    stored for use by the prefetch and rebalance paths.

    Args:
        prefetch_depth: Number of files to prefetch ahead of the compute
            cursor. ``0`` disables prefetch entirely.
        prefetch_stages: Requested number of leading stages to run on the
            prefetch I/O thread pool. Current thread-safety caps this at
            effectively 1 — values > 1 log a warning and are treated as 1.
        memory_limiter: Optional gate; when ``check()`` returns ``False``
            no new prefetch futures are submitted until memory frees up.
        buffer_pool: Optional pre-built shared buffer pool. When ``None``,
            the pool is lazily built on first ``buffer_pool`` access.
        resource_monitor: Optional monitor used to measure current RSS
            and to drive :meth:`rebalance_buffer_pool`. Defaults to a
            fresh :class:`~file_organizer.optimization.resource_monitor.ResourceMonitor`.
        memory_pressure_threshold_percent: Threshold forwarded to
            ``resource_monitor.should_evict`` when deciding whether to
            shrink the pool. Must be in ``[0, 100]``.
    """

    def __init__(
        self,
        *,
        prefetch_depth: int = 2,
        prefetch_stages: int = 1,
        memory_limiter: MemoryLimiter | None = None,
        buffer_pool: BufferPool | None = None,
        resource_monitor: ResourceMonitor | None = None,
        memory_pressure_threshold_percent: float = 85.0,
    ) -> None:
        """See the class docstring for argument semantics."""
        if not 0.0 <= memory_pressure_threshold_percent <= 100.0:
            raise ValueError(
                "memory_pressure_threshold_percent must be between 0 and 100, "
                f"got {memory_pressure_threshold_percent}"
            )

        self._prefetch_depth = max(0, prefetch_depth)
        self._prefetch_stages = max(0, prefetch_stages)
        self._memory_limiter = memory_limiter
        self._buffer_pool: BufferPool | None = buffer_pool
        self._resource_monitor = resource_monitor or ResourceMonitor()
        self._memory_pressure_threshold_percent = memory_pressure_threshold_percent
        self._pool_init_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Read-only accessors (kept explicit; the orchestrator forwards these
    # to callers that inspect its historical public attributes).
    # ------------------------------------------------------------------

    @property
    def prefetch_depth(self) -> int:
        """Number of files to prefetch ahead of the compute cursor."""
        return self._prefetch_depth

    @property
    def prefetch_stages(self) -> int:
        """Requested count of leading I/O stages (effectively capped at 1)."""
        return self._prefetch_stages

    @property
    def memory_pressure_threshold_percent(self) -> float:
        """Threshold forwarded to ``ResourceMonitor.should_evict``."""
        return self._memory_pressure_threshold_percent

    @property
    def buffer_pool(self) -> BufferPool:
        """Return the shared buffer pool, lazily creating one if needed."""
        if self._buffer_pool is None:
            with self._pool_init_lock:
                if self._buffer_pool is None:
                    self._buffer_pool = BufferPool()
        return self._buffer_pool

    @buffer_pool.setter
    def buffer_pool(self, pool: BufferPool) -> None:
        """Adopt an externally-owned buffer pool.

        Used by :class:`~file_organizer.pipeline.orchestrator.PipelineOrchestrator`,
        which keeps its own resolved pool (its adaptive-batching helpers and the
        existing tests inspect it directly) and shares that single pool with the
        executor so the prefetch path acquires/releases from the same instance.
        """
        with self._pool_init_lock:
            self._buffer_pool = pool

    # ------------------------------------------------------------------
    # Resource probes
    # ------------------------------------------------------------------

    def safe_file_size(self, file_path: Path) -> int:
        """Return file size in bytes, or ``0`` when unavailable."""
        try:
            return file_path.stat().st_size
        except OSError:
            logger.debug("Unable to stat %s for adaptive batching", file_path, exc_info=True)
            return 0

    def safe_current_rss(self) -> int:
        """Return current process RSS in bytes, or ``0`` when unavailable."""
        try:
            return self._resource_monitor.get_memory_usage().rss
        except (OSError, RuntimeError, ValueError):
            logger.debug("Unable to read current RSS for adaptive batching", exc_info=True)
            return 0

    # ------------------------------------------------------------------
    # Buffer pool management
    # ------------------------------------------------------------------

    def rebalance_buffer_pool(self) -> None:
        """Resize the buffer pool in response to memory pressure or utilization.

        - Under memory pressure (monitor says ``should_evict``): shrink
          toward ``max(initial_buffers, in_use_count)``.
        - Under high utilization (``>= 0.9``) and room to grow: grow by
          ``max(1, initial_buffers // 2)``, clamped to ``max_buffers``.
        - Otherwise: no-op.

        If no buffer pool has been built yet, the call is a true no-op —
        it does *not* lazily build one (that would pin memory under
        pressure, which is the opposite of what we want).
        """
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

    def acquire_buffer(self, file_path: Path) -> bytearray | None:
        """Acquire a reusable buffer sized for *file_path*."""
        file_size = self.safe_file_size(file_path)
        pool = self.buffer_pool
        requested = max(pool.buffer_size, file_size)
        try:
            return pool.acquire(size=requested)
        except (MemoryError, RuntimeError, ValueError, TimeoutError):
            logger.warning("Failed to acquire buffer for %s", file_path, exc_info=True)
            return None

    def release_buffer(self, file_path: Path, buffer: bytearray | None) -> None:
        """Release a previously acquired buffer; ``None`` is a safe no-op."""
        if buffer is None:
            return
        pool = self.buffer_pool
        try:
            pool.release(buffer)
        except (ValueError, RuntimeError):
            logger.warning("Failed to release buffer for %s", file_path, exc_info=True)

    # ------------------------------------------------------------------
    # Prefetched batch execution
    # ------------------------------------------------------------------

    def run_prefetched_batch(
        self,
        *,
        files: list[Path],
        stages: list[PipelineStage],
        run_stages: Callable[[StageContext, list[PipelineStage]], StageContext],
        make_context: Callable[[Path], StageContext],
        finalize_result: Callable[[StageContext, float], _ResultT],
    ) -> list[_ResultT]:
        """Run *files* through *stages* with I/O-compute overlap.

        Splits *stages* at ``effective_prefetch_stages`` (capped at 1
        for thread-safety — shared components such as ``ProcessorPool``
        are not safe for concurrent initialisation). The leading I/O
        stages are submitted to a dedicated thread pool for upcoming
        files while the compute stages run on the calling thread for
        the current file.

        At most ``prefetch_depth`` I/O futures are outstanding at any
        time. If a ``memory_limiter`` was configured, no new futures
        are opened when ``limiter.check()`` returns ``False``.

        An error in a prefetched file's I/O stages does not crash the
        batch; a failed
        :class:`~file_organizer.interfaces.pipeline.StageContext` is
        returned and the compute stages still run (they short-circuit
        on ``context.failed``).

        Per-file timing starts at submission for prefetched files and
        at the inline ``_run_io`` call for files that fall through to
        the sequential path.

        Args:
            files: Ordered list of file paths to process.
            stages: Snapshot of the stage list taken by the caller.
            run_stages: Orchestrator callback — given a context and a
                sub-list of stages, returns the context after running
                them, recording any error on the context itself.
            make_context: Orchestrator callback — builds a fresh
                :class:`StageContext` for a given file path.
            finalize_result: Orchestrator callback — converts a
                finished context + start time into the orchestrator's
                result type and updates statistics.

        Returns:
            List of finalized results in the same order as *files*.
        """
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
        # ``prefetch_depth == 0`` or single-file batches: run sequentially.
        effective_depth = max(self._prefetch_depth, 1)

        futures: _FutureMap = {}
        results: list[_ResultT] = []

        with ThreadPoolExecutor(max_workers=effective_depth) as io_exec:
            if self._prefetch_depth > 0:
                self._prime_prefetch_queue(
                    futures, io_exec, files, io_stages, run_stages, make_context
                )

            for i in range(len(files)):
                if self._prefetch_depth > 0:
                    next_i = i + self._prefetch_depth
                    if next_i < len(files) and next_i not in futures:
                        self._try_enqueue(
                            next_i, futures, io_exec, files, io_stages, run_stages, make_context
                        )

                ctx, buffer, start_time = self._resolve_context(
                    i, futures, files, io_stages, run_stages, make_context
                )

                try:
                    ctx = run_stages(ctx, compute_stages)
                    results.append(finalize_result(ctx, start_time))
                finally:
                    self.release_buffer(files[i], buffer)
                    ctx.extra.pop(BUFFER_KEY, None)

        return results

    # ------------------------------------------------------------------
    # Helpers for ``run_prefetched_batch`` — private, but promoted to
    # methods (not nested closures) so the top-level method stays under
    # the cyclomatic complexity cap and each piece is unit-testable.
    # ------------------------------------------------------------------

    def _run_io_for_file(
        self,
        file_path: Path,
        io_stages: list[PipelineStage],
        run_stages: Callable[[StageContext, list[PipelineStage]], StageContext],
        make_context: Callable[[Path], StageContext],
    ) -> tuple[StageContext, bytearray | None]:
        """Acquire a buffer, run the I/O stages, and return the context.

        Releases the buffer on any stage error so the pool never leaks.
        """
        buffer = self.acquire_buffer(file_path)
        try:
            ctx = make_context(file_path)
            if buffer is not None:
                ctx.extra[BUFFER_KEY] = buffer
            io_ctx = run_stages(ctx, io_stages)
            if buffer is not None:
                io_ctx.extra[BUFFER_KEY] = buffer
            return io_ctx, buffer
        except Exception:  # Intentional catch-all: ensures buffer cleanup on any stage error
            self.release_buffer(file_path, buffer)
            raise

    def _try_enqueue(
        self,
        idx: int,
        futures: _FutureMap,
        io_exec: ThreadPoolExecutor,
        files: list[Path],
        io_stages: list[PipelineStage],
        run_stages: Callable[[StageContext, list[PipelineStage]], StageContext],
        make_context: Callable[[Path], StageContext],
    ) -> None:
        """Submit file *idx* for prefetch unless the memory limiter refuses."""
        if self._memory_limiter is not None and not self._memory_limiter.check():
            logger.warning("Prefetch skipped for index %d due to memory limit", idx)
            return
        future = io_exec.submit(
            self._run_io_for_file, files[idx], io_stages, run_stages, make_context
        )
        futures[idx] = (future, time.monotonic())

    def _prime_prefetch_queue(
        self,
        futures: _FutureMap,
        io_exec: ThreadPoolExecutor,
        files: list[Path],
        io_stages: list[PipelineStage],
        run_stages: Callable[[StageContext, list[PipelineStage]], StageContext],
        make_context: Callable[[Path], StageContext],
    ) -> None:
        """Seed the prefetch queue with the first ``prefetch_depth`` files."""
        for i in range(min(self._prefetch_depth, len(files))):
            self._try_enqueue(i, futures, io_exec, files, io_stages, run_stages, make_context)
            if i not in futures:
                break  # limiter refused — stop priming

    def _resolve_context(
        self,
        idx: int,
        futures: _FutureMap,
        files: list[Path],
        io_stages: list[PipelineStage],
        run_stages: Callable[[StageContext, list[PipelineStage]], StageContext],
        make_context: Callable[[Path], StageContext],
    ) -> tuple[StageContext, bytearray | None, float]:
        """Return ``(ctx, buffer, start_time)`` for file *idx*.

        Uses a completed prefetch future when available; falls back to
        inline I/O. Any exception from either path is recorded on a
        fresh failed context so the batch loop keeps moving.
        """
        if idx in futures:
            future, start_time = futures.pop(idx)
            try:
                ctx, buffer = future.result()
                return ctx, buffer, start_time
            except Exception as exc:  # Intentional catch-all: future can raise any stage error
                logger.warning("Prefetch future failed for %s: %s", files[idx], exc, exc_info=True)
                ctx = make_context(files[idx])
                ctx.error = str(exc)
                return ctx, None, start_time
        start_time = time.monotonic()
        try:
            ctx, buffer = self._run_io_for_file(files[idx], io_stages, run_stages, make_context)
            return ctx, buffer, start_time
        except Exception as exc:  # Intentional catch-all: inline I/O can raise any stage error
            logger.warning("Inline I/O stage failed for %s: %s", files[idx], exc, exc_info=True)
            ctx = make_context(files[idx])
            ctx.error = str(exc)
            return ctx, None, start_time
