"""
Image utility functions for deduplication operations.

Provides helper functions for image validation, metadata extraction,
format conversion, and batch processing operations.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PIL import Image

logger = logging.getLogger(__name__)

# Supported image formats
SUPPORTED_FORMATS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif", ".webp"}

# Format preference ranking (higher is better quality)
FORMAT_QUALITY_RANK = {
    ".png": 5,      # Lossless
    ".tiff": 5,     # Lossless
    ".tif": 5,      # Lossless
    ".bmp": 4,      # Lossless but large
    ".webp": 3,     # Can be lossless or lossy
    ".jpg": 2,      # Lossy
    ".jpeg": 2,     # Lossy
    ".gif": 1,      # Limited color palette
}


class ImageMetadata:
    """
    Container for image metadata.

    Attributes:
        path: Path to image file
        width: Image width in pixels
        height: Image height in pixels
        format: Image format (JPEG, PNG, etc.)
        mode: Image mode (RGB, RGBA, L, etc.)
        size_bytes: File size in bytes
        resolution: Total pixels (width * height)
    """

    def __init__(
        self,
        path: Path,
        width: int,
        height: int,
        format: str,
        mode: str,
        size_bytes: int
    ):
        self.path = path
        self.width = width
        self.height = height
        self.format = format
        self.mode = mode
        self.size_bytes = size_bytes
        self.resolution = width * height

    def __repr__(self) -> str:
        return (
            f"ImageMetadata(path={self.path.name}, "
            f"size={self.width}x{self.height}, "
            f"format={self.format}, "
            f"bytes={self.size_bytes})"
        )

    def to_dict(self) -> Dict[str, any]:
        """Convert metadata to dictionary."""
        return {
            "path": str(self.path),
            "width": self.width,
            "height": self.height,
            "format": self.format,
            "mode": self.mode,
            "size_bytes": self.size_bytes,
            "resolution": self.resolution,
        }


def get_image_metadata(image_path: Path) -> Optional[ImageMetadata]:
    """
    Extract metadata from an image file.

    Args:
        image_path: Path to image file

    Returns:
        ImageMetadata object with image information,
        or None if image cannot be read
    """
    if not image_path.exists():
        logger.warning(f"Image not found: {image_path}")
        return None

    try:
        with Image.open(image_path) as img:
            width, height = img.size
            format = img.format or "unknown"
            mode = img.mode

        size_bytes = image_path.stat().st_size

        return ImageMetadata(
            path=image_path,
            width=width,
            height=height,
            format=format,
            mode=mode,
            size_bytes=size_bytes
        )
    except (IOError, OSError) as e:
        logger.warning(f"Could not read image {image_path}: {e}")
        return None
    except Exception as e:
        logger.error(f"Error getting metadata for {image_path}: {e}")
        return None


def get_image_dimensions(image_path: Path) -> Optional[Tuple[int, int]]:
    """
    Get image dimensions without loading full image data.

    Args:
        image_path: Path to image file

    Returns:
        Tuple of (width, height) in pixels, or None if image cannot be read
    """
    try:
        with Image.open(image_path) as img:
            return img.size
    except Exception as e:
        logger.warning(f"Could not get dimensions for {image_path}: {e}")
        return None


def get_image_format(image_path: Path) -> Optional[str]:
    """
    Get image format (JPEG, PNG, etc.).

    Args:
        image_path: Path to image file

    Returns:
        Format string (e.g., "JPEG", "PNG"), or None if cannot be determined
    """
    try:
        with Image.open(image_path) as img:
            return img.format
    except Exception as e:
        logger.warning(f"Could not determine format for {image_path}: {e}")
        return None


def is_supported_format(file_path: Path) -> bool:
    """
    Check if file has a supported image format.

    Args:
        file_path: Path to file

    Returns:
        True if file extension is in supported formats
    """
    return file_path.suffix.lower() in SUPPORTED_FORMATS


def validate_image_file(image_path: Path) -> Tuple[bool, Optional[str]]:
    """
    Validate that a file is a readable image.

    Performs comprehensive validation:
    - File exists and is readable
    - Extension is supported
    - File can be opened as image
    - Image data is not corrupt

    Args:
        image_path: Path to image file

    Returns:
        Tuple of (is_valid, error_message)
        - If valid: (True, None)
        - If invalid: (False, "error description")
    """
    if not image_path.exists():
        return False, f"File not found: {image_path}"

    if not image_path.is_file():
        return False, f"Path is not a file: {image_path}"

    if not is_supported_format(image_path):
        return False, f"Unsupported format: {image_path.suffix}"

    try:
        with Image.open(image_path) as img:
            # Verify image data is readable
            img.verify()

        # Reopen to get actual dimensions (verify closes the file)
        with Image.open(image_path) as img:
            width, height = img.size
            if width <= 0 or height <= 0:
                return False, f"Invalid dimensions: {width}x{height}"

        return True, None

    except (IOError, OSError) as e:
        return False, f"Cannot read image: {e}"
    except Exception as e:
        return False, f"Corrupt or invalid image: {e}"


def filter_valid_images(file_paths: List[Path]) -> List[Path]:
    """
    Filter list to only include valid image files.

    Args:
        file_paths: List of file paths to check

    Returns:
        List of paths that are valid images
    """
    valid_images = []

    for path in file_paths:
        is_valid, _ = validate_image_file(path)
        if is_valid:
            valid_images.append(path)

    return valid_images


def find_images_in_directory(
    directory: Path,
    recursive: bool = True,
    extensions: Optional[List[str]] = None
) -> List[Path]:
    """
    Find all image files in a directory.

    Args:
        directory: Directory to search
        recursive: If True, search subdirectories recursively
        extensions: List of extensions to include (e.g., [".jpg", ".png"]).
                   If None, uses all supported formats.

    Returns:
        List of paths to image files

    Raises:
        FileNotFoundError: If directory doesn't exist
        ValueError: If path is not a directory
    """
    if not directory.exists():
        raise FileNotFoundError(f"Directory not found: {directory}")

    if not directory.is_dir():
        raise ValueError(f"Path is not a directory: {directory}")

    if extensions is None:
        extensions = list(SUPPORTED_FORMATS)
    else:
        # Normalize extensions to lowercase with dot
        extensions = [
            ext.lower() if ext.startswith('.') else f'.{ext.lower()}'
            for ext in extensions
        ]

    image_files: List[Path] = []

    pattern = "**/*" if recursive else "*"

    for path in directory.glob(pattern):
        if path.is_file() and path.suffix.lower() in extensions:
            image_files.append(path)

    return image_files


def group_images_by_format(images: List[Path]) -> Dict[str, List[Path]]:
    """
    Group images by their file format.

    Args:
        images: List of image paths

    Returns:
        Dictionary mapping format (lowercase extension) to list of image paths
    """
    groups: Dict[str, List[Path]] = {}

    for img_path in images:
        fmt = img_path.suffix.lower()
        if fmt not in groups:
            groups[fmt] = []
        groups[fmt].append(img_path)

    return groups


def get_format_quality_score(file_path: Path) -> int:
    """
    Get quality score for image format.

    Higher score indicates better quality format (e.g., PNG > JPEG).

    Args:
        file_path: Path to image file

    Returns:
        Quality score (1-5), or 0 if format is unsupported
    """
    ext = file_path.suffix.lower()
    return FORMAT_QUALITY_RANK.get(ext, 0)


def compare_image_quality(img1: Path, img2: Path) -> int:
    """
    Compare quality of two images based on resolution and format.

    Args:
        img1: Path to first image
        img2: Path to second image

    Returns:
        -1 if img1 is better quality
         0 if equal quality
         1 if img2 is better quality

    Note: This is a simple comparison. For more sophisticated quality
          assessment, use ImageQualityAnalyzer from quality.py module.
    """
    meta1 = get_image_metadata(img1)
    meta2 = get_image_metadata(img2)

    if meta1 is None and meta2 is None:
        return 0
    if meta1 is None:
        return 1
    if meta2 is None:
        return -1

    # Compare resolution first
    if meta1.resolution != meta2.resolution:
        return -1 if meta1.resolution > meta2.resolution else 1

    # If same resolution, compare format quality
    fmt1_score = get_format_quality_score(img1)
    fmt2_score = get_format_quality_score(img2)

    if fmt1_score != fmt2_score:
        return -1 if fmt1_score > fmt2_score else 1

    # If same format, compare file size (larger is better for same format/resolution)
    if meta1.size_bytes != meta2.size_bytes:
        return -1 if meta1.size_bytes > meta2.size_bytes else 1

    return 0


def get_best_quality_image(images: List[Path]) -> Optional[Path]:
    """
    Select the best quality image from a list.

    Selection criteria (in order):
    1. Highest resolution (width * height)
    2. Best format (PNG > JPEG > GIF, etc.)
    3. Largest file size

    Args:
        images: List of image paths to compare

    Returns:
        Path to best quality image, or None if all images are invalid
    """
    if not images:
        return None

    valid_images = filter_valid_images(images)
    if not valid_images:
        return None

    # Get metadata for all valid images
    metadata_list = [
        (img, get_image_metadata(img))
        for img in valid_images
    ]

    # Filter out images where metadata couldn't be extracted
    metadata_list = [(img, meta) for img, meta in metadata_list if meta is not None]

    if not metadata_list:
        return None

    # Sort by quality criteria
    def quality_key(item: Tuple[Path, ImageMetadata]) -> Tuple[int, int, int]:
        img_path, meta = item
        return (
            meta.resolution,                      # Higher resolution is better
            get_format_quality_score(img_path),  # Better format is better
            meta.size_bytes                      # Larger file is better (less compression)
        )

    sorted_images = sorted(metadata_list, key=quality_key, reverse=True)

    return sorted_images[0][0]


def format_file_size(size_bytes: int) -> str:
    """
    Format file size in human-readable format.

    Args:
        size_bytes: File size in bytes

    Returns:
        Formatted string (e.g., "1.5 MB", "234 KB")
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


def get_image_info_string(image_path: Path) -> str:
    """
    Get formatted information string for an image.

    Args:
        image_path: Path to image file

    Returns:
        Formatted string with image information
    """
    meta = get_image_metadata(image_path)

    if meta is None:
        return f"{image_path.name}: [Cannot read image]"

    size_str = format_file_size(meta.size_bytes)

    return (
        f"{image_path.name}: "
        f"{meta.width}x{meta.height}, "
        f"{meta.format}, "
        f"{size_str}"
    )
