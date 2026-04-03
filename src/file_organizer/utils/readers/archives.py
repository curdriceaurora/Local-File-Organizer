# pyre-ignore-all-errors
"""Readers for archive formats: ZIP, 7Z, TAR, RAR."""

from __future__ import annotations

import tarfile
import zipfile
from pathlib import Path

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

from file_organizer.utils.readers._base import FileReadError


def read_zip_file(file_path: str | Path, max_files: int = 50) -> str:
    """Read contents and metadata from a ZIP archive.

    Args:
        file_path: Path to ZIP file
        max_files: Maximum number of files to list

    Returns:
        String with archive metadata and file listing

    Raises:
        FileReadError: If file cannot be read
    """
    max_files = max(0, int(max_files))
    file_path = Path(file_path)
    try:
        with zipfile.ZipFile(file_path, "r") as zf:
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
                f"ZIP Archive: {file_path.name}",
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
            logger.debug(
                f"Extracted metadata from ZIP archive {file_path.name} ({total_files} files)"
            )
            return text

    except Exception as e:  # Intentional catch-all: zipfile raises library-specific errors
        raise FileReadError(f"Failed to read ZIP file {file_path}: {e}") from e


def read_7z_file(file_path: str | Path, max_files: int = 50) -> str:
    """Read contents and metadata from a 7Z archive.

    Args:
        file_path: Path to 7Z file
        max_files: Maximum number of files to list

    Returns:
        String with archive metadata and file listing

    Raises:
        FileReadError: If file cannot be read
        ImportError: If py7zr is not installed
    """
    if not PY7ZR_AVAILABLE:
        raise ImportError("py7zr is not installed. Install with: pip install py7zr")

    max_files = max(0, int(max_files))
    file_path = Path(file_path)
    try:
        with py7zr.SevenZipFile(file_path, "r") as archive:
            all_files = archive.list()

            # Calculate statistics
            total_files = len(all_files)
            total_compressed = sum(f.compressed for f in all_files)
            total_uncompressed = sum(f.uncompressed for f in all_files)
            compression_ratio = (
                (1 - total_compressed / total_uncompressed) * 100 if total_uncompressed > 0 else 0
            )

            # Check for encryption
            encrypted = (
                archive.password_protected if hasattr(archive, "password_protected") else False
            )

            # Build metadata string
            lines = [
                f"7Z Archive: {file_path.name}",
                f"Total files: {total_files}",
                f"Compressed size: {total_compressed / 1024:.2f} KB",
                f"Uncompressed size: {total_uncompressed / 1024:.2f} KB",
                f"Compression ratio: {compression_ratio:.1f}%",
                f"Encrypted: {'Yes' if encrypted else 'No'}",
                f"\nFiles (first {min(max_files, total_files)}):",
            ]

            # List files
            for file_info in all_files[:max_files]:
                size_kb = file_info.uncompressed / 1024
                compressed_kb = file_info.compressed / 1024
                lines.append(
                    f"  - {file_info.filename} ({size_kb:.2f} KB → {compressed_kb:.2f} KB)"
                )

            if total_files > max_files:
                lines.append(f"  ... and {total_files - max_files} more files")

            text = "\n".join(lines)
            logger.debug(
                f"Extracted metadata from 7Z archive {file_path.name} ({total_files} files)"
            )
            return text

    except Exception as e:  # Intentional catch-all: py7zr raises library-specific errors
        raise FileReadError(f"Failed to read 7Z file {file_path}: {e}") from e


def read_tar_file(file_path: str | Path, max_files: int = 50) -> str:
    """Read contents and metadata from a TAR/GZ/BZ2 archive.

    Args:
        file_path: Path to TAR file (.tar, .tar.gz, .tgz, .tar.bz2)
        max_files: Maximum number of files to list

    Returns:
        String with archive metadata and file listing

    Raises:
        FileReadError: If file cannot be read
    """
    max_files = max(0, int(max_files))
    file_path = Path(file_path)
    try:
        with tarfile.open(file_path, "r:*") as tf:
            members = tf.getmembers()

            # Calculate statistics
            total_files = len([m for m in members if m.isfile()])
            total_dirs = len([m for m in members if m.isdir()])
            total_size = sum(m.size for m in members if m.isfile())

            # Determine compression type using name.endswith for compound extensions
            _name = file_path.name.lower()
            compression_type = "None"
            if _name.endswith(".tar.gz") or _name.endswith(".tgz"):
                compression_type = "GZ"
            elif _name.endswith(".tar.bz2") or _name.endswith(".tbz2"):
                compression_type = "BZ2"
            elif _name.endswith(".tar.xz") or _name.endswith(".xz"):
                compression_type = "XZ"

            # Build metadata string
            lines = [
                f"TAR Archive: {file_path.name}",
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
            logger.debug(
                f"Extracted metadata from TAR archive {file_path.name} ({total_files} files)"
            )
            return text

    except Exception as e:  # Intentional catch-all: tarfile raises library-specific errors
        raise FileReadError(f"Failed to read TAR file {file_path}: {e}") from e


def read_rar_file(file_path: str | Path, max_files: int = 50) -> str:
    """Read contents and metadata from a RAR archive.

    Args:
        file_path: Path to RAR file
        max_files: Maximum number of files to list

    Returns:
        String with archive metadata and file listing

    Raises:
        FileReadError: If file cannot be read
        ImportError: If rarfile is not installed
    """
    if not RARFILE_AVAILABLE:
        raise ImportError(
            "rarfile is not installed. Install with: pip install rarfile\n"
            "Note: RAR support also requires unrar command-line tool to be installed."
        )

    max_files = max(0, int(max_files))
    file_path = Path(file_path)
    try:
        with rarfile.RarFile(file_path, "r") as rf:
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
                f"RAR Archive: {file_path.name}",
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
            logger.debug(
                f"Extracted metadata from RAR archive {file_path.name} ({total_files} files)"
            )
            return text

    except Exception as e:  # Intentional catch-all: rarfile raises library-specific errors
        raise FileReadError(f"Failed to read RAR file {file_path}: {e}") from e
