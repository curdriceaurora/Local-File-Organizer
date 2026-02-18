"""
File system watcher package.

Provides real-time file system monitoring with debouncing, filtering,
and batch event processing using the watchdog library.
"""

from __future__ import annotations

from .config import WatcherConfig
from .handler import FileEventHandler
from .monitor import FileMonitor
from .queue import EventQueue, EventType, FileEvent

__all__ = [
    "EventQueue",
    "EventType",
    "FileEvent",
    "FileEventHandler",
    "FileMonitor",
    "WatcherConfig",
]
