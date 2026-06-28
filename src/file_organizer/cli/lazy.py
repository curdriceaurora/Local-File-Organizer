"""Lazy loading infrastructure for Typer to improve CLI startup latency."""

from __future__ import annotations

import importlib

import click
import typer
import typer.core
import typer.main

# Mapping of command/group name -> (module_path, attribute_name, short_help)
LAZY_COMMANDS: dict[str, tuple[str, str, str]] = {
    "config": ("file_organizer.cli.config_cli", "config_app", "Manage configuration and profiles."),
    "model": ("file_organizer.cli.models_cli", "model_app", "Manage AI models."),
    "autotag": ("file_organizer.cli.autotag_v2", "autotag_app", "Automatically tag files."),
    "benchmark": ("file_organizer.cli.benchmark", "benchmark_app", "Run performance benchmarks."),
    "copilot": ("file_organizer.cli.copilot", "copilot_app", "AI assistant for file operations."),
    "daemon": ("file_organizer.cli.daemon", "daemon_app", "Run the background file watcher."),
    "dedupe": ("file_organizer.cli.dedupe_v2", "dedupe_app", "Find and manage duplicate files."),
    "rules": ("file_organizer.cli.rules", "rules_app", "Manage automated organization rules."),
    "setup": ("file_organizer.cli.setup", "setup_app", "Initial configuration wizard."),
    "suggest": ("file_organizer.cli.suggest", "suggest_app", "Get AI suggestions for files."),
    "update": ("file_organizer.cli.update", "update_app", "Update the application."),
    "api": (
        "file_organizer.cli.api",
        "api_app",
        "Remote API operations via the official Python client.",
    ),
    "api-keys": (
        "file_organizer.cli.api_keys",
        "api_keys_app",
        "Manage API keys locally.",
    ),
    "marketplace": (
        "file_organizer.cli.marketplace",
        "marketplace_app",
        "Browse and manage marketplace plugins.",
    ),
}


class LazyCommandProxy:
    """Legacy compatibility shim for ``tests/cli/test_lazy.py``.

    The production command path now uses ``LazyTyperGroup.get_command`` directly.
    This class remains only for test coverage of the historical ``_load`` contract.
    """

    def __init__(self, name: str, module_name: str, attr_name: str, help_text: str) -> None:
        """Initialize the proxy metadata used for deferred command loading."""
        self.name = name
        self.module_name = module_name
        self.attr_name = attr_name
        self.help_text = help_text
        self._real_cmd: click.Command | None = None

    def _load(self) -> click.Command:
        if self._real_cmd is None:
            try:
                module = importlib.import_module(self.module_name)
                obj = getattr(module, self.attr_name)
            except (ImportError, AttributeError) as exc:
                raise click.ClickException(
                    f"Failed to load lazy command '{self.attr_name}' from '{self.module_name}': {exc}"
                ) from exc
            if isinstance(obj, typer.Typer):
                self._real_cmd = typer.main.get_group(obj)
            else:
                self._real_cmd = obj
        return self._real_cmd


def _load_lazy_command(module_name: str, attr_name: str) -> click.Command:
    """Load a lazily-registered command or Typer sub-app.

    Args:
        module_name: Module path containing the lazy command object.
        attr_name: Attribute name containing a Typer app or click command.

    Returns:
        Loaded click-compatible command object.

    Raises:
        click.ClickException: If importing ``module_name`` or looking up
            ``attr_name`` fails.
    """
    try:
        module = importlib.import_module(module_name)
        obj = getattr(module, attr_name)
    except (ImportError, AttributeError) as exc:
        raise click.ClickException(
            f"Failed to load lazy command '{attr_name}' from '{module_name}': {exc}"
        ) from exc
    if isinstance(obj, typer.Typer):
        return typer.main.get_group(obj)
    return obj


class LazyTyperGroup(typer.core.TyperGroup):
    """A TyperGroup that integrates with LazyCommandProxy for deferred loading."""

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        """Stash help-flag presence in ctx.meta before Click consumes the args.

        Click's ``Group.parse_args`` calls ``resolve_command``, which removes
        ``--help`` / ``-h`` from ``ctx.args`` before the group callback fires.
        By the time ``main_callback`` runs, the flags are gone and
        ``ctx.resilient_parsing`` is ``False`` (it is only ``True`` during
        shell-completion parsing, not for ``--help``).  Stashing the flag here
        gives ``main_callback`` a reliable signal to bypass the first-run setup
        gate when the user just wants help text.

        Parameters:
            ctx (click.Context): The Click invocation context.
            args (list[str]): Raw argument list before Click's parsing pass.

        Returns:
            list[str]: Remaining/unconsumed arguments after parsing.
        """
        # Only inspect tokens before the end-of-options marker (``--``).
        # Tokens after ``--`` are positional values and should not be
        # mistaken for a help invocation (e.g. ``fo search -- --help``
        # must NOT bypass the setup gate).
        # Only ``--help`` is checked, not ``-h``: this CLI does not register
        # ``-h`` as a help alias (Click's default help option is ``--help``
        # only), so ``-h`` can legitimately appear as a value to another
        # option (e.g. ``--type -h``) and must not trigger a gate bypass.
        args_before_terminator = args[: args.index("--")] if "--" in args else args
        ctx.meta["help_requested"] = "--help" in args_before_terminator
        return super().parse_args(ctx, args)

    def list_commands(self, ctx: click.Context) -> list[str]:
        """Return a combined list of available command names including lazy-registered commands.

        Returns:
            list[str]: Sorted list of unique command names exposed by this group.
        """
        rv = super().list_commands(ctx)
        rv.extend(LAZY_COMMANDS.keys())
        return sorted(set(rv))

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        """Resolve a command by name, loading lazy-registered commands on demand.

        Parameters:
            ctx (click.Context): The Click context for command resolution.
            cmd_name (str): The command name to resolve.

        Returns:
            click.Command | None: A loaded command when found, `None` otherwise.
        """
        if cmd_name in LAZY_COMMANDS:
            module_name, attr_name, _ = LAZY_COMMANDS[cmd_name]
            return _load_lazy_command(module_name, attr_name)
        return super().get_command(ctx, cmd_name)
