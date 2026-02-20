"""Memory profiling for tracking allocations, peak usage, and timelines.

Provides decorators and context managers for profiling memory usage
of functions and code blocks, using only stdlib facilities.
"""

from __future__ import annotations

import functools
import gc
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


@dataclass(frozen=True)
class MemorySnapshot:
    """Point-in-time snapshot of process memory.

    Attributes:
        rss: Resident set size in bytes.
        vms: Virtual memory size in bytes.
        objects_by_type: Top types by object count as (type_name, count) pairs.
        timestamp: Monotonic timestamp when snapshot was taken.
    """

    rss: int
    vms: int
    objects_by_type: tuple[tuple[str, int], ...]
    timestamp: float


@dataclass(frozen=True)
class ProfileResult:
    """Result of profiling a function call.

    Attributes:
        peak_memory: Peak RSS observed during the call in bytes.
        allocated: Estimated bytes allocated (RSS increase).
        freed: Estimated bytes freed (positive means memory was released).
        duration_ms: Wall-clock duration in milliseconds.
        func_name: Name of the profiled function.
    """

    peak_memory: int
    allocated: int
    freed: int
    duration_ms: float
    func_name: str


@dataclass
class MemoryTimeline:
    """Series of memory snapshots taken at intervals.

    Attributes:
        snapshots: Ordered list of MemorySnapshot instances.
        interval_seconds: Interval between snapshots.
    """

    snapshots: list[MemorySnapshot] = field(default_factory=list)
    interval_seconds: float = 0.0


class MemoryProfiler:
    """Profile memory usage of functions and code blocks.

    Uses OS-level memory queries and gc/object introspection from
    the standard library only. No external dependencies required.

    Example:
        >>> profiler = MemoryProfiler()
        >>> @profiler.profile
        ... def my_func():
        ...     return [0] * 1_000_000
        >>> result = my_func()
    """

    def __init__(self) -> None:
        self._tracking: bool = False
        self._snapshots: list[MemorySnapshot] = []
        self._interval: float = 0.1
        self._last_profile_result: ProfileResult | None = None

    @property
    def last_result(self) -> ProfileResult | None:
        """Get the most recent profile result."""
        return self._last_profile_result

    def profile(self, func: F) -> F:
        """Decorator that profiles memory usage of a function.

        Captures RSS before and after the call, tracking peak memory
        and duration.

        Args:
            func: The function to profile.

        Returns:
            Wrapped function that stores ProfileResult in last_result.
        """

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            gc.collect()
            mem_before = self._get_rss()
            peak = mem_before

            start = time.monotonic()
            try:
                result = func(*args, **kwargs)
            finally:
                end = time.monotonic()
                gc.collect()
                mem_after = self._get_rss()
                peak = max(peak, mem_after)

            allocated = max(0, mem_after - mem_before)
            freed = max(0, mem_before - mem_after)
            duration_ms = (end - start) * 1000.0

            self._last_profile_result = ProfileResult(
                peak_memory=peak,
                allocated=allocated,
                freed=freed,
                duration_ms=duration_ms,
                func_name=func.__name__,
            )
            return result

        return wrapper  # type: ignore[return-value]

    def get_snapshot(self) -> MemorySnapshot:
        """Take a point-in-time memory snapshot.

        Returns:
            MemorySnapshot with current RSS, VMS, and top object types.
        """
        rss, vms = self._get_rss_vms()
        objects_by_type = self._get_top_objects(limit=10)
        return MemorySnapshot(
            rss=rss,
            vms=vms,
            objects_by_type=tuple(objects_by_type),
            timestamp=time.monotonic(),
        )

    def start_tracking(self, interval_seconds: float = 0.1) -> None:
        """Begin collecting periodic memory snapshots.

        Snapshots are collected when stop_tracking is called or
        when add_snapshot is called manually.

        Args:
            interval_seconds: Desired interval between snapshots.
        """
        self._tracking = True
        self._interval = interval_seconds
        self._snapshots = []
        self._snapshots.append(self.get_snapshot())

    def stop_tracking(self) -> MemoryTimeline:
        """Stop tracking and return the collected timeline.

        Returns:
            MemoryTimeline with all collected snapshots.
        """
        if self._tracking:
            self._snapshots.append(self.get_snapshot())
        self._tracking = False
        timeline = MemoryTimeline(
            snapshots=list(self._snapshots),
            interval_seconds=self._interval,
        )
        self._snapshots = []
        return timeline

    def add_snapshot(self) -> MemorySnapshot:
        """Manually add a snapshot during tracking.

        Returns:
            The snapshot that was added.

        Raises:
            RuntimeError: If tracking has not been started.
        """
        if not self._tracking:
            raise RuntimeError("Tracking not started. Call start_tracking() first.")
        snapshot = self.get_snapshot()
        self._snapshots.append(snapshot)
        return snapshot

    @staticmethod
    def _get_rss() -> int:
        """Get current process RSS in bytes.

        Returns:
            RSS in bytes, or 0 if unavailable.
        """
        # Try /proc/self/status (Linux)
        try:
            with open("/proc/self/status") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        return int(line.split()[1]) * 1024
        except FileNotFoundError:
            pass

        # Try resource module (macOS/Unix)
        try:
            import resource

            usage = resource.getrusage(resource.RUSAGE_SELF)
            if sys.platform == "darwin":
                return usage.ru_maxrss
            return usage.ru_maxrss * 1024
        except (ImportError, AttributeError):
            pass

        return 0

    @staticmethod
    def _get_rss_vms() -> tuple[int, int]:
        """Get current process RSS and VMS in bytes.

        Returns:
            Tuple of (rss, vms) in bytes.
        """
        rss = 0
        vms = 0

        # Try /proc/self/status (Linux)
        try:
            with open("/proc/self/status") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        rss = int(line.split()[1]) * 1024
                    elif line.startswith("VmSize:"):
                        vms = int(line.split()[1]) * 1024
        except FileNotFoundError:
            pass

        # Fallback for RSS
        if rss == 0:
            try:
                import resource

                usage = resource.getrusage(resource.RUSAGE_SELF)
                if sys.platform == "darwin":
                    rss = usage.ru_maxrss
                else:
                    rss = usage.ru_maxrss * 1024
            except (ImportError, AttributeError):
                pass

        return rss, vms

    @staticmethod
    def _get_top_objects(limit: int = 10) -> list[tuple[str, int]]:
        """Get top object types by count from gc.

        Args:
            limit: Maximum number of types to return.

        Returns:
            List of (type_name, count) sorted by count descending.
        """
        type_counts: dict[str, int] = {}
        for obj in gc.get_objects():
            type_name = type(obj).__name__
            type_counts[type_name] = type_counts.get(type_name, 0) + 1

        sorted_types = sorted(type_counts.items(), key=lambda x: x[1], reverse=True)
        return sorted_types[:limit]
