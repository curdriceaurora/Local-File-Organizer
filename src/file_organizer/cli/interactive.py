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

from file_organizer.cli.state import _get_state

console = Console()


def confirm_action(message: str, *, default: bool = False) -> bool:
    """Ask the user to confirm an action.

    If the global CLI state has `yes` enabled, automatically confirms and returns True.
    If `no_interactive` is enabled, returns the provided `default` without prompting.

    Parameters:
        message (str): Prompt text shown to the user.
        default (bool): Value returned when non-interactive mode is active.

    Returns:
        bool: `True` if the action is confirmed, `False` otherwise.
    """
    state = _get_state()
    if state.yes:
        return True
    if state.no_interactive:
        return default
    return Confirm.ask(message, default=default)  # type: ignore[no-any-return]


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
    """Prompt the user to select one value from a list of allowed choices.

    If the global CLI state has `no_interactive` enabled and `default` is provided, returns `default` without prompting.

    Parameters:
        message (str): Text displayed to the user when prompting.
        choices (Sequence[str]): Permitted choice strings shown to the user.
        default (str | None): Value returned automatically in non-interactive mode or used as the prompt's default.

    Returns:
        The chosen string from `choices`.
    """
    if _get_state().no_interactive and default is not None:
        return default
    if default is not None:
        return Prompt.ask(message, choices=list(choices), default=default)  # type: ignore[no-any-return]
    return Prompt.ask(message, choices=list(choices))  # type: ignore[no-any-return]


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
