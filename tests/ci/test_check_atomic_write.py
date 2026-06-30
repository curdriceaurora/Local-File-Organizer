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


def test_string_literal_noqa_does_not_suppress_violation(tmp_path: Path) -> None:
    src = tmp_path / "string_literal.py"
    src.write_text(
        "msg = 'noqa: atomic-write'\nPath('x').write_text('data')\n",
        encoding="utf-8",
    )
    assert len(checker.check_file(src)) == 1


def test_flags_path_open_write_modes(tmp_path: Path) -> None:
    """Verify that Path.open() write/append modes are correctly flagged."""
    for mode in ["w", "wb", "a", "ab", "x", "w+", "r+"]:
        src = tmp_path / f"bad_open_{mode}.py"
        src.write_text(f"Path('x').open('{mode}')\n", encoding="utf-8")
        violations = checker.check_file(src)
        assert len(violations) == 1, f"Failed to flag Path.open with mode {mode}"
        assert "Path.open" in violations[0][1]

        # test with keyword argument
        src_kw = tmp_path / f"bad_open_kw_{mode}.py"
        src_kw.write_text(f"Path('x').open(mode='{mode}')\n", encoding="utf-8")
        violations_kw = checker.check_file(src_kw)
        assert len(violations_kw) == 1, f"Failed to flag Path.open with mode kw {mode}"
        assert "Path.open" in violations_kw[0][1]


def test_allows_path_open_read_modes(tmp_path: Path) -> None:
    """Verify that Path.open() read/binary-read modes are allowed."""
    # No args (default is read)
    src_default = tmp_path / "default_open.py"
    src_default.write_text("Path('x').open()\n", encoding="utf-8")
    assert checker.check_file(src_default) == []

    for mode in ["r", "rb", "rt"]:
        src = tmp_path / f"good_open_{mode}.py"
        src.write_text(f"Path('x').open('{mode}')\n", encoding="utf-8")
        assert checker.check_file(src) == [], f"Incorrectly flagged Path.open with mode {mode}"

        src_kw = tmp_path / f"good_open_kw_{mode}.py"
        src_kw.write_text(f"Path('x').open(mode='{mode}')\n", encoding="utf-8")
        assert checker.check_file(src_kw) == [], (
            f"Incorrectly flagged Path.open with mode kw {mode}"
        )


def test_path_open_noqa_suppressions(tmp_path: Path) -> None:
    """Verify that noqa comments on Path.open() work as expected."""
    # Bare noqa on Path.open
    src_bare = tmp_path / "open_bare.py"
    src_bare.write_text("Path('x').open('w')  # noqa\n", encoding="utf-8")
    assert len(checker.check_file(src_bare)) == 1

    # Unrelated noqa on Path.open
    src_unrelated = tmp_path / "open_unrelated.py"
    src_unrelated.write_text("Path('x').open('w')  # noqa: F401\n", encoding="utf-8")
    assert len(checker.check_file(src_unrelated)) == 1

    # Targeted noqa on Path.open
    src_exempt = tmp_path / "open_exempt.py"
    src_exempt.write_text("Path('x').open('w')  # noqa: atomic-write\n", encoding="utf-8")
    assert checker.check_file(src_exempt) == []

    # Mixed noqa list with atomic-write on Path.open
    src_mixed = tmp_path / "open_mixed.py"
    src_mixed.write_text("Path('x').open('w')  # noqa: F401, atomic-write\n", encoding="utf-8")
    assert checker.check_file(src_mixed) == []
