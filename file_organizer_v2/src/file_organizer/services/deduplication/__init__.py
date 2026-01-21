"""
Deduplication service for detecting and managing duplicate files.

This module provides hash-based duplicate detection using MD5 or SHA256 algorithms.
It includes efficient indexing, batch processing, and safe file management.
"""

from .hasher import FileHasher
from .index import DuplicateIndex
from .detector import DuplicateDetector
from .backup import BackupManager

__all__ = ["FileHasher", "DuplicateIndex", "DuplicateDetector", "BackupManager"]
