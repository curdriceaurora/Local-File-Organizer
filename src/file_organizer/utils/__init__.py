"""Utility modules for file reading, text processing, and chart generation."""

from __future__ import annotations

from pathlib import Path

from file_organizer.utils.readers import FileTooLargeError


def is_hidden(path: Path) -> bool:
    """Return True if any part of the path is hidden (starts with '.')."""
    return any(part.startswith(".") for part in path.parts)


__all__ = ["FileTooLargeError", "is_hidden"]
