"""Regression tests for the lazy ``file_organizer.core`` package init (PEP 562).

``core/__init__.py`` re-exports ``FileOrganizer`` / ``OrganizationResult`` lazily
via ``__getattr__`` specifically so that importing a lightweight sibling module
(e.g. ``core.path_guard``) does *not* eagerly pull in ``core.organizer`` and, with
it, the audio services stack (``ctranslate2`` → ``torch``). That cascade was both
a slow-import footgun and the trigger for a coverage-instrumentation segfault when
a dotted ``--cov``/``--source`` target resolved through this package.

These tests pin the invariant so a future eager ``from .organizer import ...`` in
``core/__init__.py`` fails loudly here instead of silently re-introducing the
regression.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

if shutil.which("ruff") is None:
    pytest.fail("ruff must be installed to run lazy core import regression tests")

pytestmark = [pytest.mark.unit, pytest.mark.ci]

_SRC_ROOT = Path(__file__).resolve().parents[2] / "src"


def test_importing_lightweight_core_module_does_not_pull_torch() -> None:
    """``import file_organizer.core.path_guard`` must stay torch-free.

    Run in a fresh subprocess so a ``torch`` already imported by another test in
    this process cannot mask an accidental eager cascade.
    """
    code = (
        "import sys\n"
        "import file_organizer.core.path_guard  # noqa: F401\n"
        "assert 'torch' not in sys.modules, "
        "'importing core.path_guard eagerly pulled in torch'\n"
        "assert 'ctranslate2' not in sys.modules, "
        "'importing core.path_guard eagerly pulled in ctranslate2'\n"
        "print('OK')\n"
    )
    result = subprocess.run(
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
    assert result.returncode == 0, (
        f"subprocess failed (rc={result.returncode}).\n"
        f"stdout: {result.stdout!r}\nstderr: {result.stderr!r}"
    )
    assert "OK" in result.stdout


def test_core_public_api_is_still_importable() -> None:
    """The lazy re-export must keep the public ``from core import ...`` API working."""
    from file_organizer.core import FileOrganizer, OrganizationResult

    assert FileOrganizer.__name__ == "FileOrganizer"
    assert OrganizationResult.__name__ == "OrganizationResult"


def test_core_unknown_attribute_raises_attribute_error() -> None:
    """``__getattr__`` must reject unknown names rather than swallow them."""
    import file_organizer.core as core

    with pytest.raises(AttributeError, match="DefinitelyNotAnExport"):
        _ = core.DefinitelyNotAnExport


def test_core_dir_lists_lazy_exports() -> None:
    """``dir(file_organizer.core)`` should advertise the lazy public API."""
    import file_organizer.core as core

    names = dir(core)

    assert "FileOrganizer" in names
    assert "OrganizationResult" in names
