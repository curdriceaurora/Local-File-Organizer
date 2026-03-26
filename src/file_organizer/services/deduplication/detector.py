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

from ...parallel.config import ParallelConfig
from ...utils.file_scanner import ScanConfig, StreamingFileScanner
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
    parallel_config: ParallelConfig | None = None  # Parallel processing configuration
    batch_size: int = 100  # Number of files to hash in each batch


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
        Uses parallel processing for improved performance on large file sets.

        Args:
            size_groups: dictionary of size to file lists
            options: Scan options including algorithm, parallel config, and progress callback
        """
        # Collect all files to hash (only those with potential duplicates)
        files_to_hash = [
            file_path
            for files in size_groups.values()
            if len(files) > 1  # Only hash if there are potential duplicates
            for file_path in files
        ]

        total = len(files_to_hash)
        if total == 0:
            return

        # Determine if we should use parallel processing
        # Use parallel for larger batches (>= 10 files) or if explicitly configured
        use_parallel = options.parallel_config is not None or total >= 10

        if use_parallel:
            # Process files in batches using parallel hashing
            self._process_files_parallel(files_to_hash, options, total)
        else:
            # Process files sequentially (better for small batches)
            self._process_files_sequential(files_to_hash, options, total)

    def _process_files_sequential(
        self, files: list[Path], options: ScanOptions, total: int
    ) -> None:
        """Process files sequentially (for small batches).

        Args:
            files: List of file paths to process
            options: Scan options
            total: Total number of files for progress reporting
        """
        processed = 0

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

    def _process_files_parallel(self, files: list[Path], options: ScanOptions, total: int) -> None:
        """Process files in parallel batches for optimal performance.

        Args:
            files: List of file paths to process
            options: Scan options with parallel configuration
            total: Total number of files for progress reporting
        """
        processed = 0
        batch_size = options.batch_size

        # Process files in batches
        for i in range(0, len(files), batch_size):
            batch = files[i : i + batch_size]

            # Hash batch in parallel
            hash_results = self.hasher.compute_batch_parallel(
                batch, options.algorithm, options.parallel_config
            )

            # Add successful hashes to index
            for file_path, file_hash in hash_results.items():
                self.index.add_file(file_path, file_hash)

                processed += 1

                # Call progress callback if provided
                if options.progress_callback:
                    options.progress_callback(processed, total)

    def _find_files(self, directory: Path, options: ScanOptions) -> list[Path]:
        """Find files in directory matching scan options.

        This is a helper method for backward compatibility with tests.
        Uses StreamingFileScanner internally.

        Args:
            directory: Directory to scan
            options: Scan options

        Returns:
            List of matching file paths
        """
        scanner = StreamingFileScanner()
        config = self._create_scan_config(options)

        files = []
        for chunk in scanner.scan_directory(directory, config):
            files.extend(chunk)

        return files

    def _group_by_size(self, files: list[Path], options: ScanOptions) -> dict[int, list[Path]]:
        """Group files by their size.

        This is a helper method for backward compatibility with tests.
        Files of the same size are potential duplicates.

        Args:
            files: List of file paths to group
            options: Scan options (currently unused but kept for compatibility)

        Returns:
            Dictionary mapping file sizes to lists of files
        """
        size_groups: dict[int, list[Path]] = {}

        for file_path in files:
            try:
                size = file_path.stat().st_size

                if size not in size_groups:
                    size_groups[size] = []

                size_groups[size].append(file_path)
            except (OSError, PermissionError):
                # Skip files we can't access
                continue

        return size_groups

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
