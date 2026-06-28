# pyre-ignore-all-errors
"""CLI sub-commands for copilot rule management.

Provides commands to list, add, remove, preview, import, and export
organisation rules.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from file_organizer.cli.path_validation import resolve_cli_path
from file_organizer.services.copilot.rules import ApplyResult

rules_app = typer.Typer(
    name="rules",
    help="Manage copilot organisation rules.",
)

console = Console()


@rules_app.command(name="list")
def rules_list(
    rule_set: Annotated[str, typer.Option("--set", "-s", help="Rule set name.")] = "default",
) -> None:
    """List all rules in a rule set."""
    from file_organizer.services.copilot.rules import RuleManager

    mgr = RuleManager()
    rs = mgr.load_rule_set(rule_set)

    if not rs.rules:
        console.print(f"No rules in set '{rule_set}'.")
        return

    table = Table(title=f"Rules: {rule_set}")
    table.add_column("Name", style="bold")
    table.add_column("Enabled")
    table.add_column("Priority", justify="right")
    table.add_column("Conditions")
    table.add_column("Action")
    table.add_column("Destination")

    for rule in sorted(rs.rules, key=lambda r: r.priority, reverse=True):
        status = "[green]yes[/green]" if rule.enabled else "[red]no[/red]"
        conds = ", ".join(f"{c.condition_type.value}={c.value}" for c in rule.conditions)
        table.add_row(
            rule.name,
            status,
            str(rule.priority),
            conds or "[dim]none[/dim]",
            rule.action.action_type.value,
            rule.action.destination or "[dim]-[/dim]",
        )

    console.print(table)


@rules_app.command(name="sets")
def rules_sets() -> None:
    """List available rule sets."""
    from file_organizer.services.copilot.rules import RuleManager

    mgr = RuleManager()
    names = mgr.list_rule_sets()
    if not names:
        console.print("No rule sets found. Create one with [bold]rules add[/bold].")
        return
    console.print(f"{len(names)} rule set(s):")
    for n in names:
        console.print(f"  - {n}")


@rules_app.command(name="add")
def rules_add(
    name: Annotated[str, typer.Argument(help="Rule name.")],
    extension: Annotated[
        str | None,
        typer.Option("--ext", help="File extension filter (e.g. '.pdf,.docx')."),
    ] = None,
    pattern: Annotated[str | None, typer.Option("--pattern", help="Filename glob pattern.")] = None,
    action: Annotated[
        str,
        typer.Option(
            "--action",
            "-a",
            help="Action type (move, rename, tag, categorize, archive, copy, delete, hardlink, symlink).",
        ),
    ] = "move",
    destination: Annotated[
        str, typer.Option("--dest", "-d", help="Destination path or pattern.")
    ] = "",
    priority: Annotated[
        int, typer.Option("--priority", "-p", help="Rule priority (higher = first).")
    ] = 0,
    rule_set: Annotated[str, typer.Option("--set", "-s", help="Target rule set.")] = "default",
) -> None:
    """Add a new rule to a rule set."""
    from file_organizer.services.copilot.rules.models import (
        ActionType,
        ConditionType,
        Rule,
        RuleAction,
        RuleCondition,
    )
    from file_organizer.services.copilot.rules.rule_manager import RuleManager

    conditions: list[RuleCondition] = []
    if extension:
        conditions.append(RuleCondition(condition_type=ConditionType.EXTENSION, value=extension))
    if pattern:
        conditions.append(RuleCondition(condition_type=ConditionType.NAME_PATTERN, value=pattern))

    try:
        action_type = ActionType(action)
    except ValueError:
        console.print(f"[red]Unknown action: {action}[/red]")
        console.print(f"Valid: {', '.join(a.value for a in ActionType)}")
        raise typer.Exit(code=1) from None

    rule = Rule(
        name=name,
        conditions=conditions,
        action=RuleAction(action_type=action_type, destination=destination),
        priority=priority,
    )

    mgr = RuleManager()
    mgr.add_rule(rule_set, rule)
    console.print(f"[green]Added rule '{name}' to set '{rule_set}'[/green]")


@rules_app.command(name="remove")
def rules_remove(
    name: Annotated[str, typer.Argument(help="Rule name to remove.")],
    rule_set: Annotated[str, typer.Option("--set", "-s", help="Target rule set.")] = "default",
) -> None:
    """Remove a rule from a rule set."""
    from file_organizer.services.copilot.rules import RuleManager

    mgr = RuleManager()
    if mgr.remove_rule(rule_set, name):
        console.print(f"[green]Removed rule '{name}' from '{rule_set}'[/green]")
    else:
        console.print(f"[yellow]Rule '{name}' not found in '{rule_set}'[/yellow]")


@rules_app.command(name="toggle")
def rules_toggle(
    name: Annotated[str, typer.Argument(help="Rule name to toggle.")],
    rule_set: Annotated[str, typer.Option("--set", "-s", help="Target rule set.")] = "default",
) -> None:
    """Toggle a rule's enabled/disabled state."""
    from file_organizer.services.copilot.rules import RuleManager

    mgr = RuleManager()
    new_state = mgr.toggle_rule(rule_set, name)
    if new_state is None:
        console.print(f"[yellow]Rule '{name}' not found in '{rule_set}'[/yellow]")
    else:
        state_str = "[green]enabled[/green]" if new_state else "[red]disabled[/red]"
        console.print(f"Rule '{name}' is now {state_str}")


@rules_app.command(name="preview")
def rules_preview(
    directory: Annotated[Path, typer.Argument(help="Directory to preview against.")],
    rule_set: Annotated[str, typer.Option("--set", "-s", help="Rule set to evaluate.")] = "default",
    recursive: Annotated[
        bool, typer.Option("--recursive/--no-recursive", help="Recurse into subdirectories.")
    ] = True,
    max_files: Annotated[int, typer.Option("--max-files", help="Maximum files to scan.")] = 500,
) -> None:
    """Preview what rules would do (dry-run)."""
    from file_organizer.services.copilot.rules import PreviewEngine, RuleManager

    directory = resolve_cli_path(directory, must_exist=True, must_be_dir=True)
    mgr = RuleManager()
    rs = mgr.load_rule_set(rule_set)

    if not rs.enabled_rules:
        console.print(f"[yellow]No enabled rules in set '{rule_set}'[/yellow]")
        return

    engine = PreviewEngine()
    result = engine.preview(rs, directory, recursive=recursive, max_files=max_files)

    console.print(f"\n[bold]Preview: {result.summary}[/bold]\n")

    if result.matches:
        table = Table(title="Matched Files")
        table.add_column("File", style="cyan")
        table.add_column("Rule")
        table.add_column("Action")
        table.add_column("Destination")

        for m in result.matches[:50]:
            table.add_row(
                Path(m.file_path).name,
                m.rule_name,
                m.action_type,
                m.destination or "-",
            )
        console.print(table)

    if result.errors:
        for path, err in result.errors:
            console.print(f"  [red]Error:[/red] {path}: {err}")


def _print_apply_result(result: ApplyResult) -> None:
    console.print(f"\n[bold]Rules apply: {result.summary}[/bold]\n")

    if result.results:
        table = Table(title="Rule Actions")
        table.add_column("File", style="cyan")
        table.add_column("Rule")
        table.add_column("Action")
        table.add_column("Status")
        table.add_column("Destination")
        table.add_column("Message")

        for item in result.results[:50]:
            table.add_row(
                Path(item.file_path).name,
                item.rule_name,
                item.action_type,
                item.status,
                item.destination or "-",
                item.message or "-",
            )
        console.print(table)

    if result.transaction_id:
        console.print(f"[dim]Undo transaction: {result.transaction_id}[/dim]")

    if result.errors:
        for path, err in result.errors:
            console.print(f"  [red]Error:[/red] {path}: {err}")


@rules_app.command(name="apply")
def rules_apply(
    directory: Annotated[Path, typer.Argument(help="Directory to apply rules against.")],
    rule_set: Annotated[str, typer.Option("--set", "-s", help="Rule set to evaluate.")] = "default",
    recursive: Annotated[
        bool, typer.Option("--recursive/--no-recursive", help="Recurse into subdirectories.")
    ] = True,
    max_files: Annotated[int, typer.Option("--max-files", help="Maximum files to scan.")] = 500,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview actions only.")] = False,
) -> None:
    """Apply enabled rules to files."""
    from file_organizer.services.copilot.rules import RuleExecutor, RuleManager

    directory = resolve_cli_path(directory, must_exist=True, must_be_dir=True)
    mgr = RuleManager()
    rs = mgr.load_rule_set(rule_set)

    if not rs.enabled_rules:
        console.print(f"[yellow]No enabled rules in set '{rule_set}'[/yellow]")
        return

    result = RuleExecutor().apply(
        rs,
        directory,
        recursive=recursive,
        max_files=max_files,
        dry_run=dry_run,
    )
    _print_apply_result(result)
    if result.failed_count > 0 or result.errors:
        raise typer.Exit(code=1)


@rules_app.command(name="watch")
def rules_watch(
    directory: Annotated[Path, typer.Argument(help="Directory to watch/apply rules against.")],
    rule_set: Annotated[str, typer.Option("--set", "-s", help="Rule set to evaluate.")] = "default",
    recursive: Annotated[
        bool, typer.Option("--recursive/--no-recursive", help="Recurse into subdirectories.")
    ] = True,
    max_files: Annotated[int, typer.Option("--max-files", help="Maximum files to scan.")] = 500,
    interval: Annotated[
        float, typer.Option("--interval", help="Seconds between apply runs.")
    ] = 10.0,
    once: Annotated[bool, typer.Option("--once", help="Run one watch cycle and exit.")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview actions only.")] = False,
) -> None:
    """Continuously apply enabled rules for fire-and-forget workflows."""
    from file_organizer.services.copilot.rules import RuleExecutor, RuleManager

    directory = resolve_cli_path(directory, must_exist=True, must_be_dir=True)
    mgr = RuleManager()
    rs = mgr.load_rule_set(rule_set)

    if not rs.enabled_rules:
        console.print(f"[yellow]No enabled rules in set '{rule_set}'[/yellow]")
        return

    if interval <= 0:
        raise typer.BadParameter("--interval must be greater than 0")

    console.print(f"[green]Watching {directory} with rule set '{rule_set}'[/green]")
    executor = RuleExecutor()
    if once:
        result = executor.watch(
            rs,
            directory,
            recursive=recursive,
            max_files=max_files,
            interval_seconds=interval,
            once=True,
            dry_run=dry_run,
        )
        _print_apply_result(result)
        if result.failed_count > 0 or result.errors:
            raise typer.Exit(code=1)
        return

    try:
        executor.watch(
            rs,
            directory,
            recursive=recursive,
            max_files=max_files,
            interval_seconds=interval,
            dry_run=dry_run,
            on_cycle=_print_apply_result,
        )
    except KeyboardInterrupt:
        console.print("\n[yellow]Stopped watching rules.[/yellow]")


@rules_app.command(name="export")
def rules_export(
    rule_set: Annotated[str, typer.Option("--set", "-s", help="Rule set to export.")] = "default",
    output: Annotated[Path | None, typer.Option("--output", "-o", help="Output file path.")] = None,
) -> None:
    """Export a rule set to YAML."""
    import yaml

    from file_organizer.services.copilot.rules import RuleManager

    mgr = RuleManager()
    rs = mgr.load_rule_set(rule_set)
    content = yaml.dump(rs.to_dict(), default_flow_style=False, sort_keys=False)

    if output:
        # A.cli: output file may not exist (we're creating it). The parent
        # directory must exist and be a directory; if output itself already
        # exists it must be a regular file, otherwise write_text() would
        # raise IsADirectoryError after validation. Project F3: write via
        # tempfile + os.replace so a mid-write crash or concurrent writer
        # never leaves a half-written YAML export on disk.
        output = resolve_cli_path(output, must_exist=False, must_be_dir=False)
        if not output.parent.is_dir():
            raise typer.BadParameter(f"Output directory does not exist: {output.parent}")
        if output.exists() and not output.is_file():
            raise typer.BadParameter(f"Output path is not a regular file: {output}")
        tmp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=output.parent,
                prefix=f".{output.name}.",
                suffix=".tmp",
                delete=False,
            ) as tmp_file:
                tmp_path = Path(tmp_file.name)
                tmp_file.write(content)
            os.replace(tmp_path, output)
        except OSError as exc:
            if tmp_path is not None:
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
            console.print(f"[red]Failed to write YAML: {exc}[/red]")
            raise typer.Exit(code=1) from exc
        console.print(f"[green]Exported '{rule_set}' to {output}[/green]")
    else:
        console.print(content)


@rules_app.command(name="import")
def rules_import(
    file: Annotated[Path, typer.Argument(help="YAML file to import.")],
    rule_set: Annotated[
        str | None, typer.Option("--set", "-s", help="Override rule set name.")
    ] = None,
) -> None:
    """Import a rule set from a YAML file."""
    import yaml

    # A.cli: YAML file must exist and be a regular file. `must_be_dir=False`
    # on its own only rejects directories *when must_be_dir=True*; we need
    # an explicit is_file() guard to catch the dir-passed-to-import case
    # before yaml.safe_load tries to read_text() it.
    file = resolve_cli_path(file, must_exist=True, must_be_dir=False)
    if not file.is_file():
        raise typer.BadParameter(f"Input path is not a regular file: {file}")

    from file_organizer.services.copilot.rules import RuleManager, RuleSet

    try:
        raw = yaml.safe_load(file.read_text(encoding="utf-8"))
    except Exception as exc:
        console.print(f"[red]Failed to parse YAML: {exc}[/red]")
        raise typer.Exit(code=1) from None

    rs = RuleSet.from_dict(raw)
    if rule_set:
        rs.name = rule_set

    mgr = RuleManager()
    mgr.save_rule_set(rs)
    console.print(f"[green]Imported {len(rs.rules)} rules into set '{rs.name}'[/green]")
