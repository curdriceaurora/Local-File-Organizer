"""
Duplicate file index module.

Maintains an efficient hash-to-files mapping for quick duplicate detection
and provides statistics about duplicates and potential space savings.
"""

from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class FileMetadata:
    """Metadata about a file in the duplicate index."""
    
    path: Path
    size: int
    modified_time: datetime
    accessed_time: datetime
    hash_value: str
    
    def __post_init__(self):
        """Ensure path is a Path object."""
        if not isinstance(self.path, Path):
            self.path = Path(self.path)


@dataclass
class DuplicateGroup:
    """A group of duplicate files with the same hash."""
    
    hash_value: str
    files: List[FileMetadata] = field(default_factory=list)
    
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


class DuplicateIndex:
    """
    Maintains an index of file hashes for duplicate detection.
    
    Uses a dictionary with hash as key and list of file metadata as value.
    Provides O(1) lookup for duplicate detection and various statistics.
    """
    
    def __init__(self):
        """Initialize an empty duplicate index."""
        self._index: Dict[str, List[FileMetadata]] = {}
        self._size_index: Dict[int, List[Path]] = {}
    
    def add_file(
        self,
        file_path: Path,
        file_hash: str,
        metadata: Optional[Dict] = None
    ) -> None:
        """
        Add a file to the index.
        
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
                "modified_time": datetime.fromtimestamp(stat.st_mtime),
                "accessed_time": datetime.fromtimestamp(stat.st_atime),
            }
        
        # Create metadata object
        file_metadata = FileMetadata(
            path=file_path,
            size=metadata.get("size", 0),
            modified_time=metadata.get("modified_time", datetime.now()),
            accessed_time=metadata.get("accessed_time", datetime.now()),
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
    
    def get_duplicates(self) -> Dict[str, DuplicateGroup]:
        """
        Get all duplicate file groups.
        
        Returns:
            Dictionary mapping hash values to DuplicateGroup objects.
            Only includes hashes with 2+ files (actual duplicates).
        """
        duplicates = {}
        
        for hash_value, files in self._index.items():
            if len(files) > 1:
                duplicates[hash_value] = DuplicateGroup(
                    hash_value=hash_value,
                    files=files
                )
        
        return duplicates
    
    def get_files_by_hash(self, file_hash: str) -> List[FileMetadata]:
        """
        Get all files with a specific hash.
        
        Args:
            file_hash: Hash value to look up
            
        Returns:
            List of file metadata objects with this hash
        """
        return self._index.get(file_hash, [])
    
    def get_files_by_size(self, size: int) -> List[Path]:
        """
        Get all files with a specific size.
        
        This is useful for pre-filtering before hashing.
        
        Args:
            size: File size in bytes
            
        Returns:
            List of file paths with this size
        """
        return self._size_index.get(size, [])
    
    def has_duplicates(self) -> bool:
        """
        Check if there are any duplicates in the index.
        
        Returns:
            True if there are files with duplicate hashes
        """
        return any(len(files) > 1 for files in self._index.values())
    
    def get_statistics(self) -> Dict:
        """
        Get statistics about the index.
        
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
        duplicate_files = sum(
            len(files) for files in self._index.values() if len(files) > 1
        )
        duplicate_groups = len(duplicates)
        wasted_space = sum(group.wasted_space for group in duplicates.values())
        largest_group = max(
            (group.count for group in duplicates.values()),
            default=0
        )
        
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
    
    def __len__(self) -> int:
        """Return total number of files in the index."""
        return sum(len(files) for files in self._index.values())
    
    def __contains__(self, file_hash: str) -> bool:
        """Check if a hash exists in the index."""
        return file_hash in self._index
