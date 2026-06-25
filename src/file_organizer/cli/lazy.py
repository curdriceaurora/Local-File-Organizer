"""Lazy loading infrastructure for Typer to improve CLI startup latency."""

from __future__ import annotations

import importlib
import typing

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
    "marketplace": (
        "file_organizer.cli.marketplace",
        "marketplace_app",
        "Browse and manage marketplace plugins.",
    ),
}


class LazyCommandProxy(click.Group):
    """A proxy for a click Group that defers importing its module."""

    def __init__(self, name: str, module_name: str, attr_name: str, help_text: str) -> None:
        """Initialize the proxy with the target module and command name."""
        super().__init__(name, help=help_text)
        self.module_name = module_name
        self.attr_name = attr_name
        self._real_cmd: click.Command | None = None

    def _load(self) -> click.Command:
        """Load and return the Click command or group referenced by this proxy, caching the result for subsequent calls.

        If the referenced attribute is a `typer.Typer`, it is converted to a Click group; otherwise the attribute is treated as a `click.Command` and returned as-is.

        Returns:
            click.Command: The resolved Click command or group.
        """
        if self._real_cmd is None:
            module = importlib.import_module(self.module_name)
            obj = getattr(module, self.attr_name)
            if isinstance(obj, typer.Typer):
                self._real_cmd = typer.main.get_group(obj)
            else:
                self._real_cmd = typing.cast(click.Command, obj)
        return self._real_cmd

    def invoke(self, ctx: click.Context) -> typing.Any:
        """Invoke the proxied command using the provided Click context.

        Parameters:
            ctx (click.Context): The Click context to pass to the underlying command.

        Returns:
            typing.Any: The value returned by the underlying command's `invoke` call.
        """
        return self._load().invoke(ctx)

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        """Delegate argument parsing to the lazily loaded command.

        Parameters:
            ctx (click.Context): Invocation context passed through to the real command.
            args (list[str]): The argument list to parse.

        Returns:
            list[str]: The list of remaining/unconsumed arguments after parsing.
        """
        return self._load().parse_args(ctx, args)

    def get_params(self, ctx: click.Context) -> list[click.Parameter]:
        """Delegate parameter retrieval to the lazily-loaded command.

        Returns:
            list[click.Parameter]: The parameters defined by the underlying command.
        """
        return self._load().get_params(ctx)

    def list_commands(self, ctx: click.Context) -> list[str]:
        """Return the subcommand names from the loaded command when that command implements a group interface.

        Returns:
            list[str]: The subcommand names provided by the loaded command, or an empty list if the loaded command does not provide `list_commands`.
        """
        cmd = self._load()
        if isinstance(cmd, click.Group):
            return cmd.list_commands(ctx)
        return []

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        """Delegate retrieval of a subcommand to the loaded command when that command is a group.

        Parameters:
            ctx (click.Context): Invocation context used for command lookup.
            cmd_name (str): Name of the subcommand to retrieve.

        Returns:
            click.Command | None: The resolved subcommand if found, `None` otherwise.
        """
        cmd = self._load()
        if isinstance(cmd, click.Group):
            return cmd.get_command(ctx, cmd_name)
        return None


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
        """Resolve a command by name, returning a LazyCommandProxy for entries registered in LAZY_COMMANDS.

        If `cmd_name` is present in LAZY_COMMANDS, a LazyCommandProxy configured with the registered
        module, attribute, and help text is returned; otherwise the base class resolution is used.

        Parameters:
            ctx (click.Context): The Click context for command resolution.
            cmd_name (str): The command name to resolve; if this name exists in LAZY_COMMANDS a proxy is returned.

        Returns:
            click.Command | None: A `LazyCommandProxy` or other `click.Command` when found, `None` if no command matches.
        """
        if cmd_name in LAZY_COMMANDS:
            module_name, attr_name, help_text = LAZY_COMMANDS[cmd_name]
            return LazyCommandProxy(cmd_name, module_name, attr_name, help_text)
        return super().get_command(ctx, cmd_name)
