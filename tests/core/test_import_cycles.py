"""Regression tests for import cycles that only surface on a cold interpreter.

``core.organize_options`` once imported ``services.auto_tagging.styles`` at module
scope. That runs ``services/__init__``, whose model/config imports reach
``config.methodology``, which imports ``OrganizationMethodology`` back from the
still-initializing ``organize_options`` -- crashing ``fo`` at startup.

The in-process test suite cannot catch this: ``conftest`` imports
``file_organizer.config`` first, which happens to load the modules in a
cycle-safe order. Each import therefore runs in a fresh subprocess.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.ci]

_SRC_ROOT = Path(__file__).resolve().parents[2] / "src"


@pytest.mark.parametrize(
    "module",
    [
        "file_organizer.core.organize_options",
        "file_organizer.core.plan",
        "file_organizer.cli.main",
    ],
)
def test_cold_import_has_no_cycle(module: str) -> None:
    """Importing *module* first in a fresh interpreter must succeed."""
    result = subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        capture_output=True,
        env={
            **os.environ,
            "PYTHONPATH": (
                f"{_SRC_ROOT}{os.pathsep}{os.environ['PYTHONPATH']}"
                if os.environ.get("PYTHONPATH")
                else str(_SRC_ROOT)
            ),
        },
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, (
        f"cold import of {module} failed (rc={result.returncode}).\nstderr: {result.stderr!r}"
    )
