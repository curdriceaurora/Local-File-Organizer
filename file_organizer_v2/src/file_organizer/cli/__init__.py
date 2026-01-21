"""
Command-line interface modules for File Organizer.
"""

from .dedupe import dedupe_command
from .undo_redo import undo_command, redo_command, history_command
from .autotag import setup_autotag_parser, handle_autotag_command
from .profile import profile_command

__all__ = [
    "dedupe_command",
    "undo_command",
    "redo_command",
    "history_command",
    "setup_autotag_parser",
    "handle_autotag_command",
    "profile_command",
]
