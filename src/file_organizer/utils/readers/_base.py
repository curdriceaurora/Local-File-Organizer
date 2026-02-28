"""Shared base utilities for file readers."""

from __future__ import annotations

from pathlib import Path


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
