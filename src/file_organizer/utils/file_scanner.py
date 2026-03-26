"""Streaming file scanner utility.

Provides memory-efficient file scanning using os.scandir() instead of
Path.rglob(). Implements chunked processing and supports large directories
with 50,000-100,000+ files without loading all paths into memory at once.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Generator
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class ScanConfig:
    """Configuration for file scanning operations."""

    recursive: bool = True
    follow_symlinks: bool = False
    min_file_size: int = 0  # Minimum file size to consider (bytes)
    max_file_size: int | None = None  # Maximum file size (None = no limit)
    file_patterns: list[str] | None = None  # Glob patterns to include
    exclude_patterns: list[str] | None = None  # Glob patterns to exclude
    chunk_size: int = 1000  # Number of files to yield per chunk
    max_files: int | None = None  # Maximum number of files to scan (None = no limit)
    progress_callback: Callable[[int], None] | None = None  # Called with file count


class StreamingFileScanner:
    """Memory-efficient file scanner using os.scandir().

    This scanner is optimized for large directories (50,000+ files) and
    provides chunked iteration to avoid loading all file paths into memory.
    Uses os.scandir() which is significantly faster than Path.rglob() for
    large directory trees.

    Usage:
        scanner = StreamingFileScanner()
        config = ScanConfig(recursive=True, chunk_size=1000)

        # Iterate over chunks of files
        for chunk in scanner.scan_directory(Path("/data"), config):
            process_files(chunk)

        # Or iterate over individual files
        for file_path in scanner.scan_files(Path("/data"), config):
            process_file(file_path)
    """

    def __init__(self):
        """Initialize the StreamingFileScanner."""
        self._scanned_count = 0
        self._yielded_count = 0

    def scan_directory(
        self,
        directory: Path,
        config: ScanConfig | None = None,
    ) -> Generator[list[Path], None, None]:
        """Scan directory and yield chunks of file paths.

        This is the primary method for chunked processing. It yields lists
        of file paths (chunks) to allow batch processing without loading
        all paths into memory.

        Args:
            directory: Directory to scan
            config: Scan configuration (uses defaults if None)

        Yields:
            Lists of Path objects (chunks)

        Raises:
            ValueError: If directory doesn't exist or isn't a directory
        """
        if not directory.exists():
            raise ValueError(f"Directory not found: {directory}")

        if not directory.is_dir():
            raise ValueError(f"Path is not a directory: {directory}")

        config = config or ScanConfig()
        self._scanned_count = 0
        self._yielded_count = 0

        chunk = []

        for file_path in self._scan_recursive(directory, config):
            chunk.append(file_path)
            self._yielded_count += 1

            # Yield chunk when it reaches configured size
            if len(chunk) >= config.chunk_size:
                yield chunk
                chunk = []

            # Check max_files limit
            if config.max_files is not None and self._yielded_count >= config.max_files:
                break

        # Yield remaining files
        if chunk:
            yield chunk

    def scan_files(
        self,
        directory: Path,
        config: ScanConfig | None = None,
    ) -> Generator[Path, None, None]:
        """Scan directory and yield individual file paths.

        This is a convenience method for processing files one at a time.
        For better performance with large directories, use scan_directory()
        to process files in chunks.

        Args:
            directory: Directory to scan
            config: Scan configuration (uses defaults if None)

        Yields:
            Individual Path objects

        Raises:
            ValueError: If directory doesn't exist or isn't a directory
        """
        for chunk in self.scan_directory(directory, config):
            yield from chunk

    def scan_to_list(
        self,
        directory: Path,
        config: ScanConfig | None = None,
    ) -> list[Path]:
        """Scan directory and return all matching files as a list.

        WARNING: This loads all file paths into memory. Only use for small
        directories or when you need the full list. For large directories
        (50,000+ files), use scan_directory() or scan_files() instead.

        Args:
            directory: Directory to scan
            config: Scan configuration (uses defaults if None)

        Returns:
            List of all matching file paths

        Raises:
            ValueError: If directory doesn't exist or isn't a directory
        """
        return list(self.scan_files(directory, config))

    def _scan_recursive(
        self,
        directory: Path,
        config: ScanConfig,
    ) -> Generator[Path, None, None]:
        """Recursively scan directory using os.scandir().

        This is the core scanning implementation. It uses os.scandir()
        which is significantly faster than Path.rglob() for large
        directory trees.

        Args:
            directory: Directory to scan
            config: Scan configuration

        Yields:
            File paths matching criteria
        """
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    try:
                        # Get path and check if it's a file or directory
                        entry_path = Path(entry.path)

                        # Handle symlinks
                        if entry.is_symlink():
                            if not config.follow_symlinks:
                                continue

                            # For symlinks, check if target is file or dir
                            try:
                                is_file = entry_path.is_file()
                                is_dir = entry_path.is_dir()
                            except (OSError, PermissionError):
                                continue
                        else:
                            # Fast path for non-symlinks
                            is_file = entry.is_file(follow_symlinks=False)
                            is_dir = entry.is_dir(follow_symlinks=False)

                        # Process file
                        if is_file:
                            # Increment count for every file scanned (before filtering)
                            self._scanned_count += 1

                            # Call progress callback with scanned count
                            if config.progress_callback:
                                config.progress_callback(self._scanned_count)

                            if self._matches_criteria(entry_path, entry, config):
                                yield entry_path

                        # Recurse into subdirectory
                        elif is_dir and config.recursive:
                            yield from self._scan_recursive(entry_path, config)

                    except (OSError, PermissionError) as e:
                        # Skip files/dirs we can't access
                        logger.debug(f"Skipping {entry.path}: {e}")
                        continue

        except (OSError, PermissionError) as e:
            # Skip directories we can't access
            logger.warning(f"Cannot access directory {directory}: {e}")

    def _matches_criteria(
        self,
        path: Path,
        entry: os.DirEntry,
        config: ScanConfig,
    ) -> bool:
        """Check if file matches scan criteria.

        Args:
            path: File path
            entry: DirEntry object (for efficient stat access)
            config: Scan configuration

        Returns:
            True if file matches all criteria
        """
        # Check file size constraints
        try:
            # Use entry.stat() which is faster than Path.stat()
            stat_info = entry.stat(follow_symlinks=config.follow_symlinks)
            size = stat_info.st_size

            if size < config.min_file_size:
                return False

            if config.max_file_size is not None and size > config.max_file_size:
                return False
        except (OSError, PermissionError):
            return False

        # Check include patterns
        if config.file_patterns:
            if not any(path.match(pattern) for pattern in config.file_patterns):
                return False

        # Check exclude patterns
        if config.exclude_patterns:
            if any(path.match(pattern) for pattern in config.exclude_patterns):
                return False

        return True

    @property
    def scanned_count(self) -> int:
        """Get count of files scanned (before filtering)."""
        return self._scanned_count

    @property
    def yielded_count(self) -> int:
        """Get count of files yielded (after filtering)."""
        return self._yielded_count

    def reset_counters(self) -> None:
        """Reset scan counters."""
        self._scanned_count = 0
        self._yielded_count = 0
