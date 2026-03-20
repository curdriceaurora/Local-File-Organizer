"""Coverage tests for file_organizer.optimization.resource_monitor module.

Targets uncovered branches: _get_memory_fallback Linux vs macOS paths,
_get_total_memory_fallback paths, get_system_memory_total,
_get_nvidia_gpu_memory parsing edge cases.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, mock_open, patch

import pytest

from file_organizer.optimization.resource_monitor import (
    MemoryInfo,
    ResourceMonitor,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# _get_memory_fallback
# ---------------------------------------------------------------------------


class TestGetMemoryFallback:
    """Test _get_memory_fallback with different system configs."""

    def test_linux_proc_status(self) -> None:
        """Test reading VmRSS and VmSize from /proc/self/status."""
        status = "VmSize:   400000 kB\nVmRSS:    256000 kB\nother: ignored\n"
        with (
            patch("builtins.open", mock_open(read_data=status)),
            patch.object(
                ResourceMonitor, "_get_total_memory_fallback", return_value=16_000_000_000
            ),
        ):
            result = ResourceMonitor._get_memory_fallback()
        assert result.rss == 256000 * 1024
        assert result.vms == 400000 * 1024
        assert result.percent > 0

    def test_macos_resource_fallback(self) -> None:
        """Test resource module fallback on macOS."""
        mock_resource = MagicMock()
        mock_resource.RUSAGE_SELF = 0
        mock_usage = MagicMock()
        mock_usage.ru_maxrss = 500_000_000
        mock_resource.getrusage.return_value = mock_usage

        with (
            patch("builtins.open", side_effect=FileNotFoundError),
            patch.dict("sys.modules", {"resource": mock_resource}),
            patch.object(sys, "platform", "darwin"),
            patch.object(
                ResourceMonitor, "_get_total_memory_fallback", return_value=16_000_000_000
            ),
        ):
            result = ResourceMonitor._get_memory_fallback()
        assert result.rss == 500_000_000

    def test_linux_resource_fallback(self) -> None:
        """Test resource module fallback on Linux (kB multiplied)."""
        mock_resource = MagicMock()
        mock_resource.RUSAGE_SELF = 0
        mock_usage = MagicMock()
        mock_usage.ru_maxrss = 256000
        mock_resource.getrusage.return_value = mock_usage

        with (
            patch("builtins.open", side_effect=FileNotFoundError),
            patch.dict("sys.modules", {"resource": mock_resource}),
            patch.object(sys, "platform", "linux"),
            patch.object(
                ResourceMonitor, "_get_total_memory_fallback", return_value=16_000_000_000
            ),
        ):
            result = ResourceMonitor._get_memory_fallback()
        assert result.rss == 256000 * 1024

    def test_no_memory_info_at_all(self) -> None:
        """Test when no memory info is available."""
        with (
            patch("builtins.open", side_effect=FileNotFoundError),
            patch.dict("sys.modules", {"resource": None}),
            patch.object(ResourceMonitor, "_get_total_memory_fallback", return_value=0),
        ):
            result = ResourceMonitor._get_memory_fallback()
        assert result.percent == 0.0


# ---------------------------------------------------------------------------
# _get_total_memory_fallback
# ---------------------------------------------------------------------------


class TestGetTotalMemoryFallback:
    """Test _get_total_memory_fallback paths."""

    def test_proc_meminfo(self) -> None:
        meminfo = "MemTotal:       16384000 kB\n"
        with patch("builtins.open", mock_open(read_data=meminfo)):
            result = ResourceMonitor._get_total_memory_fallback()
        assert result == 16384000 * 1024

    def test_sysctl_fallback(self) -> None:
        with (
            patch("builtins.open", side_effect=FileNotFoundError),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=0, stdout="17179869184\n")
            result = ResourceMonitor._get_total_memory_fallback()
        assert result == 17179869184

    def test_sysctl_fail(self) -> None:
        with (
            patch("builtins.open", side_effect=FileNotFoundError),
            patch("subprocess.run", side_effect=FileNotFoundError),
        ):
            result = ResourceMonitor._get_total_memory_fallback()
        assert result == 0

    def test_sysctl_nonzero_return(self) -> None:
        with (
            patch("builtins.open", side_effect=FileNotFoundError),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=1, stdout="")
            result = ResourceMonitor._get_total_memory_fallback()
        assert result == 0


# ---------------------------------------------------------------------------
# get_system_memory_total
# ---------------------------------------------------------------------------


class TestGetSystemMemoryTotal:
    """Test get_system_memory_total with/without psutil."""

    def test_with_psutil(self) -> None:
        mock_psutil = MagicMock()
        mock_psutil.virtual_memory.return_value = SimpleNamespace(total=16_000_000_000)
        with patch.dict("sys.modules", {"psutil": mock_psutil}):
            monitor = ResourceMonitor()
            result = monitor.get_system_memory_total()
        assert result == 16_000_000_000

    def test_without_psutil(self) -> None:
        with (
            patch.dict("sys.modules", {"psutil": None}),
            patch.object(ResourceMonitor, "_get_total_memory_fallback", return_value=8_000_000_000),
        ):
            monitor = ResourceMonitor()
            # psutil import will fail, falling back
            result = monitor.get_system_memory_total()
        # Should use fallback value
        assert isinstance(result, int) and result > 0


# ---------------------------------------------------------------------------
# _get_nvidia_gpu_memory additional parsing
# ---------------------------------------------------------------------------


class TestNvidiaGpuMemoryParsing:
    """Test _get_nvidia_gpu_memory parsing edge cases."""

    @patch("subprocess.run")
    def test_zero_total_mib(self, mock_run: MagicMock) -> None:
        """Test GPU with zero total MiB (percent calculation guard)."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Test GPU, 0, 0, 0\n",
        )
        result = ResourceMonitor._get_nvidia_gpu_memory()
        assert result is not None
        assert result.percent == 0.0

    @patch("subprocess.run")
    def test_insufficient_csv_parts(self, mock_run: MagicMock) -> None:
        """Test with fewer than 4 CSV parts."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="GPU Name, 1024\n",
        )
        result = ResourceMonitor._get_nvidia_gpu_memory()
        assert result is None

    @patch("subprocess.run")
    def test_whitespace_only_output(self, mock_run: MagicMock) -> None:
        """Test with whitespace-only output."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="   \n",
        )
        result = ResourceMonitor._get_nvidia_gpu_memory()
        assert result is None


# ---------------------------------------------------------------------------
# should_evict boundary values
# ---------------------------------------------------------------------------


class TestShouldEvictBoundary:
    """Test boundary values for should_evict."""

    def test_threshold_zero_is_valid(self) -> None:
        monitor = ResourceMonitor()
        with patch.object(
            ResourceMonitor,
            "get_memory_usage",
            return_value=MemoryInfo(rss=0, vms=0, percent=0.0),
        ):
            result = monitor.should_evict(threshold_percent=0.0)
        assert result is True  # 0.0 >= 0.0

    def test_threshold_100_with_low_usage(self) -> None:
        monitor = ResourceMonitor()
        with patch.object(
            ResourceMonitor,
            "get_memory_usage",
            return_value=MemoryInfo(rss=0, vms=0, percent=50.0),
        ):
            result = monitor.should_evict(threshold_percent=100.0)
        assert result is False
