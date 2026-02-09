"""CI lint guardrails for Python sources."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

FO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.ci
def test_ruff_full_lint() -> None:
    """Run full Ruff linting to prevent regressions before commits."""
    ruff = shutil.which("ruff")
    assert ruff is not None, "ruff is required to run lint guard tests"

    result = subprocess.run(
        [ruff, "check", "src"],
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
