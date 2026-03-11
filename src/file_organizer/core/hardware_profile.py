"""Hardware profiling for intelligent model and worker selection.

Detects GPU type, VRAM, system RAM, and CPU cores at startup to
auto-select appropriate model sizes and parallel worker counts.
Extends ``optimization.resource_monitor`` (NVIDIA-only) with Apple
MPS and AMD ROCm detection.
"""

from __future__ import annotations

import os
import platform
import subprocess
from dataclasses import dataclass
from enum import Enum
from typing import Any

from loguru import logger

# Model name constants — must match models/registry.py AVAILABLE_MODELS entries
_DEFAULT_TEXT_MODEL_SMALL = "qwen2.5:3b-instruct-q4_K_M"
_DEFAULT_TEXT_MODEL_LARGE = "qwen2.5:7b-instruct-q4_K_M"


class GpuType(Enum):
    """Detected GPU accelerator type."""

    NONE = "none"
    NVIDIA = "nvidia"
    APPLE_MPS = "apple_mps"
    AMD = "amd"


@dataclass(frozen=True)
class HardwareProfile:
    """Immutable snapshot of detected hardware capabilities.

    Attributes:
        gpu_type: Detected GPU accelerator (NVIDIA, Apple MPS, AMD, or None).
        gpu_name: Human-readable GPU device name, or ``None`` if no GPU.
        vram_bytes: GPU VRAM in bytes, or 0 if unavailable.
        ram_bytes: Total system RAM in bytes.
        cpu_cores: Number of logical CPU cores.
        os_name: Operating system identifier (``Darwin``, ``Linux``, etc.).
        arch: CPU architecture (``arm64``, ``x86_64``, etc.).
    """

    gpu_type: GpuType
    gpu_name: str | None
    vram_bytes: int
    ram_bytes: int
    cpu_cores: int
    os_name: str
    arch: str

    @property
    def vram_gb(self) -> float:
        """VRAM in gigabytes (rounded to 1 decimal)."""
        return round(self.vram_bytes / (1024**3), 1) if self.vram_bytes else 0.0

    @property
    def ram_gb(self) -> float:
        """System RAM in gigabytes (rounded to 1 decimal)."""
        return round(self.ram_bytes / (1024**3), 1) if self.ram_bytes else 0.0

    def recommended_text_model(self) -> str:
        """Suggest a text model name based on available RAM.

        Returns:
            Model identifier string suitable for Ollama.
        """
        ram_gb = self.ram_gb
        if ram_gb >= 16:
            return _DEFAULT_TEXT_MODEL_LARGE
        return _DEFAULT_TEXT_MODEL_SMALL

    def recommended_workers(self) -> int:
        """Suggest a default worker count for parallel processing.

        Uses half the logical core count (minimum 1) to leave headroom
        for model inference threads.

        Returns:
            Recommended ``max_workers`` value.
        """
        return max(1, self.cpu_cores // 2)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dictionary for JSON output."""
        return {
            "gpu_type": self.gpu_type.value,
            "gpu_name": self.gpu_name,
            "vram_gb": self.vram_gb,
            "ram_gb": self.ram_gb,
            "cpu_cores": self.cpu_cores,
            "os": self.os_name,
            "arch": self.arch,
            "recommended_text_model": self.recommended_text_model(),
            "recommended_workers": self.recommended_workers(),
        }


# ---------------------------------------------------------------------------
# Detection helpers
# ---------------------------------------------------------------------------


def _detect_nvidia() -> tuple[str | None, int]:
    """Detect NVIDIA GPU via ``nvidia-smi``.

    Returns:
        Tuple of (device_name, vram_bytes) or (None, 0) if unavailable.
    """
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return None, 0

        line = result.stdout.strip().split("\n")[0]
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 2:
            return None, 0

        name = parts[0]
        vram_mib = float(parts[1])
        return name, int(vram_mib * 1024 * 1024)
    except (FileNotFoundError, subprocess.SubprocessError, ValueError, IndexError):
        return None, 0


def _detect_apple_mps() -> tuple[str | None, int]:
    """Detect Apple Silicon GPU via system profiler.

    Returns:
        Tuple of (chip_name, unified_memory_bytes) or (None, 0).
    """
    if platform.system() != "Darwin":
        return None, 0

    try:
        # Check for ARM64 (Apple Silicon)
        result = subprocess.run(
            ["sysctl", "-n", "machdep.cpu.brand_string"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        brand = result.stdout.strip() if result.returncode == 0 else ""

        if "Apple" not in brand:
            return None, 0

        # Apple Silicon uses unified memory — report total system RAM as
        # "VRAM" since the GPU shares the same memory pool.
        mem_result = subprocess.run(
            ["sysctl", "-n", "hw.memsize"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        unified_mem = int(mem_result.stdout.strip()) if mem_result.returncode == 0 else 0
        return brand, unified_mem
    except (FileNotFoundError, subprocess.SubprocessError, ValueError):
        return None, 0


def _detect_amd() -> tuple[str | None, int]:
    """Detect AMD GPU via ``rocm-smi``.

    Returns:
        Tuple of (device_name, vram_bytes) or (None, 0).
    """
    try:
        result = subprocess.run(
            ["rocm-smi", "--showproductname", "--csv"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return None, 0

        lines = result.stdout.strip().split("\n")
        name = lines[1].split(",")[0].strip() if len(lines) > 1 else "AMD GPU"

        # Get VRAM
        mem_result = subprocess.run(
            ["rocm-smi", "--showmeminfo", "vram", "--csv"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        vram = 0
        if mem_result.returncode == 0:
            mem_lines = mem_result.stdout.strip().split("\n")
            if len(mem_lines) > 1:
                try:
                    vram = int(mem_lines[1].split(",")[0].strip())
                except (ValueError, IndexError):
                    pass

        return name, vram
    except (FileNotFoundError, subprocess.SubprocessError, ValueError):
        return None, 0


def _get_system_ram() -> int:
    """Get total system RAM in bytes."""
    try:
        import psutil

        return int(psutil.virtual_memory().total)
    except (ImportError, OSError):
        pass

    # Fallback: sysctl on macOS
    if platform.system() == "Darwin":
        try:
            result = subprocess.run(
                ["sysctl", "-n", "hw.memsize"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return int(result.stdout.strip())
        except (FileNotFoundError, subprocess.SubprocessError, ValueError):
            pass

    # Fallback: /proc/meminfo on Linux
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) * 1024
    except OSError:
        pass

    return 0


def _get_cpu_cores() -> int:
    """Get the number of logical CPU cores."""
    try:
        import psutil

        return psutil.cpu_count(logical=True) or 1
    except ImportError:
        return os.cpu_count() or 1


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def detect_hardware() -> HardwareProfile:
    """Detect hardware capabilities and build a profile.

    Probes GPU (NVIDIA → Apple MPS → AMD), system RAM, and CPU cores.
    Returns an immutable ``HardwareProfile`` snapshot.
    """
    gpu_type = GpuType.NONE
    gpu_name: str | None = None
    vram_bytes = 0

    # Try NVIDIA first (most common for ML workloads)
    name, vram = _detect_nvidia()
    if name:
        gpu_type = GpuType.NVIDIA
        gpu_name = name
        vram_bytes = vram
    else:
        # Try Apple MPS
        name, vram = _detect_apple_mps()
        if name:
            gpu_type = GpuType.APPLE_MPS
            gpu_name = name
            vram_bytes = vram
        else:
            # Try AMD ROCm
            name, vram = _detect_amd()
            if name:
                gpu_type = GpuType.AMD
                gpu_name = name
                vram_bytes = vram

    profile = HardwareProfile(
        gpu_type=gpu_type,
        gpu_name=gpu_name,
        vram_bytes=vram_bytes,
        ram_bytes=_get_system_ram(),
        cpu_cores=_get_cpu_cores(),
        os_name=platform.system(),
        arch=platform.machine(),
    )

    logger.info(
        "Hardware profile: {}, {}GB VRAM, {}GB RAM, {} cores",
        gpu_type.value,
        profile.vram_gb,
        profile.ram_gb,
        profile.cpu_cores,
    )

    return profile
