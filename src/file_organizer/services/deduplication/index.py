"""Duplicate file index module.

Maintains an efficient hash-to-files mapping for quick duplicate detection
and provides statistics about duplicates and potential space savings.
Supports streaming index building for memory-efficient processing of large
file sets.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Generator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class FileMetadata:
    """Metadata about a file in the duplicate index."""

    path: Path
    size: int
    modified_time: datetime
    accessed_time: datetime
    hash_value: str

    def __post_init__(self) -> None:
        """Ensure path is a Path object."""
        if not isinstance(self.path, Path):
            self.path = Path(self.path)


@dataclass
class DuplicateGroup:
    """A group of duplicate files with the same hash."""

    hash_value: str
    files: list[FileMetadata] = field(default_factory=list)

    @property
    def count(self) -> int:
        """Number of files in this duplicate group."""
        return len(self.files)

    @property
    def total_size(self) -> int:
        """Total size of all files in this group."""
        if not self.files:
            return 0
        # All files have the same size, multiply by count
        return self.files[0].size * self.count

    @property
    def wasted_space(self) -> int:
        """Space that could be saved by keeping only one file."""
        if self.count <= 1:
            return 0
        # Keep one copy, delete the rest
        return self.files[0].size * (self.count - 1)


@dataclass
class IndexBuildConfig:
    """Configuration for streaming index building operations."""

    chunk_size: int = 1000  # Number of files to process per chunk
    max_files: int | None = None  # Maximum number of files to process (None = no limit)
    progress_callback: Callable[[int], None] | None = None  # Called with file count
    hash_function: Callable[[Path], str] | None = None  # Custom hash function (path -> hash)


class DuplicateIndex:
    """Maintains an index of file hashes for duplicate detection.

    Uses a dictionary with hash as key and list of file metadata as value.
    Provides O(1) lookup for duplicate detection and various statistics.
    """

    def __init__(self) -> None:
        """Initialize an empty duplicate index."""
        self._index: dict[str, list[FileMetadata]] = {}
        self._size_index: dict[int, list[Path]] = {}

    def add_file(
        self, file_path: Path, file_hash: str, metadata: dict[str, Any] | None = None
    ) -> None:
        """Add a file to the index.

        Args:
            file_path: Path to the file
            file_hash: Hash value of the file
            metadata: Optional dictionary with file metadata.
                     Expected keys: size, modified_time, accessed_time
        """
        # Get file stats if metadata not provided
        if metadata is None:
            stat = file_path.stat()
            metadata = {
                "size": stat.st_size,
                "modified_time": datetime.fromtimestamp(stat.st_mtime, tz=UTC),
                "accessed_time": datetime.fromtimestamp(stat.st_atime, tz=UTC),
            }

        # Create metadata object — normalize naive datetimes from callers
        modified_time = metadata.get("modified_time", datetime.now(UTC))
        if isinstance(modified_time, datetime) and modified_time.tzinfo is None:
            modified_time = modified_time.replace(tzinfo=UTC)
        accessed_time = metadata.get("accessed_time", datetime.now(UTC))
        if isinstance(accessed_time, datetime) and accessed_time.tzinfo is None:
            accessed_time = accessed_time.replace(tzinfo=UTC)
        file_metadata = FileMetadata(
            path=file_path,
            size=metadata.get("size", 0),
            modified_time=modified_time,
            accessed_time=accessed_time,
            hash_value=file_hash,
        )

        # Add to hash index
        if file_hash not in self._index:
            self._index[file_hash] = []
        self._index[file_hash].append(file_metadata)

        # Add to size index for quick pre-filtering
        size = file_metadata.size
        if size not in self._size_index:
            self._size_index[size] = []
        self._size_index[size].append(file_path)

    def get_duplicates(self) -> dict[str, DuplicateGroup]:
        """Get all duplicate file groups.

        Returns:
            Dictionary mapping hash values to DuplicateGroup objects.
            Only includes hashes with 2+ files (actual duplicates).
        """
        duplicates = {}

        for hash_value, files in self._index.items():
            if len(files) > 1:
                duplicates[hash_value] = DuplicateGroup(hash_value=hash_value, files=files)

        return duplicates

    def get_files_by_hash(self, file_hash: str) -> list[FileMetadata]:
        """Get all files with a specific hash.

        Args:
            file_hash: Hash value to look up

        Returns:
            List of file metadata objects with this hash
        """
        return self._index.get(file_hash, [])

    def get_files_by_size(self, size: int) -> list[Path]:
        """Get all files with a specific size.

        This is useful for pre-filtering before hashing.

        Args:
            size: File size in bytes

        Returns:
            List of file paths with this size
        """
        return self._size_index.get(size, [])

    def has_duplicates(self) -> bool:
        """Check if there are any duplicates in the index.

        Returns:
            True if there are files with duplicate hashes
        """
        return any(len(files) > 1 for files in self._index.values())

    def get_statistics(self) -> dict[str, Any]:
        """Get statistics about the index.

        Returns:
            Dictionary with statistics including:
            - total_files: Total number of indexed files
            - unique_files: Number of unique files (unique hashes)
            - duplicate_files: Number of files that have duplicates
            - duplicate_groups: Number of duplicate groups
            - wasted_space: Total space that could be saved
            - largest_group: Size of the largest duplicate group
        """
        duplicates = self.get_duplicates()

        total_files = sum(len(files) for files in self._index.values())
        unique_files = len(self._index)
        duplicate_files = sum(len(files) for files in self._index.values() if len(files) > 1)
        duplicate_groups = len(duplicates)
        wasted_space = sum(group.wasted_space for group in duplicates.values())
        largest_group = max((group.count for group in duplicates.values()), default=0)

        return {
            "total_files": total_files,
            "unique_files": unique_files,
            "duplicate_files": duplicate_files,
            "duplicate_groups": duplicate_groups,
            "wasted_space": wasted_space,
            "wasted_space_mb": round(wasted_space / (1024 * 1024), 2),
            "largest_group": largest_group,
        }

    def clear(self) -> None:
        """Clear all data from the index."""
        self._index.clear()
        self._size_index.clear()

    def build_from_directory_streaming(
        self,
        directory: Path,
        hash_function: Callable[[Path], str],
        config: IndexBuildConfig | None = None,
    ) -> Generator[int, None, None]:
        """Build index from top-level files in a directory using streaming approach.

        This method yields progress updates as chunks are processed, allowing
        memory-efficient processing of large file sets without loading all
        file metadata into memory at once. The directory scan is intentionally
        non-recursive; only immediate child files are included.

        Args:
            directory: Directory whose immediate child files should be scanned
            hash_function: Function that takes a file path and returns its hash
            config: Build configuration (uses defaults if None)

        Yields:
            Number of files processed so far

        Raises:
            ValueError: If directory doesn't exist or isn't a directory

        Example:
            index = DuplicateIndex()
            config = IndexBuildConfig(chunk_size=1000)

            for progress in index.build_from_directory_streaming(
                Path("/data"), compute_hash, config
            ):
                print(f"Processed {progress} files")
        """
        if not directory.exists():
            raise ValueError(f"Directory not found: {directory}")

        if not directory.is_dir():
            raise ValueError(f"Path is not a directory: {directory}")

        config = config or IndexBuildConfig()
        processed_count = 0

        # Get all files from directory
        files = [f for f in directory.iterdir() if f.is_file()]

        # Limit files if max_files is set
        if config.max_files is not None:
            files = files[: config.max_files]

        # Process files in chunks
        for i in range(0, len(files), config.chunk_size):
            chunk = files[i : i + config.chunk_size]

            for file_path in chunk:
                try:
                    # Compute hash using provided function
                    file_hash = hash_function(file_path)

                    # Add to index
                    self.add_file(file_path, file_hash)

                    processed_count += 1

                    # Call progress callback if provided
                    if config.progress_callback is not None:
                        config.progress_callback(processed_count)

                except (OSError, PermissionError) as e:
                    logger.warning(f"Failed to process file {file_path}: {e}")
                    continue

            # Yield progress after each chunk
            yield processed_count

    def build_from_files_streaming(
        self,
        files: list[Path],
        hash_function: Callable[[Path], str],
        config: IndexBuildConfig | None = None,
    ) -> Generator[int, None, None]:
        """Build index from list of files using streaming approach.

        This method processes files in chunks and yields progress updates,
        allowing memory-efficient processing of large file lists.

        Args:
            files: List of file paths to index
            hash_function: Function that takes a file path and returns its hash
            config: Build configuration (uses defaults if None)

        Yields:
            Number of files processed so far

        Example:
            index = DuplicateIndex()
            config = IndexBuildConfig(chunk_size=500)
            file_list = [Path(f) for f in my_files]

            for progress in index.build_from_files_streaming(
                file_list, compute_hash, config
            ):
                print(f"Processed {progress} files")
        """
        config = config or IndexBuildConfig()
        processed_count = 0

        # Limit files if max_files is set
        if config.max_files is not None:
            files = files[: config.max_files]

        # Process files in chunks
        for i in range(0, len(files), config.chunk_size):
            chunk = files[i : i + config.chunk_size]

            for file_path in chunk:
                try:
                    # Skip non-files
                    if not file_path.is_file():
                        continue

                    # Compute hash using provided function
                    file_hash = hash_function(file_path)

                    # Add to index
                    self.add_file(file_path, file_hash)

                    processed_count += 1

                    # Call progress callback if provided
                    if config.progress_callback is not None:
                        config.progress_callback(processed_count)

                except (OSError, PermissionError) as e:
                    logger.warning(f"Failed to process file {file_path}: {e}")
                    continue

            # Yield progress after each chunk
            yield processed_count

    def add_files_batch(
        self,
        file_hash_pairs: list[tuple[Path, str]],
        metadata_dict: dict[Path, dict[str, Any]] | None = None,
    ) -> int:
        """Add multiple files to the index in a batch.

        This method is more efficient than calling add_file() repeatedly
        for large numbers of files.

        Args:
            file_hash_pairs: List of (file_path, hash) tuples
            metadata_dict: Optional dict mapping paths to metadata dicts

        Returns:
            Number of files successfully added

        Example:
            index = DuplicateIndex()
            pairs = [(Path("/a.txt"), "hash1"), (Path("/b.txt"), "hash2")]
            count = index.add_files_batch(pairs)
        """
        added_count = 0

        for file_path, file_hash in file_hash_pairs:
            try:
                # Get metadata if provided
                metadata = None
                if metadata_dict is not None:
                    metadata = metadata_dict.get(file_path)

                # Add to index
                self.add_file(file_path, file_hash, metadata)
                added_count += 1

            except (OSError, PermissionError) as e:
                logger.warning(f"Failed to add file {file_path}: {e}")
                continue

        return added_count

    def __len__(self) -> int:
        """Return total number of files in the index."""
        return sum(len(files) for files in self._index.values())

    def __contains__(self, file_hash: str) -> bool:
        """Check if a hash exists in the index."""
        return file_hash in self._index
