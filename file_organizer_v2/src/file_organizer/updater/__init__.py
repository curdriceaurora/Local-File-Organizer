"""Auto-update mechanism for File Organizer.

Checks GitHub Releases for new versions, downloads with SHA256
verification, and performs atomic binary replacement.
"""
from __future__ import annotations

from file_organizer.updater.checker import ReleaseInfo, UpdateChecker
from file_organizer.updater.installer import UpdateInstaller
from file_organizer.updater.manager import UpdateManager

__all__ = [
    "ReleaseInfo",
    "UpdateChecker",
    "UpdateInstaller",
    "UpdateManager",
]
