"""System resource monitoring for intelligent model management.

Provides memory and GPU monitoring to inform cache eviction decisions
and prevent out-of-memory conditions during model loading.
"""

from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MemoryInfo:
    """System memory usage information.

    Attributes:
        rss: Resident set size in bytes (physical memory used by process).
        vms: Virtual memory size in bytes (total virtual memory used).
        percent: Percentage of total system memory used by this process.
    """

    rss: int
    vms: int
    percent: float


@dataclass(frozen=True)
class GpuMemoryInfo:
    """GPU memory usage information.

    Attributes:
        total: Total GPU memory in bytes.
        used: Used GPU memory in bytes.
        free: Free GPU memory in bytes.
        percent: Percentage of GPU memory used.
        device_name: Name/identifier of the GPU device.
    """

    total: int
    used: int
    free: int
    percent: float
    device_name: str


class ResourceMonitor:
    """Monitor system resources for model management decisions.

    Provides methods to query current memory and GPU usage to help
    determine when models should be evicted or when new models can
    be safely loaded.

    Example:
        >>> monitor = ResourceMonitor()
        >>> mem = monitor.get_memory_usage()
        >>> print(f"Process using {mem.percent:.1f}% of system memory")
        >>> if monitor.should_evict(threshold_percent=85.0):
        ...     cache.evict_lru()
    """

    def get_memory_usage(self) -> MemoryInfo:
        """Get current process memory usage.

        Attempts to use psutil if available, falling back to OS-specific
        methods.

        Returns:
            MemoryInfo with current memory statistics.
        """
        try:
            return self._get_memory_psutil()
        except ImportError:
            logger.debug("psutil not available, using fallback memory query")
            return self._get_memory_fallback()

    def get_gpu_memory(self) -> GpuMemoryInfo | None:
        """Get GPU memory usage if available.

        Queries NVIDIA GPUs via nvidia-smi. Returns None if no GPU is
        available or the query fails.

        Returns:
            GpuMemoryInfo if a GPU is detected, None otherwise.
        """
        try:
            return self._get_nvidia_gpu_memory()
        except (FileNotFoundError, subprocess.SubprocessError, ValueError):
            logger.debug("No NVIDIA GPU detected or nvidia-smi unavailable")
            return None

    def should_evict(self, threshold_percent: float = 85.0) -> bool:
        """Determine if models should be evicted based on memory pressure.

        Checks system memory usage against the threshold. If usage exceeds
        the threshold, returns True to suggest evicting cached models.

        Args:
            threshold_percent: Memory usage percentage above which eviction
                is recommended. Must be between 0 and 100.

        Returns:
            True if memory usage exceeds the threshold.

        Raises:
            ValueError: If threshold_percent is not between 0 and 100.
        """
        if not 0.0 <= threshold_percent <= 100.0:
            raise ValueError(
                f"threshold_percent must be between 0 and 100, got {threshold_percent}"
            )

        mem = self.get_memory_usage()
        should = mem.percent >= threshold_percent
        if should:
            logger.warning(
                "Memory pressure detected: %.1f%% >= %.1f%% threshold",
                mem.percent,
                threshold_percent,
            )
        return should

    def get_system_memory_total(self) -> int:
        """Get total system memory in bytes.

        Returns:
            Total system memory in bytes.
        """
        try:
            import psutil

            return int(psutil.virtual_memory().total)
        except ImportError:
            return self._get_total_memory_fallback()

    @staticmethod
    def _get_memory_psutil() -> MemoryInfo:
        """Get memory info using psutil.

        Returns:
            MemoryInfo from psutil process memory info.

        Raises:
            ImportError: If psutil is not installed.
        """
        import psutil

        process = psutil.Process(os.getpid())
        mem_info = process.memory_info()
        total_mem = psutil.virtual_memory().total
        percent = (mem_info.rss / total_mem) * 100.0 if total_mem > 0 else 0.0

        return MemoryInfo(
            rss=mem_info.rss,
            vms=mem_info.vms,
            percent=percent,
        )

    @staticmethod
    def _get_memory_fallback() -> MemoryInfo:
        """Get memory info using OS-specific fallback methods.

        Uses /proc/self/status on Linux or resource module on macOS/Unix.

        Returns:
            MemoryInfo with best-effort memory statistics.
        """
        rss = 0
        vms = 0

        # Try /proc/self/status (Linux)
        try:
            with open("/proc/self/status") as f:  # noqa: safedir-required  # read-only Linux proc FS — not a user-supplied path
                for line in f:
                    if line.startswith("VmRSS:"):
                        rss = int(line.split()[1]) * 1024  # Convert kB to bytes
                    elif line.startswith("VmSize:"):
                        vms = int(line.split()[1]) * 1024
        except FileNotFoundError:
            pass

        # Try resource module (macOS/Unix)
        if rss == 0:
            try:
                import resource

                usage = resource.getrusage(resource.RUSAGE_SELF)
                # On macOS, ru_maxrss is in bytes; on Linux, in kilobytes
                import sys

                if sys.platform == "darwin":
                    rss = usage.ru_maxrss
                else:
                    rss = usage.ru_maxrss * 1024
            except (ImportError, AttributeError):
                pass

        # Estimate percent from total memory
        total = ResourceMonitor._get_total_memory_fallback()
        percent = (rss / total) * 100.0 if total > 0 else 0.0

        return MemoryInfo(rss=rss, vms=vms, percent=percent)

    @staticmethod
    def _get_total_memory_fallback() -> int:
        """Get total system memory without psutil.

        Returns:
            Total memory in bytes, or 0 if unknown.
        """
        # Try /proc/meminfo (Linux)
        try:
            with open("/proc/meminfo") as f:  # noqa: safedir-required  # read-only Linux proc FS — not a user-supplied path
                for line in f:
                    if line.startswith("MemTotal:"):
                        return int(line.split()[1]) * 1024
        except FileNotFoundError:
            pass

        # Try sysctl (macOS)
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

        return 0

    @staticmethod
    def _get_nvidia_gpu_memory() -> GpuMemoryInfo | None:
        """Query NVIDIA GPU memory via nvidia-smi.

        Returns:
            GpuMemoryInfo for the first GPU, or None if unavailable.

        Raises:
            FileNotFoundError: If nvidia-smi is not found.
            subprocess.SubprocessError: If nvidia-smi command fails.
            ValueError: If output cannot be parsed.
        """
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,memory.used,memory.free",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            return None

        lines = result.stdout.strip().split("\n")
        if not lines or not lines[0].strip():
            return None

        # Parse first GPU
        parts = [p.strip() for p in lines[0].split(",")]
        if len(parts) < 4:
            return None

        device_name = parts[0]
        total_mib = float(parts[1])
        used_mib = float(parts[2])
        free_mib = float(parts[3])

        total_bytes = int(total_mib * 1024 * 1024)
        used_bytes = int(used_mib * 1024 * 1024)
        free_bytes = int(free_mib * 1024 * 1024)
        percent = (used_mib / total_mib) * 100.0 if total_mib > 0 else 0.0

        return GpuMemoryInfo(
            total=total_bytes,
            used=used_bytes,
            free=free_bytes,
            percent=percent,
            device_name=device_name,
        )
