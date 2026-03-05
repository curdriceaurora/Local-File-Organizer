"""Coverage tests for file_organizer.optimization.batch_sizer module.

Targets uncovered branches: per_file_cost <= 0, _get_available_memory
fallback paths, _get_total_memory sysctl path, _get_rss resource module
path, and adjust_from_feedback with actual_per_file <= 0.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, mock_open, patch

import pytest

from file_organizer.optimization.batch_sizer import AdaptiveBatchSizer

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# calculate_batch_size - per_file_cost <= 0 branch
# ---------------------------------------------------------------------------


class TestBatchSizerPerFileCostZero:
    """Test calculate_batch_size when per_file_cost is zero or negative."""

    @patch.object(
        AdaptiveBatchSizer,
        "_get_available_memory",
        return_value=1_000_000_000,
    )
    def test_zero_size_files_no_overhead(self, mock_mem: MagicMock) -> None:
        """When all file sizes are 0 and no overhead, per_file_cost = 0."""
        sizer = AdaptiveBatchSizer()
        file_sizes = [0] * 50
        batch_size = sizer.calculate_batch_size(file_sizes, overhead_per_file=0)
        # per_file_cost <= 0 => min(len(files), max_batch_size)
        assert batch_size == 50

    @patch.object(
        AdaptiveBatchSizer,
        "_get_available_memory",
        return_value=1_000_000_000,
    )
    def test_zero_size_files_capped_by_max(self, mock_mem: MagicMock) -> None:
        """Zero-cost files capped by max_batch_size."""
        sizer = AdaptiveBatchSizer()
        sizer.set_bounds(min_size=1, max_size=10)
        file_sizes = [0] * 50
        batch_size = sizer.calculate_batch_size(file_sizes, overhead_per_file=0)
        assert batch_size == 10


# ---------------------------------------------------------------------------
# _get_available_memory fallback paths
# ---------------------------------------------------------------------------


class TestGetAvailableMemory:
    """Test _get_available_memory with different system configurations."""

    def test_proc_meminfo_available(self) -> None:
        """Test reading from /proc/meminfo (MemAvailable line)."""
        meminfo = "MemTotal:       16384000 kB\nMemAvailable:   8192000 kB\n"
        with patch("builtins.open", mock_open(read_data=meminfo)):
            result = AdaptiveBatchSizer._get_available_memory()
        assert result == 8192000 * 1024

    def test_proc_meminfo_no_available_line(self) -> None:
        """Test /proc/meminfo without MemAvailable line falls through."""
        meminfo = "MemTotal:       16384000 kB\nMemFree:   4096000 kB\n"
        with patch("builtins.open", mock_open(read_data=meminfo)):
            # MemAvailable not found, falls through to total memory approach
            result = AdaptiveBatchSizer._get_available_memory()
        # Should still get a value through the fallback path
        assert isinstance(result, int)
        assert result >= 0

    def test_proc_meminfo_not_found_uses_total(self) -> None:
        """Test fallback when /proc/meminfo doesn't exist."""
        with (
            patch("builtins.open", side_effect=FileNotFoundError),
            patch.object(AdaptiveBatchSizer, "_get_total_memory", return_value=16_000_000_000),
            patch.object(AdaptiveBatchSizer, "_get_rss", return_value=1_000_000_000),
        ):
            result = AdaptiveBatchSizer._get_available_memory()
        assert result == 15_000_000_000  # total - rss

    def test_no_memory_info_returns_zero(self) -> None:
        """Test when no memory info is available at all."""
        with (
            patch("builtins.open", side_effect=FileNotFoundError),
            patch.object(AdaptiveBatchSizer, "_get_total_memory", return_value=0),
        ):
            result = AdaptiveBatchSizer._get_available_memory()
        assert result == 0


# ---------------------------------------------------------------------------
# _get_total_memory paths
# ---------------------------------------------------------------------------


class TestGetTotalMemory:
    """Test _get_total_memory with different system configurations."""

    def test_proc_meminfo(self) -> None:
        """Test reading MemTotal from /proc/meminfo."""
        meminfo = "MemTotal:       16384000 kB\nMemFree:   8192000 kB\n"
        with patch("builtins.open", mock_open(read_data=meminfo)):
            result = AdaptiveBatchSizer._get_total_memory()
        assert result == 16384000 * 1024

    def test_sysctl_fallback(self) -> None:
        """Test sysctl fallback (macOS)."""
        with (
            patch("builtins.open", side_effect=FileNotFoundError),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=0, stdout="17179869184\n")
            result = AdaptiveBatchSizer._get_total_memory()
        assert result == 17179869184

    def test_sysctl_fails(self) -> None:
        """Test when sysctl also fails."""
        with (
            patch("builtins.open", side_effect=FileNotFoundError),
            patch("subprocess.run", side_effect=FileNotFoundError),
        ):
            result = AdaptiveBatchSizer._get_total_memory()
        assert result == 0

    def test_sysctl_nonzero_exit(self) -> None:
        """Test sysctl with non-zero exit code."""
        with (
            patch("builtins.open", side_effect=FileNotFoundError),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=1, stdout="")
            result = AdaptiveBatchSizer._get_total_memory()
        assert result == 0


# ---------------------------------------------------------------------------
# _get_rss paths
# ---------------------------------------------------------------------------


class TestGetRss:
    """Test _get_rss with different system configurations."""

    def test_proc_self_status(self) -> None:
        """Test reading VmRSS from /proc/self/status."""
        status = "VmPeak:   500000 kB\nVmRSS:    256000 kB\nVmSize:   400000 kB\n"
        with patch("builtins.open", mock_open(read_data=status)):
            result = AdaptiveBatchSizer._get_rss()
        assert result == 256000 * 1024

    def test_resource_module_darwin(self) -> None:
        """Test resource module on macOS."""
        mock_resource = MagicMock()
        mock_resource.RUSAGE_SELF = 0
        mock_usage = MagicMock()
        mock_usage.ru_maxrss = 500_000_000  # bytes on macOS
        mock_resource.getrusage.return_value = mock_usage

        with (
            patch("builtins.open", side_effect=FileNotFoundError),
            patch.dict("sys.modules", {"resource": mock_resource}),
            patch.object(sys, "platform", "darwin"),
        ):
            result = AdaptiveBatchSizer._get_rss()
        assert result == 500_000_000

    def test_resource_module_linux(self) -> None:
        """Test resource module on Linux (kilobytes)."""
        mock_resource = MagicMock()
        mock_resource.RUSAGE_SELF = 0
        mock_usage = MagicMock()
        mock_usage.ru_maxrss = 256000  # kilobytes on Linux
        mock_resource.getrusage.return_value = mock_usage

        with (
            patch("builtins.open", side_effect=FileNotFoundError),
            patch.dict("sys.modules", {"resource": mock_resource}),
            patch.object(sys, "platform", "linux"),
        ):
            result = AdaptiveBatchSizer._get_rss()
        assert result == 256000 * 1024

    def test_no_rss_available(self) -> None:
        """Test when no RSS info is available."""
        with (
            patch("builtins.open", side_effect=FileNotFoundError),
            patch.dict("sys.modules", {"resource": None}),
        ):
            # resource import will raise due to None module
            result = AdaptiveBatchSizer._get_rss()
        # No RSS info available, should return 0
        assert result == 0


# ---------------------------------------------------------------------------
# adjust_from_feedback edge cases
# ---------------------------------------------------------------------------


class TestAdjustFromFeedbackCoverage:
    """Additional branches for adjust_from_feedback."""

    @patch.object(
        AdaptiveBatchSizer,
        "_get_available_memory",
        return_value=1_000_000_000,
    )
    def test_actual_per_file_zero(self, mock_mem: MagicMock) -> None:
        """Test when actual_memory=0 gives per_file=0, returns same batch_size."""
        sizer = AdaptiveBatchSizer()
        result = sizer.adjust_from_feedback(actual_memory=0, batch_size=10)
        # actual_per_file = 0/10 = 0, should return batch_size unchanged
        assert result == 10

    @patch.object(
        AdaptiveBatchSizer,
        "_get_available_memory",
        return_value=1_000_000_000,
    )
    def test_negative_batch_returns_min(self, mock_mem: MagicMock) -> None:
        """Test with negative batch_size returns min."""
        sizer = AdaptiveBatchSizer()
        result = sizer.adjust_from_feedback(actual_memory=1024, batch_size=-5)
        assert result == sizer.min_batch_size

    @patch.object(
        AdaptiveBatchSizer,
        "_get_available_memory",
        return_value=1_000_000_000,
    )
    def test_adjust_respects_min_bound(self, mock_mem: MagicMock) -> None:
        """Test that adjusted size respects min_batch_size."""
        sizer = AdaptiveBatchSizer(target_memory_percent=70.0)
        sizer.set_bounds(min_size=5, max_size=1000)
        # Budget=700M, actual=700M for 1 file => per_file=700M => new=1
        # But min is 5
        result = sizer.adjust_from_feedback(actual_memory=700_000_000, batch_size=1)
        assert result >= 5
