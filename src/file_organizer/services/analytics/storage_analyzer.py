"""Storage analysis module.

Analyzes storage usage, file distributions, and identifies optimization opportunities.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from file_organizer.core.path_guard import safe_walk

from ...models.analytics import FileDistribution, FileInfo, StorageStats

logger = logging.getLogger(__name__)


class StorageAnalyzer:
    """Analyzes storage usage and file organization patterns.

    Features:
    - Directory size analysis
    - File type distribution
    - Large file identification
    - Storage trend tracking
    """

    def __init__(self) -> None:
        """Initialize the storage analyzer."""
        self.cache_ttl = 3600  # 1 hour cache TTL
        self._cache: dict[str, Any] = {}

    def analyze_directory(
        self, path: Path, max_depth: int | None = None, use_cache: bool = True
    ) -> StorageStats:
        """Analyze storage usage in a directory.

        Args:
            path: Directory path to analyze
            max_depth: Maximum depth to traverse (None = unlimited)
            use_cache: Use cached results if available

        Returns:
            StorageStats object with analysis results
        """
        if not path.exists() or not path.is_dir():
            raise ValueError(f"Invalid directory: {path}")

        cache_key = f"{path}_{max_depth}"

        if use_cache and cache_key in self._cache:
            cached_time, cached_stats = self._cache[cache_key]
            if (datetime.now(UTC) - cached_time).seconds < self.cache_ttl:
                logger.debug(f"Using cached analysis for {path}")
                return cached_stats  # type: ignore[no-any-return]

        logger.info(f"Analyzing directory: {path}")

        files_list, directory_count = self._scan(path, max_depth)

        total_size = 0
        size_by_type: dict[str, int] = {}
        for info in files_list:
            total_size += info.size
            size_by_type[info.type] = size_by_type.get(info.type, 0) + info.size
        file_count = len(files_list)

        # Find largest files
        largest_files = sorted(files_list, key=lambda f: f.size, reverse=True)[:20]

        stats = StorageStats(
            all_files=files_list,
            total_size=total_size,
            organized_size=total_size,  # Would be calculated from organized files
            saved_size=0,  # Would be calculated from deduplication
            file_count=file_count,
            directory_count=directory_count,
            largest_files=largest_files,
            size_by_type=size_by_type,
        )

        # Cache results
        self._cache[cache_key] = (datetime.now(UTC), stats)

        logger.info(
            f"Analysis complete: {file_count} files, "
            f"{stats.formatted_total_size}, "
            f"{directory_count} directories"
        )

        return stats

    def _scan(self, path: Path, max_depth: int | None = None) -> tuple[list[FileInfo], int]:
        """Walk *path* once, returning every file plus the directory count.

        The single traversal behind :meth:`analyze_directory`, extracted so its
        result can be reused instead of re-walked (#1672).

        ``item.stat()`` is called **once** per file here. It was previously
        called twice — once for the size and again for the mtime — which
        doubled the stat syscalls of the dashboard's largest walk for no
        benefit.

        Args:
            path: Directory to walk.
            max_depth: Maximum depth to traverse (None = unlimited).

        Returns:
            ``(files, directory_count)``. Directories are counted but not
            returned, matching what :meth:`analyze_directory` needs.
        """
        files_list: list[FileInfo] = []
        directory_count = 0

        for item in self._walk_directory(path, max_depth):
            if item.is_file():
                try:
                    st = item.stat()
                except OSError:
                    continue
                files_list.append(
                    FileInfo(
                        path=item,
                        size=st.st_size,
                        type=item.suffix.lower() or "no_extension",
                        modified=datetime.fromtimestamp(st.st_mtime, tz=UTC),
                    )
                )
            elif item.is_dir():
                directory_count += 1

        return files_list, directory_count

    def calculate_size_distribution(self, path: Path) -> FileDistribution:
        """Calculate file distribution by type and size ranges.

        Args:
            path: Directory path

        Returns:
            FileDistribution object
        """
        distribution = FileDistribution()

        size_ranges = {
            "tiny": (0, 1024),  # < 1KB
            "small": (1024, 1024 * 1024),  # 1KB - 1MB
            "medium": (1024 * 1024, 100 * 1024 * 1024),  # 1MB - 100MB
            "large": (100 * 1024 * 1024, 1024 * 1024 * 1024),  # 100MB - 1GB
            "huge": (1024 * 1024 * 1024, float("inf")),  # > 1GB
        }

        # include_hidden=True: this measures disk usage, and a size distribution
        # that silently omits dotfiles is wrong. It also keeps these totals
        # consistent with analyze_directory's _walk_directory, which has always
        # counted hidden entries. Symlinks stay excluded — following them would
        # double-count, or count bytes living outside the analysed tree.
        for file_path in safe_walk(path, only_files=True, include_hidden=True):
            distribution.total_files += 1

            # By type
            file_type = file_path.suffix.lower() or "no_extension"
            distribution.by_type[file_type] = distribution.by_type.get(file_type, 0) + 1

            # By size range
            size = file_path.stat().st_size
            for range_name, (min_size, max_size) in size_ranges.items():
                if min_size <= size < max_size:
                    distribution.by_size_range[range_name] = (
                        distribution.by_size_range.get(range_name, 0) + 1
                    )
                    break

        logger.info(
            f"Distribution: {distribution.total_files} files across "
            f"{len(distribution.by_type)} types"
        )

        return distribution

    def identify_large_files(
        self,
        path: Path,
        threshold: int = 100 * 1024 * 1024,  # 100MB
        top_n: int = 50,
    ) -> list[FileInfo]:
        """Identify large files above threshold.

        Args:
            path: Directory path
            threshold: Size threshold in bytes
            top_n: Maximum number of files to return

        Returns:
            List of FileInfo objects for large files
        """
        large_files = []

        # include_hidden=True for the same reason as calculate_size_distribution:
        # a large dotfile still occupies the disk the user is asking about.
        for file_path in safe_walk(path, only_files=True, include_hidden=True):
            size = file_path.stat().st_size
            if size >= threshold:
                large_files.append(
                    FileInfo(
                        path=file_path,
                        size=size,
                        type=file_path.suffix.lower(),
                        modified=datetime.fromtimestamp(file_path.stat().st_mtime, tz=UTC),
                    )
                )

        # Sort by size descending
        large_files.sort(key=lambda f: f.size, reverse=True)

        logger.info(f"Found {len(large_files)} files above {threshold / (1024 * 1024):.1f}MB")

        return large_files[:top_n]

    def get_duplicate_space(self, duplicate_groups: list[dict[str, Any]]) -> int:
        """Calculate space wasted by duplicates.

        Args:
            duplicate_groups: List of duplicate groups from deduplication

        Returns:
            Total wasted space in bytes
        """
        wasted = 0

        for group in duplicate_groups:
            files = group.get("files", [])
            if len(files) > 1:
                # Get size of first file (representative)
                first_file = Path(files[0])
                if first_file.exists():
                    file_size = first_file.stat().st_size
                    # Wasted space = (count - 1) * size
                    wasted += (len(files) - 1) * file_size

        return wasted

    def _walk_directory(
        self, path: Path, max_depth: int | None = None, current_depth: int = 0
    ) -> Any:
        """Walk directory with depth limit.

        Args:
            path: Directory path
            max_depth: Maximum depth (None = unlimited)
            current_depth: Current depth level

        Yields:
            Path objects
        """
        if max_depth is not None and current_depth > max_depth:
            return

        try:
            for item in path.iterdir():
                yield item

                if item.is_dir() and not item.is_symlink():
                    yield from self._walk_directory(item, max_depth, current_depth + 1)
        except PermissionError:
            logger.warning(f"Permission denied: {path}")
        except OSError as e:
            logger.error(f"Error walking {path}: {e}")

    def walk_directory(self, path: Path, max_depth: int | None = None) -> Any:
        """Walk directory with optional depth limit (public API).

        Args:
            path: Directory path
            max_depth: Maximum depth (None = unlimited)

        Raises:
            FileNotFoundError: If ``path`` does not exist.
            NotADirectoryError: If ``path`` exists but is not a directory.

        Yields:
            Path objects for all items up to max_depth
        """
        if not path.exists():
            raise FileNotFoundError(f"Directory not found: {path}")
        if not path.is_dir():
            raise NotADirectoryError(f"Not a directory: {path}")
        return self._walk_directory(path, max_depth)

    def clear_cache(self) -> None:
        """Clear the analysis cache."""
        self._cache.clear()
        logger.info("Storage analysis cache cleared")
