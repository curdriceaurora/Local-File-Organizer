"""
Configuration for the file system watcher.

Defines the WatcherConfig dataclass for controlling monitoring behavior
including directory selection, filtering, debouncing, and batching.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# Default patterns to exclude from watching
DEFAULT_EXCLUDE_PATTERNS: list[str] = [
    "*.tmp",
    "*.temp",
    "*.swp",
    "*.swo",
    "*~",
    ".git/*",
    ".git",
    "__pycache__/*",
    "__pycache__",
    ".DS_Store",
    "Thumbs.db",
    ".venv/*",
    ".env/*",
    "node_modules/*",
    "*.pyc",
    "*.pyo",
]


@dataclass
class WatcherConfig:
    """
    Configuration for the file system monitor.

    Controls which directories to watch, how events are filtered,
    debounce timing, and batch processing parameters.

    Attributes:
        watch_directories: List of directory paths to monitor.
        recursive: Whether to monitor subdirectories recursively.
        exclude_patterns: Glob patterns for files/directories to ignore.
        debounce_seconds: Minimum delay before processing an event on a file.
            Events within this window are collapsed into one.
        batch_size: Maximum number of events to dequeue in a single batch.
        file_types: If set, only process files with these extensions
            (e.g., [".txt", ".pdf"]). None means all file types.
    """

    watch_directories: list[Path] = field(default_factory=list)
    recursive: bool = True
    exclude_patterns: list[str] = field(default_factory=lambda: list(DEFAULT_EXCLUDE_PATTERNS))
    debounce_seconds: float = 2.0
    batch_size: int = 10
    file_types: list[str] | None = None

    def __post_init__(self) -> None:
        """Validate and normalize configuration after initialization."""
        # Normalize paths
        self.watch_directories = [Path(p) for p in self.watch_directories]

        # Normalize file type extensions to include leading dot
        if self.file_types is not None:
            self.file_types = [ext if ext.startswith(".") else f".{ext}" for ext in self.file_types]

        # Validate debounce_seconds
        if self.debounce_seconds < 0:
            raise ValueError(f"debounce_seconds must be non-negative, got {self.debounce_seconds}")

        # Validate batch_size
        if self.batch_size < 1:
            raise ValueError(f"batch_size must be at least 1, got {self.batch_size}")

    def should_include_file(self, path: Path) -> bool:
        """
        Check whether a file path passes the configured filters.

        Applies both exclude pattern matching and file type filtering.

        Args:
            path: The file path to check.

        Returns:
            True if the file should be processed, False if it should be ignored.
        """
        path_str = str(path)

        # Check exclude patterns
        for pattern in self.exclude_patterns:
            if _matches_pattern(path_str, pattern):
                return False

        # Check file type filter
        if self.file_types is not None:
            if path.suffix.lower() not in self.file_types:
                return False

        return True


def _matches_pattern(path_str: str, pattern: str) -> bool:
    """
    Check if a path string matches a glob-like exclude pattern.

    Supports simple glob matching with '*' wildcards. This is a lightweight
    implementation that handles the most common patterns without pulling in
    fnmatch for every event.

    Args:
        path_str: The file path as a string.
        pattern: A glob-like pattern (e.g., '*.tmp', '.git/*').

    Returns:
        True if the path matches the pattern.
    """
    import fnmatch
    from pathlib import PurePosixPath

    # Check against the full path and each individual component
    path_parts = PurePosixPath(path_str).parts

    # Match against the full path
    if fnmatch.fnmatch(path_str, pattern):
        return True

    # Match against each path component
    for part in path_parts:
        if fnmatch.fnmatch(part, pattern):
            return True

    # Match against the filename
    filename = PurePosixPath(path_str).name
    if fnmatch.fnmatch(filename, pattern):
        return True

    return False
