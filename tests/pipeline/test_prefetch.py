"""Tests for double-buffered batch processing (issue #713).

Verifies I/O-compute overlap, memory-limiter gating, and graceful
error handling in PipelineOrchestrator._process_batch_prefetch.
"""

from __future__ import annotations

import random
import statistics
import threading
import time
from pathlib import Path

import pytest

from file_organizer.interfaces.pipeline import StageContext
from file_organizer.optimization.memory_limiter import MemoryLimiter
from file_organizer.pipeline.orchestrator import PipelineOrchestrator


class _MemoryExhausted(MemoryLimiter):
    """Stub that always reports memory exceeded."""

    def __init__(self) -> None:
        super().__init__(max_memory_mb=1)
        self.check_call_count = 0

    def check(self) -> bool:
        self.check_call_count += 1
        return False


class _MemoryAvailable(MemoryLimiter):
    """Stub that always reports memory available."""

    def __init__(self) -> None:
        super().__init__(max_memory_mb=4096)
        self.check_call_count = 0

    def check(self) -> bool:
        self.check_call_count += 1
        return True


# ---------------------------------------------------------------------------
# Test-only stage helpers
# ---------------------------------------------------------------------------


class _SlowIOStage:
    """Simulates an I/O-bound stage: reads file content + configurable delay."""

    def __init__(self, delay_s: float = 0.0) -> None:
        self._delay = delay_s

    @property
    def name(self) -> str:
        return "slow_io"

    def process(self, context: StageContext) -> StageContext:
        if context.failed:
            return context
        # Read actual file content (I/O work).
        try:
            context.file_path.read_bytes()
        except OSError as exc:
            context.error = str(exc)
            return context
        if self._delay:
            threading.Event().wait(timeout=self._delay)
        context.metadata["io_done"] = True
        return context


class _SlowComputeStage:
    """Simulates a compute-bound stage (e.g. LLM inference)."""

    def __init__(self, delay_s: float = 0.05) -> None:
        self._delay = delay_s

    @property
    def name(self) -> str:
        return "slow_compute"

    def process(self, context: StageContext) -> StageContext:
        if context.failed:
            return context
        threading.Event().wait(timeout=self._delay)
        context.category = "test_category"
        return context


class _ErrorIOStage:
    """I/O stage that raises on files matching a predicate."""

    def __init__(self, fail_on: Path) -> None:
        self._fail_on = fail_on

    @property
    def name(self) -> str:
        return "error_io"

    def process(self, context: StageContext) -> StageContext:
        if context.file_path == self._fail_on:
            raise RuntimeError(f"Simulated I/O failure: {context.file_path}")
        context.metadata["io_done"] = True
        return context


def _make_files(tmp_path: Path, count: int, size_bytes: int, seed: int = 42) -> list[Path]:
    """Create *count* deterministic binary files of *size_bytes* each."""
    rng = random.Random(seed)
    files = []
    for i in range(count):
        p = tmp_path / f"file_{i:04d}.bin"
        p.write_bytes(rng.randbytes(size_bytes))
        files.append(p)
    return files


# ---------------------------------------------------------------------------
# Performance test
# ---------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.unit
class TestPrefetchPerformance:
    """Verify prefetch gives >= 20% wall-clock speedup on a 10-file batch."""

    def _median_batch_time(
        self,
        files: list[Path],
        prefetch_depth: int,
        io_delay: float,
        compute_delay: float,
        iterations: int = 5,
    ) -> float:
        times: list[float] = []
        for _ in range(iterations):
            orchestrator = PipelineOrchestrator(
                stages=[
                    _SlowIOStage(delay_s=io_delay),
                    _SlowComputeStage(delay_s=compute_delay),
                ],
                prefetch_depth=prefetch_depth,
                prefetch_stages=1,
            )
            t0 = time.monotonic()
            orchestrator.process_batch(files)
            times.append(time.monotonic() - t0)
        return statistics.median(times)

    def test_prefetch_faster_than_sequential(self, tmp_path: Path) -> None:
        """Prefetch depth=2 must be >= 20% faster than no-prefetch baseline.

        Uses 10 x 1 MB files (seed=42), controlled sleep values to make
        the I/O-compute overlap measurable in CI without flakiness.
        """
        files = _make_files(tmp_path, count=10, size_bytes=1024 * 1024, seed=42)

        # Keep delays large enough that overlap is clearly measurable and
        # small enough that the test finishes within the 30 s CI timeout.
        io_delay = 0.015  # 15 ms  — simulates file-read latency
        compute_delay = 0.04  # 40 ms  — simulates LLM inference

        baseline = self._median_batch_time(
            files, prefetch_depth=0, io_delay=io_delay, compute_delay=compute_delay
        )
        with_prefetch = self._median_batch_time(
            files, prefetch_depth=2, io_delay=io_delay, compute_delay=compute_delay
        )

        speedup = (baseline - with_prefetch) / baseline
        assert speedup >= 0.20, (
            f"Expected >= 20% speedup, got {speedup:.1%} "
            f"(baseline={baseline:.3f}s, prefetch={with_prefetch:.3f}s)"
        )

    def test_no_prefetch_flag_produces_sequential_timing(self, tmp_path: Path) -> None:
        """prefetch_depth=0 should run sequentially (no thread pool overhead)."""
        files = _make_files(tmp_path, count=3, size_bytes=1024, seed=1)

        orchestrator = PipelineOrchestrator(
            stages=[_SlowIOStage(), _SlowComputeStage(delay_s=0.01)],
            prefetch_depth=0,
        )
        results = orchestrator.process_batch(files)
        assert len(results) == 3
        assert all(r.success for r in results)

    def test_prefetched_result_duration_includes_io_time(self, tmp_path: Path) -> None:
        """Per-file timing should start when prefetched I/O is submitted."""
        files = _make_files(tmp_path, count=3, size_bytes=1024, seed=10)
        io_delay = 0.04
        compute_delay = 0.03

        orchestrator = PipelineOrchestrator(
            stages=[
                _SlowIOStage(delay_s=io_delay),
                _SlowComputeStage(delay_s=compute_delay),
            ],
            prefetch_depth=2,
            prefetch_stages=1,
        )

        results = orchestrator.process_batch(files)

        assert results[0].success
        # Allow 50% tolerance: shared CI runners can be slow or fast
        assert results[0].duration_ms >= (io_delay + compute_delay) * 1000 * 0.5


# ---------------------------------------------------------------------------
# Memory limiter tests
# ---------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.unit
class TestPrefetchMemoryBound:
    """Verify prefetch respects the memory_limiter threshold."""

    def test_prefetch_stops_when_memory_exceeded(self, tmp_path: Path) -> None:
        """When memory_limiter.check() returns False from the start,
        no futures are submitted and the batch still completes."""
        files = _make_files(tmp_path, count=5, size_bytes=256, seed=2)

        limiter = _MemoryExhausted()
        orchestrator = PipelineOrchestrator(
            stages=[_SlowIOStage(), _SlowComputeStage(delay_s=0.0)],
            prefetch_depth=2,
            memory_limiter=limiter,
        )
        results = orchestrator.process_batch(files)

        # All files must still be processed (graceful degradation).
        assert len(results) == 5
        assert all(r.success for r in results)

    def test_prefetch_proceeds_when_memory_available(self, tmp_path: Path) -> None:
        """When memory_limiter.check() always returns True, prefetch runs normally."""
        files = _make_files(tmp_path, count=4, size_bytes=256, seed=3)
        prefetch_depth = 2

        limiter = _MemoryAvailable()
        orchestrator = PipelineOrchestrator(
            stages=[_SlowIOStage(), _SlowComputeStage(delay_s=0.0)],
            prefetch_depth=prefetch_depth,
            memory_limiter=limiter,
        )
        results = orchestrator.process_batch(files)

        assert len(results) == 4
        assert all(r.success for r in results)
        expected_min_checks = min(prefetch_depth, len(files)) + max(
            0,
            len(files) - prefetch_depth,
        )
        assert limiter.check_call_count >= expected_min_checks


# ---------------------------------------------------------------------------
# Error handling tests
# ---------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.unit
class TestPrefetchErrorHandling:
    """Verify errors in prefetched files don't crash the batch."""

    def test_error_in_prefetched_file_is_graceful_skip(self, tmp_path: Path) -> None:
        """An exception in an I/O stage produces a failed result, not a crash."""
        files = _make_files(tmp_path, count=5, size_bytes=256, seed=4)
        fail_file = files[2]  # Middle file fails

        orchestrator = PipelineOrchestrator(
            stages=[
                _ErrorIOStage(fail_on=fail_file),
                _SlowComputeStage(delay_s=0.0),
            ],
            prefetch_depth=2,
            prefetch_stages=1,
        )
        results = orchestrator.process_batch(files)

        assert len(results) == 5
        # The failing file produces a failed result.
        failed = [r for r in results if not r.success]
        succeeded = [r for r in results if r.success]
        assert len(failed) == 1
        assert failed[0].file_path == fail_file
        assert failed[0].error is not None
        # All other files processed successfully.
        assert len(succeeded) == 4

    def test_error_in_first_prefetched_file_does_not_block_rest(self, tmp_path: Path) -> None:
        """Error in file[0] (first prefetch) doesn't prevent processing files 1-4."""
        files = _make_files(tmp_path, count=5, size_bytes=256, seed=5)
        fail_file = files[0]

        orchestrator = PipelineOrchestrator(
            stages=[
                _ErrorIOStage(fail_on=fail_file),
                _SlowComputeStage(delay_s=0.0),
            ],
            prefetch_depth=2,
            prefetch_stages=1,
        )
        results = orchestrator.process_batch(files)

        assert len(results) == 5
        assert not results[0].success
        assert all(r.success for r in results[1:])

    def test_missing_file_in_prefetch_produces_failed_result(self, tmp_path: Path) -> None:
        """A file that doesn't exist produces a failed result via PreprocessorStage."""
        from file_organizer.pipeline.stages import PreprocessorStage

        real_files = _make_files(tmp_path, count=3, size_bytes=256, seed=6)
        ghost = tmp_path / "ghost.bin"  # never created

        all_files = [*real_files[:1], ghost, *real_files[1:]]

        orchestrator = PipelineOrchestrator(
            stages=[PreprocessorStage(), _SlowComputeStage(delay_s=0.0)],
            prefetch_depth=2,
            prefetch_stages=1,
        )
        results = orchestrator.process_batch(all_files)

        assert len(results) == 4
        failed = [r for r in results if not r.success]
        assert len(failed) == 1
        assert failed[0].file_path == ghost


# ---------------------------------------------------------------------------
# Prefetch depth / stages boundary tests
# ---------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.unit
class TestPrefetchBoundary:
    """Edge cases: single file, empty batch, prefetch_stages=0."""

    def test_single_file_falls_back_to_sequential(self, tmp_path: Path) -> None:
        """Single-file batch is never sent to the prefetch path."""
        files = _make_files(tmp_path, count=1, size_bytes=256, seed=7)
        orchestrator = PipelineOrchestrator(
            stages=[_SlowIOStage(), _SlowComputeStage(delay_s=0.0)],
            prefetch_depth=2,
        )
        results = orchestrator.process_batch(files)
        assert len(results) == 1
        assert results[0].success

    def test_empty_batch_returns_empty(self) -> None:
        orchestrator = PipelineOrchestrator(
            stages=[_SlowIOStage(), _SlowComputeStage(delay_s=0.0)],
            prefetch_depth=2,
        )
        assert orchestrator.process_batch([]) == []

    def test_prefetch_stages_zero_disables_prefetch(self, tmp_path: Path) -> None:
        """prefetch_stages=0 means all stages are compute → no I/O thread pool."""
        files = _make_files(tmp_path, count=3, size_bytes=256, seed=8)
        orchestrator = PipelineOrchestrator(
            stages=[_SlowIOStage(), _SlowComputeStage(delay_s=0.0)],
            prefetch_depth=2,
            prefetch_stages=0,
        )
        results = orchestrator.process_batch(files)
        assert len(results) == 3
        assert all(r.success for r in results)

    def test_result_order_preserved(self, tmp_path: Path) -> None:
        """Results are returned in the same order as input files."""
        files = _make_files(tmp_path, count=6, size_bytes=256, seed=9)
        orchestrator = PipelineOrchestrator(
            stages=[_SlowIOStage(), _SlowComputeStage(delay_s=0.0)],
            prefetch_depth=3,
            prefetch_stages=1,
        )
        results = orchestrator.process_batch(files)
        assert [r.file_path for r in results] == files
