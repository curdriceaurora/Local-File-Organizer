"""File system operations for the organizer.

Handles file collection, organization (copy/link), simulation,
fallback-by-extension, and empty-directory cleanup.  Extracted from
``organizer.py`` to separate I/O concerns from orchestration.
"""

from __future__ import annotations

import datetime
import os
import shutil
import sqlite3
from pathlib import Path

from loguru import logger
from rich.console import Console

from file_organizer.core.types import (
    AUDIO_EXTENSIONS,
    AUDIO_FALLBACK_FOLDER,
    IMAGE_FALLBACK_FOLDER,
    TEXT_FALLBACK_MAP,
    VIDEO_EXTENSIONS,
    VIDEO_FALLBACK_FOLDER,
)
from file_organizer.history.models import OperationType
from file_organizer.services import ProcessedFile, ProcessedImage
from file_organizer.undo import UndoManager


def collect_files(path: Path, console: Console) -> list[Path]:
    """Collect all non-hidden files from *path*.

    Args:
        path: Directory to scan or single file.
        console: Rich console for status output.

    Returns:
        List of discovered file paths.
    """
    files: list[Path] = []
    if path.is_file():
        files.append(path)
    else:
        for root, dirnames, filenames in os.walk(path):
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for filename in filenames:
                if not filename.startswith("."):
                    files.append(Path(root) / filename)

    console.print(f"[green]✓[/green] Found {len(files)} files")
    return files


def fallback_by_extension(files: list[Path]) -> list[ProcessedFile]:
    """Organize files by extension when the AI model is unavailable.

    Args:
        files: List of file paths to organize.

    Returns:
        List of ``ProcessedFile`` with extension-based folder assignment.
    """
    from file_organizer.core.types import IMAGE_EXTENSIONS as _IMG_EXT

    results: list[ProcessedFile] = []
    for file_path in files:
        ext = file_path.suffix.lower()
        if ext in TEXT_FALLBACK_MAP:
            folder = TEXT_FALLBACK_MAP[ext]
        elif ext in _IMG_EXT:
            try:
                year = str(
                    datetime.datetime.fromtimestamp(file_path.stat().st_mtime, tz=datetime.UTC).year
                )
            except OSError:
                year = "Unknown"
            folder = f"{IMAGE_FALLBACK_FOLDER}/{year}"
        elif ext in AUDIO_EXTENSIONS:
            folder = AUDIO_FALLBACK_FOLDER
        elif ext in VIDEO_EXTENSIONS:
            folder = VIDEO_FALLBACK_FOLDER
        else:
            folder = "Other"

        results.append(
            ProcessedFile(
                file_path=file_path,
                description=f"Extension-based organization (Ollama unavailable): {ext}",
                folder_name=folder,
                filename=file_path.stem,
                error=None,
            )
        )
        logger.debug("Fallback organized {} -> {}/{}", file_path.name, folder, file_path.name)
    return results


def organize_files(
    processed: list[ProcessedFile | ProcessedImage],
    output_path: Path,
    skip_existing: bool,
    *,
    use_hardlinks: bool,
    undo_manager: UndoManager | None,
    transaction_id: str | None,
) -> dict[str, list[str]]:
    """Copy or link processed files into the output directory.

    Args:
        processed: Processed file results.
        output_path: Target directory.
        skip_existing: Whether to skip files that already exist.
        use_hardlinks: Use hard links instead of copying.
        undo_manager: Optional undo manager for operation logging.
        transaction_id: Current transaction ID for undo support.

    Returns:
        Dictionary mapping folder names to file name lists.
    """
    organized: dict[str, list[str]] = {}
    output_path.mkdir(parents=True, exist_ok=True)

    for result in processed:
        if result.error:
            continue

        folder_path = output_path / result.folder_name
        folder_path.mkdir(parents=True, exist_ok=True)

        new_filename = f"{result.filename}{result.file_path.suffix}"
        new_path = folder_path / new_filename

        if new_path.exists() and skip_existing:
            logger.debug("Skipping existing file: {}", new_path)
            continue

        counter = 1
        while new_path.exists():
            new_filename = f"{result.filename}_{counter}{result.file_path.suffix}"
            new_path = folder_path / new_filename
            counter += 1

        try:
            if use_hardlinks:
                os.link(result.file_path, new_path)
            else:
                shutil.copy2(result.file_path, new_path)

            if undo_manager is not None and transaction_id is not None:
                try:
                    undo_manager.history.log_operation(
                        OperationType.COPY,
                        source_path=result.file_path,
                        destination_path=new_path,
                        transaction_id=transaction_id,
                    )
                except (OSError, ValueError, RuntimeError, sqlite3.Error) as undo_err:
                    logger.warning("Undo log failed for {}: {}", result.file_path, undo_err)

            organized.setdefault(result.folder_name, []).append(new_filename)

        except OSError as e:
            logger.opt(exception=e).error("Failed to organize {}", result.file_path)

    return organized


def simulate_organization(
    processed: list[ProcessedFile | ProcessedImage],
    output_path: Path,
) -> dict[str, list[str]]:
    """Simulate organization without moving files.

    Args:
        processed: Processed file results.
        output_path: Target directory (unused, for signature compatibility).

    Returns:
        Dictionary mapping folder names to file name lists.
    """
    organized: dict[str, list[str]] = {}
    for result in processed:
        if result.error:
            continue
        new_filename = f"{result.filename}{result.file_path.suffix}"
        organized.setdefault(result.folder_name, []).append(new_filename)
    return organized


def cleanup_empty_dirs(root: Path) -> None:
    """Remove empty directories under *root*, bottom-up.

    Only directories strictly below *root* are removed.

    Args:
        root: The output directory used during organize.
    """
    for dirpath in sorted(root.rglob("*"), reverse=True):
        if dirpath.is_dir() and dirpath != root:
            try:
                dirpath.rmdir()
            except OSError:
                pass
