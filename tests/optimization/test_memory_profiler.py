"""Tests for MemoryProfiler - memory tracking, profiling, and timeline snapshots."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.optimization.memory_profiler import (
    MemoryProfiler,
    MemorySnapshot,
    MemoryTimeline,
    ProfileResult,
)


@pytest.mark.unit
class TestMemorySnapshot:
    """Tests for the MemorySnapshot dataclass."""

    def test_create_snapshot(self) -> None:
        """Test creating a MemorySnapshot instance."""
        snapshot = MemorySnapshot(
            rss=100_000_000,
            vms=200_000_000,
            objects_by_type=(("list", 5000), ("dict", 3000)),
            timestamp=1234.5,
        )
        assert snapshot.rss == 100_000_000
        assert snapshot.vms == 200_000_000
        assert len(snapshot.objects_by_type) == 2
        assert snapshot.objects_by_type[0] == ("list", 5000)
        assert snapshot.timestamp == 1234.5

    def test_snapshot_frozen(self) -> None:
        """Test that MemorySnapshot is immutable."""
        snapshot = MemorySnapshot(rss=1024, vms=2048, objects_by_type=(), timestamp=0.0)
        with pytest.raises(AttributeError):
            snapshot.rss = 999  # type: ignore[misc]

    def test_snapshot_equality(self) -> None:
        """Test MemorySnapshot equality comparison."""
        snap1 = MemorySnapshot(rss=1024, vms=2048, objects_by_type=(), timestamp=1.0)
        snap2 = MemorySnapshot(rss=1024, vms=2048, objects_by_type=(), timestamp=1.0)
        assert snap1 == snap2

    def test_snapshot_with_empty_objects(self) -> None:
        """Test snapshot with no tracked objects."""
        snapshot = MemorySnapshot(rss=0, vms=0, objects_by_type=(), timestamp=0.0)
        assert snapshot.objects_by_type == ()


@pytest.mark.unit
class TestProfileResult:
    """Tests for the ProfileResult dataclass."""

    def test_create_profile_result(self) -> None:
        """Test creating a ProfileResult instance."""
        result = ProfileResult(
            peak_memory=500_000_000,
            allocated=100_000_000,
            freed=0,
            duration_ms=42.5,
            func_name="my_func",
        )
        assert result.peak_memory == 500_000_000
        assert result.allocated == 100_000_000
        assert result.freed == 0
        assert result.duration_ms == 42.5
        assert result.func_name == "my_func"

    def test_profile_result_frozen(self) -> None:
        """Test that ProfileResult is immutable."""
        result = ProfileResult(peak_memory=0, allocated=0, freed=0, duration_ms=0.0, func_name="f")
        with pytest.raises(AttributeError):
            result.peak_memory = 999  # type: ignore[misc]


@pytest.mark.unit
class TestMemoryTimeline:
    """Tests for the MemoryTimeline dataclass."""

    def test_create_empty_timeline(self) -> None:
        """Test creating an empty MemoryTimeline."""
        timeline = MemoryTimeline()
        assert timeline.snapshots == []
        assert timeline.interval_seconds == 0.0

    def test_create_timeline_with_snapshots(self) -> None:
        """Test creating a timeline with pre-populated snapshots."""
        snaps = [
            MemorySnapshot(rss=100, vms=200, objects_by_type=(), timestamp=1.0),
            MemorySnapshot(rss=150, vms=250, objects_by_type=(), timestamp=2.0),
        ]
        timeline = MemoryTimeline(snapshots=snaps, interval_seconds=1.0)
        assert len(timeline.snapshots) == 2
        assert timeline.interval_seconds == 1.0

    def test_timeline_is_mutable(self) -> None:
        """Test that MemoryTimeline allows adding snapshots."""
        timeline = MemoryTimeline()
        snap = MemorySnapshot(rss=100, vms=200, objects_by_type=(), timestamp=1.0)
        timeline.snapshots.append(snap)
        assert len(timeline.snapshots) == 1


@pytest.mark.unit
class TestMemoryProfilerInit:
    """Tests for MemoryProfiler initialization."""

    def test_default_init(self) -> None:
        """Test default initialization."""
        profiler = MemoryProfiler()
        assert profiler.last_result is None

    def test_no_tracking_initially(self) -> None:
        """Test that tracking is not active initially."""
        profiler = MemoryProfiler()
        assert profiler._tracking is False


@pytest.mark.unit
class TestMemoryProfilerProfile:
    """Tests for the profile decorator."""

    @patch.object(MemoryProfiler, "_get_rss", return_value=100_000_000)
    def test_profile_captures_result(self, mock_rss: MagicMock) -> None:
        """Test that profile decorator captures profiling data."""
        profiler = MemoryProfiler()

        @profiler.profile
        def sample_func() -> str:
            return "hello"

        result = sample_func()
        assert result == "hello"
        assert profiler.last_result is not None
        assert profiler.last_result.func_name == "sample_func"
        assert profiler.last_result.duration_ms >= 0.0

    @patch.object(MemoryProfiler, "_get_rss", return_value=100_000_000)
    def test_profile_preserves_function_name(self, mock_rss: MagicMock) -> None:
        """Test that the decorated function retains its name."""
        profiler = MemoryProfiler()

        @profiler.profile
        def my_named_function() -> None:
            pass

        assert my_named_function.__name__ == "my_named_function"

    def test_profile_records_duration(self) -> None:
        """Test that duration is recorded correctly."""
        profiler = MemoryProfiler()

        with patch.object(MemoryProfiler, "_get_rss", return_value=50_000_000):

            @profiler.profile
            def slow_func() -> None:
                time.sleep(0.05)

            slow_func()

        assert profiler.last_result is not None
        assert profiler.last_result.duration_ms >= 40.0

    def test_profile_detects_allocation(self) -> None:
        """Test that allocation is detected when RSS increases."""
        profiler = MemoryProfiler()
        call_count = 0

        def increasing_rss() -> int:
            nonlocal call_count
            call_count += 1
            if call_count <= 1:
                return 100_000_000  # Before
            return 150_000_000  # After

        with patch.object(MemoryProfiler, "_get_rss", side_effect=increasing_rss):

            @profiler.profile
            def allocating_func() -> list[int]:
                return [0] * 1000

            allocating_func()

        assert profiler.last_result is not None
        assert profiler.last_result.allocated == 50_000_000

    def test_profile_detects_freed_memory(self) -> None:
        """Test that freed memory is detected when RSS decreases."""
        profiler = MemoryProfiler()
        call_count = 0

        def decreasing_rss() -> int:
            nonlocal call_count
            call_count += 1
            if call_count <= 1:
                return 200_000_000  # Before
            return 150_000_000  # After

        with patch.object(MemoryProfiler, "_get_rss", side_effect=decreasing_rss):

            @profiler.profile
            def freeing_func() -> None:
                pass

            freeing_func()

        assert profiler.last_result is not None
        assert profiler.last_result.freed == 50_000_000
        assert profiler.last_result.allocated == 0

    @patch.object(MemoryProfiler, "_get_rss", return_value=100_000_000)
    def test_profile_with_arguments(self, mock_rss: MagicMock) -> None:
        """Test that profiled functions accept arguments correctly."""
        profiler = MemoryProfiler()

        @profiler.profile
        def add(a: int, b: int) -> int:
            return a + b

        result = add(3, 4)
        assert result == 7
        assert profiler.last_result is not None

    @patch.object(MemoryProfiler, "_get_rss", return_value=100_000_000)
    def test_profile_with_kwargs(self, mock_rss: MagicMock) -> None:
        """Test that profiled functions accept keyword arguments."""
        profiler = MemoryProfiler()

        @profiler.profile
        def greet(name: str, greeting: str = "Hello") -> str:
            return f"{greeting}, {name}"

        result = greet("World", greeting="Hi")
        assert result == "Hi, World"

    def test_profile_peak_memory(self) -> None:
        """Test that peak memory is the max of before/after RSS."""
        profiler = MemoryProfiler()
        call_count = 0

        def rss_values() -> int:
            nonlocal call_count
            call_count += 1
            if call_count <= 1:
                return 100_000_000
            return 300_000_000

        with patch.object(MemoryProfiler, "_get_rss", side_effect=rss_values):

            @profiler.profile
            def func() -> None:
                pass

            func()

        assert profiler.last_result is not None
        assert profiler.last_result.peak_memory == 300_000_000

    @patch.object(MemoryProfiler, "_get_rss", return_value=100_000_000)
    def test_profile_overwrites_last_result(self, mock_rss: MagicMock) -> None:
        """Test that subsequent calls overwrite last_result."""
        profiler = MemoryProfiler()

        @profiler.profile
        def func_a() -> None:
            pass

        @profiler.profile
        def func_b() -> None:
            pass

        func_a()
        assert profiler.last_result is not None
        assert profiler.last_result.func_name == "func_a"

        func_b()
        assert profiler.last_result.func_name == "func_b"


@pytest.mark.unit
class TestMemoryProfilerSnapshot:
    """Tests for get_snapshot method."""

    @patch.object(
        MemoryProfiler,
        "_get_rss_vms",
        return_value=(100_000_000, 200_000_000),
    )
    @patch.object(
        MemoryProfiler,
        "_get_top_objects",
        return_value=[("list", 5000), ("dict", 3000)],
    )
    def test_get_snapshot(self, mock_objects: MagicMock, mock_rss_vms: MagicMock) -> None:
        """Test getting a memory snapshot."""
        profiler = MemoryProfiler()
        snapshot = profiler.get_snapshot()

        assert snapshot.rss == 100_000_000
        assert snapshot.vms == 200_000_000
        assert len(snapshot.objects_by_type) == 2
        assert snapshot.timestamp > 0

    @patch.object(
        MemoryProfiler,
        "_get_rss_vms",
        return_value=(0, 0),
    )
    @patch.object(
        MemoryProfiler,
        "_get_top_objects",
        return_value=[],
    )
    def test_get_snapshot_zero_memory(
        self, mock_objects: MagicMock, mock_rss_vms: MagicMock
    ) -> None:
        """Test snapshot when memory info is unavailable."""
        profiler = MemoryProfiler()
        snapshot = profiler.get_snapshot()

        assert snapshot.rss == 0
        assert snapshot.vms == 0


@pytest.mark.unit
class TestMemoryProfilerTracking:
    """Tests for start_tracking/stop_tracking/add_snapshot."""

    @patch.object(
        MemoryProfiler,
        "_get_rss_vms",
        return_value=(100_000_000, 200_000_000),
    )
    @patch.object(
        MemoryProfiler,
        "_get_top_objects",
        return_value=[],
    )
    def test_start_stop_tracking(self, mock_objects: MagicMock, mock_rss_vms: MagicMock) -> None:
        """Test basic start/stop tracking flow."""
        profiler = MemoryProfiler()
        profiler.start_tracking(interval_seconds=0.5)
        timeline = profiler.stop_tracking()

        assert isinstance(timeline, MemoryTimeline)
        # Should have at least 2 snapshots (start + stop)
        assert len(timeline.snapshots) >= 2
        assert timeline.interval_seconds == 0.5

    @patch.object(
        MemoryProfiler,
        "_get_rss_vms",
        return_value=(100_000_000, 200_000_000),
    )
    @patch.object(
        MemoryProfiler,
        "_get_top_objects",
        return_value=[],
    )
    def test_add_snapshot_during_tracking(
        self, mock_objects: MagicMock, mock_rss_vms: MagicMock
    ) -> None:
        """Test manually adding snapshots during tracking."""
        profiler = MemoryProfiler()
        profiler.start_tracking()

        profiler.add_snapshot()
        profiler.add_snapshot()

        timeline = profiler.stop_tracking()
        # start snapshot + 2 manual + stop snapshot = 4
        assert len(timeline.snapshots) == 4

    def test_add_snapshot_without_tracking_raises(self) -> None:
        """Test that add_snapshot raises when not tracking."""
        profiler = MemoryProfiler()
        with pytest.raises(RuntimeError, match="Tracking not started"):
            profiler.add_snapshot()

    @patch.object(
        MemoryProfiler,
        "_get_rss_vms",
        return_value=(100_000_000, 200_000_000),
    )
    @patch.object(
        MemoryProfiler,
        "_get_top_objects",
        return_value=[],
    )
    def test_stop_tracking_clears_snapshots(
        self, mock_objects: MagicMock, mock_rss_vms: MagicMock
    ) -> None:
        """Test that stopping tracking clears internal state."""
        profiler = MemoryProfiler()
        profiler.start_tracking()
        profiler.stop_tracking()

        # Internal snapshots should be cleared
        assert profiler._snapshots == []
        assert profiler._tracking is False

    @patch.object(
        MemoryProfiler,
        "_get_rss_vms",
        return_value=(100_000_000, 200_000_000),
    )
    @patch.object(
        MemoryProfiler,
        "_get_top_objects",
        return_value=[],
    )
    def test_stop_tracking_without_start(
        self, mock_objects: MagicMock, mock_rss_vms: MagicMock
    ) -> None:
        """Test stop_tracking when tracking was never started."""
        profiler = MemoryProfiler()
        timeline = profiler.stop_tracking()

        # Should still return a valid timeline (empty)
        assert isinstance(timeline, MemoryTimeline)
        assert len(timeline.snapshots) == 0


@pytest.mark.unit
class TestMemoryProfilerTopObjects:
    """Tests for _get_top_objects static method."""

    def test_get_top_objects_returns_list(self) -> None:
        """Test that _get_top_objects returns a list of tuples."""
        result = MemoryProfiler._get_top_objects(limit=5)
        assert isinstance(result, list)
        assert len(result) <= 5
        for item in result:
            assert isinstance(item, tuple)
            assert len(item) == 2
            assert isinstance(item[0], str)
            assert isinstance(item[1], int)

    def test_get_top_objects_sorted_descending(self) -> None:
        """Test that results are sorted by count descending."""
        result = MemoryProfiler._get_top_objects(limit=10)
        if len(result) > 1:
            for i in range(len(result) - 1):
                assert result[i][1] >= result[i + 1][1]

    def test_get_top_objects_respects_limit(self) -> None:
        """Test that limit is respected."""
        result = MemoryProfiler._get_top_objects(limit=3)
        assert len(result) <= 3
