"""Adaptive batch sizing based on available memory.

Provides dynamic batch size calculation that adjusts based on
system memory constraints and runtime feedback.
"""

from __future__ import annotations

import logging
import sys

logger = logging.getLogger(__name__)


class AdaptiveBatchSizer:
    """Calculate batch sizes dynamically based on memory availability.

    Determines how many files to process in a single batch by
    considering available system memory, target utilization, and
    per-file overhead.

    Args:
        target_memory_percent: Target percentage of total system memory
            to use for batching (0.0 to 100.0).

    Example:
        >>> sizer = AdaptiveBatchSizer(target_memory_percent=70.0)
        >>> file_sizes = [1024 * 1024 * 5] * 100  # 100 files, 5MB each
        >>> batch_size = sizer.calculate_batch_size(file_sizes, overhead_per_file=1024)
        >>> print(f"Process {batch_size} files per batch")
    """

    def __init__(self, target_memory_percent: float = 70.0) -> None:
        """Set up the batch sizer targeting the given memory usage percentage."""
        if not 0.0 < target_memory_percent <= 100.0:
            raise ValueError(
                f"target_memory_percent must be between 0 and 100 "
                f"(exclusive of 0), got {target_memory_percent}"
            )
        self._target_memory_percent = target_memory_percent
        self._history: list[tuple[int, int]] = []
        self._min_batch_size = 1
        self._max_batch_size = 1000

    @property
    def target_memory_percent(self) -> float:
        """Target memory utilization percentage."""
        return self._target_memory_percent

    @property
    def min_batch_size(self) -> int:
        """Minimum allowed batch size."""
        return self._min_batch_size

    @property
    def max_batch_size(self) -> int:
        """Maximum allowed batch size."""
        return self._max_batch_size

    def set_bounds(self, min_size: int = 1, max_size: int = 1000) -> None:
        """Set minimum and maximum batch size bounds.

        Args:
            min_size: Minimum batch size (must be >= 1).
            max_size: Maximum batch size (must be >= min_size).

        Raises:
            ValueError: If bounds are invalid.
        """
        if min_size < 1:
            raise ValueError(f"min_size must be >= 1, got {min_size}")
        if max_size < min_size:
            raise ValueError(f"max_size ({max_size}) must be >= min_size ({min_size})")
        self._min_batch_size = min_size
        self._max_batch_size = max_size

    def calculate_batch_size(
        self,
        file_sizes: list[int],
        overhead_per_file: int = 0,
    ) -> int:
        """Calculate optimal batch size based on file sizes and memory.

        Estimates how many files from the list can fit in the target
        memory budget.

        Args:
            file_sizes: List of file sizes in bytes.
            overhead_per_file: Additional memory overhead per file in bytes
                (e.g., for metadata, intermediate buffers).

        Returns:
            Recommended batch size (number of files).
        """
        if not file_sizes:
            return self._min_batch_size

        available_memory = self._get_available_memory()
        if available_memory <= 0:
            return self._min_batch_size

        target_budget = int(available_memory * (self._target_memory_percent / 100.0))

        # Use average file size for estimation
        avg_file_size = sum(file_sizes) / len(file_sizes)
        per_file_cost = avg_file_size + overhead_per_file

        if per_file_cost <= 0:
            return min(len(file_sizes), self._max_batch_size)

        batch_size = int(target_budget / per_file_cost)

        # Apply bounds
        batch_size = max(self._min_batch_size, batch_size)
        batch_size = min(self._max_batch_size, batch_size)
        batch_size = min(len(file_sizes), batch_size)

        logger.debug(
            "Calculated batch size: %d (budget: %d bytes, per_file: %d bytes, files: %d)",
            batch_size,
            target_budget,
            int(per_file_cost),
            len(file_sizes),
        )

        return batch_size

    def adjust_from_feedback(
        self,
        actual_memory: int,
        batch_size: int,
    ) -> int:
        """Adjust batch size based on actual memory usage feedback.

        Learns from previous batch executions to refine future estimates.

        Args:
            actual_memory: Actual memory used in bytes for the last batch.
            batch_size: Batch size that was used.

        Returns:
            Adjusted batch size recommendation for next iteration.
        """
        if batch_size <= 0:
            return self._min_batch_size

        self._history.append((actual_memory, batch_size))

        available_memory = self._get_available_memory()
        if available_memory <= 0:
            return self._min_batch_size

        target_budget = int(available_memory * (self._target_memory_percent / 100.0))

        # Calculate actual per-file cost
        actual_per_file = actual_memory / batch_size

        if actual_per_file <= 0:
            return batch_size

        # Calculate new batch size based on actual cost
        new_batch_size = int(target_budget / actual_per_file)

        # Apply bounds
        new_batch_size = max(self._min_batch_size, new_batch_size)
        new_batch_size = min(self._max_batch_size, new_batch_size)

        logger.debug(
            "Adjusted batch size: %d -> %d (actual memory: %d bytes, per_file: %d bytes)",
            batch_size,
            new_batch_size,
            actual_memory,
            int(actual_per_file),
        )

        return new_batch_size

    def get_history(self) -> list[tuple[int, int]]:
        """Get the history of (actual_memory, batch_size) feedback pairs.

        Returns:
            List of (actual_memory_bytes, batch_size) tuples.
        """
        return list(self._history)

    def clear_history(self) -> None:
        """Clear the feedback history."""
        self._history = []

    @staticmethod
    def _get_available_memory() -> int:
        """Get available system memory in bytes.

        Returns:
            Available memory in bytes, or 0 if unknown.
        """
        # Try /proc/meminfo (Linux)
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemAvailable:"):
                        return int(line.split()[1]) * 1024
        except FileNotFoundError:
            pass

        # Try getting total memory and estimating available
        total = AdaptiveBatchSizer._get_total_memory()
        if total > 0:
            # Estimate: use total memory as upper bound
            # Subtract current RSS for a rough available estimate
            current_rss = AdaptiveBatchSizer._get_rss()
            available = total - current_rss
            return max(0, available)

        return 0

    @staticmethod
    def _get_total_memory() -> int:
        """Get total system memory in bytes.

        Returns:
            Total memory in bytes, or 0 if unknown.
        """
        # Try /proc/meminfo (Linux)
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        return int(line.split()[1]) * 1024
        except FileNotFoundError:
            pass

        # Try sysctl (macOS)
        try:
            import subprocess

            result = subprocess.run(
                ["sysctl", "-n", "hw.memsize"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return int(result.stdout.strip())
        except (FileNotFoundError, ImportError, ValueError):
            pass

        return 0

    @staticmethod
    def _get_rss() -> int:
        """Get current process RSS in bytes.

        Returns:
            RSS in bytes, or 0 if unavailable.
        """
        try:
            with open("/proc/self/status") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        return int(line.split()[1]) * 1024
        except FileNotFoundError:
            pass

        try:
            import resource

            usage = resource.getrusage(resource.RUSAGE_SELF)
            if sys.platform == "darwin":
                return usage.ru_maxrss
            return usage.ru_maxrss * 1024
        except (ImportError, AttributeError):
            pass

        return 0
