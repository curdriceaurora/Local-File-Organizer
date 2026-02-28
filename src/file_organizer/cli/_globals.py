"""Mutable CLI global state shared across command modules.

These flags are set by the main callback before any command runs and may be
read by individual command modules via ``import file_organizer.cli._globals as _g``.
"""

from __future__ import annotations

verbose: bool = False
dry_run: bool = False
json_output: bool = False
yes: bool = False
no_interactive: bool = False
