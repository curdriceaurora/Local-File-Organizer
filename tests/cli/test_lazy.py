"""Tests for the lazy CLI command loading infrastructure."""

from __future__ import annotations

import types
from unittest.mock import patch

import click
import pytest

from file_organizer.cli.lazy import LazyCommandProxy, LazyTyperGroup

pytestmark = [pytest.mark.ci, pytest.mark.unit, pytest.mark.integration]


def test_load_returns_non_typer_command_as_is() -> None:
    """A LazyCommandProxy whose target attribute is a plain click.Command
    (not a typer.Typer) is used directly, without conversion."""
    real_command = click.Command(name="real", callback=lambda: None)
    fake_module = types.SimpleNamespace(real_cmd=real_command)

    proxy = LazyCommandProxy("real", "fake.module.path", "real_cmd", "help text")

    with patch("importlib.import_module", return_value=fake_module) as mock_import:
        loaded = proxy._load()

    mock_import.assert_called_once_with("fake.module.path")
    assert loaded is real_command


def test_load_caches_result_across_calls() -> None:
    """Subsequent _load() calls reuse the cached command without re-importing."""
    real_command = click.Command(name="real", callback=lambda: None)
    fake_module = types.SimpleNamespace(real_cmd=real_command)

    proxy = LazyCommandProxy("real", "fake.module.path", "real_cmd", "help text")

    with patch("importlib.import_module", return_value=fake_module) as mock_import:
        first = proxy._load()
        second = proxy._load()

    mock_import.assert_called_once()
    assert first is second is real_command


class _TrackingCommand(click.Command):
    """Track help-width limits passed by LazyTyperGroup.format_commands."""

    def __init__(self, name: str, *, short_help: str, hidden: bool = False) -> None:
        super().__init__(name=name, callback=lambda: None, short_help=short_help, hidden=hidden)
        self.seen_limits: list[int] = []

    def get_short_help_str(self, limit: int = 45) -> str:
        self.seen_limits.append(limit)
        return super().get_short_help_str(limit)


class _FixedCommandGroup(LazyTyperGroup):
    """Test helper that bypasses global lazy-command registration."""

    def __init__(self, commands: dict[str, click.Command]) -> None:
        super().__init__(name="fo")
        self._commands = commands

    def list_commands(self, ctx: click.Context) -> list[str]:
        return list(self._commands.keys())

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        return self._commands.get(cmd_name)


class _RecordingFormatter:
    """Minimal formatter used to inspect grouped command output."""

    def __init__(self, width: int | None) -> None:
        self.width = width
        self._current_section: str | None = None
        self.sections: list[tuple[str, list[tuple[str, str]]]] = []

    def section(self, title: str):
        formatter = self

        class _Section:
            def __enter__(self_nonlocal):
                formatter._current_section = title

            def __exit__(self_nonlocal, exc_type, exc, tb):
                formatter._current_section = None

        return _Section()

    def write_dl(self, rows: list[tuple[str, str]]) -> None:
        if self._current_section is None:
            return
        self.sections.append((self._current_section, list(rows)))


def test_format_commands_handles_none_width_and_minimum_help_limit() -> None:
    """format_commands should tolerate width=None and clamp help width to >= 10."""
    long_name = "x" * 75
    organize_command = _TrackingCommand("organize", short_help="Organize files")
    long_command = _TrackingCommand(long_name, short_help="Long command help")
    hidden_command = _TrackingCommand("hidden", short_help="Hidden command", hidden=True)

    group = _FixedCommandGroup(
        {"organize": organize_command, long_name: long_command, "hidden": hidden_command}
    )
    ctx = click.Context(group)
    formatter = _RecordingFormatter(width=None)

    group.format_commands(ctx, formatter)
    section_titles = {title for title, _ in formatter.sections}
    rendered_rows = [name for _, rows in formatter.sections for name, _ in rows]

    assert "Core Commands" in section_titles
    assert "Advanced Commands" in section_titles
    assert "hidden" not in rendered_rows
    assert organize_command.seen_limits and organize_command.seen_limits[0] == 10
    assert long_command.seen_limits and long_command.seen_limits[0] == 10


def test_format_commands_returns_when_no_visible_commands() -> None:
    """format_commands should be a no-op when every command is hidden."""
    hidden_command = _TrackingCommand("hidden", short_help="Hidden command", hidden=True)
    group = _FixedCommandGroup({"hidden": hidden_command})
    ctx = click.Context(group)
    formatter = _RecordingFormatter(width=80)

    group.format_commands(ctx, formatter)

    assert formatter.sections == []
