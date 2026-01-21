"""
Duplicate detection orchestrator.

Coordinates hash computation, index building, and provides high-level
interface for duplicate detection workflows.
"""

from pathlib import Path
from typing import List, Optional, Callable
from dataclasses import dataclass

from .hasher import FileHasher, HashAlgorithm
from .index import DuplicateIndex, FileMetadata


@dataclass
class ScanOptions:
    """Options for directory scanning."""
    
    algorithm: HashAlgorithm = "sha256"
    recursive: bool = True
    follow_symlinks: bool = False
    min_file_size: int = 0  # Minimum file size to consider (bytes)
    max_file_size: Optional[int] = None  # Maximum file size (None = no limit)
    file_patterns: Optional[List[str]] = None  # Glob patterns to include
    exclude_patterns: Optional[List[str]] = None  # Glob patterns to exclude
    progress_callback: Optional[Callable[[int, int], None]] = None  # (current, total)


class DuplicateDetector:
    """
    High-level orchestrator for duplicate file detection.
    
    Coordinates FileHasher and DuplicateIndex to provide a complete
    duplicate detection workflow. Includes optimizations like size
    pre-filtering to avoid unnecessary hashing.
    """
    
    def __init__(
        self,
        hasher: Optional[FileHasher] = None,
        index: Optional[DuplicateIndex] = None
    ):
        """
        Initialize the DuplicateDetector.
        
        Args:
            hasher: FileHasher instance (creates default if None)
            index: DuplicateIndex instance (creates new if None)
        """
        self.hasher = hasher or FileHasher()
        self.index = index or DuplicateIndex()
    
    def scan_directory(
        self,
        directory: Path,
        options: Optional[ScanOptions] = None
    ) -> DuplicateIndex:
        """
        Scan a directory for duplicate files.
        
        This is the main entry point for duplicate detection. It:
        1. Recursively finds all files in the directory
        2. Groups files by size (optimization)
        3. Hashes only files with duplicate sizes
        4. Builds the duplicate index
        
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
        
        # Step 1: Find all files
        files = self._find_files(directory, options)
        
        if not files:
            return self.index
        
        # Step 2: Group by size (optimization - different sizes can't be duplicates)
        size_groups = self._group_by_size(files, options)
        
        # Step 3: Hash files and build index
        self._process_files(size_groups, options)
        
        return self.index
    
    def _find_files(
        self,
        directory: Path,
        options: ScanOptions
    ) -> List[Path]:
        """
        Find all files in directory matching the criteria.
        
        Args:
            directory: Directory to search
            options: Scan options with filters
            
        Returns:
            List of file paths matching criteria
        """
        files = []
        
        # Use rglob for recursive, glob for non-recursive
        if options.recursive:
            pattern = "**/*"
        else:
            pattern = "*"
        
        for path in directory.rglob(pattern) if options.recursive else directory.glob(pattern):
            # Skip if not a file
            if not path.is_file():
                continue
            
            # Skip symlinks if requested
            if path.is_symlink() and not options.follow_symlinks:
                continue
            
            # Check file size constraints
            try:
                size = path.stat().st_size
                
                if size < options.min_file_size:
                    continue
                
                if options.max_file_size is not None and size > options.max_file_size:
                    continue
            except (OSError, PermissionError):
                continue
            
            # Check include patterns
            if options.file_patterns:
                if not any(path.match(pattern) for pattern in options.file_patterns):
                    continue
            
            # Check exclude patterns
            if options.exclude_patterns:
                if any(path.match(pattern) for pattern in options.exclude_patterns):
                    continue
            
            files.append(path)
        
        return files
    
    def _group_by_size(
        self,
        files: List[Path],
        options: ScanOptions
    ) -> dict[int, List[Path]]:
        """
        Group files by size.
        
        This is an optimization - files with unique sizes cannot be duplicates,
        so we skip hashing them.
        
        Args:
            files: List of files to group
            options: Scan options (unused but kept for consistency)
            
        Returns:
            Dictionary mapping file sizes to lists of files
        """
        size_groups: dict[int, List[Path]] = {}
        
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
    
    def _process_files(
        self,
        size_groups: dict[int, List[Path]],
        options: ScanOptions
    ) -> None:
        """
        Process files by hashing and adding to index.
        
        Only hashes files that have potential duplicates (2+ files with same size).
        
        Args:
            size_groups: Dictionary of size to file lists
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
        for size, files in size_groups.items():
            # Optimization: skip groups with only one file
            if len(files) == 1:
                # Still add to index for completeness
                file_path = files[0]
                # Give it a unique "hash" since we're not computing it
                self.index.add_file(file_path, f"unique_{size}_{file_path}")
                continue
            
            # Hash files in this size group
            for file_path in files:
                try:
                    # Compute hash
                    file_hash = self.hasher.compute_hash(
                        file_path,
                        options.algorithm
                    )
                    
                    # Add to index
                    self.index.add_file(file_path, file_hash)
                    
                    processed += 1
                    
                    # Call progress callback if provided
                    if options.progress_callback:
                        options.progress_callback(processed, total)
                
                except (FileNotFoundError, PermissionError, ValueError) as e:
                    # Log error but continue
                    print(f"Warning: Could not process {file_path}: {e}")
                    continue
    
    def find_duplicates_of_file(
        self,
        file_path: Path,
        search_directory: Path,
        algorithm: HashAlgorithm = "sha256"
    ) -> List[FileMetadata]:
        """
        Find all duplicates of a specific file in a directory.
        
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
    
    def get_duplicate_groups(self):
        """
        Get all groups of duplicate files.
        
        Returns:
            Dictionary mapping hashes to DuplicateGroup objects
        """
        return self.index.get_duplicates()
    
    def get_statistics(self):
        """
        Get statistics about detected duplicates.
        
        Returns:
            Dictionary with duplicate statistics
        """
        return self.index.get_statistics()
    
    def clear(self):
        """Clear the index and start fresh."""
        self.index.clear()
