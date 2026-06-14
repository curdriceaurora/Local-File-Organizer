# pyre-ignore-all-errors
"""Readers for archive formats: ZIP, 7Z, TAR, RAR.

Each public ``read_X_file`` function accepts either a path (legacy) or an
open binary file-like via the ``fileobj`` keyword. The file-like path is the
SafeDir-friendly entry point: callers open via ``SafeDir.open_for_reader``,
wrap in ``os.fdopen(fd, "rb")``, and hand to the reader. Path-based callers
continue to work unchanged.

The underlying parse logic lives in private ``_parse_X`` helpers so the
fileobj and path branches share a single implementation.
"""

from __future__ import annotations

import tarfile
import zipfile
from pathlib import Path
from typing import BinaryIO

try:
    import py7zr

    PY7ZR_AVAILABLE = True
except ImportError:
    PY7ZR_AVAILABLE = False

try:
    import rarfile

    RARFILE_AVAILABLE = True
except ImportError:
    RARFILE_AVAILABLE = False

from loguru import logger

from file_organizer.utils.readers._base import FileReadError, _check_fd_size


def _parse_zip(fileobj: BinaryIO, max_files: int, label: str) -> str:
    with zipfile.ZipFile(fileobj, "r") as zf:
        # Cache infolist() so the archive is iterated only once
        entries = zf.infolist()
        info_list = entries[:max_files]

        # Calculate statistics
        total_files = len(entries)
        total_compressed = sum(info.compress_size for info in entries)
        total_uncompressed = sum(info.file_size for info in entries)
        compression_ratio = (
            (1 - total_compressed / total_uncompressed) * 100 if total_uncompressed > 0 else 0
        )

        # Check for encryption
        encrypted = any(info.flag_bits & 0x1 for info in entries)

        # Build metadata string
        lines = [
            f"ZIP Archive: {label}",
            f"Total files: {total_files}",
            f"Compressed size: {total_compressed / 1024:.2f} KB",
            f"Uncompressed size: {total_uncompressed / 1024:.2f} KB",
            f"Compression ratio: {compression_ratio:.1f}%",
            f"Encrypted: {'Yes' if encrypted else 'No'}",
            f"\nFiles (first {min(max_files, total_files)}):",
        ]

        # List files
        for info in info_list:
            size_kb = info.file_size / 1024
            compressed_kb = info.compress_size / 1024
            lines.append(f"  - {info.filename} ({size_kb:.2f} KB → {compressed_kb:.2f} KB)")

        if total_files > max_files:
            lines.append(f"  ... and {total_files - max_files} more files")

        text = "\n".join(lines)
        logger.debug(f"Extracted metadata from ZIP archive {label} ({total_files} files)")
        return text


def read_zip_file(
    file_path: str | Path | None = None,
    max_files: int = 50,
    *,
    fileobj: BinaryIO | None = None,
) -> str:
    """Read contents and metadata from a ZIP archive.

    Args:
        file_path: Path to ZIP file (legacy entry point).
        max_files: Maximum number of files to list
        fileobj: Open binary file-like (SafeDir-friendly entry point). When
            given, ``file_path`` is used only for the log label.

    Returns:
        String with archive metadata and file listing

    Raises:
        FileReadError: If file cannot be read
        FileTooLargeError: If the file behind ``fileobj`` exceeds the limit.
        ValueError: If neither ``file_path`` nor ``fileobj`` is provided.
    """
    max_files = max(0, int(max_files))
    if fileobj is not None:
        label = Path(file_path).name if file_path is not None else "<fileobj>"
        # Size check outside the try so ``FileTooLargeError`` propagates.
        _check_fd_size(fileobj)
        try:
            return _parse_zip(fileobj, max_files, label)
        except Exception as e:  # Intentional catch-all: zipfile raises library-specific errors
            raise FileReadError(f"Failed to read ZIP file {label}: {e}") from e
    if file_path is None:
        raise ValueError("read_zip_file requires file_path or fileobj")
    path = Path(file_path)
    try:
        with path.open(
            "rb"
        ) as f:  # safedir: ok — legacy path-branch; SafeDir-aware callers pass fileobj=
            return _parse_zip(f, max_files, path.name)
    except Exception as e:  # Intentional catch-all: zipfile raises library-specific errors
        raise FileReadError(f"Failed to read ZIP file {path}: {e}") from e


def _parse_7z(fileobj: BinaryIO, max_files: int, label: str) -> str:
    with py7zr.SevenZipFile(fileobj, "r") as archive:
        all_files = archive.list()

        # Calculate statistics
        total_files = len(all_files)
        total_compressed = sum(f.compressed or 0 for f in all_files)
        total_uncompressed = sum(f.uncompressed or 0 for f in all_files)
        compression_ratio = (
            (1 - total_compressed / total_uncompressed) * 100 if total_uncompressed > 0 else 0
        )

        # Check for encryption
        encrypted = archive.password_protected if hasattr(archive, "password_protected") else False

        # Build metadata string
        lines = [
            f"7Z Archive: {label}",
            f"Total files: {total_files}",
            f"Compressed size: {total_compressed / 1024:.2f} KB",
            f"Uncompressed size: {total_uncompressed / 1024:.2f} KB",
            f"Compression ratio: {compression_ratio:.1f}%",
            f"Encrypted: {'Yes' if encrypted else 'No'}",
            f"\nFiles (first {min(max_files, total_files)}):",
        ]

        # List files
        for file_info in all_files[:max_files]:
            size_kb = (file_info.uncompressed or 0) / 1024
            compressed_kb = (file_info.compressed or 0) / 1024
            lines.append(f"  - {file_info.filename} ({size_kb:.2f} KB → {compressed_kb:.2f} KB)")

        if total_files > max_files:
            lines.append(f"  ... and {total_files - max_files} more files")

        text = "\n".join(lines)
        logger.debug(f"Extracted metadata from 7Z archive {label} ({total_files} files)")
        return text


def read_7z_file(
    file_path: str | Path | None = None,
    max_files: int = 50,
    *,
    fileobj: BinaryIO | None = None,
) -> str:
    """Read contents and metadata from a 7Z archive.

    Args:
        file_path: Path to 7Z file (legacy entry point).
        max_files: Maximum number of files to list
        fileobj: Open binary file-like (SafeDir-friendly entry point). When
            given, ``file_path`` is used only for the log label.

    Returns:
        String with archive metadata and file listing

    Raises:
        FileReadError: If file cannot be read
        ImportError: If py7zr is not installed
        FileTooLargeError: If the file behind ``fileobj`` exceeds the limit.
        ValueError: If neither ``file_path`` nor ``fileobj`` is provided.
    """
    if not PY7ZR_AVAILABLE:
        raise ImportError("py7zr is not installed. Install with: pip install py7zr")

    max_files = max(0, int(max_files))
    if fileobj is not None:
        label = Path(file_path).name if file_path is not None else "<fileobj>"
        _check_fd_size(fileobj)
        try:
            return _parse_7z(fileobj, max_files, label)
        except Exception as e:  # Intentional catch-all: py7zr raises library-specific errors
            raise FileReadError(f"Failed to read 7Z file {label}: {e}") from e
    if file_path is None:
        raise ValueError("read_7z_file requires file_path or fileobj")
    path = Path(file_path)
    try:
        with path.open(
            "rb"
        ) as f:  # safedir: ok — legacy path-branch; SafeDir-aware callers pass fileobj=
            return _parse_7z(f, max_files, path.name)
    except Exception as e:  # Intentional catch-all: py7zr raises library-specific errors
        raise FileReadError(f"Failed to read 7Z file {path}: {e}") from e


def _detect_tar_compression(name_lower: str) -> str:
    """Return the compression label shown in tar metadata.

    Derived from the filename, not the magic bytes — matches legacy behavior.
    ``<fileobj>`` (the default label when no path was supplied) reports
    ``"Unknown"`` rather than the misleading ``"None"``.
    """
    if name_lower.endswith(".tar.gz") or name_lower.endswith(".tgz"):
        return "GZ"
    if name_lower.endswith(".tar.bz2") or name_lower.endswith(".tbz2"):
        return "BZ2"
    if name_lower.endswith(".tar.xz") or name_lower.endswith(".xz"):
        return "XZ"
    if name_lower.endswith(".tar"):
        return "None"
    # Caller did not supply a usable filename (e.g. direct fileobj= without
    # file_path=). tarfile itself auto-detects the underlying stream below;
    # we just can't display the type in the metadata header.
    return "Unknown"


def _parse_tar(fileobj: BinaryIO, max_files: int, label: str) -> str:
    # ``mode="r:*"`` auto-detects compression from the stream's magic bytes
    # (gz / bz2 / xz / plain); requires the fileobj to be seekable, which
    # both ``path.open("rb")`` and ``os.fdopen(SafeDir fd, "rb")`` are.
    with tarfile.open(fileobj=fileobj, mode="r:*") as tf:
        members = tf.getmembers()

        # Calculate statistics
        total_files = len([m for m in members if m.isfile()])
        total_dirs = len([m for m in members if m.isdir()])
        total_size = sum(m.size for m in members if m.isfile())

        compression_type = _detect_tar_compression(label.lower())

        # Build metadata string
        lines = [
            f"TAR Archive: {label}",
            f"Compression: {compression_type}",
            f"Total files: {total_files}",
            f"Total directories: {total_dirs}",
            f"Total size: {total_size / 1024:.2f} KB",
            f"\nFiles (first {min(max_files, total_files)}):",
        ]

        # List files (skip directories)
        file_members = [m for m in members if m.isfile()][:max_files]
        for member in file_members:
            size_kb = member.size / 1024
            lines.append(f"  - {member.name} ({size_kb:.2f} KB)")

        if total_files > max_files:
            lines.append(f"  ... and {total_files - max_files} more files")

        text = "\n".join(lines)
        logger.debug(f"Extracted metadata from TAR archive {label} ({total_files} files)")
        return text


def read_tar_file(
    file_path: str | Path | None = None,
    max_files: int = 50,
    *,
    fileobj: BinaryIO | None = None,
) -> str:
    """Read contents and metadata from a TAR/GZ/BZ2/XZ archive.

    Args:
        file_path: Path to TAR file (``.tar``, ``.tar.gz`` / ``.tgz``,
            ``.tar.bz2`` / ``.tbz2``, ``.tar.xz`` / ``.xz``). Used as
            the compression-type hint when ``fileobj`` is supplied.
        max_files: Maximum number of files to list
        fileobj: Open binary file-like (SafeDir-friendly entry point). The
            stream must be seekable (file fds and ``BytesIO`` both qualify);
            compression is auto-detected from the magic bytes by ``tarfile``
            itself, while the displayed compression type still derives from
            the filename hint.

    Returns:
        String with archive metadata and file listing

    Raises:
        FileReadError: If file cannot be read
        FileTooLargeError: If the file behind ``fileobj`` exceeds the limit.
        ValueError: If neither ``file_path`` nor ``fileobj`` is provided.
    """
    max_files = max(0, int(max_files))
    if fileobj is not None:
        label = Path(file_path).name if file_path is not None else "<fileobj>"
        _check_fd_size(fileobj)
        try:
            return _parse_tar(fileobj, max_files, label)
        except Exception as e:  # Intentional catch-all: tarfile raises library-specific errors
            raise FileReadError(f"Failed to read TAR file {label}: {e}") from e
    if file_path is None:
        raise ValueError("read_tar_file requires file_path or fileobj")
    path = Path(file_path)
    try:
        with path.open(
            "rb"
        ) as f:  # safedir: ok — legacy path-branch; SafeDir-aware callers pass fileobj=
            return _parse_tar(f, max_files, path.name)
    except Exception as e:  # Intentional catch-all: tarfile raises library-specific errors
        raise FileReadError(f"Failed to read TAR file {path}: {e}") from e


def _parse_rar(fileobj: BinaryIO, max_files: int, label: str) -> str:
    with rarfile.RarFile(fileobj, "r") as rf:
        info_list = rf.infolist()

        # Calculate statistics
        total_files = len(info_list)
        total_compressed = sum(info.compress_size for info in info_list)
        total_uncompressed = sum(info.file_size for info in info_list)
        compression_ratio = (
            (1 - total_compressed / total_uncompressed) * 100 if total_uncompressed > 0 else 0
        )

        # Check for encryption
        encrypted = rf.needs_password()

        # Build metadata string
        lines = [
            f"RAR Archive: {label}",
            f"Total files: {total_files}",
            f"Compressed size: {total_compressed / 1024:.2f} KB",
            f"Uncompressed size: {total_uncompressed / 1024:.2f} KB",
            f"Compression ratio: {compression_ratio:.1f}%",
            f"Encrypted: {'Yes' if encrypted else 'No'}",
            f"\nFiles (first {min(max_files, total_files)}):",
        ]

        # List files
        for info in info_list[:max_files]:
            size_kb = info.file_size / 1024
            compressed_kb = info.compress_size / 1024
            lines.append(f"  - {info.filename} ({size_kb:.2f} KB → {compressed_kb:.2f} KB)")

        if total_files > max_files:
            lines.append(f"  ... and {total_files - max_files} more files")

        text = "\n".join(lines)
        logger.debug(f"Extracted metadata from RAR archive {label} ({total_files} files)")
        return text


def read_rar_file(
    file_path: str | Path | None = None,
    max_files: int = 50,
    *,
    fileobj: BinaryIO | None = None,
) -> str:
    """Read contents and metadata from a RAR archive.

    Args:
        file_path: Path to RAR file (legacy entry point).
        max_files: Maximum number of files to list
        fileobj: Open binary file-like (SafeDir-friendly entry point). When
            given, ``file_path`` is used only for the log label.

    Returns:
        String with archive metadata and file listing

    Raises:
        FileReadError: If file cannot be read
        ImportError: If rarfile is not installed
        FileTooLargeError: If the file behind ``fileobj`` exceeds the limit.
        ValueError: If neither ``file_path`` nor ``fileobj`` is provided.
    """
    if not RARFILE_AVAILABLE:
        raise ImportError(
            "rarfile is not installed. Install with: pip install rarfile\n"
            "Note: RAR support also requires unrar command-line tool to be installed."
        )

    max_files = max(0, int(max_files))
    if fileobj is not None:
        label = Path(file_path).name if file_path is not None else "<fileobj>"
        _check_fd_size(fileobj)
        try:
            return _parse_rar(fileobj, max_files, label)
        except rarfile.RarCannotExec as e:
            raise FileReadError(
                f"Failed to read RAR file {label}: unrar tool not found. "
                "Install the unrar command-line tool to extract RAR archives."
            ) from e
        except Exception as e:  # Intentional catch-all: rarfile raises library-specific errors
            raise FileReadError(f"Failed to read RAR file {label}: {e}") from e
    if file_path is None:
        raise ValueError("read_rar_file requires file_path or fileobj")
    path = Path(file_path)
    try:
        with path.open(
            "rb"
        ) as f:  # safedir: ok — legacy path-branch; SafeDir-aware callers pass fileobj=
            return _parse_rar(f, max_files, path.name)
    except rarfile.RarCannotExec as e:
        raise FileReadError(
            f"Failed to read RAR file {path}: unrar tool not found. "
            "Install the unrar command-line tool to extract RAR archives."
        ) from e
    except Exception as e:  # Intentional catch-all: rarfile raises library-specific errors
        raise FileReadError(f"Failed to read RAR file {path}: {e}") from e
