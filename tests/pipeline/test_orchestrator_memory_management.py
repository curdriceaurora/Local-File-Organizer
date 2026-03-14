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
        self.calculate_calls: list[tuple[list[int], int]] = []
        self.adjust_calls: list[tuple[int, int]] = []

    def calculate_batch_size(self, file_sizes: list[int], overhead_per_file: int = 0) -> int:
        self.calculate_calls.append((list(file_sizes), overhead_per_file))
        return self.chunk_size

    def adjust_from_feedback(self, actual_memory: int, batch_size: int) -> int:
        self.adjust_calls.append((actual_memory, batch_size))
        return self.adjusted_size


@dataclass
class _MonitorStub:
    should_evict_value: bool = False
    rss_value: int = 42_000_000

    def __post_init__(self) -> None:
        self.should_evict_calls: list[float] = []

    def should_evict(self, threshold_percent: float = 85.0) -> bool:
        self.should_evict_calls.append(threshold_percent)
        return self.should_evict_value

    def get_memory_usage(self) -> MemoryInfo:
        return MemoryInfo(rss=self.rss_value, vms=self.rss_value * 2, percent=50.0)


class _PassThroughStage:
    @property
    def name(self) -> str:
        return "pass"

    def process(self, context: StageContext) -> StageContext:
        context.extra["visited"] = True
        return context


class _ReplacingStage:
    @property
    def name(self) -> str:
        return "replace"

    def process(self, context: StageContext) -> StageContext:
        return StageContext(file_path=context.file_path, dry_run=context.dry_run)


def _make_files(tmp_path: Path, count: int) -> list[Path]:
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
    assert pool.in_use_count == 0
    assert pool.available_buffers == pool.total_buffers
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
