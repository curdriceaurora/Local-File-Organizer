"""Command-line interface modules for File Organizer."""

from __future__ import annotations

# Lazy-load all CLI sub-apps and utilities to reduce startup latency.
# The entrypoint (file_organizer.cli:main) accesses `main` and `app` which
# trigger cli.main imports — this module defers everything else.

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

_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    "app": ("file_organizer.cli.main", "app"),
    "main": ("file_organizer.cli.main", "main"),
    "autotag_app": ("file_organizer.cli.autotag_v2", "autotag_app"),
    "complete_directory": ("file_organizer.cli.completion", "complete_directory"),
    "complete_file": ("file_organizer.cli.completion", "complete_file"),
    "copilot_app": ("file_organizer.cli.copilot", "copilot_app"),
    "daemon_app": ("file_organizer.cli.daemon", "daemon_app"),
    "dedupe_command": ("file_organizer.cli.dedupe", "dedupe_command"),
    "dedupe_app": ("file_organizer.cli.dedupe_v2", "dedupe_app"),
    "confirm_action": ("file_organizer.cli.interactive", "confirm_action"),
    "create_progress": ("file_organizer.cli.interactive", "create_progress"),
    "prompt_choice": ("file_organizer.cli.interactive", "prompt_choice"),
    "prompt_directory": ("file_organizer.cli.interactive", "prompt_directory"),
    "profile_command": ("file_organizer.cli.profile", "profile_command"),
    "rules_app": ("file_organizer.cli.rules", "rules_app"),
    "suggest_app": ("file_organizer.cli.suggest", "suggest_app"),
    "history_command": ("file_organizer.cli.undo_redo", "history_command"),
    "redo_command": ("file_organizer.cli.undo_redo", "redo_command"),
    "undo_command": ("file_organizer.cli.undo_redo", "undo_command"),
    "update_app": ("file_organizer.cli.update", "update_app"),
    "setup_autotag_parser": ("file_organizer.cli.autotag", "setup_autotag_parser"),
    "handle_autotag_command": ("file_organizer.cli.autotag", "handle_autotag_command"),
}


def __getattr__(name: str) -> object:
    """Lazily import CLI attributes on first access."""
    if name in _LAZY_IMPORTS:
        module_path, attr = _LAZY_IMPORTS[name]
        import importlib

        module = importlib.import_module(module_path)
        value = getattr(module, attr)
        # Cache in module globals to avoid repeated lookups
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
