"""Regression tests for lazy optional-dependency probes in the readers package.

``utils/readers/scientific.py`` advertises optional readers via
``H5PY_AVAILABLE`` / ``NETCDF4_AVAILABLE`` / ``SCIPY_AVAILABLE``. Those flags
used to be set by a module-scope ``import netCDF4``, which made *any* import of
``file_organizer.utils.readers`` load netCDF4 — and through it netCDF4's bundled
OpenSSL/Kerberos/curl dylibs.

That is not merely a slow-import footgun. ``tests/conftest.py`` imports
``file_organizer.api``, which reaches this module transitively, so every pytest
process loaded netCDF4 during collection. A process holding netCDF4 cannot
safely ``fork()`` and then call ``sqlite3.connect()`` in the child: the child
takes SIGSEGV roughly four times in five on macOS. mutmut forks once per
mutant, so this is what made the ``organizer`` mutation profile report hundreds
of "segfaults" (#1726) — the organizer tests reach sqlite3 via
``execute_plan`` → ``UndoManager`` → ``HistoryTracker``.

These tests pin the invariant so a future module-scope ``import netCDF4`` fails
here loudly instead of silently re-breaking fork safety.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.ci]

_SRC_ROOT = Path(__file__).resolve().parents[2] / "src"


def _run(code: str) -> subprocess.CompletedProcess[str]:
    """Run *code* in a fresh interpreter with ``src`` importable."""
    return subprocess.run(
        [sys.executable, "-c", code],
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


def test_importing_readers_does_not_load_netcdf4() -> None:
    """Importing the readers package must not pull in netCDF4.

    Run in a fresh subprocess so a netCDF4 already imported by another test in
    this process cannot mask an accidental eager import.
    """
    result = _run(
        "import sys\n"
        "import file_organizer.utils.readers  # noqa: F401\n"
        "assert 'netCDF4' not in sys.modules, "
        "'importing utils.readers eagerly pulled in netCDF4, which breaks "
        "fork+sqlite3 (see #1726)'\n"
        "print('OK')\n"
    )
    assert result.returncode == 0, (
        f"subprocess failed (rc={result.returncode}).\n"
        f"stdout: {result.stdout!r}\nstderr: {result.stderr!r}"
    )
    assert "OK" in result.stdout


def test_importing_api_does_not_load_netcdf4() -> None:
    """The conftest import path (``file_organizer.api``) must stay netCDF4-free.

    This is the path that actually poisoned every pytest process: conftest
    imports ``file_organizer.api``, which reaches ``utils.readers``.
    """
    result = _run(
        "import sys\n"
        "import file_organizer.api  # noqa: F401\n"
        "assert 'netCDF4' not in sys.modules, "
        "'importing file_organizer.api eagerly pulled in netCDF4 (see #1726)'\n"
        "print('OK')\n"
    )
    assert result.returncode == 0, (
        f"subprocess failed (rc={result.returncode}).\n"
        f"stdout: {result.stdout!r}\nstderr: {result.stderr!r}"
    )
    assert "OK" in result.stdout


def test_netcdf4_availability_flag_still_reflects_installation() -> None:
    """``NETCDF4_AVAILABLE`` must keep reporting real availability.

    The flag is monkeypatched by a dozen reader tests, so it has to remain a
    plain module attribute whose value matches whether netCDF4 can be imported
    — deferring the import must not turn it into a permanent ``False``.
    """
    result = _run(
        "import importlib.util\n"
        "from file_organizer.utils.readers import scientific\n"
        "installed = importlib.util.find_spec('netCDF4') is not None\n"
        "assert scientific.NETCDF4_AVAILABLE == installed, (\n"
        "    f'NETCDF4_AVAILABLE={scientific.NETCDF4_AVAILABLE} but "
        "installed={installed}')\n"
        "print('OK')\n"
    )
    assert result.returncode == 0, (
        f"subprocess failed (rc={result.returncode}).\n"
        f"stdout: {result.stdout!r}\nstderr: {result.stderr!r}"
    )
    assert "OK" in result.stdout
