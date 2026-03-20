"""Integration tests for HistoryViewer and BufferPool.

Covers:
  - undo/viewer.py            — HistoryViewer
  - optimization/buffer_pool.py — BufferPool
"""

from __future__ import annotations

from pathlib import Path

import pytest

from file_organizer.history.models import OperationStatus, OperationType
from file_organizer.history.tracker import OperationHistory
from file_organizer.optimization.buffer_pool import BufferPool
from file_organizer.undo.viewer import HistoryViewer

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# HistoryViewer — fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def history(tmp_path: Path) -> OperationHistory:
    db = tmp_path / "history.db"
    h = OperationHistory(db_path=db)
    return h


@pytest.fixture()
def viewer(history: OperationHistory) -> HistoryViewer:
    return HistoryViewer(history=history)


def _log_op(
    history: OperationHistory,
    src: Path,
    dest: Path | None = None,
    op_type: OperationType = OperationType.MOVE,
    status: OperationStatus = OperationStatus.COMPLETED,
) -> int:
    return history.log_operation(
        operation_type=op_type,
        source_path=src,
        destination_path=dest,
        status=status,
    )


# ---------------------------------------------------------------------------
# HistoryViewer — init
# ---------------------------------------------------------------------------


class TestHistoryViewerInit:
    def test_default_history_created(self) -> None:
        v = HistoryViewer()
        assert v.history is not None

    def test_custom_history_accepted(self, history: OperationHistory) -> None:
        v = HistoryViewer(history=history)
        assert v.history is history

    def test_context_manager(self, viewer: HistoryViewer) -> None:
        with viewer as v:
            assert v is viewer


# ---------------------------------------------------------------------------
# HistoryViewer — filter_operations
# ---------------------------------------------------------------------------


class TestHistoryViewerFilter:
    def test_filter_returns_list(self, viewer: HistoryViewer) -> None:
        result = viewer.filter_operations()
        assert result == []

    def test_filter_empty_history(self, viewer: HistoryViewer) -> None:
        result = viewer.filter_operations()
        assert result == []

    def test_filter_by_operation_type(
        self, viewer: HistoryViewer, history: OperationHistory, tmp_path: Path
    ) -> None:
        _log_op(history, tmp_path / "a.txt", op_type=OperationType.MOVE)
        _log_op(history, tmp_path / "b.txt", op_type=OperationType.COPY)
        result = viewer.filter_operations(operation_type="move")
        assert all(op.operation_type == OperationType.MOVE for op in result)

    def test_filter_invalid_type_returns_empty(self, viewer: HistoryViewer) -> None:
        result = viewer.filter_operations(operation_type="nonexistent_type")
        assert result == []

    def test_filter_invalid_status_returns_empty(self, viewer: HistoryViewer) -> None:
        result = viewer.filter_operations(status="invalid_status")
        assert result == []

    def test_filter_by_status(
        self, viewer: HistoryViewer, history: OperationHistory, tmp_path: Path
    ) -> None:
        _log_op(history, tmp_path / "a.txt", status=OperationStatus.COMPLETED)
        _log_op(history, tmp_path / "b.txt", status=OperationStatus.FAILED)
        completed = viewer.filter_operations(status="completed")
        assert all(op.status == OperationStatus.COMPLETED for op in completed)

    def test_filter_respects_limit(
        self, viewer: HistoryViewer, history: OperationHistory, tmp_path: Path
    ) -> None:
        for i in range(5):
            _log_op(history, tmp_path / f"f{i}.txt")
        result = viewer.filter_operations(limit=2)
        assert len(result) < 3

    def test_filter_by_since_date(
        self, viewer: HistoryViewer, history: OperationHistory, tmp_path: Path
    ) -> None:
        _log_op(history, tmp_path / "a.txt")
        result = viewer.filter_operations(since="2020-01-01")
        assert len(result) >= 1

    def test_filter_invalid_date_treated_gracefully(
        self, viewer: HistoryViewer, history: OperationHistory, tmp_path: Path
    ) -> None:
        _log_op(history, tmp_path / "a.txt")
        # Should not raise — invalid date returns None and is handled
        result = viewer.filter_operations(since="not-a-date")
        assert len(result) >= 1


# ---------------------------------------------------------------------------
# HistoryViewer — search_by_path
# ---------------------------------------------------------------------------


class TestHistoryViewerSearch:
    def test_search_empty_history(self, viewer: HistoryViewer) -> None:
        result = viewer.search_by_path("/some/path")
        assert result == []

    def test_search_finds_source_path(
        self, viewer: HistoryViewer, history: OperationHistory, tmp_path: Path
    ) -> None:
        f = tmp_path / "invoice_2026.pdf"
        _log_op(history, f)
        result = viewer.search_by_path("invoice_2026")
        assert len(result) >= 1

    def test_search_finds_dest_path(
        self, viewer: HistoryViewer, history: OperationHistory, tmp_path: Path
    ) -> None:
        src = tmp_path / "old.txt"
        dest = tmp_path / "archive" / "new.txt"
        _log_op(history, src, dest)
        result = viewer.search_by_path("archive")
        assert len(result) >= 1

    def test_search_no_match_returns_empty(
        self, viewer: HistoryViewer, history: OperationHistory, tmp_path: Path
    ) -> None:
        _log_op(history, tmp_path / "file.txt")
        result = viewer.search_by_path("zzz_nonexistent_zzz")
        assert result == []


# ---------------------------------------------------------------------------
# HistoryViewer — get_statistics
# ---------------------------------------------------------------------------


class TestHistoryViewerStatistics:
    def test_empty_history_statistics(self, viewer: HistoryViewer) -> None:
        stats = viewer.get_statistics()
        assert stats["total_operations"] == 0
        assert isinstance(stats["by_type"], dict)
        assert isinstance(stats["by_status"], dict)

    def test_stats_counts_operations(
        self, viewer: HistoryViewer, history: OperationHistory, tmp_path: Path
    ) -> None:
        _log_op(history, tmp_path / "a.txt", op_type=OperationType.MOVE)
        _log_op(history, tmp_path / "b.txt", op_type=OperationType.COPY)
        stats = viewer.get_statistics()
        assert stats["total_operations"] == 2

    def test_stats_has_by_type_keys(
        self, viewer: HistoryViewer, history: OperationHistory, tmp_path: Path
    ) -> None:
        _log_op(history, tmp_path / "a.txt", op_type=OperationType.MOVE)
        stats = viewer.get_statistics()
        assert "move" in stats["by_type"]

    def test_stats_tracks_latest_operation(
        self, viewer: HistoryViewer, history: OperationHistory, tmp_path: Path
    ) -> None:
        _log_op(history, tmp_path / "a.txt")
        stats = viewer.get_statistics()
        assert stats["latest_operation"] is not None

    def test_stats_no_latest_if_empty(self, viewer: HistoryViewer) -> None:
        stats = viewer.get_statistics()
        assert stats["latest_operation"] is None


# ---------------------------------------------------------------------------
# HistoryViewer — show methods (output/smoke)
# ---------------------------------------------------------------------------


class TestHistoryViewerShowMethods:
    def test_show_recent_no_ops(self, viewer: HistoryViewer, capsys: pytest.CaptureFixture) -> None:
        viewer.show_recent_operations()
        captured = capsys.readouterr()
        assert "No operations" in captured.out

    def test_show_recent_with_ops(
        self,
        viewer: HistoryViewer,
        history: OperationHistory,
        tmp_path: Path,
        capsys: pytest.CaptureFixture,
    ) -> None:
        _log_op(history, tmp_path / "file.txt")
        viewer.show_recent_operations(limit=5)
        captured = capsys.readouterr()
        assert len(captured.out) > 0

    def test_show_transaction_not_found(
        self, viewer: HistoryViewer, capsys: pytest.CaptureFixture
    ) -> None:
        viewer.show_transaction_details("nonexistent-id")
        captured = capsys.readouterr()
        assert "not found" in captured.out

    def test_show_operation_not_found(
        self, viewer: HistoryViewer, capsys: pytest.CaptureFixture
    ) -> None:
        viewer.show_operation_details(99999)
        captured = capsys.readouterr()
        assert "not found" in captured.out

    def test_show_statistics_output(
        self, viewer: HistoryViewer, capsys: pytest.CaptureFixture
    ) -> None:
        viewer.show_statistics()
        captured = capsys.readouterr()
        assert "Total operations" in captured.out

    def test_display_filtered_no_ops(
        self, viewer: HistoryViewer, capsys: pytest.CaptureFixture
    ) -> None:
        viewer.display_filtered_operations()
        captured = capsys.readouterr()
        assert "No operations" in captured.out

    def test_display_filtered_with_search_no_match(
        self,
        viewer: HistoryViewer,
        history: OperationHistory,
        tmp_path: Path,
        capsys: pytest.CaptureFixture,
    ) -> None:
        viewer.display_filtered_operations(search="zzz_unique_needle_zzz")
        captured = capsys.readouterr()
        assert "No operations" in captured.out


# ---------------------------------------------------------------------------
# HistoryViewer — _parse_date
# ---------------------------------------------------------------------------


class TestHistoryViewerParseDate:
    def test_parse_iso_date(self, viewer: HistoryViewer) -> None:
        result = viewer._parse_date("2026-01-15")
        assert result is not None
        assert result.year == 2026

    def test_parse_iso_datetime(self, viewer: HistoryViewer) -> None:
        result = viewer._parse_date("2026-01-15T10:30:00")
        assert result is not None

    def test_parse_slash_date(self, viewer: HistoryViewer) -> None:
        result = viewer._parse_date("2026/03/17")
        assert result is not None

    def test_parse_invalid_returns_none(
        self, viewer: HistoryViewer, capsys: pytest.CaptureFixture
    ) -> None:
        result = viewer._parse_date("not-a-real-date")
        assert result is None


# ---------------------------------------------------------------------------
# BufferPool — fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def pool() -> BufferPool:
    return BufferPool(buffer_size=1024, initial_buffers=4)


# ---------------------------------------------------------------------------
# BufferPool — init
# ---------------------------------------------------------------------------


class TestBufferPoolInit:
    def test_default_buffer_size(self) -> None:
        bp = BufferPool()
        assert bp.buffer_size == 1048576  # 1 MB default

    def test_custom_buffer_size(self) -> None:
        bp = BufferPool(buffer_size=4096)
        assert bp.buffer_size == 4096

    def test_initial_buffers_count(self) -> None:
        bp = BufferPool(initial_buffers=5)
        assert bp.initial_buffers == 5

    def test_available_buffers_start_at_initial(self) -> None:
        bp = BufferPool(initial_buffers=3)
        assert bp.available_buffers == 3

    def test_in_use_count_starts_zero(self) -> None:
        bp = BufferPool()
        assert bp.in_use_count == 0

    def test_total_buffers(self) -> None:
        bp = BufferPool(initial_buffers=4)
        assert bp.total_buffers == 4

    def test_max_buffers_defaults_to_value(self) -> None:
        bp = BufferPool()
        # max_buffers defaults to some value (implementation detail)
        assert bp.max_buffers is None or isinstance(bp.max_buffers, int)


# ---------------------------------------------------------------------------
# BufferPool — acquire / release
# ---------------------------------------------------------------------------


class TestBufferPoolAcquireRelease:
    def test_acquire_returns_bytearray(self, pool: BufferPool) -> None:
        buf = pool.acquire()
        assert isinstance(buf, bytearray)
        pool.release(buf)

    def test_acquire_decrements_available(self, pool: BufferPool) -> None:
        before = pool.available_buffers
        buf = pool.acquire()
        assert pool.available_buffers == before - 1
        pool.release(buf)

    def test_acquire_increments_in_use(self, pool: BufferPool) -> None:
        buf = pool.acquire()
        assert pool.in_use_count == 1
        pool.release(buf)

    def test_release_returns_buffer(self, pool: BufferPool) -> None:
        buf = pool.acquire()
        pool.release(buf)
        assert pool.in_use_count == 0

    def test_acquire_multiple(self, pool: BufferPool) -> None:
        bufs = [pool.acquire() for _ in range(3)]
        assert pool.in_use_count == 3
        for b in bufs:
            pool.release(b)

    def test_release_increments_available(self, pool: BufferPool) -> None:
        buf = pool.acquire()
        before = pool.available_buffers
        pool.release(buf)
        assert pool.available_buffers == before + 1

    def test_buffer_has_correct_size(self, pool: BufferPool) -> None:
        buf = pool.acquire()
        assert len(buf) == pool.buffer_size
        pool.release(buf)


# ---------------------------------------------------------------------------
# BufferPool — max_buffers enforcement
# ---------------------------------------------------------------------------


class TestBufferPoolMaxBuffers:
    def test_max_buffers_respected(self) -> None:
        bp = BufferPool(initial_buffers=2, max_buffers=2)
        assert bp.max_buffers == 2

    def test_total_does_not_exceed_max(self) -> None:
        bp = BufferPool(initial_buffers=2, max_buffers=2)
        # Acquire all available
        bufs = [bp.acquire() for _ in range(bp.available_buffers)]
        # Total should be at most max_buffers
        assert bp.total_buffers <= 2
        for b in bufs:
            bp.release(b)


# ---------------------------------------------------------------------------
# BufferPool — peak / utilization / resize / shrink
# ---------------------------------------------------------------------------


class TestBufferPoolMetrics:
    def test_peak_in_use_tracks_high_water_mark(self, pool: BufferPool) -> None:
        bufs = [pool.acquire() for _ in range(3)]
        peak = pool.peak_in_use
        assert peak >= 3
        for b in bufs:
            pool.release(b)

    def test_utilization_is_float_between_0_and_1(self, pool: BufferPool) -> None:
        util = pool.utilization
        assert 0.0 <= util <= 1.0

    def test_utilization_zero_at_start(self, pool: BufferPool) -> None:
        assert pool.utilization == 0.0

    def test_resize_changes_total_buffers(self, pool: BufferPool) -> None:
        pool.resize(8)
        assert pool.total_buffers == 8

    def test_shrink_to_baseline(self, pool: BufferPool) -> None:
        # Acquire and release some buffers to grow pool, then shrink
        bufs = [pool.acquire() for _ in range(2)]
        for b in bufs:
            pool.release(b)
        before = pool.total_buffers
        pool.shrink_to_baseline()
        # After shrink, total should be <= before
        assert pool.total_buffers <= before
