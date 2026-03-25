"""CI ratchet: MD031 blanks-around-fences violations must not increase.

Enforces two invariants (issue #936):

1. No new MD031 violations in files changed vs origin/main (per-PR gate).
2. Global MD031 violation count must be non-increasing (ratchet).

Baseline: 215 violations across 29 files as of 2026-03-21.
Reduce the baseline as violations are fixed in follow-up batches.
"""

from __future__ import annotations

import subprocess
import warnings
from pathlib import Path

import pytest

FO_ROOT = Path(__file__).resolve().parents[2]
_EXCLUDED_MD_PREFIXES = (".auto-claude/",)

# Current global violation count.  Reduce this constant as violations are fixed
# in follow-up PRs — the test will fail if the count increases.
_MD031_BASELINE = 215

pytestmark = pytest.mark.ci


def _run_pymarkdown_md031(files: list[Path]) -> list[str]:
    """Run pymarkdown with the project config on given files; return MD031 lines."""
    if not files:
        return []
    result = subprocess.run(
        [
            "pymarkdown",
            "-c",
            str(FO_ROOT / ".pymarkdown.json"),
            "scan",
            *[str(f) for f in files],
        ],
        capture_output=True,
        text=True,
        cwd=FO_ROOT,
    )
    return [line for line in result.stdout.splitlines() if "MD031" in line]


def _get_changed_md_files() -> list[Path]:
    """Return .md files changed vs origin/main that exist on disk.

    Falls back to HEAD^..HEAD if origin/main is unavailable (e.g. shallow
    clones or local branches without a remote fetch).
    """
    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACMR", "origin/main...HEAD"],
        capture_output=True,
        text=True,
        cwd=FO_ROOT,
    )
    if result.returncode != 0 or "unknown revision" in result.stderr or "fatal" in result.stderr:
        warnings.warn(
            f"MD031 ratchet: origin/main unavailable, falling back to HEAD^..HEAD "
            f"({result.stderr.strip()!r})",
            stacklevel=2,
        )
        result = subprocess.run(
            ["git", "diff", "--name-only", "--diff-filter=ACMR", "HEAD^..HEAD"],
            capture_output=True,
            text=True,
            cwd=FO_ROOT,
        )
        if result.returncode != 0 or "fatal" in result.stderr:
            warnings.warn(
                f"MD031 ratchet: HEAD^..HEAD fallback also failed (rc={result.returncode}) "
                f"({result.stderr.strip()!r}); returning no changed files",
                stacklevel=2,
            )
            return []
    paths = []
    for line in result.stdout.splitlines():
        if line.endswith(".md"):
            if line.startswith(_EXCLUDED_MD_PREFIXES):
                continue
            p = FO_ROOT / line
            if p.exists():
                paths.append(p)
    return paths


def _get_all_md_files() -> list[Path]:
    """Return all tracked .md files."""
    result = subprocess.run(
        ["git", "ls-files", "*.md"],
        capture_output=True,
        text=True,
        cwd=FO_ROOT,
    )
    paths = []
    for line in result.stdout.splitlines():
        if line.startswith(_EXCLUDED_MD_PREFIXES):
            continue
        p = FO_ROOT / line
        if p.exists():
            paths.append(p)
    return paths


def test_no_new_md031_violations_in_changed_files() -> None:
    """Files changed in this branch must have zero MD031 violations."""
    changed = _get_changed_md_files()
    if not changed:
        pytest.skip("No .md files changed vs origin/main")
    violations = _run_pymarkdown_md031(changed)
    assert not violations, (
        f"MD031 violations detected in {len(changed)} changed file(s).\n"
        "Add blank lines before/after fenced code blocks to fix:\n" + "\n".join(violations)
    )


def test_global_md031_violation_count_does_not_increase() -> None:
    """Global MD031 violation count must not exceed the current baseline."""
    all_files = _get_all_md_files()
    violations = _run_pymarkdown_md031(all_files)
    count = len(violations)
    assert count <= _MD031_BASELINE, (
        f"MD031 global violation count increased: {count} > baseline {_MD031_BASELINE}.\n"
        "A new violation was introduced outside the changed-file gate.\n"
        "First 20 violations:\n" + "\n".join(violations[:20])
    )
