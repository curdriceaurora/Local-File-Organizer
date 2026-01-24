"""
File hashing module for duplicate detection.

Provides FileHasher class with MD5 and SHA256 support, chunked reading
for large files, and batch processing capabilities.
"""

import hashlib
from pathlib import Path
from typing import Dict, List, Literal

HashAlgorithm = Literal["md5", "sha256"]


class FileHasher:
    """
    Computes cryptographic hashes of files for duplicate detection.

    Supports MD5 (faster) and SHA256 (more secure) algorithms.
    Uses chunked reading for memory efficiency with large files.
    """

    # Default chunk size: 64KB (optimal for most systems)
    DEFAULT_CHUNK_SIZE = 65536
    # Minimum chunk size: 1KB (smaller would be inefficient)
    MIN_CHUNK_SIZE = 1024
    # Maximum chunk size: 10MB (larger could cause memory issues)
    MAX_CHUNK_SIZE = 10 * 1024 * 1024

    def __init__(self, chunk_size: int = DEFAULT_CHUNK_SIZE):
        """
        Initialize the FileHasher.

        Args:
            chunk_size: Size of chunks to read at a time (in bytes).
                       Default is 64KB for optimal performance.
                       Must be between 1KB and 10MB.

        Raises:
            ValueError: If chunk_size is invalid
        """
        if not isinstance(chunk_size, int):
            raise ValueError(
                f"chunk_size must be an integer, got {type(chunk_size).__name__}"
            )

        if chunk_size < self.MIN_CHUNK_SIZE:
            raise ValueError(
                f"chunk_size must be at least {self.MIN_CHUNK_SIZE} bytes (1KB), "
                f"got {chunk_size}"
            )

        if chunk_size > self.MAX_CHUNK_SIZE:
            raise ValueError(
                f"chunk_size must not exceed {self.MAX_CHUNK_SIZE} bytes (10MB), "
                f"got {chunk_size}"
            )

        self.chunk_size = chunk_size
    
    def compute_hash(
        self, 
        file_path: Path, 
        algorithm: HashAlgorithm = "sha256"
    ) -> str:
        """
        Compute hash of a single file.
        
        Args:
            file_path: Path to the file to hash
            algorithm: Hash algorithm to use ("md5" or "sha256")
            
        Returns:
            Hexadecimal string representation of the file hash
            
        Raises:
            FileNotFoundError: If file doesn't exist
            PermissionError: If file can't be read
            ValueError: If algorithm is not supported
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        if not file_path.is_file():
            raise ValueError(f"Path is not a file: {file_path}")
        
        # Create hash object
        if algorithm == "md5":
            hasher = hashlib.md5()
        elif algorithm == "sha256":
            hasher = hashlib.sha256()
        else:
            raise ValueError(
                f"Unsupported algorithm: {algorithm}. "
                f"Use 'md5' or 'sha256'."
            )
        
        # Read file in chunks for memory efficiency
        try:
            with open(file_path, "rb") as f:
                while True:
                    chunk = f.read(self.chunk_size)
                    if not chunk:
                        break
                    hasher.update(chunk)
        except PermissionError as e:
            raise PermissionError(f"Cannot read file: {file_path}") from e
        
        return hasher.hexdigest()
    
    def compute_batch(
        self,
        file_paths: List[Path],
        algorithm: HashAlgorithm = "sha256"
    ) -> Dict[Path, str]:
        """
        Compute hashes for multiple files.
        
        This method processes files sequentially but returns all results
        together. Errors for individual files are logged but don't stop
        the batch process.
        
        Args:
            file_paths: List of file paths to hash
            algorithm: Hash algorithm to use ("md5" or "sha256")
            
        Returns:
            Dictionary mapping file paths to their hash values.
            Files that couldn't be hashed are excluded from results.
        """
        results = {}
        
        for file_path in file_paths:
            try:
                hash_value = self.compute_hash(file_path, algorithm)
                results[file_path] = hash_value
            except (FileNotFoundError, PermissionError, ValueError) as e:
                # Log error but continue processing
                # In a production system, this would use proper logging
                print(f"Warning: Could not hash {file_path}: {e}")
                continue
        
        return results
    
    def get_file_size(self, file_path: Path) -> int:
        """
        Get file size in bytes.
        
        This is a quick pre-filter before hashing - files of different
        sizes cannot be duplicates.
        
        Args:
            file_path: Path to the file
            
        Returns:
            File size in bytes
            
        Raises:
            FileNotFoundError: If file doesn't exist
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        return file_path.stat().st_size
    
    @staticmethod
    def validate_algorithm(algorithm: str) -> HashAlgorithm:
        """
        Validate that the algorithm is supported.
        
        Args:
            algorithm: Algorithm name to validate
            
        Returns:
            The algorithm as a HashAlgorithm type
            
        Raises:
            ValueError: If algorithm is not supported
        """
        algorithm = algorithm.lower()
        if algorithm not in ("md5", "sha256"):
            raise ValueError(
                f"Unsupported algorithm: {algorithm}. "
                f"Use 'md5' or 'sha256'."
            )
        return algorithm  # type: ignore
