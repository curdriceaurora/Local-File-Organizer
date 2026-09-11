"""Version-safe access to typer's underlying Click machinery.

typer 0.26 switched its ``TyperGroup``/``TyperCommand`` internals from the
real, published ``click`` package to a vendored fork (``typer._click``) with
its own ``Context``, ``Command``, ``Parameter``, ``ParameterSource`` and
exception classes. Below 0.26, typer builds directly on real ``click`` and
those two sets of classes are identical; at 0.26+ they are distinct classes
that happen to look alike, so code written against real ``click`` silently
stops interoperating with typer's own dispatch:

- ``click.get_current_context()`` reads real click's context stack, which
  typer's vendored dispatch never pushes onto -- it always returns ``None``
  under 0.26+, so any state stashed via a typer callback (``ctx.obj``,
  ``CLIState`` flags) reads back as defaults.
- ``ctx.get_parameter_source(name) == click.core.ParameterSource.COMMANDLINE``
  compares an enum member from typer's vendored fork against one from real
  click. Two different ``Enum`` classes are never ``==`` to each other, so
  this comparison is always ``False`` under 0.26+ -- code that branches on
  "was this explicitly passed on the command line" silently takes the
  "no" branch every time.

This module picks the one that actually matches the ``TyperGroup`` this
process's ``typer`` build uses, so the rest of the CLI package can import
from here instead of guessing.

The ``TYPE_CHECKING`` branch below always types these as typer's vendored
fork: mypy checks one environment at a time, and this project's pinned
range resolves to a >=0.26 typer everywhere mypy runs. The runtime ``else``
branch is what actually executes, and falls back to real ``click`` on a
typer <0.26 install. Plain attribute assignment (rather than a second
``from x import y``) is used in both runtime branches so a linter's
redefinition check can't "helpfully" prune the branch that doesn't happen
to run in whatever environment last touched this file.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import typer

# Stable across the whole >=0.12 range: typer has always publicly exported
# its own Abort/Exit, and they round-trip correctly through
# ``app(standalone_mode=False)`` regardless of which Click a given typer
# build wraps -- unlike ``click.exceptions.Abort``/``Exit``, which stop
# matching once typer vendors its own fork (see UsageError below).
Abort = typer.Abort
Exit = typer.Exit

if TYPE_CHECKING:
    from typer._click.core import Command as Command
    from typer._click.core import Context as Context
    from typer._click.core import Parameter as Parameter
    from typer._click.core import ParameterSource as ParameterSource
    from typer._click.exceptions import UsageError as UsageError
    from typer._click.formatting import HelpFormatter as HelpFormatter
    from typer._click.globals import get_current_context as get_current_context

    TYPER_VENDORS_CLICK: bool
else:
    try:
        # typer >= 0.26: TyperGroup/TyperCommand are built on typer's own
        # vendored fork -- these are the classes real Context/Command
        # objects flowing through typer's dispatch actually are.
        import typer._click.core as _vendored_core
        import typer._click.exceptions as _vendored_exceptions
        import typer._click.formatting as _vendored_formatting
        import typer.main as _typer_main

        Command = _vendored_core.Command
        Context = _vendored_core.Context
        Parameter = _vendored_core.Parameter
        ParameterSource = _vendored_core.ParameterSource
        UsageError = _vendored_exceptions.UsageError
        HelpFormatter = _vendored_formatting.HelpFormatter
        get_current_context = _typer_main.get_current_context
        TYPER_VENDORS_CLICK = True
    except ImportError:  # pragma: no cover -- exercised only on typer < 0.26
        # typer < 0.26: TyperGroup/TyperCommand are built directly on real
        # click, so real click's classes are the correct ones.
        import click as _click
        import click.core as _click_core
        import click.exceptions as _click_exceptions

        Command = _click_core.Command
        Context = _click_core.Context
        Parameter = _click_core.Parameter
        ParameterSource = _click_core.ParameterSource
        UsageError = _click_exceptions.UsageError
        HelpFormatter = _click.HelpFormatter
        get_current_context = _click.get_current_context
        TYPER_VENDORS_CLICK = False
