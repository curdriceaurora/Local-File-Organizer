"""Guard public CLI entry points against capability-registry drift."""

from __future__ import annotations

import click
import pytest
import typer.core
import typer.main

from file_organizer.cli._typer_compat import Command, Context
from file_organizer.cli.lazy import DEVELOPER_ONLY_COMMANDS
from file_organizer.cli.main import app
from file_organizer.core.capabilities import Surface, get_capability_registry

pytestmark = [pytest.mark.ci, pytest.mark.unit]


def _discover_entry_points(
    group: Command,
    context: Context,
    path: tuple[str, ...] = ("fo",),
) -> tuple[set[str], set[str]]:
    """Recursively discover command paths and resolvable command/option entry points.

    Duck-types on ``list_commands``/``get_command`` rather than checking
    ``isinstance(command, click.Group)``: under typer >= 0.26, a Typer app's
    own group (and cli/lazy.py's LazyCommandProxy) are built on typer's
    vendored Click fork, not real click.Group, so that isinstance check
    would silently stop recursing into every lazy sub-app (see
    cli/_typer_compat.py). Likewise, a parameter is checked against both
    ``typer.core.TyperOption`` (what typer's own ``Option`` decorator
    produces) and real ``click.Option`` (what cli/profile.py's raw
    ``@click.option()``-decorated commands produce) -- neither is a
    subclass of the other post-0.26, so checking only one would silently
    drop every option path from whichever kind of command isn't checked.
    """
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
        child_context = Context(command, parent=context)
        for parameter in command.get_params(child_context):
            if isinstance(parameter, (typer.core.TyperOption, click.Option)):
                resolvable.update(
                    f"{serialized_path} {option}"
                    for option in (*parameter.opts, *parameter.secondary_opts)
                )
        if hasattr(command, "list_commands"):
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
    discovered, resolvable = _discover_entry_points(root, Context(root))
    registered = {
        entry_point
        for capability in get_capability_registry().capabilities
        for entry_point in capability.support_for(Surface.CLI).entry_points
    }

    missing = discovered - registered
    stale = registered - resolvable
    assert not missing, f"public CLI commands missing capability ownership: {sorted(missing)}"
    assert not stale, f"registry CLI entry points that do not resolve: {sorted(stale)}"
