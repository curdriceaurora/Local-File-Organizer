# pyre-ignore-all-errors
"""CLI sub-commands for copilot rule management.

Provides commands to list, add, remove, preview, import, and export
organisation rules.
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

rules_app = typer.Typer(
    name="rules",
    help="Manage copilot organisation rules.",
)

console = Console()


@rules_app.command(name="list")
def rules_list(
    rule_set: str = typer.Option("default", "--set", "-s", help="Rule set name."),
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
    name: str = typer.Argument(..., help="Rule name."),
    extension: str | None = typer.Option(
        None, "--ext", help="File extension filter (e.g. '.pdf,.docx')."
    ),
    pattern: str | None = typer.Option(None, "--pattern", help="Filename glob pattern."),
    action: str = typer.Option(
        "move",
        "--action",
        "-a",
        help="Action type (move, rename, tag, categorize, archive, copy, delete).",
    ),
    destination: str = typer.Option("", "--dest", "-d", help="Destination path or pattern."),
    priority: int = typer.Option(0, "--priority", "-p", help="Rule priority (higher = first)."),
    rule_set: str = typer.Option("default", "--set", "-s", help="Target rule set."),
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
    name: str = typer.Argument(..., help="Rule name to remove."),
    rule_set: str = typer.Option("default", "--set", "-s", help="Target rule set."),
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
    name: str = typer.Argument(..., help="Rule name to toggle."),
    rule_set: str = typer.Option("default", "--set", "-s", help="Target rule set."),
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
    directory: Path = typer.Argument(..., help="Directory to preview against."),
    rule_set: str = typer.Option("default", "--set", "-s", help="Rule set to evaluate."),
    recursive: bool = typer.Option(
        True, "--recursive/--no-recursive", help="Recurse into subdirectories."
    ),
    max_files: int = typer.Option(500, "--max-files", help="Maximum files to scan."),
) -> None:
    """Preview what rules would do (dry-run)."""
    from file_organizer.services.copilot.rules import PreviewEngine, RuleManager

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


@rules_app.command(name="export")
def rules_export(
    rule_set: str = typer.Option("default", "--set", "-s", help="Rule set to export."),
    output: Path | None = typer.Option(None, "--output", "-o", help="Output file path."),
) -> None:
    """Export a rule set to YAML."""
    import yaml  # type: ignore[import-untyped]

    from file_organizer.services.copilot.rules import RuleManager

    mgr = RuleManager()
    rs = mgr.load_rule_set(rule_set)
    content = yaml.dump(rs.to_dict(), default_flow_style=False, sort_keys=False)

    if output:
        output.write_text(content, encoding="utf-8")
        console.print(f"[green]Exported '{rule_set}' to {output}[/green]")
    else:
        console.print(content)


@rules_app.command(name="import")
def rules_import(
    file: Path = typer.Argument(..., help="YAML file to import."),
    rule_set: str | None = typer.Option(None, "--set", "-s", help="Override rule set name."),
) -> None:
    """Import a rule set from a YAML file."""
    import yaml

    from file_organizer.services.copilot.rules import RuleManager, RuleSet

    if not file.exists():
        console.print(f"[red]File not found: {file}[/red]")
        raise typer.Exit(code=1)

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
