"""Regression tests for the models <-> services import cycle.

``models/text_model.py`` imports ``config.defaults``; ``config/__init__.py``
reaches ``core/organize_options.py``, which builds a default
``OrganizeOptions()`` at import time. When that construction imported
``file_organizer.services`` (for the tag-style validators), ``services/__init__``
eagerly loaded ``smart_suggestions`` / ``text_processor``, which import
``TextModel`` back from the still-initializing ``models`` package, so a cold
``import file_organizer.models`` raised ``ImportError``. It only worked when
something imported ``file_organizer.config`` or ``file_organizer.services`` first.

Each import runs in a fresh interpreter so modules already loaded by other tests
in this process cannot mask the cycle.
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
    "code",
    [
        "import file_organizer.models",
        "import file_organizer.models.base",
        "import file_organizer",
        "import file_organizer; import file_organizer.models.base",
        "import file_organizer.models.text_model",
        "import file_organizer.core.organize_options",
    ],
)
def test_cold_import_succeeds(code: str) -> None:
    result = subprocess.run(
        [sys.executable, "-c", f"{code}\nprint('OK')"],
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
        f"{code!r} failed in a fresh interpreter (rc={result.returncode}).\n"
        f"stderr: {result.stderr!r}"
    )
    assert "OK" in result.stdout


def test_default_options_do_not_import_services() -> None:
    """The import-time default ``OrganizeOptions()`` must not load ``services``.

    That is the edge that closed the cycle; pin it directly so a future eager
    import in ``organize_options`` fails here with a clear message.
    """
    code = (
        "import sys\n"
        "import file_organizer.core.organize_options  # noqa: F401\n"
        "assert 'file_organizer.services' not in sys.modules, "
        "'core.organize_options imported file_organizer.services at load time'\n"
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
        f"subprocess failed (rc={result.returncode}).\nstderr: {result.stderr!r}"
    )
    assert "OK" in result.stdout
