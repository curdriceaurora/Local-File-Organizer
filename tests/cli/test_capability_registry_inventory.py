"""Guard public CLI entry points against capability-registry drift."""

from __future__ import annotations

import click
import pytest
import typer.main

from file_organizer.cli.main import app
from file_organizer.core.capabilities import Surface, get_capability_registry

pytestmark = [pytest.mark.ci, pytest.mark.unit]

_DEVELOPER_ONLY_COMMANDS = {"benchmark", "docs"}


def test_public_cli_commands_are_assigned_to_capabilities() -> None:
    root = typer.main.get_group(app)
    root_context = click.Context(root)
    discovered: set[str] = set()
    for command_name in root.list_commands(root_context):
        if command_name in _DEVELOPER_ONLY_COMMANDS:
            continue
        command = root.get_command(root_context, command_name)
        if isinstance(command, click.Group):
            context = click.Context(command, parent=root_context)
            discovered.update(
                f"fo {command_name} {subcommand}" for subcommand in command.list_commands(context)
            )
        else:
            discovered.add(f"fo {command_name}")

    registered = {
        entry_point
        for capability in get_capability_registry().capabilities
        for entry_point in capability.support_for(Surface.CLI).entry_points
    }
    missing = {
        command
        for command in discovered
        if command not in registered
        and not any(entry_point.startswith(f"{command} ") for entry_point in registered)
    }

    assert not missing, f"public CLI commands missing capability ownership: {sorted(missing)}"
