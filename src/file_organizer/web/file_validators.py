"""Validation functions for web file operations."""

from __future__ import annotations

import os
from pathlib import Path

from file_organizer.api.exceptions import ApiError

_MAX_UPLOAD_BYTES = 25 * 1024 * 1024


def validate_upload_filename(filename: str, allow_hidden: bool = False) -> str:
    """Validate an upload filename.

    Args:
        filename: The filename to validate.
        allow_hidden: Whether to allow hidden files (starting with '.').

    Returns:
        The validated filename.

    Raises:
        ApiError: If the filename is invalid.
    """
    if not filename:
        raise ApiError(
            status_code=400,
            error="invalid_filename",
            message="Filename must not be empty",
        )

    raw_name = os.path.basename(filename).strip()
    if not allow_hidden and raw_name.startswith("."):
        raise ApiError(
            status_code=400,
            error="hidden_file_rejected",
            message=f"Hidden files are not allowed: {raw_name}",
        )

    return filename


def validate_file_size(size_bytes: int, max_bytes: int = _MAX_UPLOAD_BYTES) -> int:
    """Validate file size is within allowed limits.

    Args:
        size_bytes: The file size in bytes.
        max_bytes: Maximum allowed size in bytes.

    Returns:
        The validated size in bytes.

    Raises:
        ApiError: If the file size exceeds the limit.
    """
    if size_bytes > max_bytes:
        raise ApiError(
            status_code=400,
            error="file_too_large",
            message=f"File size {size_bytes} bytes exceeds upload limit of {max_bytes} bytes",
        )
    return size_bytes


def validate_file_not_exists(file_path: Path, filename: str) -> None:
    """Validate that a file does not already exist at the target path.

    Args:
        file_path: The full path where the file would be saved.
        filename: The filename for error messages.

    Raises:
        ApiError: If the file already exists.
    """
    if file_path.exists():
        raise ApiError(
            status_code=409,
            error="file_exists",
            message=f"File already exists: {filename}",
        )


def validate_upload_path(upload_dir: Path) -> Path:
    """Validate that the upload directory exists and is accessible.

    Args:
        upload_dir: The directory where files will be uploaded.

    Returns:
        The validated directory path.

    Raises:
        ApiError: If the directory does not exist or is not a directory.
    """
    if not upload_dir.exists():
        raise ApiError(
            status_code=400,
            error="invalid_path",
            message="Upload directory does not exist",
        )
    if not upload_dir.is_dir():
        raise ApiError(
            status_code=400,
            error="invalid_path",
            message="Upload path is not a directory",
        )
    return upload_dir
