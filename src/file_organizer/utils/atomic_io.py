"""Atomic file-write helpers.

Provides :func:`fsync_directory` — a POSIX-only helper that fsyncs a
directory entry after an atomic rename so the rename is durable on crash.

Windows does not support opening directories with :func:`os.open`, so the
function is a no-op on that platform.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def fsync_directory(path: Path) -> None:
    """Fsync *path*'s parent directory to persist a preceding atomic rename.

    On POSIX systems, calling :func:`os.replace` to atomically rename a temp
    file into its final location is not guaranteed to be durable until the
    containing directory entry is also fsynced.  Windows neither requires nor
    supports this pattern (``os.open`` on a directory raises
    :class:`PermissionError`), so this function is a no-op there.

    Args:
        path: The final destination path whose parent directory should be
            fsynced.
    """
    if sys.platform == "win32":
        return
    dir_fd = os.open(str(path.parent), os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)
