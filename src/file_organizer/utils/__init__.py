"""Utility modules for file reading, text processing, and chart generation."""

from __future__ import annotations

from pathlib import Path

from file_organizer.utils.readers import FileTooLargeError


def is_hidden(path: Path) -> bool:
    """Return True if any file or directory component is hidden."""
    return any(part.startswith(".") and part not in {".", ".."} for part in path.parts)


__all__ = ["FileTooLargeError", "is_hidden"]
