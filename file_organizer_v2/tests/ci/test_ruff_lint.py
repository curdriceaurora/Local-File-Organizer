"""CI lint guardrails for Python sources."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

FO_ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.ci
def test_ruff_import_ordering() -> None:
    """Ensure import ordering stays clean (prevents I001 regressions)."""
    ruff = shutil.which("ruff")
    assert ruff is not None, "ruff is required to run lint guard tests"

    result = subprocess.run(
        [ruff, "check", "src", "--select", "I"],
        cwd=FO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(
            "ruff import ordering failed:\n"
            f"{result.stdout}\n{result.stderr}"
        )
