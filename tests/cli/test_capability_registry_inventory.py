"""Guard public CLI entry points against capability-registry drift."""

from __future__ import annotations

import click
import pytest
import typer.main

from file_organizer.cli.lazy import DEVELOPER_ONLY_COMMANDS
from file_organizer.cli.main import app
from file_organizer.core.capabilities import Surface, get_capability_registry

pytestmark = [pytest.mark.ci, pytest.mark.unit]


def _discover_entry_points(
    group: click.Group,
    context: click.Context,
    path: tuple[str, ...] = ("fo",),
) -> tuple[set[str], set[str]]:
    """Recursively discover command paths and resolvable command/option entry points."""
    commands: set[str] = set()
    resolvable: set[str] = set()
    for command_name in group.list_commands(context):
        if len(path) == 1 and command_name in DEVELOPER_ONLY_COMMANDS:
            continue
        command = group.get_command(context, command_name)
        assert command is not None, f"listed CLI command {command_name!r} did not resolve"
        command_path = (*path, command_name)
        serialized_path = " ".join(command_path)
        resolvable.add(serialized_path)
        child_context = click.Context(command, parent=context)
        for parameter in command.get_params(child_context):
            if isinstance(parameter, click.Option):
                resolvable.update(
                    f"{serialized_path} {option}"
                    for option in (*parameter.opts, *parameter.secondary_opts)
                )
        if isinstance(command, click.Group):
            child_commands, child_resolvable = _discover_entry_points(
                command, child_context, command_path
            )
            commands.update(child_commands)
            resolvable.update(child_resolvable)
        else:
            commands.add(serialized_path)
    return commands, resolvable


def test_public_cli_commands_and_registry_entries_match() -> None:
    root = typer.main.get_group(app)
    discovered, resolvable = _discover_entry_points(root, click.Context(root))
    registered = {
        entry_point
        for capability in get_capability_registry().capabilities
        for entry_point in capability.support_for(Surface.CLI).entry_points
    }

    missing = discovered - registered
    stale = registered - resolvable
    assert not missing, f"public CLI commands missing capability ownership: {sorted(missing)}"
    assert not stale, f"registry CLI entry points that do not resolve: {sorted(stale)}"
