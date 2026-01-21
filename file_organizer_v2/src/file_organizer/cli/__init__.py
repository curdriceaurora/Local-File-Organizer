"""
Command-line interface modules for File Organizer.
"""

from .dedupe import dedupe_command
from .undo_redo import undo_command, redo_command, history_command

__all__ = [
    "dedupe_command",
    "undo_command",
    "redo_command",
    "history_command",
]
