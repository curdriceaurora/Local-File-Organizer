"""Memory leak detection by tracking object count changes over time.

Monitors gc-tracked objects and identifies types whose instance counts
are consistently growing, which may indicate memory leaks.
"""

from __future__ import annotations

import gc
import logging
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LeakSuspect:
    """A type suspected of leaking memory.

    Attributes:
        type_name: Name of the suspected leaking type.
        count_delta: Net change in instance count since tracking started.
        size_delta: Estimated change in total size (bytes) for this type.
    """

    type_name: str
    count_delta: int
    size_delta: int


@dataclass(frozen=True)
class _TypeSnapshot:
    """Internal snapshot of a type's object count and estimated size.

    Attributes:
        count: Number of instances of this type.
        total_size: Estimated total size in bytes.
        timestamp: Monotonic timestamp of the snapshot.
    """

    count: int
    total_size: int
    timestamp: float


class LeakDetector:
    """Detect potential memory leaks by tracking object count growth.

    Monitors gc-tracked objects over time and reports types whose
    instance counts grow consistently, suggesting a memory leak.

    Uses only stdlib gc module for object introspection.

    Example:
        >>> detector = LeakDetector()
        >>> detector.start()
        >>> # ... run some code that might leak ...
        >>> suspects = detector.check()
        >>> for s in suspects:
        ...     print(f"{s.type_name}: +{s.count_delta} objects")
    """

    def __init__(
        self,
        min_count_delta: int = 10,
        ignore_types: set[str] | None = None,
    ) -> None:
        """Initialize the leak detector.

        Args:
            min_count_delta: Minimum count increase to consider a type
                as a leak suspect.
            ignore_types: Set of type names to ignore (e.g., framework
                internals that are known to grow).
        """
        if min_count_delta < 1:
            raise ValueError(f"min_count_delta must be >= 1, got {min_count_delta}")
        self._min_count_delta = min_count_delta
        self._ignore_types: set[str] = ignore_types or set()
        self._baseline: dict[str, _TypeSnapshot] | None = None
        self._started: bool = False
        self._check_count: int = 0

    @property
    def is_tracking(self) -> bool:
        """Whether leak detection is currently active."""
        return self._started

    @property
    def check_count(self) -> int:
        """Number of times check() has been called since start."""
        return self._check_count

    def start(self) -> None:
        """Start leak detection by capturing a baseline snapshot.

        Forces a garbage collection before taking the baseline to
        get accurate starting counts.
        """
        gc.collect()
        self._baseline = self._snapshot_types()
        self._started = True
        self._check_count = 0
        logger.debug(
            "Leak detector started with %d tracked types",
            len(self._baseline),
        )

    def stop(self) -> None:
        """Stop leak detection and clear the baseline."""
        self._started = False
        self._baseline = None
        self._check_count = 0
        logger.debug("Leak detector stopped")

    def check(self) -> list[LeakSuspect]:
        """Check for potential memory leaks since start().

        Compares current object counts against the baseline and
        identifies types with significant count increases.

        Returns:
            List of LeakSuspect instances sorted by count_delta descending.

        Raises:
            RuntimeError: If start() has not been called.
        """
        if not self._started or self._baseline is None:
            raise RuntimeError("Leak detector not started. Call start() first.")

        self._check_count += 1
        gc.collect()
        current = self._snapshot_types()

        suspects: list[LeakSuspect] = []
        for type_name, current_snap in current.items():
            if type_name in self._ignore_types:
                continue

            baseline = self._baseline
            assert baseline is not None
            baseline_snap = baseline.get(type_name)
            if baseline_snap is None:
                # New type that appeared after baseline
                count_delta = current_snap.count
                size_delta = current_snap.total_size
            else:
                count_delta = current_snap.count - baseline_snap.count
                size_delta = current_snap.total_size - baseline_snap.total_size

            if count_delta >= self._min_count_delta:
                suspects.append(
                    LeakSuspect(
                        type_name=type_name,
                        count_delta=count_delta,
                        size_delta=size_delta,
                    )
                )

        # Sort by count_delta descending
        suspects.sort(key=lambda s: s.count_delta, reverse=True)

        if suspects:
            logger.warning(
                "Leak detector found %d suspect types (check #%d)",
                len(suspects),
                self._check_count,
            )

        return suspects

    def reset_baseline(self) -> None:
        """Reset the baseline to current state.

        Useful after expected growth (e.g., initialization) to start
        fresh leak detection.

        Raises:
            RuntimeError: If start() has not been called.
        """
        if not self._started:
            raise RuntimeError("Leak detector not started. Call start() first.")
        gc.collect()
        self._baseline = self._snapshot_types()
        self._check_count = 0
        logger.debug("Leak detector baseline reset")

    @staticmethod
    def _snapshot_types() -> dict[str, _TypeSnapshot]:
        """Take a snapshot of all gc-tracked object types.

        Returns:
            Dict mapping type names to their snapshot data.
        """
        import sys as _sys

        type_counts: dict[str, int] = {}
        type_sizes: dict[str, int] = {}
        now = time.monotonic()

        for obj in gc.get_objects():
            type_name = type(obj).__name__
            type_counts[type_name] = type_counts.get(type_name, 0) + 1
            try:
                type_sizes[type_name] = type_sizes.get(type_name, 0) + _sys.getsizeof(obj)
            except TypeError:
                # Some objects don't support getsizeof
                pass

        result: dict[str, _TypeSnapshot] = {}
        for type_name, count in type_counts.items():
            result[type_name] = _TypeSnapshot(
                count=count,
                total_size=type_sizes.get(type_name, 0),
                timestamp=now,
            )

        return result
