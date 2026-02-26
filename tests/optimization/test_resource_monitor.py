"""Tests for ResourceMonitor - system memory and GPU monitoring with mocked system calls."""

from __future__ import annotations

import subprocess
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.optimization.resource_monitor import (
    GpuMemoryInfo,
    MemoryInfo,
    ResourceMonitor,
)


@pytest.mark.unit
class TestMemoryInfo:
    """Tests for the MemoryInfo dataclass."""

    def test_create_memory_info(self) -> None:
        """Test creating a MemoryInfo instance."""
        info = MemoryInfo(rss=1024 * 1024, vms=2048 * 1024, percent=12.5)
        assert info.rss == 1024 * 1024
        assert info.vms == 2048 * 1024
        assert info.percent == 12.5

    def test_memory_info_frozen(self) -> None:
        """Test that MemoryInfo is immutable (frozen dataclass)."""
        info = MemoryInfo(rss=1024, vms=2048, percent=1.0)
        with pytest.raises(AttributeError):
            info.rss = 999  # type: ignore[misc]

    def test_memory_info_equality(self) -> None:
        """Test MemoryInfo equality comparison."""
        info1 = MemoryInfo(rss=1024, vms=2048, percent=1.0)
        info2 = MemoryInfo(rss=1024, vms=2048, percent=1.0)
        assert info1 == info2


@pytest.mark.unit
class TestGpuMemoryInfo:
    """Tests for the GpuMemoryInfo dataclass."""

    def test_create_gpu_memory_info(self) -> None:
        """Test creating a GpuMemoryInfo instance."""
        info = GpuMemoryInfo(
            total=8 * 1024 * 1024 * 1024,
            used=4 * 1024 * 1024 * 1024,
            free=4 * 1024 * 1024 * 1024,
            percent=50.0,
            device_name="NVIDIA RTX 4090",
        )
        assert info.total == 8 * 1024 * 1024 * 1024
        assert info.percent == 50.0
        assert info.device_name == "NVIDIA RTX 4090"

    def test_gpu_memory_info_frozen(self) -> None:
        """Test that GpuMemoryInfo is immutable."""
        info = GpuMemoryInfo(total=1024, used=512, free=512, percent=50.0, device_name="GPU")
        with pytest.raises(AttributeError):
            info.total = 999  # type: ignore[misc]


@pytest.mark.unit
class TestResourceMonitorMemory:
    """Tests for get_memory_usage with mocked psutil."""

    @patch("file_organizer.optimization.resource_monitor.ResourceMonitor._get_memory_psutil")
    def test_get_memory_usage_with_psutil(self, mock_psutil: MagicMock) -> None:
        """Test that psutil is preferred when available."""
        expected = MemoryInfo(rss=100_000_000, vms=200_000_000, percent=5.0)
        mock_psutil.return_value = expected

        monitor = ResourceMonitor()
        result = monitor.get_memory_usage()

        assert result == expected
        mock_psutil.assert_called_once()

    @patch(
        "file_organizer.optimization.resource_monitor.ResourceMonitor._get_memory_psutil",
        side_effect=ImportError("No module named 'psutil'"),
    )
    @patch("file_organizer.optimization.resource_monitor.ResourceMonitor._get_memory_fallback")
    def test_get_memory_usage_fallback(
        self, mock_fallback: MagicMock, mock_psutil: MagicMock
    ) -> None:
        """Test fallback when psutil is not available."""
        expected = MemoryInfo(rss=50_000_000, vms=0, percent=2.5)
        mock_fallback.return_value = expected

        monitor = ResourceMonitor()
        result = monitor.get_memory_usage()

        assert result == expected
        mock_fallback.assert_called_once()

    def test_get_memory_psutil_with_mock(self) -> None:
        """Test _get_memory_psutil with fully mocked psutil module."""
        mock_process_info = SimpleNamespace(
            rss=500_000_000,
            vms=1_000_000_000,
        )
        mock_process = MagicMock()
        mock_process.memory_info.return_value = mock_process_info

        mock_vm = SimpleNamespace(total=16_000_000_000)

        mock_psutil = MagicMock()
        mock_psutil.Process.return_value = mock_process
        mock_psutil.virtual_memory.return_value = mock_vm

        with patch.dict("sys.modules", {"psutil": mock_psutil}):
            result = ResourceMonitor._get_memory_psutil()

        assert result.rss == 500_000_000
        assert result.vms == 1_000_000_000
        expected_percent = (500_000_000 / 16_000_000_000) * 100.0
        assert abs(result.percent - expected_percent) < 0.01


@pytest.mark.unit
class TestResourceMonitorGPU:
    """Tests for GPU memory monitoring with mocked subprocess calls."""

    @patch("subprocess.run")
    def test_get_gpu_memory_nvidia(self, mock_run: MagicMock) -> None:
        """Test parsing nvidia-smi output."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="NVIDIA RTX 4090, 24576, 8192, 16384\n",
        )

        monitor = ResourceMonitor()
        result = monitor.get_gpu_memory()

        assert result is not None
        assert result.device_name == "NVIDIA RTX 4090"
        assert result.total == 24576 * 1024 * 1024
        assert result.used == 8192 * 1024 * 1024
        assert result.free == 16384 * 1024 * 1024
        assert abs(result.percent - (8192 / 24576 * 100)) < 0.01

    @patch("subprocess.run", side_effect=FileNotFoundError("nvidia-smi not found"))
    def test_get_gpu_memory_no_nvidia(self, mock_run: MagicMock) -> None:
        """Test that None is returned when nvidia-smi is not available."""
        monitor = ResourceMonitor()
        result = monitor.get_gpu_memory()
        assert result is None

    @patch("subprocess.run")
    def test_get_gpu_memory_nonzero_exit(self, mock_run: MagicMock) -> None:
        """Test that None is returned on nvidia-smi failure."""
        mock_run.return_value = MagicMock(returncode=1, stdout="")

        monitor = ResourceMonitor()
        result = monitor.get_gpu_memory()
        assert result is None

    @patch("subprocess.run")
    def test_get_gpu_memory_empty_output(self, mock_run: MagicMock) -> None:
        """Test that None is returned on empty nvidia-smi output."""
        mock_run.return_value = MagicMock(returncode=0, stdout="")

        monitor = ResourceMonitor()
        result = monitor.get_gpu_memory()
        assert result is None

    @patch("subprocess.run")
    def test_get_gpu_memory_malformed_output(self, mock_run: MagicMock) -> None:
        """Test that None is returned on malformed nvidia-smi output."""
        mock_run.return_value = MagicMock(returncode=0, stdout="garbage data\n")

        monitor = ResourceMonitor()
        result = monitor.get_gpu_memory()
        assert result is None

    @patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="nvidia-smi", timeout=10))
    def test_get_gpu_memory_timeout(self, mock_run: MagicMock) -> None:
        """Test that None is returned on nvidia-smi timeout."""
        monitor = ResourceMonitor()
        result = monitor.get_gpu_memory()
        assert result is None


@pytest.mark.unit
class TestResourceMonitorShouldEvict:
    """Tests for the should_evict decision method."""

    @patch.object(ResourceMonitor, "get_memory_usage")
    def test_should_evict_above_threshold(self, mock_mem: MagicMock) -> None:
        """Test that should_evict returns True when above threshold."""
        mock_mem.return_value = MemoryInfo(rss=0, vms=0, percent=90.0)

        monitor = ResourceMonitor()
        assert monitor.should_evict(threshold_percent=85.0) is True

    @patch.object(ResourceMonitor, "get_memory_usage")
    def test_should_not_evict_below_threshold(self, mock_mem: MagicMock) -> None:
        """Test that should_evict returns False when below threshold."""
        mock_mem.return_value = MemoryInfo(rss=0, vms=0, percent=50.0)

        monitor = ResourceMonitor()
        assert monitor.should_evict(threshold_percent=85.0) is False

    @patch.object(ResourceMonitor, "get_memory_usage")
    def test_should_evict_at_threshold(self, mock_mem: MagicMock) -> None:
        """Test that should_evict returns True when exactly at threshold."""
        mock_mem.return_value = MemoryInfo(rss=0, vms=0, percent=85.0)

        monitor = ResourceMonitor()
        assert monitor.should_evict(threshold_percent=85.0) is True

    def test_should_evict_invalid_threshold_high(self) -> None:
        """Test that invalid threshold raises ValueError."""
        monitor = ResourceMonitor()
        with pytest.raises(ValueError, match="threshold_percent must be between"):
            monitor.should_evict(threshold_percent=101.0)

    def test_should_evict_invalid_threshold_negative(self) -> None:
        """Test that negative threshold raises ValueError."""
        monitor = ResourceMonitor()
        with pytest.raises(ValueError, match="threshold_percent must be between"):
            monitor.should_evict(threshold_percent=-1.0)

    @patch.object(ResourceMonitor, "get_memory_usage")
    def test_should_evict_default_threshold(self, mock_mem: MagicMock) -> None:
        """Test default threshold of 85%."""
        mock_mem.return_value = MemoryInfo(rss=0, vms=0, percent=86.0)

        monitor = ResourceMonitor()
        assert monitor.should_evict() is True
