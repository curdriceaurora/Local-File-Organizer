"""Tests for the WP-6.1 atomic-write CI rail."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.ci.guardrails import check_atomic_write as checker

pytestmark = [pytest.mark.unit, pytest.mark.ci]


def test_flags_path_write_text_call(tmp_path: Path) -> None:
    src = tmp_path / "bad.py"
    src.write_text("Path('x').write_text('data')\n", encoding="utf-8")
    violations = checker.check_file(src)
    assert len(violations) == 1
    assert "write_text" in violations[0][1]


def test_allows_targeted_atomic_write_noqa(tmp_path: Path) -> None:
    src = tmp_path / "exempt.py"
    src.write_text("Path('x').write_text('data')  # noqa: atomic-write\n", encoding="utf-8")
    assert checker.check_file(src) == []


def test_bare_noqa_does_not_suppress_violation(tmp_path: Path) -> None:
    src = tmp_path / "bare.py"
    src.write_text("Path('x').write_text('data')  # noqa\n", encoding="utf-8")
    violations = checker.check_file(src)
    assert len(violations) == 1


def test_unrelated_noqa_code_does_not_suppress_violation(tmp_path: Path) -> None:
    src = tmp_path / "other.py"
    src.write_text("Path('x').write_text('data')  # noqa: F401\n", encoding="utf-8")
    violations = checker.check_file(src)
    assert len(violations) == 1


def test_mixed_noqa_list_with_atomic_write_suppresses_violation(tmp_path: Path) -> None:
    src = tmp_path / "mixed.py"
    src.write_text("Path('x').write_text('data')  # noqa: F401, atomic-write\n", encoding="utf-8")
    assert checker.check_file(src) == []
