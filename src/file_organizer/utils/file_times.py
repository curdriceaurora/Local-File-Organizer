"""Cross-platform file timestamp helpers."""

from __future__ import annotations

import os


def creation_timestamp(stat_result: os.stat_result, *, platform_name: str | None = None) -> float:
    """Return best-effort creation timestamp across platforms.

    Preference order:
    - macOS: ``st_birthtime`` (true file creation time)
    - Windows: ``st_ctime`` (creation time on NTFS)
    - Linux/other: ``st_mtime`` fallback
    """
    birth_time = getattr(stat_result, "st_birthtime", None)
    if isinstance(birth_time, int | float):
        return float(birth_time)
    if (platform_name or os.name) == "nt":
        return float(getattr(stat_result, "st_ctime", stat_result.st_mtime))
    return float(stat_result.st_mtime)
