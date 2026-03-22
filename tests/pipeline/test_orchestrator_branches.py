"""Integration tests for PipelineOrchestrator branch coverage.

Targets branches in orchestrator.py that are not exercised by the
existing unit tests:

- memory_pressure_threshold_percent validation (ValueError)
- buffer_pool property lazy-init (double-checked locking)
- set_stages() and stages property
- _run_stages: stage returns None, stage raises, pre-failed context passthrough
- _finalize_result: success vs failure stat paths, processor_type from extra
- _make_context: dry_run derived from config.should_move_files
- _acquire_buffer / _release_buffer error paths
- _safe_file_size: OSError fallback
- _safe_current_rss: OSError / RuntimeError / ValueError fallback
- _rebalance_buffer_pool: pool=None skip, under-pressure shrink, high-utilisation grow
- process_batch with stages + prefetch_stages>1 warning
- process_batch with stages + prefetch_depth=0 (sequential chunk loop)
- stop() cleanup with monitor and watch_thread
"""

from __future__ import annotations

import logging
import math
import threading
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from file_organizer.interfaces.pipeline import StageContext
from file_organizer.optimization.buffer_pool import BufferPool
from file_organizer.pipeline.config import PipelineConfig
from file_organizer.pipeline.orchestrator import PipelineOrchestrator
from file_organizer.pipeline.router import ProcessorType

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Minimal stage helpers
# ---------------------------------------------------------------------------


class _PassStage:
    """Stage that sets a known marker on context.extra and returns it."""

    @property
    def name(self) -> str:
        """Return the stage name identifier."""
        return "pass_stage"

    def process(self, context: StageContext) -> StageContext:
        """Mark context as visited and set a test category."""
        context.extra["pass_stage_visited"] = True
        context.category = "test_cat"
        return context


class _FailingStage:
    """Stage that always raises RuntimeError."""

    @property
    def name(self) -> str:
        """Return the stage name identifier."""
        return "failing_stage"

    def process(self, context: StageContext) -> StageContext:
        """Raise RuntimeError unconditionally to simulate a stage failure."""
        raise RuntimeError("stage explosion")


class _NoneReturnStage:
    """Stage that illegally returns None."""

    @property
    def name(self) -> str:
        """Return the stage name identifier."""
        return "none_return_stage"

    def process(self, context: StageContext) -> StageContext:  # type: ignore[return-value]
        """Return None to exercise the None-return guard in the orchestrator."""
        return None  # type: ignore[return-value]


class _ErrorSettingStage:
    """Stage that marks context as failed by setting context.error."""

    @property
    def name(self) -> str:
        """Return the stage name identifier."""
        return "error_setting_stage"

    def process(self, context: StageContext) -> StageContext:
        """Set context.error to trigger the error-result branch in the orchestrator."""
        context.error = "deliberate failure"
        return context


class _SentinelStage:
    """Stage that records whether it was called."""

    def __init__(self) -> None:
        self.called = False

    @property
    def name(self) -> str:
        """Return the stage name identifier."""
        return "sentinel_stage"

    def process(self, context: StageContext) -> StageContext:
        """Mark self.called True and assign a sentinel category."""
        self.called = True
        context.category = "sentinel_cat"
        return context


class _ProcessorTypeStage:
    """Stage that stores a processor_type in context.extra (like AnalyzerStage)."""

    @property
    def name(self) -> str:
        """Return the stage name identifier."""
        return "processor_type_stage"

    def process(self, context: StageContext) -> StageContext:
        """Store a ProcessorType in context.extra and set a typed category."""
        context.extra["analyzer.processor_type"] = ProcessorType.TEXT
        context.category = "typed_cat"
        return context


# ---------------------------------------------------------------------------
# TestMemoryPressureThresholdValidation
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestMemoryPressureThresholdValidation:
    """Validate the memory_pressure_threshold_percent guard at init."""

    def test_negative_threshold_raises_value_error(self) -> None:
        """A negative memory_pressure_threshold_percent raises ValueError at construction."""
        with pytest.raises(ValueError, match="memory_pressure_threshold_percent"):
            PipelineOrchestrator(memory_pressure_threshold_percent=-1.0)

    def test_threshold_above_100_raises_value_error(self) -> None:
        """A threshold greater than 100 raises ValueError at construction."""
        with pytest.raises(ValueError, match="memory_pressure_threshold_percent"):
            PipelineOrchestrator(memory_pressure_threshold_percent=100.1)

    def test_boundary_values_are_accepted(self) -> None:
        """Threshold values of exactly 0.0 and 100.0 are accepted without error."""
        orch_zero = PipelineOrchestrator(memory_pressure_threshold_percent=0.0)
        assert orch_zero._memory_pressure_threshold_percent == 0.0

        orch_hundred = PipelineOrchestrator(memory_pressure_threshold_percent=100.0)
        assert orch_hundred._memory_pressure_threshold_percent == 100.0


# ---------------------------------------------------------------------------
# TestBufferPoolLazyInit
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestBufferPoolLazyInit:
    """buffer_pool property initialises exactly once under concurrent access."""

    def test_buffer_pool_lazily_created_when_none(self) -> None:
        """buffer_pool is lazily initialised once and the same instance is returned to all callers."""
        orch = PipelineOrchestrator()
        results: list[object] = []
        barrier = threading.Barrier(2)

        def _access() -> None:
            """Wait at the barrier then read buffer_pool."""
            barrier.wait(timeout=5)
            results.append(orch.buffer_pool)

        t1 = threading.Thread(target=_access)
        t2 = threading.Thread(target=_access)
        t1.start()
        t2.start()
        t1.join(timeout=5)
        t2.join(timeout=5)

        assert not t1.is_alive(), "thread 1 did not finish within timeout"
        assert not t2.is_alive(), "thread 2 did not finish within timeout"
        assert len(results) == 2
        assert results[0] is not None
        assert results[1] is not None
        assert orch._buffer_pool is not None
        assert results[0] is results[1]

    def test_supplied_buffer_pool_is_returned_directly(self) -> None:
        """A BufferPool supplied at construction is returned unchanged by the property."""
        custom_pool = BufferPool(buffer_size=512, initial_buffers=2, max_buffers=4)
        orch = PipelineOrchestrator(buffer_pool=custom_pool)
        assert orch.buffer_pool is custom_pool


# ---------------------------------------------------------------------------
# TestSetStages
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestSetStages:
    """set_stages() replaces the stage list; stages property returns a copy."""

    def test_stages_property_returns_copy(self) -> None:
        """stages property returns equal but distinct list objects on successive accesses."""
        s = _PassStage()
        orch = PipelineOrchestrator(stages=[s])
        copy1 = orch.stages
        copy2 = orch.stages
        assert copy1 == copy2
        assert copy1 is not copy2  # different list objects

    def test_set_stages_replaces_list(self) -> None:
        """set_stages() replaces the current stage list with the provided list."""
        orch = PipelineOrchestrator()
        assert orch.stages == []

        s = _PassStage()
        orch.set_stages([s])
        assert orch.stages == [s]

    def test_set_stages_empty_clears_list(self) -> None:
        """set_stages([]) clears all existing stages."""
        orch = PipelineOrchestrator(stages=[_PassStage()])
        orch.set_stages([])
        assert orch.stages == []

    def test_set_stages_is_thread_safe(self, tmp_path: Path) -> None:
        """Multiple threads calling set_stages() must not corrupt internal state."""
        orch = PipelineOrchestrator()
        errors: list[Exception] = []

        def swap(stages: list) -> None:
            """Call set_stages 50 times and capture any exceptions."""
            try:
                for _ in range(50):
                    orch.set_stages(stages)
            except Exception as exc:
                errors.append(exc)

        t1 = threading.Thread(target=swap, args=([_PassStage()],))
        t2 = threading.Thread(target=swap, args=([],))
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        assert errors == []


# ---------------------------------------------------------------------------
# TestRunStages
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestRunStages:
    """_run_stages: stage raising, returning None, pre-failed passthrough."""

    def test_stage_raising_records_error_on_context(self, tmp_path: Path) -> None:
        """A stage that raises records the exception message in the result error field."""
        f = tmp_path / "a.txt"
        f.write_text("x")
        orch = PipelineOrchestrator(stages=[_FailingStage()])
        result = orch.process_file(f)
        assert result.success is False
        assert "stage explosion" in result.error

    def test_stage_returning_none_records_error(self, tmp_path: Path) -> None:
        """A stage that returns None causes failure with 'returned None' in the error."""
        f = tmp_path / "a.txt"
        f.write_text("x")
        orch = PipelineOrchestrator(stages=[_NoneReturnStage()])
        result = orch.process_file(f)
        assert result.success is False
        assert "returned None" in result.error

    def test_pre_failed_context_skips_subsequent_stages(self, tmp_path: Path) -> None:
        """After the first stage marks context failed, later stages must NOT run."""
        sentinel = _SentinelStage()
        orch = PipelineOrchestrator(stages=[_ErrorSettingStage(), sentinel])
        f = tmp_path / "a.txt"
        f.write_text("x")
        result = orch.process_file(f)
        assert result.success is False
        assert result.error == "deliberate failure"
        assert sentinel.called is False

    def test_successful_stage_pipeline(self, tmp_path: Path) -> None:
        """Happy-path: pass stage sets category, result is successful."""
        f = tmp_path / "a.txt"
        f.write_text("x")
        orch = PipelineOrchestrator(stages=[_PassStage()])
        result = orch.process_file(f)
        assert result.success is True
        assert result.category == "test_cat"


# ---------------------------------------------------------------------------
# TestFinalizeResult
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestFinalizeResult:
    """_finalize_result: stat counters, processor_type from extra, dry_run."""

    def test_successful_result_increments_successful_counter(self, tmp_path: Path) -> None:
        """A successful file increments stats.successful and stats.total_processed."""
        f = tmp_path / "a.txt"
        f.write_text("x")
        orch = PipelineOrchestrator(stages=[_PassStage()])
        orch.process_file(f)
        assert orch.stats.successful == 1
        assert orch.stats.failed == 0
        assert orch.stats.total_processed == 1

    def test_failed_result_increments_failed_counter(self, tmp_path: Path) -> None:
        """A failed file increments stats.failed and stats.total_processed."""
        f = tmp_path / "a.txt"
        f.write_text("x")
        orch = PipelineOrchestrator(stages=[_FailingStage()])
        orch.process_file(f)
        assert orch.stats.failed == 1
        assert orch.stats.successful == 0
        assert orch.stats.total_processed == 1

    def test_processor_type_extracted_from_context_extra(self, tmp_path: Path) -> None:
        """processor_type is read from context.extra['analyzer.processor_type']."""
        f = tmp_path / "a.txt"
        f.write_text("x")
        orch = PipelineOrchestrator(stages=[_ProcessorTypeStage()])
        result = orch.process_file(f)
        assert result.processor_type == ProcessorType.TEXT

    def test_missing_processor_type_in_extra_defaults_to_unknown(self, tmp_path: Path) -> None:
        """processor_type defaults to UNKNOWN when not set in context.extra."""
        f = tmp_path / "a.txt"
        f.write_text("x")
        orch = PipelineOrchestrator(stages=[_PassStage()])
        result = orch.process_file(f)
        assert result.processor_type == ProcessorType.UNKNOWN

    def test_dry_run_flag_comes_from_config(self, tmp_path: Path) -> None:
        """result.dry_run is True when PipelineConfig has dry_run=True."""
        f = tmp_path / "a.txt"
        f.write_text("x")
        # dry_run=True, auto_organize=False → should_move_files=False → context.dry_run=True
        config = PipelineConfig(output_directory=tmp_path / "out", dry_run=True)
        orch = PipelineOrchestrator(config, stages=[_PassStage()])
        result = orch.process_file(f)
        assert result.dry_run is True

    def test_dry_run_false_when_auto_organize_enabled(self, tmp_path: Path) -> None:
        """result.dry_run is False when dry_run=False and auto_organize=True."""
        f = tmp_path / "a.txt"
        f.write_text("x")
        config = PipelineConfig(
            output_directory=tmp_path / "out",
            dry_run=False,
            auto_organize=True,
        )
        orch = PipelineOrchestrator(config, stages=[_PassStage()])
        result = orch.process_file(f)
        assert result.dry_run is False

    def test_duration_ms_is_positive(self, tmp_path: Path) -> None:
        """result.duration_ms is a finite non-negative value."""
        f = tmp_path / "a.txt"
        f.write_text("x")
        orch = PipelineOrchestrator(stages=[_PassStage()])
        result = orch.process_file(f)
        assert math.isfinite(result.duration_ms)
        assert result.duration_ms >= 0.0


# ---------------------------------------------------------------------------
# TestSafeFileSizeFallback
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestSafeFileSizeFallback:
    """_safe_file_size returns 0 when stat() raises OSError."""

    def test_safe_file_size_returns_zero_on_oserror(self) -> None:
        """_safe_file_size returns 0 when stat() raises OSError for a nonexistent path."""
        orch = PipelineOrchestrator()
        ghost = Path("/nonexistent/totally/made/up.bin")
        size = orch._safe_file_size(ghost)
        assert size == 0

    def test_safe_file_size_returns_actual_size_for_real_file(self, tmp_path: Path) -> None:
        """_safe_file_size returns the correct byte count for an existing file."""
        f = tmp_path / "data.bin"
        f.write_bytes(b"x" * 100)
        orch = PipelineOrchestrator()
        size = orch._safe_file_size(f)
        assert size == 100


# ---------------------------------------------------------------------------
# TestSafeCurrentRssFallback
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestSafeCurrentRssFallback:
    """_safe_current_rss returns 0 when ResourceMonitor raises."""

    def test_safe_current_rss_returns_zero_on_oserror(self) -> None:
        """_safe_current_rss returns 0 when get_memory_usage raises OSError."""
        orch = PipelineOrchestrator()
        mock_monitor = MagicMock()
        mock_monitor.get_memory_usage.side_effect = OSError("no /proc")
        orch._resource_monitor = mock_monitor
        rss = orch._safe_current_rss()
        assert rss == 0

    def test_safe_current_rss_returns_zero_on_runtime_error(self) -> None:
        """_safe_current_rss returns 0 when get_memory_usage raises RuntimeError."""
        orch = PipelineOrchestrator()
        mock_monitor = MagicMock()
        mock_monitor.get_memory_usage.side_effect = RuntimeError("platform unsupported")
        orch._resource_monitor = mock_monitor
        rss = orch._safe_current_rss()
        assert rss == 0

    def test_safe_current_rss_returns_zero_on_value_error(self) -> None:
        """_safe_current_rss returns 0 when get_memory_usage raises ValueError."""
        orch = PipelineOrchestrator()
        mock_monitor = MagicMock()
        mock_monitor.get_memory_usage.side_effect = ValueError("bad format")
        orch._resource_monitor = mock_monitor
        rss = orch._safe_current_rss()
        assert rss == 0

    def test_safe_current_rss_returns_actual_value_on_success(self) -> None:
        """_safe_current_rss returns the rss value from get_memory_usage on success."""
        orch = PipelineOrchestrator()
        mock_monitor = MagicMock()
        mock_rss_info = MagicMock()
        mock_rss_info.rss = 123_456_789
        mock_monitor.get_memory_usage.return_value = mock_rss_info
        orch._resource_monitor = mock_monitor
        rss = orch._safe_current_rss()
        assert rss == 123_456_789


# ---------------------------------------------------------------------------
# TestRebalanceBufferPool
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestRebalanceBufferPool:
    """_rebalance_buffer_pool: skip when None, shrink under pressure, grow on high utilisation."""

    def test_no_pool_skips_rebalance(self) -> None:
        """When _buffer_pool is None, _rebalance_buffer_pool is a no-op."""
        orch = PipelineOrchestrator()
        # Ensure pool is None (no lazy-init has fired yet)
        assert orch._buffer_pool is None
        # Must not raise
        orch._rebalance_buffer_pool()

    def test_under_memory_pressure_shrinks_pool(self) -> None:
        """should_evict=True triggers a resize down to initial_buffers."""
        pool = BufferPool(buffer_size=256, initial_buffers=2, max_buffers=8)
        pool.resize(6)
        assert pool.total_buffers == 6

        mock_monitor = MagicMock()
        mock_monitor.should_evict.return_value = True

        orch = PipelineOrchestrator(buffer_pool=pool, resource_monitor=mock_monitor)
        orch._rebalance_buffer_pool()

        # Pool should have been resized down to initial_buffers (2)
        assert pool.total_buffers == pool.initial_buffers
        mock_monitor.should_evict.assert_called_once_with(
            threshold_percent=orch._memory_pressure_threshold_percent
        )

    def test_high_utilisation_grows_pool(self, tmp_path: Path) -> None:
        """utilization >= 0.9 and room to grow triggers a resize up."""
        pool = BufferPool(buffer_size=256, initial_buffers=2, max_buffers=8)
        # Acquire buffers to push utilisation to 100%
        acquired = [pool.acquire() for _ in range(2)]
        assert pool.utilization == 1.0

        mock_monitor = MagicMock()
        mock_monitor.should_evict.return_value = False  # no pressure

        orch = PipelineOrchestrator(buffer_pool=pool, resource_monitor=mock_monitor)
        before = pool.total_buffers
        orch._rebalance_buffer_pool()

        assert pool.total_buffers > before
        # Cleanup
        for buf in acquired:
            pool.release(buf)

    def test_monitor_exception_in_rebalance_is_swallowed(self) -> None:
        """OSError from should_evict must not propagate from _rebalance_buffer_pool."""
        pool = BufferPool(buffer_size=256, initial_buffers=2, max_buffers=4)
        mock_monitor = MagicMock()
        mock_monitor.should_evict.side_effect = OSError("no metrics")

        orch = PipelineOrchestrator(buffer_pool=pool, resource_monitor=mock_monitor)
        # Should not raise
        orch._rebalance_buffer_pool()

    def test_runtime_error_in_rebalance_is_swallowed(self) -> None:
        """RuntimeError from should_evict is swallowed and does not propagate."""
        pool = BufferPool(buffer_size=256, initial_buffers=2, max_buffers=4)
        mock_monitor = MagicMock()
        mock_monitor.should_evict.side_effect = RuntimeError("crash")

        orch = PipelineOrchestrator(buffer_pool=pool, resource_monitor=mock_monitor)
        orch._rebalance_buffer_pool()


# ---------------------------------------------------------------------------
# TestAcquireReleaseBuffer
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestAcquireReleaseBuffer:
    """_acquire_buffer and _release_buffer error path coverage."""

    def test_acquire_returns_none_on_pool_exception(self, tmp_path: Path) -> None:
        """Processing continues successfully even when pool.acquire() raises an exception."""
        f = tmp_path / "a.txt"
        f.write_text("x")
        pool = MagicMock()
        pool.buffer_size = 1024
        pool.acquire.side_effect = RuntimeError("pool full")
        orch = PipelineOrchestrator(buffer_pool=pool, stages=[_PassStage()])
        # Should not raise; should fall through with buffer=None
        result = orch.process_file(f)
        # The stage still runs — result is produced even when buffer acquisition fails
        assert result.success is True

    def test_release_none_buffer_is_no_op(self, tmp_path: Path) -> None:
        """_release_buffer(path, None) must not call pool.release."""
        pool = MagicMock(spec=BufferPool)
        pool.buffer_size = 1024
        pool.acquire.return_value = bytearray(1024)
        orch = PipelineOrchestrator(buffer_pool=pool)
        f = tmp_path / "a.txt"
        f.write_text("x")
        # Call with None buffer directly
        orch._release_buffer(f, None)
        pool.release.assert_not_called()

    def test_release_exception_is_swallowed(self, tmp_path: Path) -> None:
        """Exceptions from pool.release must not propagate."""
        pool = BufferPool(buffer_size=256, initial_buffers=2, max_buffers=4)
        buf = pool.acquire()
        pool.release(buf)  # return it so we can get it again

        # Now make a mock that raises on release
        mock_pool = MagicMock(spec=BufferPool)
        mock_pool.buffer_size = 256
        mock_pool.acquire.return_value = bytearray(256)
        mock_pool.release.side_effect = RuntimeError("release failed")

        orch = PipelineOrchestrator(buffer_pool=mock_pool, stages=[_PassStage()])
        f = tmp_path / "a.txt"
        f.write_text("x")
        # Must not raise despite release failure
        result = orch.process_file(f)
        assert result.success is True


# ---------------------------------------------------------------------------
# TestStagedBatchProcessing
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestStagedBatchProcessing:
    """process_batch with stages and various prefetch configurations."""

    def test_staged_batch_sequential_prefetch_depth_zero(self, tmp_path: Path) -> None:
        """stages + prefetch_depth=0 → sequential processing, all results succeed."""
        files = [tmp_path / f"f{i}.txt" for i in range(4)]
        for f in files:
            f.write_text("data")

        orch = PipelineOrchestrator(stages=[_PassStage()], prefetch_depth=0)
        results = orch.process_batch(files)

        assert len(results) == 4
        assert all(r.success for r in results)
        assert all(r.category == "test_cat" for r in results)

    def test_staged_batch_order_preserved_sequential(self, tmp_path: Path) -> None:
        """process_batch returns results in the same order as input files."""
        files = [tmp_path / f"f{i}.txt" for i in range(5)]
        for f in files:
            f.write_text("x")

        orch = PipelineOrchestrator(stages=[_PassStage()], prefetch_depth=0)
        results = orch.process_batch(files)

        assert [r.file_path for r in results] == files

    def test_staged_batch_empty_returns_empty(self) -> None:
        """process_batch returns an empty list when given no files."""
        orch = PipelineOrchestrator(stages=[_PassStage()])
        assert orch.process_batch([]) == []

    def test_prefetch_stages_greater_than_one_logs_warning(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """prefetch_stages=2 triggers a warning and is capped to 1."""

        files = [tmp_path / f"f{i}.txt" for i in range(3)]
        for f in files:
            f.write_text("data")

        orch = PipelineOrchestrator(
            stages=[_PassStage()],
            prefetch_depth=2,
            prefetch_stages=2,
        )
        with caplog.at_level(logging.WARNING, logger="file_organizer.pipeline.orchestrator"):
            results = orch.process_batch(files)

        # All results must be produced despite the warning
        assert len(results) == 3
        assert all(r.success for r in results)
        # The warning must mention "not fully supported" / "capping"
        warning_texts = " ".join(r.message for r in caplog.records if r.levelno == logging.WARNING)
        assert "not fully supported" in warning_texts or "capping" in warning_texts

    def test_staged_batch_failure_does_not_stop_other_files(self, tmp_path: Path) -> None:
        """A failure in one file does not prevent processing of remaining files."""
        good1 = tmp_path / "good1.txt"
        good1.write_text("x")
        good2 = tmp_path / "good2.txt"
        good2.write_text("x")

        # FailingStage raises → that file fails; others still go through
        orch = PipelineOrchestrator(stages=[_FailingStage()], prefetch_depth=0)
        results = orch.process_batch([good1, good2])

        assert len(results) == 2
        assert results[0].success is False
        assert results[1].success is False  # both fail since same failing stage

    def test_staged_batch_updates_stats(self, tmp_path: Path) -> None:
        """process_batch updates orchestrator stats for all processed files."""
        files = [tmp_path / f"f{i}.txt" for i in range(3)]
        for f in files:
            f.write_text("data")

        orch = PipelineOrchestrator(stages=[_PassStage()], prefetch_depth=0)
        orch.process_batch(files)

        assert orch.stats.total_processed == 3
        assert orch.stats.successful == 3
        assert orch.stats.failed == 0


# ---------------------------------------------------------------------------
# TestNotifyWithStagedPath
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestNotifyWithStagedPath:
    """_notify is called from _finalize_result; verify it fires on staged path too."""

    def test_callback_called_on_staged_success(self, tmp_path: Path) -> None:
        """notification_callback is called with (file, True) on a successful staged result."""
        f = tmp_path / "a.txt"
        f.write_text("x")
        callback = MagicMock()
        config = PipelineConfig(
            output_directory=tmp_path / "out",
            notification_callback=callback,
        )
        orch = PipelineOrchestrator(config, stages=[_PassStage()])
        orch.process_file(f)
        callback.assert_called_once_with(f, True)

    def test_callback_called_on_staged_failure(self, tmp_path: Path) -> None:
        """notification_callback is called with (file, False) on a failed staged result."""
        f = tmp_path / "a.txt"
        f.write_text("x")
        callback = MagicMock()
        config = PipelineConfig(
            output_directory=tmp_path / "out",
            notification_callback=callback,
        )
        orch = PipelineOrchestrator(config, stages=[_FailingStage()])
        orch.process_file(f)
        callback.assert_called_once_with(f, False)

    def test_callback_exception_does_not_propagate_in_staged_path(self, tmp_path: Path) -> None:
        """An exception raised by notification_callback does not propagate to the caller."""
        f = tmp_path / "a.txt"
        f.write_text("x")
        bad_callback = MagicMock(side_effect=RuntimeError("callback broke"))
        config = PipelineConfig(
            output_directory=tmp_path / "out",
            notification_callback=bad_callback,
        )
        orch = PipelineOrchestrator(config, stages=[_PassStage()])
        # Must not raise despite callback failure
        result = orch.process_file(f)
        assert result.success is True


# ---------------------------------------------------------------------------
# TestStopWithMonitorCleanup
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestStopWithMonitorCleanup:
    """stop() path that exercises monitor.stop() and watch_thread.join()."""

    def test_stop_calls_monitor_stop_and_clears_it(self) -> None:
        """stop() must call _monitor.stop() and set _monitor to None."""
        orch = PipelineOrchestrator()
        orch._running = True
        mock_monitor = MagicMock()
        orch._monitor = mock_monitor

        orch.stop()

        mock_monitor.stop.assert_called_once()
        assert orch._monitor is None

    def test_stop_joins_watch_thread_and_clears_it(self) -> None:
        """stop() must join _watch_thread and set it to None."""
        orch = PipelineOrchestrator()
        orch._running = True

        joined = threading.Event()

        class _FakeThread:
            """Minimal thread substitute that sets an Event on join()."""

            daemon = True

            def join(self, timeout: float | None = None) -> None:
                """Signal that join was called."""
                joined.set()

        fake_thread = _FakeThread()
        orch._watch_thread = fake_thread  # type: ignore[assignment]

        orch.stop()

        assert joined.is_set()
        assert orch._watch_thread is None

    def test_stop_when_not_running_is_noop(self) -> None:
        """stop() on a non-running pipeline is safe and makes no monitor calls."""
        orch = PipelineOrchestrator()
        mock_monitor = MagicMock()
        orch._monitor = mock_monitor

        orch.stop()

        mock_monitor.stop.assert_not_called()


# ---------------------------------------------------------------------------
# TestMakeContext
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestMakeContext:
    """_make_context derives dry_run from config.should_move_files."""

    def test_make_context_dry_run_true_when_should_not_move(self, tmp_path: Path) -> None:
        """ctx.dry_run is True when config.should_move_files is False."""
        config = PipelineConfig(output_directory=tmp_path, dry_run=True, auto_organize=False)
        orch = PipelineOrchestrator(config)
        ctx = orch._make_context(tmp_path / "f.txt")
        # should_move_files = not dry_run and auto_organize = False → dry_run=True on ctx
        assert ctx.dry_run is True

    def test_make_context_dry_run_false_when_should_move(self, tmp_path: Path) -> None:
        """ctx.dry_run is False when config.should_move_files is True."""
        config = PipelineConfig(output_directory=tmp_path, dry_run=False, auto_organize=True)
        orch = PipelineOrchestrator(config)
        ctx = orch._make_context(tmp_path / "f.txt")
        # should_move_files = True → dry_run=False on ctx
        assert ctx.dry_run is False

    def test_make_context_file_path_is_set(self, tmp_path: Path) -> None:
        """_make_context sets ctx.file_path to the given path."""
        orch = PipelineOrchestrator()
        target = tmp_path / "doc.pdf"
        ctx = orch._make_context(target)
        assert ctx.file_path == target


# ---------------------------------------------------------------------------
# TestBufferKeyInContext
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestBufferKeyInContext:
    """Buffer is placed into context.extra[_BUFFER_KEY] and cleaned up afterward."""

    def test_buffer_not_present_after_process_file_staged(self, tmp_path: Path) -> None:
        """After _process_file_staged completes, the buffer must not leak via extra."""
        from file_organizer.pipeline.orchestrator import _BUFFER_KEY

        captured_extras: list[dict] = []

        class _CapturingStage:
            """Stage that copies context.extra into captured_extras for later inspection."""

            @property
            def name(self) -> str:
                """Return the stage name identifier."""
                return "capturing"

            def process(self, context: StageContext) -> StageContext:
                """Snapshot context.extra and return context unchanged."""
                captured_extras.append(dict(context.extra))
                return context

        f = tmp_path / "a.txt"
        f.write_text("hello")
        orch = PipelineOrchestrator(stages=[_CapturingStage()])
        orch.process_file(f)

        # The buffer key was present during processing (captured by the stage)
        assert _BUFFER_KEY in captured_extras[0]
        # But after _process_file_staged the orchestrator releases the buffer;
        # the context.extra is not accessible post-call, so we confirm no leak
        # by checking that the pool returns all buffers
        assert orch.buffer_pool.in_use_count == 0
