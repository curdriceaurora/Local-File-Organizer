"""Pin ``cli/update.py``'s module-level coverage to a unit-marked test.

``cli/lazy.py`` imports ``file_organizer.cli.update`` lazily on the first
``fo update ...`` dispatch, and Python runs a module's top-level code only once
per process. In the combined CI run (``--cov-context=test``, randomized order,
xdist), whichever test triggers that first import is the only one whose
coverage context records those lines. When it is the integration-marked
``test_cli_update_coverage.py``, the unit coverage floor for
``src/file_organizer/cli/update.py`` reads 0%. Reloading here always executes
the module body under this unit context, regardless of run order (same pattern
as ``tests/cli/test_cli_config.py`` for ``config_cli``).
"""

from __future__ import annotations

import importlib

import pytest
from typer.testing import CliRunner

pytestmark = [pytest.mark.unit]


def test_update_module_reloads_and_registers_commands() -> None:
    import file_organizer.cli.update as update

    update = importlib.reload(update)

    names = {cmd.name for cmd in update.update_app.registered_commands}
    assert names == {"check", "install", "rollback"}

    result = CliRunner().invoke(update.update_app, ["--help"])
    assert result.exit_code == 0
    for name in ("check", "install", "rollback"):
        assert name in result.output
