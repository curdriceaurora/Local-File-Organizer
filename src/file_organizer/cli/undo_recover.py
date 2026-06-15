"""``fo recover`` — replay / sweep the durable_move journal (#1248, WP-1.2b).

A crash mid cross-device rollback move leaves the durable_move JSONL
journal with unfinished ``started`` / ``copied`` entries and possibly
orphan files on disk. :func:`durable_move.sweep` reconciles those on the
next run; this command exposes that reconciliation explicitly so an
operator can run it on demand.

``--dry-run`` reports what sweep WOULD do — it calls the same pure
:func:`durable_move.plan_recovery_actions` planner sweep uses, so the
preview and the real run can never drift — without mutating disk.
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from file_organizer.undo._journal import default_journal_path
from file_organizer.undo.durable_move import (
    plan_recovery_actions,
    read_journal_under_shared_lock,
    sweep,
)

console = Console()


def recover(
    journal: Path | None = typer.Option(
        None,
        "--journal",
        help="Path to the durable_move journal. Defaults to the shared undo journal.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Report planned recovery actions without mutating the journal or disk.",
    ),
) -> None:
    """Replay or sweep the durable_move journal to recover interrupted moves."""
    journal_path = journal if journal is not None else default_journal_path()

    if not journal_path.exists():
        console.print(f"No journal at {journal_path}; nothing to recover.")
        raise typer.Exit(code=0)

    if dry_run:
        _render_dry_run(journal_path)
        raise typer.Exit(code=0)

    try:
        sweep(journal_path)
    except OSError as exc:
        # Surface a clean error, not a stack trace — sweep can fail on
        # transient FS issues (permissions, disk full during compaction).
        console.print(f"[red]Recovery failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(f"Recovery sweep complete for {journal_path}.")
    raise typer.Exit(code=0)


def _render_dry_run(journal_path: Path) -> None:
    """Print the planner's decisions for the journal without mutating it."""
    entries = read_journal_under_shared_lock(journal_path)
    if not entries:
        console.print(f"Journal {journal_path} has no entries; nothing to recover.")
        return
    plan = plan_recovery_actions(entries)
    console.print(f"[bold]Planned recovery actions for {journal_path}[/bold] (dry run):")
    for action in plan:
        # ``markup=False`` so a verb/reason containing bracketed text
        # isn't swallowed as Rich style markup.
        console.print(f"  - {action.verb}: {action.reason}", markup=False)
