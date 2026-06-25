"""Tests for CLIState dataclass.

Verifies defaults, field types, and that the state is isolated
per-invocation when used via typer's ctx.obj.
"""

from __future__ import annotations

import pytest
import typer
from typer.testing import CliRunner

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# CLIState dataclass
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCLIStateDefaults:
    """CLIState defaults all flags to False."""

    def test_all_defaults_false(self) -> None:
        from file_organizer.cli.state import CLIState

        s = CLIState()
        assert s.verbose is False
        assert s.dry_run is False
        assert s.json_output is False
        assert s.yes is False
        assert s.no_interactive is False

    def test_fields_settable(self) -> None:
        from file_organizer.cli.state import CLIState

        s = CLIState(verbose=True, dry_run=True, json_output=True, yes=True, no_interactive=True)
        assert s.verbose is True
        assert s.dry_run is True
        assert s.json_output is True
        assert s.yes is True
        assert s.no_interactive is True

    def test_instances_are_independent(self) -> None:
        """Two CLIState instances do not share state."""
        from file_organizer.cli.state import CLIState

        a = CLIState(verbose=True)
        b = CLIState()
        assert a.verbose is True
        assert b.verbose is False


# ---------------------------------------------------------------------------
# _get_state helper (used by command modules)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetState:
    """_get_state() returns CLIState from ctx.obj or falls back to defaults."""

    def test_no_context_returns_defaults(self) -> None:
        """Outside a typer invocation, _get_state() returns CLIState()."""
        from file_organizer.cli.state import CLIState, _get_state

        result = _get_state()
        assert isinstance(result, CLIState)
        assert result.verbose is False
        assert result.dry_run is False

    def test_with_context_returns_ctx_obj(self) -> None:
        """Inside a typer invocation, _get_state() returns the ctx.obj CLIState."""
        from file_organizer.cli.state import CLIState, _get_state

        captured: list[CLIState] = []

        test_app = typer.Typer()

        @test_app.callback()
        def cb(ctx: typer.Context) -> None:
            ctx.obj = CLIState(verbose=True, dry_run=True)

        @test_app.command()
        def cmd() -> None:
            captured.append(_get_state())

        result = CliRunner().invoke(test_app, ["cmd"])
        assert result.exit_code == 0, result.output
        assert len(captured) == 1
        assert captured[0].verbose is True
        assert captured[0].dry_run is True

    def test_ctx_obj_not_cli_state_returns_defaults(self) -> None:
        """If ctx.obj is something else (e.g. dict), _get_state() falls back to defaults."""
        from file_organizer.cli.state import CLIState, _get_state

        captured: list[CLIState] = []

        test_app = typer.Typer()

        @test_app.callback()
        def cb(ctx: typer.Context) -> None:
            ctx.obj = {"not": "a CLIState"}

        @test_app.command()
        def cmd() -> None:
            captured.append(_get_state())

        result = CliRunner().invoke(test_app, ["cmd"])
        assert result.exit_code == 0, result.output
        assert len(captured) == 1
        assert isinstance(captured[0], CLIState)
        assert captured[0].verbose is False


# ---------------------------------------------------------------------------
# Isolation: two sequential invocations do not share state
# ---------------------------------------------------------------------------


@pytest.mark.ci
class TestCLIStateIsolation:
    """Each CliRunner invocation gets a fresh CLIState — no leakage."""

    def test_state_not_shared_across_invocations(self) -> None:
        """Flag set in invocation 1 must not appear in invocation 2."""
        from file_organizer.cli.state import CLIState, _get_state

        results: list[bool] = []

        test_app = typer.Typer()

        @test_app.callback()
        def cb(
            ctx: typer.Context,
            verbose: bool = typer.Option(False, "--verbose"),
        ) -> None:
            ctx.obj = CLIState(verbose=verbose)

        @test_app.command()
        def cmd() -> None:
            results.append(_get_state().verbose)

        runner = CliRunner()
        r1 = runner.invoke(test_app, ["--verbose", "cmd"])
        r2 = runner.invoke(test_app, ["cmd"])
        assert r1.exit_code == 0, r1.output
        assert r2.exit_code == 0, r2.output

        assert results == [True, False], (
            f"State leaked between invocations: {results}. "
            "Each CliRunner.invoke() must produce an independent CLIState."
        )
