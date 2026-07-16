"""Upload persistence helpers for web file operations."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import UploadFile

from file_organizer.api.exceptions import ApiError
from file_organizer.utils.atomic_write import atomic_write_with
from file_organizer.web._helpers import (
    MAX_UPLOAD_BYTES,
    UPLOAD_CHUNK_SIZE,
    sanitize_upload_name,
)
from file_organizer.web.file_validators import (
    validate_file_not_exists,
    validate_file_size,
    validate_upload_filename,
)


def process_file_uploads(
    files: list[UploadFile],
    target_dir: Path,
    allow_hidden: bool = False,
) -> tuple[int, list[str]]:
    """Process multiple file uploads to a target directory."""
    saved = 0
    errors: list[str] = []

    for upload in files:
        try:
            error = save_upload(upload, target_dir, allow_hidden)
        finally:
            if upload.file:
                upload.file.close()

        if error is None:
            saved += 1
        elif upload.filename:
            errors.append(error)

    return saved, errors


def save_upload(upload: UploadFile, target_dir: Path, allow_hidden: bool) -> str | None:
    """Validate and save a single upload file.

    Returns an error message string if the upload failed, an empty string if it
    was skipped because no filename was provided, or ``None`` on success.
    """
    if not upload.filename:
        return ""

    try:
        validate_upload_filename(upload.filename, allow_hidden=allow_hidden)
    except ApiError as exc:
        return exc.message

    filename = upload.filename
    assert filename is not None
    safe_name = sanitize_upload_name(filename, allow_hidden=allow_hidden)
    if safe_name is None:
        return f"Rejected {filename}: invalid filename."

    destination = target_dir / safe_name
    try:
        validate_file_not_exists(destination, safe_name)
    except ApiError as exc:
        return exc.message

    try:
        write_upload_chunks(upload, destination, safe_name)
    except ApiError as exc:
        return exc.message
    except OSError:
        return f"Failed to save {safe_name}."

    return None


def write_upload_chunks(upload: UploadFile, destination: Path, safe_name: str) -> None:
    """Stream upload chunks to disk, enforcing size limit."""
    total_bytes = 0

    def _writer(handle: Any) -> None:
        """Copy upload chunks into the atomic write handle."""
        nonlocal total_bytes
        while True:
            chunk = upload.file.read(UPLOAD_CHUNK_SIZE)
            if not chunk:
                break
            total_bytes += len(chunk)
            try:
                validate_file_size(total_bytes, MAX_UPLOAD_BYTES)
            except ApiError:
                raise ApiError(
                    status_code=400,
                    error="file_too_large",
                    message=f"{safe_name} exceeds upload size limit.",
                ) from None
            handle.write(chunk)

    atomic_write_with(destination, _writer, mode="wb")
