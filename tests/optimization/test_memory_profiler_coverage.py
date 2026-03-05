"""Coverage tests for file_organizer.optimization.memory_profiler module.

Targets uncovered branches: _get_rss Linux/macOS paths, _get_rss_vms
fallback paths, profile decorator exception handling, and
stop_tracking without start.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, mock_open, patch

import pytest

from file_organizer.optimization.memory_profiler import (
    MemoryProfiler,
    MemorySnapshot,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# _get_rss paths
# ---------------------------------------------------------------------------


class TestGetRssCoverage:
    """Test _get_rss with different system configurations."""

    def test_linux_proc_status(self) -> None:
        """Test reading VmRSS from /proc/self/status."""
        status = "VmPeak:   500000 kB\nVmRSS:    256000 kB\n"
        with patch("builtins.open", mock_open(read_data=status)):
            result = MemoryProfiler._get_rss()
        assert result == 256000 * 1024

    def test_macos_resource(self) -> None:
        """Test resource module on macOS (bytes)."""
        mock_resource = MagicMock()
        mock_resource.RUSAGE_SELF = 0
        mock_usage = MagicMock()
        mock_usage.ru_maxrss = 500_000_000
        mock_resource.getrusage.return_value = mock_usage

        with (
            patch("builtins.open", side_effect=FileNotFoundError),
            patch.dict("sys.modules", {"resource": mock_resource}),
            patch.object(sys, "platform", "darwin"),
        ):
            result = MemoryProfiler._get_rss()
        assert result == 500_000_000

    def test_linux_resource(self) -> None:
        """Test resource module on Linux (kilobytes)."""
        mock_resource = MagicMock()
        mock_resource.RUSAGE_SELF = 0
        mock_usage = MagicMock()
        mock_usage.ru_maxrss = 256000
        mock_resource.getrusage.return_value = mock_usage

        with (
            patch("builtins.open", side_effect=FileNotFoundError),
            patch.dict("sys.modules", {"resource": mock_resource}),
            patch.object(sys, "platform", "linux"),
        ):
            result = MemoryProfiler._get_rss()
        assert result == 256000 * 1024

    def test_no_rss_info(self) -> None:
        """Test when no RSS info is available returns zero."""
        with (
            patch("builtins.open", side_effect=FileNotFoundError),
            patch.dict("sys.modules", {"resource": None}),
        ):
            result = MemoryProfiler._get_rss()
        assert result == 0


# ---------------------------------------------------------------------------
# _get_rss_vms paths
# ---------------------------------------------------------------------------


class TestGetRssVmsCoverage:
    """Test _get_rss_vms with different system configurations."""

    def test_linux_proc_status(self) -> None:
        """Test reading both VmRSS and VmSize from /proc/self/status."""
        status = "VmSize:   400000 kB\nVmRSS:    256000 kB\n"
        with patch("builtins.open", mock_open(read_data=status)):
            rss, vms = MemoryProfiler._get_rss_vms()
        assert rss == 256000 * 1024
        assert vms == 400000 * 1024

    def test_fallback_when_proc_missing(self) -> None:
        """Test fallback when /proc/self/status is missing."""
        mock_resource = MagicMock()
        mock_resource.RUSAGE_SELF = 0
        mock_usage = MagicMock()
        mock_usage.ru_maxrss = 500_000_000
        mock_resource.getrusage.return_value = mock_usage

        with (
            patch("builtins.open", side_effect=FileNotFoundError),
            patch.dict("sys.modules", {"resource": mock_resource}),
            patch.object(sys, "platform", "darwin"),
        ):
            rss, vms = MemoryProfiler._get_rss_vms()
        assert rss == 500_000_000
        assert vms == 0  # VMS not available from resource module

    def test_linux_resource_fallback(self) -> None:
        """Test resource module on Linux (kilobytes)."""
        mock_resource = MagicMock()
        mock_resource.RUSAGE_SELF = 0
        mock_usage = MagicMock()
        mock_usage.ru_maxrss = 256000
        mock_resource.getrusage.return_value = mock_usage

        with (
            patch("builtins.open", side_effect=FileNotFoundError),
            patch.dict("sys.modules", {"resource": mock_resource}),
            patch.object(sys, "platform", "linux"),
        ):
            rss, vms = MemoryProfiler._get_rss_vms()
        assert rss == 256000 * 1024
        assert vms == 0  # VMS not available from resource module

    def test_no_info_returns_zeros(self) -> None:
        """Test when no memory info is available."""
        with (
            patch("builtins.open", side_effect=FileNotFoundError),
            patch.dict("sys.modules", {"resource": None}),
        ):
            rss, vms = MemoryProfiler._get_rss_vms()
        assert rss == 0
        assert vms == 0


# ---------------------------------------------------------------------------
# Profile decorator - exception in profiled function
# ---------------------------------------------------------------------------


class TestProfileDecoratorExceptions:
    """Test profile decorator when profiled function raises."""

    @patch.object(MemoryProfiler, "_get_rss", return_value=100_000_000)
    def test_profile_reraises_exception(self, mock_rss: MagicMock) -> None:
        """Test that exceptions in profiled functions propagate."""
        profiler = MemoryProfiler()

        @profiler.profile
        def failing_func() -> None:
            raise ValueError("test error")

        with pytest.raises(ValueError, match="test error"):
            failing_func()

        # The exception prevents execution from reaching the code after
        # the try/finally block, so last_result is never assigned.
        assert profiler.last_result is None


# ---------------------------------------------------------------------------
# Tracking edge cases
# ---------------------------------------------------------------------------


class TestTrackingEdgeCases:
    """Test tracking edge cases."""

    @patch.object(
        MemoryProfiler,
        "_get_rss_vms",
        return_value=(100_000_000, 200_000_000),
    )
    @patch.object(MemoryProfiler, "_get_top_objects", return_value=[])
    def test_multiple_start_tracking_resets(
        self, mock_objects: MagicMock, mock_rss_vms: MagicMock
    ) -> None:
        """Test that calling start_tracking again resets snapshots."""
        profiler = MemoryProfiler()
        profiler.start_tracking()
        profiler.add_snapshot()
        profiler.add_snapshot()
        # Restart tracking
        profiler.start_tracking(interval_seconds=0.5)
        timeline = profiler.stop_tracking()
        # Should only have start + stop = 2 snapshots
        assert len(timeline.snapshots) == 2
        assert timeline.interval_seconds == 0.5

    @patch.object(
        MemoryProfiler,
        "_get_rss_vms",
        return_value=(100_000_000, 200_000_000),
    )
    @patch.object(MemoryProfiler, "_get_top_objects", return_value=[])
    def test_add_snapshot_returns_snapshot(
        self, mock_objects: MagicMock, mock_rss_vms: MagicMock
    ) -> None:
        """Test that add_snapshot returns the snapshot."""
        profiler = MemoryProfiler()
        profiler.start_tracking()
        snap = profiler.add_snapshot()
        assert isinstance(snap, MemorySnapshot)
        assert snap.rss == 100_000_000
        profiler.stop_tracking()


# ---------------------------------------------------------------------------
# _get_top_objects edge cases
# ---------------------------------------------------------------------------


class TestGetTopObjectsCoverage:
    """Additional coverage for _get_top_objects."""

    def test_limit_zero(self) -> None:
        """Test with limit=0 returns empty list."""
        result = MemoryProfiler._get_top_objects(limit=0)
        assert result == []

    def test_limit_one(self) -> None:
        """Test with limit=1 returns single item."""
        result = MemoryProfiler._get_top_objects(limit=1)
        assert len(result) == 1
