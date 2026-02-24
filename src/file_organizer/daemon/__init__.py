"""Background daemon package.

Provides a long-running daemon service that combines file watching
with auto-organization, including PID file management, signal handling,
and periodic task scheduling.
"""

from __future__ import annotations

from .config import DaemonConfig
from .pid import PidFileManager
from .scheduler import DaemonScheduler
from .service import DaemonService

__all__ = [
    "DaemonConfig",
    "DaemonScheduler",
    "DaemonService",
    "PidFileManager",
]
