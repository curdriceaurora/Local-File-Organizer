"""Duplicate detection orchestrator.

Coordinates hash computation, index building, and provides high-level
interface for duplicate detection workflows.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ...utils.file_scanner import StreamingFileScanner, ScanConfig
from .hasher import FileHasher, HashAlgorithm
from .index import DuplicateIndex, FileMetadata

logger = logging.getLogger(__name__)


@dataclass
class ScanOptions:
    """Options for directory scanning."""

    algorithm: HashAlgorithm = "sha256"
    recursive: bool = True
    follow_symlinks: bool = False
    min_file_size: int = 0  # Minimum file size to consider (bytes)
    max_file_size: int | None = None  # Maximum file size (None = no limit)
    file_patterns: list[str] | None = None  # Glob patterns to include
    exclude_patterns: list[str] | None = None  # Glob patterns to exclude
    progress_callback: Callable[[int, int], None] | None = None  # (current, total)


class DuplicateDetector:
    """High-level orchestrator for duplicate file detection.

    Coordinates FileHasher and DuplicateIndex to provide a complete
    duplicate detection workflow. Includes optimizations like size
    pre-filtering to avoid unnecessary hashing.
    """

    def __init__(self, hasher: FileHasher | None = None, index: DuplicateIndex | None = None):
        """Initialize the DuplicateDetector.

        Args:
            hasher: FileHasher instance (creates default if None)
            index: DuplicateIndex instance (creates new if None)
        """
        self.hasher = hasher or FileHasher()
        self.index = index or DuplicateIndex()

    def scan_directory(self, directory: Path, options: ScanOptions | None = None) -> DuplicateIndex:
        """Scan a directory for duplicate files.

        This is the main entry point for duplicate detection. It:
        1. Streams files from directory using memory-efficient scanner
        2. Groups files by size (optimization)
        3. Hashes only files with duplicate sizes
        4. Builds the duplicate index

        Uses streaming approach to handle large directories (50,000+ files)
        without loading all paths into memory.

        Args:
            directory: Directory to scan
            options: Scan options (uses defaults if None)

        Returns:
            DuplicateIndex with all files indexed

        Raises:
            ValueError: If directory doesn't exist or isn't a directory
        """
        if not directory.exists():
            raise ValueError(f"Directory not found: {directory}")

        if not directory.is_dir():
            raise ValueError(f"Path is not a directory: {directory}")

        options = options or ScanOptions()

        # Create streaming scanner
        scanner = StreamingFileScanner()

        # Convert ScanOptions to ScanConfig
        scan_config = self._create_scan_config(options)

        # Step 1 & 2: Stream files and group by size in chunks
        size_groups = self._stream_and_group_by_size(directory, scanner, scan_config)

        if not size_groups:
            return self.index

        # Step 3: Hash files and build index
        self._process_files(size_groups, options)

        return self.index

    def _create_scan_config(self, options: ScanOptions) -> ScanConfig:
        """Convert ScanOptions to ScanConfig for StreamingFileScanner.

        Args:
            options: Deduplication scan options

        Returns:
            ScanConfig for file scanner
        """
        # Note: ScanConfig doesn't need algorithm, and has different progress callback signature
        return ScanConfig(
            recursive=options.recursive,
            follow_symlinks=options.follow_symlinks,
            min_file_size=options.min_file_size,
            max_file_size=options.max_file_size,
            file_patterns=options.file_patterns,
            exclude_patterns=options.exclude_patterns,
            chunk_size=1000,  # Process 1000 files at a time
            max_files=None,
            progress_callback=None,  # We'll handle progress in _process_files
        )

    def _stream_and_group_by_size(
        self,
        directory: Path,
        scanner: StreamingFileScanner,
        config: ScanConfig,
    ) -> dict[int, list[Path]]:
        """Stream files and group by size using memory-efficient chunked processing.

        This avoids loading all file paths into memory at once. Files are
        processed in chunks and grouped by size as they're streamed.

        Args:
            directory: Directory to scan
            scanner: StreamingFileScanner instance
            config: Scan configuration

        Returns:
            Dictionary mapping file sizes to lists of files
        """
        size_groups: dict[int, list[Path]] = {}

        # Stream files in chunks
        for chunk in scanner.scan_directory(directory, config):
            # Group this chunk by size
            for file_path in chunk:
                try:
                    size = file_path.stat().st_size

                    if size not in size_groups:
                        size_groups[size] = []

                    size_groups[size].append(file_path)
                except (OSError, PermissionError):
                    # Skip files we can't access
                    continue

        return size_groups

    def _process_files(self, size_groups: dict[int, list[Path]], options: ScanOptions) -> None:
        """Process files by hashing and adding to index.

        Only hashes files that have potential duplicates (2+ files with same size).

        Args:
            size_groups: dictionary of size to file lists
            options: Scan options including algorithm and progress callback
        """
        # Count total files to hash (only those with potential duplicates)
        files_to_hash = [
            file_path
            for files in size_groups.values()
            if len(files) > 1  # Only hash if there are potential duplicates
            for file_path in files
        ]

        total = len(files_to_hash)
        processed = 0

        # Process each size group
        for _size, files in size_groups.items():
            # Skip groups with only one file - unique sizes cannot be duplicates
            if len(files) == 1:
                continue

            # Hash files in this size group
            for file_path in files:
                try:
                    # Compute hash
                    file_hash = self.hasher.compute_hash(file_path, options.algorithm)

                    # Add to index
                    self.index.add_file(file_path, file_hash)

                    processed += 1

                    # Call progress callback if provided
                    if options.progress_callback:
                        options.progress_callback(processed, total)

                except (FileNotFoundError, PermissionError, ValueError) as e:
                    # Log error but continue
                    logger.warning("Could not process %s: %s", file_path, e, exc_info=True)
                    continue

    def find_duplicates_of_file(
        self, file_path: Path, search_directory: Path, algorithm: HashAlgorithm = "sha256"
    ) -> list[FileMetadata]:
        """Find all duplicates of a specific file in a directory.

        This is useful for checking if a file already exists elsewhere.

        Args:
            file_path: File to find duplicates of
            search_directory: Directory to search in
            algorithm: Hash algorithm to use

        Returns:
            List of files that are duplicates of the target file
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Compute hash of target file
        target_hash = self.hasher.compute_hash(file_path, algorithm)

        # Scan directory
        options = ScanOptions(algorithm=algorithm)
        self.scan_directory(search_directory, options)

        # Find files with matching hash (excluding the target itself)
        duplicates = [
            metadata
            for metadata in self.index.get_files_by_hash(target_hash)
            if metadata.path.resolve() != file_path.resolve()
        ]

        return duplicates

    def get_duplicate_groups(self) -> dict[str, Any]:
        """Get all groups of duplicate files.

        Returns:
            Dictionary mapping hashes to DuplicateGroup objects
        """
        return self.index.get_duplicates()

    def get_statistics(self) -> dict[str, Any]:
        """Get statistics about detected duplicates.

        Returns:
            Dictionary with duplicate statistics
        """
        return self.index.get_statistics()

    def clear(self) -> None:
        """Clear the index and start fresh."""
        self.index.clear()
