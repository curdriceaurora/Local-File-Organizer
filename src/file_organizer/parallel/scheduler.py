"""Task scheduling for parallel file processing.

This module provides file ordering strategies to optimize batch throughput,
such as processing small files first or grouping files by type.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from file_organizer._compat import StrEnum


class PriorityStrategy(StrEnum):
    """Strategy for ordering files before parallel processing."""

    SIZE_ASC = "size_asc"
    SIZE_DESC = "size_desc"
    TYPE_GROUPED = "type_grouped"
    CUSTOM = "custom"


class TaskScheduler:
    """Schedules files for parallel processing based on a priority strategy.

    The scheduler reorders a list of file paths to improve throughput.
    For example, processing small files first reduces average latency,
    while grouping by type can improve cache locality.
    """

    def schedule(
        self,
        files: list[Path],
        strategy: PriorityStrategy = PriorityStrategy.SIZE_ASC,
        priority_fn: Callable[[Path], int | float] | None = None,
    ) -> list[Path]:
        """Order files according to the given priority strategy.

        Args:
            files: List of file paths to schedule.
            strategy: Ordering strategy to apply.
            priority_fn: Custom sort key function, required when
                strategy is CUSTOM. Lower values are processed first.

        Returns:
            A new list of paths in the scheduled order.

        Raises:
            ValueError: If strategy is CUSTOM but no priority_fn is provided.
        """
        if not files:
            return []

        if strategy == PriorityStrategy.SIZE_ASC:
            return self._sort_by_size(files, reverse=False)

        if strategy == PriorityStrategy.SIZE_DESC:
            return self._sort_by_size(files, reverse=True)

        if strategy == PriorityStrategy.TYPE_GROUPED:
            return self._group_by_type(files)

        if strategy == PriorityStrategy.CUSTOM:
            if priority_fn is None:
                raise ValueError("priority_fn is required when strategy is CUSTOM")
            return sorted(files, key=priority_fn)

        # Unreachable with current enum, but satisfies exhaustiveness
        return list(files)  # pragma: no cover

    @staticmethod
    def _sort_by_size(files: list[Path], *, reverse: bool) -> list[Path]:
        """Sort files by size.

        Non-existent files are assigned size 0 so they sort to the front
        (ascending) and can fail fast during processing.

        Args:
            files: List of file paths.
            reverse: If True, sort largest first.

        Returns:
            Sorted list of paths.
        """

        def _safe_size(path: Path) -> int:
            try:
                return path.stat().st_size
            except OSError:
                return 0

        return sorted(files, key=_safe_size, reverse=reverse)

    @staticmethod
    def _group_by_type(files: list[Path]) -> list[Path]:
        """Group files by their suffix, then sort within each group by name.

        Files without a suffix are grouped under the empty string and placed
        last.

        Args:
            files: List of file paths.

        Returns:
            Grouped and sorted list of paths.
        """
        groups: dict[str, list[Path]] = {}
        for path in files:
            ext = path.suffix.lower()
            groups.setdefault(ext, []).append(path)

        result: list[Path] = []
        for ext in sorted(groups.keys(), key=lambda e: (e == "", e)):
            result.extend(sorted(groups[ext]))
        return result
