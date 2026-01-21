"""
Deduplication service for detecting and managing duplicate files.

This module provides:
- Hash-based duplicate detection using MD5 or SHA256 algorithms
- Perceptual image hashing for detecting visually similar images
- Efficient indexing, batch processing, and safe file management
"""

from .backup import BackupManager
from .detector import DuplicateDetector
from .hasher import FileHasher
from .image_dedup import ImageDeduplicator
from .image_utils import (
    ImageMetadata,
    filter_valid_images,
    find_images_in_directory,
    format_file_size,
    get_best_quality_image,
    get_image_info_string,
    get_image_metadata,
    validate_image_file,
)
from .index import DuplicateIndex

__all__ = [
    # Hash-based deduplication
    "FileHasher",
    "DuplicateIndex",
    "DuplicateDetector",
    "BackupManager",
    # Image deduplication
    "ImageDeduplicator",
    "ImageMetadata",
    # Image utilities
    "get_image_metadata",
    "validate_image_file",
    "filter_valid_images",
    "find_images_in_directory",
    "get_best_quality_image",
    "get_image_info_string",
    "format_file_size",
]
