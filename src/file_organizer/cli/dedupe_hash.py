"""Hash-based duplicate detection coordination for CLI.

Provides a CLI-friendly interface for hash-based duplicate detection,
wrapping the services layer with progress reporting and user feedback.
Extracted from dedupe.py to separate scanning logic from UI orchestration.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console

if TYPE_CHECKING:
    from file_organizer.services.deduplication.detector import DuplicateDetector, ScanOptions
    from file_organizer.services.deduplication.hasher import HashAlgorithm
    from file_organizer.services.deduplication.index import DuplicateGroup


class ProgressTracker:
    """Tracks hash computation progress with visual feedback."""

    def __init__(self, console: Console):
        """Initialize progress tracker.

        Args:
            console: Rich console for progress display.
        """
        self.console = console
        self.progress_bar = None
        self.has_tqdm = False

        try:
            from tqdm import tqdm

            self.tqdm = tqdm
            self.has_tqdm = True
        except ImportError:
            console.print("[dim]Install tqdm for progress bars: pip install tqdm[/dim]")

    def callback(self, current: int, total: int) -> None:
        """Progress callback for file hashing.

        Args:
            current: Number of files processed so far.
            total: Total number of files to process.
        """
        if not self.has_tqdm:
            return

        if self.progress_bar is None:
            self.progress_bar = self.tqdm(total=total, desc="Hashing files", unit="files")
        self.progress_bar.update(1)

    def close(self) -> None:
        """Close the progress bar if it exists."""
        if self.progress_bar is not None:
            self.progress_bar.close()
            self.progress_bar = None


def scan_for_duplicates(
    directory: Path,
    detector: DuplicateDetector,
    scan_options: ScanOptions,
    console: Console,
    progress_tracker: ProgressTracker | None = None,
) -> dict[str, DuplicateGroup]:
    """Scan directory for duplicate files using hash-based detection.

    Args:
        directory: Directory to scan for duplicates.
        detector: Initialized duplicate detector instance.
        scan_options: Configuration for the scanning process.
        console: Rich console for user feedback.
        progress_tracker: Optional progress tracker to close after scanning.

    Returns:
        Dictionary mapping file hashes to duplicate groups.
    """
    console.print("[bold]Scanning for files...[/bold]")

    # Scan directory (detector updates internal index)
    detector.scan_directory(directory, scan_options)

    # Close progress bar if tracking
    if progress_tracker is not None:
        progress_tracker.close()

    # Get duplicate groups
    duplicate_groups = detector.get_duplicate_groups()

    if not duplicate_groups:
        console.print("\n[green]✓ No duplicate files found![/green]")
        return {}

    total_groups = len(duplicate_groups)
    total_duplicates = sum(group.count for group in duplicate_groups.values())

    console.print(
        f"\n[green]✓ Found {total_groups} duplicate group(s) with {total_duplicates} files total[/green]\n"
    )

    return duplicate_groups


def create_scan_options(
    algorithm: HashAlgorithm,
    recursive: bool = True,
    min_file_size: int = 0,
    max_file_size: int | None = None,
    file_patterns: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
) -> ScanOptions:
    """Create scan options for duplicate detection.

    Args:
        algorithm: Hash algorithm to use ('md5' or 'sha256').
        recursive: If True, scan subdirectories.
        min_file_size: Minimum file size to consider (bytes).
        max_file_size: Maximum file size to consider (bytes, None for unlimited).
        file_patterns: File patterns to include (e.g., ['*.jpg', '*.png']).
        exclude_patterns: File patterns to exclude.
        progress_callback: Optional callback for progress updates.

    Returns:
        Configured ScanOptions instance.
    """
    from file_organizer.services.deduplication.detector import ScanOptions

    return ScanOptions(
        algorithm=algorithm,
        recursive=recursive,
        min_file_size=min_file_size,
        max_file_size=max_file_size,
        file_patterns=file_patterns,
        exclude_patterns=exclude_patterns,
        progress_callback=progress_callback,
    )


def initialize_hash_detector() -> DuplicateDetector:
    """Initialize the hash-based duplicate detector.

    Returns:
        Configured DuplicateDetector instance.
    """
    from file_organizer.services.deduplication.detector import DuplicateDetector

    return DuplicateDetector()
