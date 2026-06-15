"""Shared base utilities for file readers."""

from __future__ import annotations

import os
from pathlib import Path
from typing import BinaryIO


class FileReadError(Exception):
    """Exception raised when file reading fails."""


class FileTooLargeError(OSError):
    """Raised when a file exceeds the maximum allowed size for processing."""


MAX_FILE_SIZE_BYTES: int = 500 * 1024 * 1024  # 500 MB


def _check_file_size(file_path: Path, max_bytes: int = MAX_FILE_SIZE_BYTES) -> None:
    """Raise FileTooLargeError if file exceeds max_bytes.

    .. note::
        This is an **internal** helper for the ``readers`` sub-package.
        It is not part of the public API and may change without notice.

    Args:
        file_path: Path to the file to check.
        max_bytes: Maximum allowed file size in bytes.

    Raises:
        FileTooLargeError: If the file is larger than max_bytes.
    """
    try:
        size = file_path.stat().st_size
    except OSError:
        return  # Let the reader handle missing/inaccessible files
    if size > max_bytes:
        mb = size / (1024 * 1024)
        limit_mb = max_bytes / (1024 * 1024)
        raise FileTooLargeError(
            f"File too large to process: {mb:.1f} MB (limit: {limit_mb:.0f} MB): {file_path}"
        )


def _check_fd_size(fileobj: BinaryIO, max_bytes: int = MAX_FILE_SIZE_BYTES) -> None:
    """Raise FileTooLargeError if the file behind *fileobj* exceeds max_bytes.

    Uses ``os.fstat`` on the underlying fd — avoids re-resolving the path
    (which could be intercepted between a previous ``lstat`` and now).
    Falls back silently if the fileobj doesn't expose ``fileno()`` (e.g.
    in-memory ``BytesIO`` used in tests); the reader's downstream parse
    will raise its own error if the content is truly oversized.
    """
    try:
        fd = fileobj.fileno()
    except (AttributeError, OSError, ValueError):
        # In-memory wrappers (``BytesIO``) raise ``io.UnsupportedOperation``
        # which subclasses both ``OSError`` and ``ValueError`` — be liberal.
        return
    try:
        size = os.fstat(fd).st_size
    except OSError:
        return
    if size > max_bytes:
        mb = size / (1024 * 1024)
        limit_mb = max_bytes / (1024 * 1024)
        raise FileTooLargeError(
            f"File too large to process: {mb:.1f} MB (limit: {limit_mb:.0f} MB)"
        )


# Decompression-bomb guard for archive readers. A bomb has a tiny *compressed*
# size (so it sails past MAX_FILE_SIZE_BYTES) but an enormous declared
# *uncompressed* size. Archive readers only read the central directory (no
# decompression happens here), but the declared totals let us refuse the
# archive before any downstream consumer extracts it.
MAX_ARCHIVE_UNCOMPRESSED_BYTES: int = 2 * 1024 * 1024 * 1024  # 2 GB declared expansion
MAX_ARCHIVE_COMPRESSION_RATIO: float = 1000.0
# Only apply the ratio test once the declared expansion passes this floor, so a
# small but legitimately highly-compressible archive is not flagged as a bomb.
_COMPRESSION_RATIO_FLOOR_BYTES: int = 64 * 1024 * 1024  # 64 MB


def _check_decompression_bomb(
    total_uncompressed: int,
    total_compressed: int,
    label: str,
    *,
    max_uncompressed: int = MAX_ARCHIVE_UNCOMPRESSED_BYTES,
    max_ratio: float = MAX_ARCHIVE_COMPRESSION_RATIO,
) -> None:
    """Raise FileTooLargeError if an archive's *declared* expansion is bomb-like.

    .. note::
        Internal helper for the ``readers`` sub-package; not public API.

    Two independent triggers:

    - **absolute**: declared uncompressed total exceeds ``max_uncompressed``;
    - **ratio**: uncompressed/compressed exceeds ``max_ratio`` once the expanded
      size passes ``_COMPRESSION_RATIO_FLOOR_BYTES`` (so an ordinary, highly
      compressible archive is not flagged).

    Args:
        total_uncompressed: Sum of declared uncompressed entry sizes.
        total_compressed: Sum of declared compressed entry sizes (0 when the
            format reports no per-entry compressed size, e.g. tar — then only
            the absolute trigger applies).
        label: Archive label for the error message.
        max_uncompressed: Absolute cap on declared uncompressed bytes.
        max_ratio: Maximum allowed uncompressed/compressed ratio (applied only
            above ``_COMPRESSION_RATIO_FLOOR_BYTES``).

    Raises:
        FileTooLargeError: If either trigger fires.
    """
    if total_uncompressed > max_uncompressed:
        gb = total_uncompressed / (1024**3)
        limit_gb = max_uncompressed / (1024**3)
        raise FileTooLargeError(
            f"Archive expands to {gb:.1f} GB (limit: {limit_gb:.0f} GB): {label}"
        )
    if (
        total_compressed > 0
        and total_uncompressed > _COMPRESSION_RATIO_FLOOR_BYTES
        and total_uncompressed / total_compressed > max_ratio
    ):
        ratio = total_uncompressed / total_compressed
        raise FileTooLargeError(
            f"Archive compression ratio {ratio:.1f}:1 exceeds {max_ratio:.0f}:1 "
            f"(possible decompression bomb): {label}"
        )
