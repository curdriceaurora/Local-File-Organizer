"""Image utility functions for deduplication operations.

Provides helper functions for image validation, metadata extraction,
format conversion, and batch processing operations.

Every image read goes through :func:`safedir_image_open`, which routes
``PIL.Image.open`` through a SafeDir-opened file descriptor on POSIX. A
symlink swapped into the organize root between the directory walk and the
read is refused with ``SymlinkRejected`` (an ``OSError`` subclass) rather
than dereferenced — closes the symlink-following surface in the image dedup
ingestion pipeline (#264). On Windows (where SafeDir's ``dir_fd`` +
``O_NOFOLLOW`` primitives are unavailable) the legacy path-based
``Image.open`` is used.

**Anchoring**: callers that have a trusted-root context (the directory they
walked to find the image) should pass ``trusted_root=`` to
:func:`safedir_image_open`. The helper then traverses every component of the
relative path with ``open_subdir`` so each intermediate directory is checked
for symlinks too — closes the nested-symlink-ancestor TOCTOU window. Without
``trusted_root``, the helper falls back to parent-rooted opening (only the
final component is protected; suitable for standalone validation calls that
don't sit behind a directory walk).
"""

from __future__ import annotations

import contextlib
import logging
import os
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError
from PIL.Image import DecompressionBombError

from file_organizer.core.path_guard import safe_walk
from file_organizer.utils.safedir import SafeDir

logger = logging.getLogger(__name__)

# Supported image formats
SUPPORTED_FORMATS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif", ".webp"}


@contextlib.contextmanager
def safedir_image_open(
    image_path: Path,
    *,
    trusted_root: Path | None = None,
) -> Iterator[tuple[Image.Image, int | None]]:
    """Yield ``(PIL.Image, fd)`` opened via SafeDir; refuses symlinks.

    Args:
        image_path: Path to the image file.
        trusted_root: Anchor directory whose contents are trusted. When given,
            the helper opens ``trusted_root`` as a SafeDir and traverses each
            intermediate component of ``image_path.relative_to(trusted_root)``
            via ``open_subdir`` — each step rejects symlinks with
            ``O_NOFOLLOW``, closing the nested-symlink-ancestor TOCTOU window.
            When ``None``, falls back to opening ``image_path.parent`` directly
            (only the final component is protected; OK for standalone
            validation calls without a walk context).

    Yields:
        ``(img, fd)`` where ``fd`` is the underlying SafeDir-opened file
        descriptor (or ``None`` on the Windows / non-SafeDir fallback path).
        Callers that need race-free metadata reads (file size, mtime) should
        use ``os.fstat(fd)`` rather than ``image_path.stat()`` — the latter can
        mismatch on a post-open swap.

    Raises:
        SymlinkRejected: If ``image_path`` or any intermediate ancestor (under
            ``trusted_root``, when supplied) is a symlink. Subclasses
            ``OSError`` so callers' existing ``except OSError`` paths catch
            refused symlinks too.
        ValueError: If ``image_path`` is not under ``trusted_root``.
        OSError: For other open failures (permission denied, etc.).
    """
    if sys.platform == "win32":
        with Image.open(image_path) as img:
            yield img, None
        return

    stack = contextlib.ExitStack()
    img: Image.Image | None = None
    fd: int | None = None
    try:
        # Construction phase — narrowly catch NotImplementedError here so a
        # NotImplementedError raised inside the yield (by the caller's code or
        # by a PIL operation) propagates normally rather than being mistaken
        # for "SafeDir unavailable".
        try:
            stack.__enter__()
            if trusted_root is None:
                # Parent-rooted (legacy / standalone): only the final
                # component is O_NOFOLLOW-protected. Documented above.
                sd = stack.enter_context(SafeDir.open_root(image_path.parent))
                name = image_path.name
            else:
                # Trusted-root traversal: every intermediate component is
                # rejected if it's a symlink. ``relative_to`` raises ValueError
                # if the image is outside the trusted root — itself a security
                # violation worth surfacing.
                relative = image_path.relative_to(trusted_root)
                parts = relative.parts
                if not parts:
                    raise ValueError(
                        f"image_path {image_path!r} equals trusted_root {trusted_root!r}; "
                        "expected a file inside the root"
                    )
                sd = stack.enter_context(SafeDir.open_root(trusted_root))
                for part in parts[:-1]:
                    sd = stack.enter_context(sd.open_subdir(part))
                name = parts[-1]
            fd = sd.open_for_reader(name)
            # fdopen takes ownership only once it returns; explicitly close the
            # raw fd if fdopen itself raises.
            try:
                fileobj = os.fdopen(fd, "rb", closefd=True)
            except OSError:
                os.close(fd)
                raise
            stack.enter_context(fileobj)
            img = stack.enter_context(Image.open(fileobj))
        except NotImplementedError:
            # SafeDir's POSIX primitives unavailable on this build; close any
            # partially-entered stack frames and fall back to direct
            # ``Image.open(path)``. Yield from inside the fallback's own
            # ``with`` so cleanup is structured.
            stack.close()
            logger.debug("SafeDir unavailable; using legacy Image.open for %s", image_path.name)
            with Image.open(image_path) as fallback_img:
                yield fallback_img, None
            return

        # Yield from outside the construction-try so the caller's exceptions
        # propagate cleanly — including NotImplementedError raised inside the
        # with-block body, which used to be swallowed.
        assert img is not None  # always set by the construction phase
        yield img, fd
    finally:
        stack.close()


# Format preference ranking (higher is better quality)
FORMAT_QUALITY_RANK = {
    ".png": 5,  # Lossless
    ".tiff": 5,  # Lossless
    ".tif": 5,  # Lossless
    ".bmp": 4,  # Lossless but large
    ".webp": 3,  # Can be lossless or lossy
    ".jpg": 2,  # Lossy
    ".jpeg": 2,  # Lossy
    ".gif": 1,  # Limited color palette
}


class ImageMetadata:
    """Container for image metadata.

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
        self, path: Path, width: int, height: int, image_format: str, mode: str, size_bytes: int
    ):
        """Initialize ImageMetadata."""
        self.path = path
        self.width = width
        self.height = height
        self.format = image_format
        self.mode = mode
        self.size_bytes = size_bytes
        self.resolution = width * height

    def __repr__(self) -> str:
        """Return string representation of ImageMetadata."""
        return (
            f"ImageMetadata(path={self.path.name}, "
            f"size={self.width}x{self.height}, "
            f"format={self.format}, "
            f"bytes={self.size_bytes})"
        )

    def to_dict(self) -> dict[str, Any]:
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


def get_image_metadata(image_path: Path) -> ImageMetadata | None:
    """Extract metadata from an image file.

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
        # Stat from the SafeDir-opened fd so size_bytes describes the same
        # non-symlink file the dimensions were read from. Falls back to
        # ``image_path.stat()`` when ``fd is None`` (Windows / SafeDir-
        # unavailable code path).
        with safedir_image_open(image_path) as (img, fd):
            width, height = img.size
            image_format = img.format or "unknown"
            mode = img.mode
            size_bytes = os.fstat(fd).st_size if fd is not None else image_path.stat().st_size

        return ImageMetadata(
            path=image_path,
            width=width,
            height=height,
            image_format=image_format,
            mode=mode,
            size_bytes=size_bytes,
        )
    except OSError as e:
        logger.warning(f"Could not read image {image_path}: {e}")
        return None
    except DecompressionBombError as e:
        logger.error(f"Decompression bomb detected for {image_path}: {e}")
        return None
    except (ValueError, TypeError, RuntimeError, UnidentifiedImageError) as e:
        logger.error(f"Error getting metadata for {image_path}: {e}")
        return None


def get_image_dimensions(image_path: Path) -> tuple[int, int] | None:
    """Get image dimensions without loading full image data.

    Args:
        image_path: Path to image file

    Returns:
        Tuple of (width, height) in pixels, or None if image cannot be read
    """
    try:
        with safedir_image_open(image_path) as (img, _fd):
            return img.size  # type: ignore[no-any-return]
    except (OSError, ValueError) as e:
        logger.warning(f"Could not get dimensions for {image_path}: {e}")
        return None


def get_image_format(image_path: Path) -> str | None:
    """Get image format (JPEG, PNG, etc.).

    Args:
        image_path: Path to image file

    Returns:
        Format string (e.g., "JPEG", "PNG"), or None if cannot be determined
    """
    try:
        with safedir_image_open(image_path) as (img, _fd):
            return img.format  # type: ignore[no-any-return]
    except (OSError, ValueError) as e:
        logger.warning(f"Could not determine format for {image_path}: {e}")
        return None


def is_supported_format(file_path: Path) -> bool:
    """Check if file has a supported image format.

    Args:
        file_path: Path to file

    Returns:
        True if file extension is in supported formats
    """
    return file_path.suffix.lower() in SUPPORTED_FORMATS


def validate_image_file(image_path: Path) -> tuple[bool, str | None]:
    """Validate that a file is a readable image.

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
        with safedir_image_open(image_path) as (img, _fd):
            # Verify image data is readable
            img.verify()

        # Reopen to get actual dimensions (verify closes the file)
        with safedir_image_open(image_path) as (img, _fd):
            width, height = img.size
            if width <= 0 or height <= 0:
                return False, f"Invalid dimensions: {width}x{height}"

        return True, None

    except OSError as e:
        return False, f"Cannot read image: {e}"
    except DecompressionBombError as e:
        return False, f"Oversized image blocked: {e}"
    except (ValueError, TypeError, RuntimeError, UnidentifiedImageError) as e:
        return False, f"Corrupt or invalid image: {e}"


def filter_valid_images(file_paths: list[Path]) -> list[Path]:
    """Filter list to only include valid image files.

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
    directory: Path, recursive: bool = True, extensions: list[str] | None = None
) -> list[Path]:
    """Find all image files in a directory.

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
            ext.lower() if ext.startswith(".") else f".{ext.lower()}" for ext in extensions
        ]

    image_files: list[Path] = []

    # Hidden images are part of this public helper's established result set;
    # safe_walk still supplies the required symlink and file-type filtering.
    for path in safe_walk(directory, recursive=recursive, include_hidden=True):
        if path.suffix.lower() in extensions:
            image_files.append(path)

    return image_files


def group_images_by_format(images: list[Path]) -> dict[str, list[Path]]:
    """Group images by their file format.

    Args:
        images: List of image paths

    Returns:
        Dictionary mapping format (lowercase extension) to list of image paths
    """
    groups: dict[str, list[Path]] = {}

    for img_path in images:
        fmt = img_path.suffix.lower()
        if fmt not in groups:
            groups[fmt] = []
        groups[fmt].append(img_path)

    return groups


def get_format_quality_score(file_path: Path) -> int:
    """Get quality score for image format.

    Higher score indicates better quality format (e.g., PNG > JPEG).

    Args:
        file_path: Path to image file

    Returns:
        Quality score (1-5), or 0 if format is unsupported
    """
    ext = file_path.suffix.lower()
    return FORMAT_QUALITY_RANK.get(ext, 0)


def compare_image_quality(img1: Path, img2: Path) -> int:
    """Compare quality of two images based on resolution and format.

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


def get_best_quality_image(images: list[Path]) -> Path | None:
    """Select the best quality image from a list.

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

    # Get metadata for all valid images, filtering out None values
    valid_metadata: list[tuple[Path, ImageMetadata]] = []
    for img in valid_images:
        meta = get_image_metadata(img)
        if meta is not None:
            valid_metadata.append((img, meta))

    if not valid_metadata:
        return None

    # Sort by quality criteria
    def quality_key(item: tuple[Path, ImageMetadata]) -> tuple[int, int, int]:
        """Generate quality score tuple for image sorting.

        Args:
            item: Tuple of (image_path, metadata) to score

        Returns:
            Tuple of (resolution, format_quality, file_size) for sorting
        """
        img_path, meta = item
        return (
            meta.resolution,  # Higher resolution is better
            get_format_quality_score(img_path),  # Better format is better
            meta.size_bytes,  # Larger file is better (less compression)
        )

    sorted_images = sorted(valid_metadata, key=quality_key, reverse=True)

    return sorted_images[0][0]


def format_file_size(size_bytes: int) -> str:
    """Format file size in human-readable format.

    Args:
        size_bytes: File size in bytes

    Returns:
        Formatted string (e.g., "1.5 MB", "234 KB")
    """
    size: float = float(size_bytes)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"


def get_image_info_string(image_path: Path) -> str:
    """Get formatted information string for an image.

    Args:
        image_path: Path to image file

    Returns:
        Formatted string with image information
    """
    meta = get_image_metadata(image_path)

    if meta is None:
        return f"{image_path.name}: [Cannot read image]"

    size_str = format_file_size(meta.size_bytes)

    return f"{image_path.name}: {meta.width}x{meta.height}, {meta.format}, {size_str}"
