"""Tests for hardware profile detection.

Mocks psutil, subprocess, and platform to test NVIDIA, Apple MPS,
and no-GPU detection scenarios without requiring actual hardware.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from file_organizer.core.hardware_profile import (
    GpuType,
    HardwareProfile,
    detect_hardware,
)

# ---------------------------------------------------------------------------
# HardwareProfile dataclass tests
# ---------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.unit
class TestHardwareProfile:
    """Test HardwareProfile properties and recommendations."""

    def _make_profile(
        self,
        *,
        gpu_type: GpuType = GpuType.NONE,
        gpu_name: str | None = None,
        vram_bytes: int = 0,
        ram_bytes: int = 16 * 1024**3,
        cpu_cores: int = 8,
    ) -> HardwareProfile:
        return HardwareProfile(
            gpu_type=gpu_type,
            gpu_name=gpu_name,
            vram_bytes=vram_bytes,
            ram_bytes=ram_bytes,
            cpu_cores=cpu_cores,
            os_name="Darwin",
            arch="arm64",
        )

    def test_vram_gb_property(self) -> None:
        profile = self._make_profile(vram_bytes=8 * 1024**3)
        assert profile.vram_gb == 8.0

    def test_vram_gb_zero_when_no_gpu(self) -> None:
        profile = self._make_profile(vram_bytes=0)
        assert profile.vram_gb == 0.0

    def test_ram_gb_property(self) -> None:
        profile = self._make_profile(ram_bytes=32 * 1024**3)
        assert profile.ram_gb == 32.0

    def test_recommends_7b_for_16gb_ram(self) -> None:
        profile = self._make_profile(ram_bytes=16 * 1024**3)
        assert "7b" in profile.recommended_text_model()

    def test_recommends_3b_for_8gb_ram(self) -> None:
        profile = self._make_profile(ram_bytes=8 * 1024**3)
        assert "3b" in profile.recommended_text_model()

    def test_recommends_3b_for_4gb_ram(self) -> None:
        profile = self._make_profile(ram_bytes=4 * 1024**3)
        assert "3b" in profile.recommended_text_model()

    def test_recommended_workers_half_cores(self) -> None:
        profile = self._make_profile(cpu_cores=8)
        assert profile.recommended_workers() == 4

    def test_recommended_workers_minimum_one(self) -> None:
        profile = self._make_profile(cpu_cores=1)
        assert profile.recommended_workers() == 1

    def test_to_dict_contains_all_fields(self) -> None:
        profile = self._make_profile(
            gpu_type=GpuType.NVIDIA,
            gpu_name="RTX 4090",
            vram_bytes=24 * 1024**3,
        )
        d = profile.to_dict()
        assert d["gpu_type"] == "nvidia"
        assert d["gpu_name"] == "RTX 4090"
        assert d["vram_gb"] == 24.0
        assert d["ram_gb"] == 16.0
        assert d["cpu_cores"] == 8
        assert d["os"] == "Darwin"
        assert d["arch"] == "arm64"
        assert d["recommended_text_model"] == profile.recommended_text_model()
        assert d["recommended_workers"] == profile.recommended_workers()

    def test_frozen_dataclass(self) -> None:
        profile = self._make_profile()
        with pytest.raises(AttributeError):
            profile.cpu_cores = 99  # type: ignore[misc]


# ---------------------------------------------------------------------------
# detect_hardware() integration tests with mocked subprocess
# ---------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.unit
class TestDetectHardware:
    """Test detect_hardware() under mocked subprocess and psutil."""

    @patch("file_organizer.core.hardware_profile._get_cpu_cores", return_value=10)
    @patch(
        "file_organizer.core.hardware_profile._get_system_ram",
        return_value=32 * 1024**3,
    )
    @patch("file_organizer.core.hardware_profile._detect_amd", return_value=(None, 0))
    @patch(
        "file_organizer.core.hardware_profile._detect_apple_mps",
        return_value=(None, 0),
    )
    @patch(
        "file_organizer.core.hardware_profile._detect_nvidia",
        return_value=("RTX 4090", 24 * 1024**3),
    )
    def test_nvidia_detection(
        self,
        _nv: MagicMock,
        _mps: MagicMock,
        _amd: MagicMock,
        _ram: MagicMock,
        _cpu: MagicMock,
    ) -> None:
        profile = detect_hardware()
        assert profile.gpu_type == GpuType.NVIDIA
        assert profile.gpu_name == "RTX 4090"
        assert profile.vram_gb == 24.0
        assert profile.ram_gb == 32.0
        assert profile.cpu_cores == 10

    @patch("file_organizer.core.hardware_profile._get_cpu_cores", return_value=8)
    @patch(
        "file_organizer.core.hardware_profile._get_system_ram",
        return_value=16 * 1024**3,
    )
    @patch("file_organizer.core.hardware_profile._detect_amd", return_value=(None, 0))
    @patch(
        "file_organizer.core.hardware_profile._detect_apple_mps",
        return_value=("Apple M2 Pro", 16 * 1024**3),
    )
    @patch(
        "file_organizer.core.hardware_profile._detect_nvidia",
        return_value=(None, 0),
    )
    def test_apple_mps_detection(
        self,
        _nv: MagicMock,
        _mps: MagicMock,
        _amd: MagicMock,
        _ram: MagicMock,
        _cpu: MagicMock,
    ) -> None:
        profile = detect_hardware()
        assert profile.gpu_type == GpuType.APPLE_MPS
        assert profile.gpu_name == "Apple M2 Pro"

    @patch("file_organizer.core.hardware_profile._get_cpu_cores", return_value=4)
    @patch(
        "file_organizer.core.hardware_profile._get_system_ram",
        return_value=8 * 1024**3,
    )
    @patch("file_organizer.core.hardware_profile._detect_amd", return_value=(None, 0))
    @patch(
        "file_organizer.core.hardware_profile._detect_apple_mps",
        return_value=(None, 0),
    )
    @patch(
        "file_organizer.core.hardware_profile._detect_nvidia",
        return_value=(None, 0),
    )
    def test_no_gpu_detection(
        self,
        _nv: MagicMock,
        _mps: MagicMock,
        _amd: MagicMock,
        _ram: MagicMock,
        _cpu: MagicMock,
    ) -> None:
        profile = detect_hardware()
        assert profile.gpu_type == GpuType.NONE
        assert profile.gpu_name is None
        assert profile.vram_bytes == 0

    @patch("file_organizer.core.hardware_profile._get_cpu_cores", return_value=16)
    @patch(
        "file_organizer.core.hardware_profile._get_system_ram",
        return_value=64 * 1024**3,
    )
    @patch(
        "file_organizer.core.hardware_profile._detect_amd",
        return_value=("Radeon RX 7900 XTX", 24 * 1024**3),
    )
    @patch(
        "file_organizer.core.hardware_profile._detect_apple_mps",
        return_value=(None, 0),
    )
    @patch(
        "file_organizer.core.hardware_profile._detect_nvidia",
        return_value=(None, 0),
    )
    def test_amd_detection(
        self,
        _nv: MagicMock,
        _mps: MagicMock,
        _amd: MagicMock,
        _ram: MagicMock,
        _cpu: MagicMock,
    ) -> None:
        profile = detect_hardware()
        assert profile.gpu_type == GpuType.AMD
        assert profile.gpu_name == "Radeon RX 7900 XTX"


# ---------------------------------------------------------------------------
# Low-level detection helper tests
# ---------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.unit
class TestDetectionHelpers:
    """Test individual GPU detection helpers."""

    @patch("subprocess.run")
    def test_nvidia_detect_success(self, mock_run: MagicMock) -> None:
        from file_organizer.core.hardware_profile import _detect_nvidia

        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="NVIDIA GeForce RTX 4090, 24564\n",
        )
        name, vram = _detect_nvidia()
        assert name == "NVIDIA GeForce RTX 4090"
        assert vram == int(24564 * 1024 * 1024)

    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_nvidia_detect_no_nvidia_smi(self, _: MagicMock) -> None:
        from file_organizer.core.hardware_profile import _detect_nvidia

        name, vram = _detect_nvidia()
        assert name is None
        assert vram == 0

    @patch("platform.system", return_value="Linux")
    def test_apple_mps_not_on_linux(self, _: MagicMock) -> None:
        from file_organizer.core.hardware_profile import _detect_apple_mps

        name, vram = _detect_apple_mps()
        assert name is None

    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_amd_detect_no_rocm_smi(self, _: MagicMock) -> None:
        from file_organizer.core.hardware_profile import _detect_amd

        name, vram = _detect_amd()
        assert name is None
        assert vram == 0
