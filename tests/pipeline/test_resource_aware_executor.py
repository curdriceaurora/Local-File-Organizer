"""Tests for ``ResourceAwareExecutor`` (D2 seam, hardening roadmap §3 D).

The executor owns prefetch, memory limiting, and buffer rebalancing —
concerns the orchestrator previously held inline. These tests exercise
each responsibility in isolation so the seam is regression-resistant
and integration-coverage-preserving.

See ``test_orchestrator*.py`` for the integrated orchestrator-level
behaviour; this file targets the executor contract directly.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from file_organizer.interfaces.pipeline import PipelineStage, StageContext
from file_organizer.optimization.buffer_pool import BufferPool
from file_organizer.optimization.memory_limiter import MemoryLimiter
from file_organizer.optimization.resource_monitor import MemoryInfo
from file_organizer.pipeline.resource_aware_executor import ResourceAwareExecutor

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class _StageResult:
    """Minimal shape returned by ``finalize_result`` callback in tests."""

    file_path: Path
    success: bool
    duration_ms: float


class _RecordingStage:
    """PipelineStage test double that records every ``process`` call.

    ``test_preserves_file_order`` relies on ``run_prefetched_batch``
    assembling results in input-index order rather than completion
    order; no artificial delay is needed. The project's C1 CI
    guardrail forbids ``time.sleep`` in changed tests.
    """

    name = "recorder"

    def __init__(self, label: str) -> None:
        self.label = label
        self.calls: list[Path] = []

    def process(self, context: StageContext) -> StageContext:
        self.calls.append(context.file_path)
        context.extra.setdefault("stages_seen", []).append(self.label)
        return context


def _make_context(file_path: Path) -> StageContext:
    return StageContext(file_path=file_path, dry_run=True)


def _run_stages(context: StageContext, stages: list[PipelineStage]) -> StageContext:
    """Trivial stage runner — matches the orchestrator's semantics for tests."""
    for stage in stages:
        if context.failed:
            break
        returned = stage.process(context)
        if returned is None:
            context.error = f"Stage {stage.name!r} returned None"
            break
        context = returned
    return context


def _finalize_result(context: StageContext, start_time: float) -> _StageResult:
    duration_ms = (time.monotonic() - start_time) * 1000
    return _StageResult(
        file_path=context.file_path,
        success=not context.failed,
        duration_ms=duration_ms,
    )


# ---------------------------------------------------------------------------
# Unit tests: construction + parameter validation
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.ci
class TestConstruction:
    def test_accepts_resource_dependencies(self) -> None:
        limiter = MagicMock(spec=MemoryLimiter)
        pool = BufferPool()
        monitor = MagicMock()
        executor = ResourceAwareExecutor(
            prefetch_depth=3,
            prefetch_stages=1,
            memory_limiter=limiter,
            buffer_pool=pool,
            resource_monitor=monitor,
            memory_pressure_threshold_percent=75.0,
        )
        assert executor.prefetch_depth == 3
        assert executor.prefetch_stages == 1
        assert executor.buffer_pool is pool
        assert executor.memory_pressure_threshold_percent == 75.0

    def test_clamps_negative_prefetch_to_zero(self) -> None:
        executor = ResourceAwareExecutor(prefetch_depth=-5, prefetch_stages=-1)
        assert executor.prefetch_depth == 0
        assert executor.prefetch_stages == 0

    def test_rejects_out_of_range_memory_threshold(self) -> None:
        with pytest.raises(ValueError, match="between 0 and 100"):
            ResourceAwareExecutor(memory_pressure_threshold_percent=150.0)
        with pytest.raises(ValueError, match="between 0 and 100"):
            ResourceAwareExecutor(memory_pressure_threshold_percent=-1.0)

    def test_buffer_pool_lazily_created_when_none(self) -> None:
        executor = ResourceAwareExecutor()
        # Access triggers lazy creation.
        pool = executor.buffer_pool
        assert isinstance(pool, BufferPool)
        # Second access returns the same pool (not a fresh one).
        assert executor.buffer_pool is pool


# ---------------------------------------------------------------------------
# Unit tests: buffer acquire / release
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.ci
class TestBufferAcquireRelease:
    def test_acquires_buffer_sized_for_file(self, tmp_path: Path) -> None:
        f = tmp_path / "data.bin"
        f.write_bytes(b"x" * 4096)
        pool = BufferPool(buffer_size=1024, initial_buffers=1, max_buffers=2)
        executor = ResourceAwareExecutor(buffer_pool=pool)

        buffer = executor.acquire_buffer(f)

        assert buffer is not None
        assert len(buffer) >= 4096

    def test_release_returns_buffer_to_pool(self, tmp_path: Path) -> None:
        f = tmp_path / "data.bin"
        f.write_bytes(b"x" * 512)
        pool = BufferPool(buffer_size=1024, initial_buffers=1, max_buffers=2)
        executor = ResourceAwareExecutor(buffer_pool=pool)

        before_in_use = pool.in_use_count
        buffer = executor.acquire_buffer(f)
        assert pool.in_use_count == before_in_use + 1
        executor.release_buffer(f, buffer)
        assert pool.in_use_count == before_in_use

    def test_release_none_is_noop(self, tmp_path: Path) -> None:
        executor = ResourceAwareExecutor()
        # Must not raise; must not disturb the pool.
        executor.release_buffer(tmp_path / "nope", None)

    def test_missing_file_yields_safe_zero_size(self, tmp_path: Path) -> None:
        missing = tmp_path / "nonexistent"
        executor = ResourceAwareExecutor()
        assert executor.safe_file_size(missing) == 0


# ---------------------------------------------------------------------------
# Unit tests: buffer pool rebalancing
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.ci
class TestRebalanceBufferPool:
    def test_no_op_when_no_pool(self) -> None:
        monitor = MagicMock()
        executor = ResourceAwareExecutor(resource_monitor=monitor, buffer_pool=None)
        # No buffer pool access has happened; calling rebalance must not
        # lazily build one.
        executor.rebalance_buffer_pool()
        monitor.should_evict.assert_not_called()

    def test_shrinks_pool_under_memory_pressure(self) -> None:
        pool = BufferPool(initial_buffers=2, max_buffers=8)
        # Grow the pool first so there's room to shrink.
        pool.resize(8)
        assert pool.total_buffers == 8
        monitor = MagicMock()
        monitor.should_evict.return_value = True
        executor = ResourceAwareExecutor(
            buffer_pool=pool,
            resource_monitor=monitor,
            memory_pressure_threshold_percent=80.0,
        )
        executor.rebalance_buffer_pool()
        monitor.should_evict.assert_called_once_with(threshold_percent=80.0)
        assert pool.total_buffers <= 2 + pool.in_use_count

    def test_grows_pool_at_high_utilization(self) -> None:
        pool = BufferPool(initial_buffers=2, max_buffers=8)
        # Acquire buffers to push utilization to 100% (forces >= 0.9).
        b1 = pool.acquire()
        b2 = pool.acquire()
        assert pool.utilization >= 0.9
        monitor = MagicMock()
        monitor.should_evict.return_value = False
        executor = ResourceAwareExecutor(
            buffer_pool=pool,
            resource_monitor=monitor,
        )
        before = pool.total_buffers
        executor.rebalance_buffer_pool()
        assert pool.total_buffers > before
        # Clean up acquired buffers.
        pool.release(b1)
        pool.release(b2)

    def test_swallows_should_evict_exception(self) -> None:
        pool = BufferPool()
        monitor = MagicMock()
        monitor.should_evict.side_effect = OSError("sysfs blip")
        executor = ResourceAwareExecutor(buffer_pool=pool, resource_monitor=monitor)
        # Must not raise — logs and returns.
        executor.rebalance_buffer_pool()


# ---------------------------------------------------------------------------
# Unit tests: prefetched batch execution
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.ci
class TestRunPrefetchedBatch:
    def test_single_stage_runs_each_file_once(self, tmp_path: Path) -> None:
        files = [tmp_path / f"f{i}.txt" for i in range(3)]
        for f in files:
            f.write_text("x")
        stage = _RecordingStage("io")
        executor = ResourceAwareExecutor(prefetch_depth=2, prefetch_stages=1)

        results = executor.run_prefetched_batch(
            files=files,
            stages=[stage],
            run_stages=_run_stages,
            make_context=_make_context,
            finalize_result=_finalize_result,
        )

        assert [r.file_path for r in results] == files
        assert all(r.success for r in results)
        assert sorted(stage.calls) == sorted(files)
        assert len(stage.calls) == len(files)

    def test_caps_prefetch_stages_at_one(self, tmp_path: Path) -> None:
        files = [tmp_path / f"f{i}.txt" for i in range(2)]
        for f in files:
            f.write_text("x")
        io_stage = _RecordingStage("io")
        compute_stage = _RecordingStage("compute")
        executor = ResourceAwareExecutor(prefetch_depth=2, prefetch_stages=5)

        results = executor.run_prefetched_batch(
            files=files,
            stages=[io_stage, compute_stage],
            run_stages=_run_stages,
            make_context=_make_context,
            finalize_result=_finalize_result,
        )

        # Both stages run for both files; prefetch_stages=5 is clamped to 1
        # but compute stage still runs on the calling thread.
        assert len(io_stage.calls) == 2
        assert len(compute_stage.calls) == 2
        assert all(r.success for r in results)

    def test_preserves_file_order(self, tmp_path: Path) -> None:
        # Results must come back in input-index order regardless of future
        # completion order from the prefetch thread pool. ``prefetch_depth=3``
        # means up to three files have outstanding I/O futures at any time —
        # the loop consumes them in input order, not completion order.
        files = [tmp_path / f"f{i}.txt" for i in range(4)]
        for f in files:
            f.write_text("x")
        stage = _RecordingStage("io")
        executor = ResourceAwareExecutor(prefetch_depth=3, prefetch_stages=1)

        results = executor.run_prefetched_batch(
            files=files,
            stages=[stage],
            run_stages=_run_stages,
            make_context=_make_context,
            finalize_result=_finalize_result,
        )

        assert [r.file_path for r in results] == files
        assert stage.calls == files or sorted(stage.calls) == sorted(files)

    def test_respects_memory_limiter(self, tmp_path: Path) -> None:
        files = [tmp_path / f"f{i}.txt" for i in range(4)]
        for f in files:
            f.write_text("x")
        stage = _RecordingStage("io")
        limiter = MagicMock(spec=MemoryLimiter)
        # Deny every check — forces sequential inline fallback.
        limiter.check.return_value = False
        executor = ResourceAwareExecutor(
            prefetch_depth=2,
            prefetch_stages=1,
            memory_limiter=limiter,
        )

        results = executor.run_prefetched_batch(
            files=files,
            stages=[stage],
            run_stages=_run_stages,
            make_context=_make_context,
            finalize_result=_finalize_result,
        )

        assert len(results) == len(files)
        assert all(r.success for r in results)
        # Every file must have traversed the inline fallback — the stage
        # ran once per file exactly. (``limiter.check.called`` alone would
        # pass even if the executor silently dropped files.)
        assert sorted(stage.calls) == sorted(files)
        assert len(stage.calls) == len(files)
        # Priming attempts one enqueue, breaks on denial; the main loop
        # then attempts one lookahead per iteration while the index is
        # in range (len(files) - prefetch_depth attempts total). For
        # len=4, prefetch_depth=2 that's 1 (prime) + 2 (lookahead) = 3.
        # ``>= 2`` is the minimum viable signal: priming + at least one
        # lookahead enforcement. Lower would mean the limiter was never
        # actually enforced per file.
        assert limiter.check.call_count >= 2

    def test_stage_error_surfaces_on_context(self, tmp_path: Path) -> None:
        files = [tmp_path / "f.txt"]
        files[0].write_text("x")

        class _Explode:
            name = "explode"

            def process(self, context: StageContext) -> StageContext:
                raise RuntimeError("boom")

        # Use a real BufferPool so buffer leak-safety on stage error is pinned:
        # a stage that explodes must still release every acquired buffer.
        pool = BufferPool(buffer_size=64, initial_buffers=2, max_buffers=4)
        executor = ResourceAwareExecutor(prefetch_depth=1, prefetch_stages=1, buffer_pool=pool)
        results = executor.run_prefetched_batch(
            files=files,
            stages=[_Explode()],
            run_stages=_run_stages,
            make_context=_make_context,
            finalize_result=_finalize_result,
        )
        # Executor must not propagate the error — the batch should complete
        # and the failing file surfaces via ``success=False``.
        assert len(results) == 1
        assert results[0].success is False
        # No buffer leaked despite the stage error.
        assert pool.in_use_count == 0


# ---------------------------------------------------------------------------
# Integration tests: executor + real pool + real resource monitor
#
# These tests guarantee that the D2 extraction does not drop integration
# coverage of the resource-aware surface when orchestrator.py delegates
# to this class.
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestResourceAwareExecutorIntegration:
    def test_end_to_end_prefetch_with_real_pool(self, tmp_path: Path) -> None:
        """Full prefetch path with a real BufferPool + real stages."""
        files = [tmp_path / f"doc_{i}.txt" for i in range(4)]
        for i, f in enumerate(files):
            f.write_text(f"content {i}" * 20)
        stage = _RecordingStage("io")
        pool = BufferPool(buffer_size=256, initial_buffers=2, max_buffers=6)
        executor = ResourceAwareExecutor(
            prefetch_depth=2,
            prefetch_stages=1,
            buffer_pool=pool,
        )

        results = executor.run_prefetched_batch(
            files=files,
            stages=[stage],
            run_stages=_run_stages,
            make_context=_make_context,
            finalize_result=_finalize_result,
        )

        assert [r.file_path for r in results] == files
        assert all(r.success for r in results)
        assert len(stage.calls) == len(files)

    def test_rebalance_grows_under_utilization_and_shrinks_on_pressure(self) -> None:
        pool = BufferPool(initial_buffers=2, max_buffers=8)
        monitor = MagicMock()
        executor = ResourceAwareExecutor(
            buffer_pool=pool,
            resource_monitor=monitor,
            memory_pressure_threshold_percent=85.0,
        )

        # Phase 1: drive utilization high; monitor reports no pressure.
        b1, b2 = pool.acquire(), pool.acquire()
        monitor.should_evict.return_value = False
        before = pool.total_buffers
        executor.rebalance_buffer_pool()
        after_growth = pool.total_buffers
        assert after_growth > before

        # Phase 2: release buffers and flip pressure to True.
        pool.release(b1)
        pool.release(b2)
        monitor.should_evict.return_value = True
        executor.rebalance_buffer_pool()
        after_shrink = pool.total_buffers
        assert after_shrink <= after_growth

    def test_safe_current_rss_reads_monitor(self) -> None:
        monitor = MagicMock()
        monitor.get_memory_usage.return_value = MemoryInfo(
            rss=1024 * 1024 * 100,
            vms=1024 * 1024 * 200,
            percent=12.5,
        )
        executor = ResourceAwareExecutor(resource_monitor=monitor)

        rss = executor.safe_current_rss()

        assert rss == 1024 * 1024 * 100
        monitor.get_memory_usage.assert_called_once()

    def test_safe_current_rss_swallows_monitor_error(self) -> None:
        monitor = MagicMock()
        monitor.get_memory_usage.side_effect = OSError("proc vanished")
        executor = ResourceAwareExecutor(resource_monitor=monitor)
        assert executor.safe_current_rss() == 0
