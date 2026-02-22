"""
Command-line interface modules for File Organizer.
"""

from __future__ import annotations

from file_organizer.cli.main import app, main

from .autotag import handle_autotag_command, setup_autotag_parser
from .autotag_v2 import autotag_app
from .completion import complete_directory, complete_file
from .copilot import copilot_app
from .daemon import daemon_app
from .dedupe import dedupe_command
from .dedupe_v2 import dedupe_app
from .interactive import confirm_action, create_progress, prompt_choice, prompt_directory
from .profile import profile_command
from .rules import rules_app
from .suggest import suggest_app
from .undo_redo import history_command, redo_command, undo_command
from .update import update_app

__all__ = [
    "app",
    "autotag_app",
    "copilot_app",
    "daemon_app",
    "main",
    "complete_directory",
    "complete_file",
    "confirm_action",
    "create_progress",
    "dedupe_app",
    "dedupe_command",
    "history_command",
    "prompt_choice",
    "prompt_directory",
    "redo_command",
    "rules_app",
    "setup_autotag_parser",
    "handle_autotag_command",
    "suggest_app",
    "profile_command",
    "undo_command",
    "update_app",
]
