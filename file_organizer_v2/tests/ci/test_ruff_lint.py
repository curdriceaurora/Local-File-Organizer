"""CI lint guardrails for Python sources."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

FO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.ci
def test_ruff_full_lint() -> None:
    """Run Ruff linting across core sources and CI guardrails."""
    ruff = shutil.which("ruff")
    assert ruff is not None, "ruff is required to run lint guard tests"

    result = subprocess.run(
        [ruff, "check", "src", "tests/ci"],
        cwd=FO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(
            "ruff linting failed:\n"
            f"{result.stdout}\n{result.stderr}"
        )
