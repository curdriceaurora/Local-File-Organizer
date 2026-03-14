"""Memory-management integration tests for PipelineOrchestrator."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from unittest.mock import Mock

import pytest

from file_organizer.interfaces.pipeline import StageContext
from file_organizer.optimization.buffer_pool import BufferPool
from file_organizer.optimization.resource_monitor import MemoryInfo
from file_organizer.pipeline.config import PipelineConfig
from file_organizer.pipeline.orchestrator import PipelineOrchestrator, ProcessingResult

pytestmark = [pytest.mark.unit, pytest.mark.ci]


@dataclass
class _FixedBatchSizer:
    chunk_size: int
    adjusted_size: int

    def __post_init__(self) -> None:
        """
        Initialize internal call-tracking lists for batch size calculation and adjustment.
        
        Sets up two empty lists:
        - `calculate_calls`: records tuples of (file_sizes, overhead_per_file) for each calculate_batch_size invocation.
        - `adjust_calls`: records tuples of (actual_memory, batch_size) for each adjust_from_feedback invocation.
        """
        self.calculate_calls: list[tuple[list[int], int]] = []
        self.adjust_calls: list[tuple[int, int]] = []

    def calculate_batch_size(self, file_sizes: list[int], overhead_per_file: int = 0) -> int:
        """
        Return the configured chunk size and record the inputs used to compute it.
        
        Parameters:
            file_sizes (list[int]): Sizes (in bytes) of the files considered for sizing the batch.
            overhead_per_file (int): Additional overhead (in bytes) to account for each file.
        
        Returns:
            int: The configured chunk size to use for the batch.
        """
        self.calculate_calls.append((list(file_sizes), overhead_per_file))
        return self.chunk_size

    def adjust_from_feedback(self, actual_memory: int, batch_size: int) -> int:
        """
        Record observed memory usage and the batch size as feedback, and return the configured adjusted batch size.
        
        Parameters:
            actual_memory (int): Observed memory usage in bytes.
            batch_size (int): The batch size that produced the observed memory usage.
        
        Returns:
            int: The adjusted batch size configured on this sizer.
        """
        self.adjust_calls.append((actual_memory, batch_size))
        return self.adjusted_size


@dataclass
class _MonitorStub:
    should_evict_value: bool = False
    rss_value: int = 42_000_000

    def __post_init__(self) -> None:
        """
        Initialize runtime state for the monitor stub.
        
        Creates an empty `should_evict_calls` list used to record the `threshold_percent` values passed to `should_evict` during tests.
        """
        self.should_evict_calls: list[float] = []

    def should_evict(self, threshold_percent: float = 85.0) -> bool:
        """
        Record a memory-pressure threshold check and indicate whether eviction should occur.
        
        Parameters:
            threshold_percent (float): Threshold percentage used for the eviction check.
        
        Returns:
            `true` if eviction should occur, `false` otherwise.
        """
        self.should_evict_calls.append(threshold_percent)
        return self.should_evict_value

    def get_memory_usage(self) -> MemoryInfo:
        """
        Provide simulated process memory statistics for tests.
        
        Returns:
            MemoryInfo: Object with `rss` set to the stub's `rss_value`, `vms` set to twice `rss_value`, and `percent` set to 50.0.
        """
        return MemoryInfo(rss=self.rss_value, vms=self.rss_value * 2, percent=50.0)


class _PassThroughStage:
    @property
    def name(self) -> str:
        """
        Stage identifier for the pass-through stage.
        
        Returns:
            str: The string "pass" representing the stage's name.
        """
        return "pass"

    def process(self, context: StageContext) -> StageContext:
        """
        Mark the provided StageContext as visited by setting context.extra["visited"] to True and return it.
        
        Parameters:
            context (StageContext): The processing context to mark; this object is mutated in-place.
        
        Returns:
            StageContext: The same context instance with `extra["visited"]` set to `True`.
        """
        context.extra["visited"] = True
        return context


class _ReplacingStage:
    @property
    def name(self) -> str:
        """
        Provides the stage's name.
        
        Returns:
            str: The literal 'replace' identifying this stage.
        """
        return "replace"

    def process(self, context: StageContext) -> StageContext:
        """
        Produce a new StageContext preserving the original file path and dry-run flag.
        
        Parameters:
            context (StageContext): The incoming stage context to replace.
        
        Returns:
            StageContext: A new context whose `file_path` is copied from `context.file_path` and whose `dry_run` flag matches `context.dry_run`.
        """
        return StageContext(file_path=context.file_path, dry_run=context.dry_run)


def _make_files(tmp_path: Path, count: int) -> list[Path]:
    """
    Create a sequence of test files with deterministic contents in the given directory.
    
    Each file is named "file-{i}.txt" (i from 0 to count-1) and contains the string "data-" followed by i+1 occurrences of "x".
    
    Parameters:
        tmp_path (Path): Directory where files will be created.
        count (int): Number of files to create.
    
    Returns:
        list[Path]: Ordered list of Paths to the created files.
    """
    files: list[Path] = []
    for i in range(count):
        path = tmp_path / f"file-{i}.txt"
        path.write_text("data-" + ("x" * (i + 1)), encoding="utf-8")
        files.append(path)
    return files


def test_process_batch_uses_adaptive_batch_sizer_for_legacy_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that legacy-file processing uses the adaptive batch sizer and records sizing calls.
    
    Asserts that processing five test files produces five successful results, that the provided batch sizer's
    calculate_batch_size was called exactly once, adjust_from_feedback was called twice, and that the sizes
    passed to calculate_batch_size match the files' on-disk sizes.
    """
    files = _make_files(tmp_path, 5)
    sizer = _FixedBatchSizer(chunk_size=2, adjusted_size=2)
    monitor = _MonitorStub(should_evict_value=False)
    orchestrator = PipelineOrchestrator(
        PipelineConfig(output_directory=tmp_path / "out"),
        batch_sizer=sizer,  # type: ignore[arg-type]
        resource_monitor=monitor,  # type: ignore[arg-type]
    )

    legacy_stub = Mock(
        side_effect=lambda path: ProcessingResult(
            file_path=path,
            success=True,
            dry_run=True,
        )
    )
    monkeypatch.setattr(orchestrator, "_process_file_legacy", legacy_stub)

    results = orchestrator.process_batch(files)

    assert len(results) == 5
    assert all(result.success for result in results)
    assert len(sizer.calculate_calls) == 1
    assert len(sizer.adjust_calls) == 2
    assert sizer.calculate_calls[0][0] == [path.stat().st_size for path in files]


def test_memory_pressure_shrinks_buffer_pool(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    files = _make_files(tmp_path, 3)
    sizer = _FixedBatchSizer(chunk_size=2, adjusted_size=2)
    monitor = _MonitorStub(should_evict_value=True)
    pool = BufferPool(buffer_size=256, initial_buffers=2, max_buffers=8)
    assert pool.resize(6) == 6
    assert pool.total_buffers == 6

    orchestrator = PipelineOrchestrator(
        PipelineConfig(output_directory=tmp_path / "out"),
        batch_sizer=sizer,  # type: ignore[arg-type]
        buffer_pool=pool,
        resource_monitor=monitor,  # type: ignore[arg-type]
        memory_pressure_threshold_percent=85.0,
    )
    legacy_stub = Mock(
        side_effect=lambda path: ProcessingResult(
            file_path=path,
            success=True,
            dry_run=True,
        )
    )
    monkeypatch.setattr(orchestrator, "_process_file_legacy", legacy_stub)

    orchestrator.process_batch(files)

    assert pool.total_buffers == pool.initial_buffers
    assert monitor.should_evict_calls
    assert all(threshold == 85.0 for threshold in monitor.should_evict_calls)


def test_staged_batch_processing_returns_buffers_to_pool(tmp_path: Path) -> None:
    files = _make_files(tmp_path, 4)
    pool = BufferPool(buffer_size=128, initial_buffers=2, max_buffers=6)
    monitor = _MonitorStub(should_evict_value=False)
    sizer = _FixedBatchSizer(chunk_size=2, adjusted_size=2)
    orchestrator = PipelineOrchestrator(
        PipelineConfig(output_directory=tmp_path / "out"),
        stages=[_PassThroughStage()],
        prefetch_depth=0,
        batch_sizer=sizer,  # type: ignore[arg-type]
        buffer_pool=pool,
        resource_monitor=monitor,  # type: ignore[arg-type]
    )

    results = orchestrator.process_batch(files)

    assert len(results) == len(files)
    assert all(result.success for result in results)
    assert pool.in_use_count == 0
    assert pool.available_buffers == pool.total_buffers


def test_prefetch_with_replacement_stage_still_releases_buffers(tmp_path: Path) -> None:
    files = _make_files(tmp_path, 4)
    pool = BufferPool(buffer_size=128, initial_buffers=2, max_buffers=6)
    monitor = _MonitorStub(should_evict_value=False)
    sizer = _FixedBatchSizer(chunk_size=4, adjusted_size=4)
    orchestrator = PipelineOrchestrator(
        PipelineConfig(output_directory=tmp_path / "out"),
        stages=[_ReplacingStage()],
        prefetch_depth=2,
        prefetch_stages=1,
        batch_sizer=sizer,  # type: ignore[arg-type]
        buffer_pool=pool,
        resource_monitor=monitor,  # type: ignore[arg-type]
    )

    results = orchestrator.process_batch(files)

    assert len(results) == len(files)
    assert all(result.success for result in results)
    assert pool.in_use_count == 0
    assert pool.available_buffers == pool.total_buffers
