"""Utility modules for file reading, text processing, and chart generation."""

from __future__ import annotations

from pathlib import Path

from file_organizer.utils.readers import FileTooLargeError


def is_hidden(path: Path) -> bool:
    """Return True if the file or directory name starts with '.' (is hidden)."""
    return path.name.startswith(".")


__all__ = ["FileTooLargeError", "is_hidden"]
