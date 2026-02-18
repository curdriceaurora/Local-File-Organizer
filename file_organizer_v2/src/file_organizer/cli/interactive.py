"""Rich-based interactive prompts and progress helpers for the CLI.

All prompt functions respect a global ``--yes`` / ``--no-interactive``
flag so that scripts can suppress interactive behaviour.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeRemainingColumn,
)
from rich.prompt import Confirm, Prompt

# Module-level flags set by main_callback in main.py
_yes: bool = False
_no_interactive: bool = False

console = Console()


def set_flags(*, yes: bool = False, no_interactive: bool = False) -> None:
    """Update the module-level interactive flags.

    Called by ``main_callback()`` during CLI startup.

    Args:
        yes: If ``True``, auto-confirm all prompts.
        no_interactive: If ``True``, skip all interactive prompts.
    """
    global _yes, _no_interactive
    _yes = yes
    _no_interactive = no_interactive


def confirm_action(message: str, *, default: bool = False) -> bool:
    """Ask the user for confirmation.

    Returns ``True`` immediately when ``--yes`` is active.  Returns
    *default* when ``--no-interactive`` is active.

    Args:
        message: Prompt text.
        default: Default answer if non-interactive.

    Returns:
        ``True`` if the user confirmed (or auto-confirmed).
    """
    if _yes:
        return True
    if _no_interactive:
        return default
    return Confirm.ask(message, default=default)


def prompt_directory(message: str = "Enter directory path") -> Path:
    """Prompt the user for a valid directory path.

    Re-prompts until a valid directory is entered.

    Args:
        message: Prompt text.

    Returns:
        Validated ``Path`` pointing to an existing directory.
    """
    while True:
        raw = Prompt.ask(message)
        path = Path(raw).expanduser().resolve()
        if path.is_dir():
            return path
        console.print(f"[red]Not a valid directory: {path}[/red]")


def prompt_choice(
    message: str,
    choices: Sequence[str],
    *,
    default: str | None = None,
) -> str:
    """Prompt the user to pick from a list of choices.

    Args:
        message: Prompt text.
        choices: Allowed values.
        default: Pre-selected value.

    Returns:
        The chosen string.
    """
    if _no_interactive and default is not None:
        return default
    return Prompt.ask(message, choices=list(choices), default=default)


def create_progress() -> Progress:
    """Create a pre-configured Rich ``Progress`` bar.

    Returns:
        A ``Progress`` instance with spinner, description, bar, percentage,
        and ETA columns.
    """
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        console=console,
    )
