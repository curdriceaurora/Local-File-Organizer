"""Tests for the WP-6.2 test-separator-paths CI rail."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.ci.guardrails import check_test_separator_paths as checker

pytestmark = [pytest.mark.unit, pytest.mark.ci]


def test_flags_posix_separator_in_path_constructor(tmp_path: Path) -> None:
    src = tmp_path / "bad.py"
    src.write_text('value = Path("docs/report.pdf")\n', encoding="utf-8")
    violations = checker.check_file(src)
    assert len(violations) == 1
    assert "docs/report.pdf" in violations[0][1]  # noqa: test-separator-paths


def test_flags_windows_separator_in_path_constructor(tmp_path: Path) -> None:
    src = tmp_path / "bad.py"
    src.write_text(r'value = Path("docs\\report.pdf")' "\n", encoding="utf-8")
    violations = checker.check_file(src)
    assert len(violations) == 1
    assert "docs\\report.pdf" in violations[0][1]  # noqa: test-separator-paths


def test_targeted_noqa_suppresses_violation(tmp_path: Path) -> None:
    src = tmp_path / "exempt.py"
    src.write_text(
        'value = Path("docs/report.pdf")  # noqa: test-separator-paths\n',
        encoding="utf-8",
    )
    assert checker.check_file(src) == []


def test_comma_separated_targeted_noqa_suppresses_violation(tmp_path: Path) -> None:
    src = tmp_path / "exempt_codes.py"
    src.write_text(
        'value = Path("docs/report.pdf")  # noqa: E501, test-separator-paths\n',
        encoding="utf-8",
    )
    assert checker.check_file(src) == []


def test_bare_noqa_does_not_suppress_violation(tmp_path: Path) -> None:
    src = tmp_path / "bare.py"
    src.write_text('value = Path("docs/report.pdf")  # noqa\n', encoding="utf-8")
    violations = checker.check_file(src)
    assert len(violations) == 1


def test_unrelated_noqa_code_does_not_suppress_violation(tmp_path: Path) -> None:
    src = tmp_path / "other.py"
    src.write_text('value = Path("docs/report.pdf")  # noqa: E501\n', encoding="utf-8")
    violations = checker.check_file(src)
    assert len(violations) == 1


def test_noqa_suffix_does_not_suppress_violation(tmp_path: Path) -> None:
    src = tmp_path / "suffix.py"
    src.write_text(
        'value = Path("docs/report.pdf")  # noqa: test-separator-paths-extra\n',
        encoding="utf-8",
    )
    violations = checker.check_file(src)
    assert len(violations) == 1


def test_string_literal_noqa_text_does_not_suppress_violation(tmp_path: Path) -> None:
    src = tmp_path / "string_literal.py"
    src.write_text(
        'message = "contains noqa: test-separator-paths"\nvalue = Path("docs/report.pdf")\n',
        encoding="utf-8",
    )
    violations = checker.check_file(src)
    assert len(violations) == 1


def test_hash_in_string_literal_does_not_suppress_violation(tmp_path: Path) -> None:
    src = tmp_path / "hash_string.py"
    src.write_text(
        'value = Path("docs/# noqa: test-separator-paths/report.pdf")\n',
        encoding="utf-8",
    )
    violations = checker.check_file(src)
    assert len(violations) == 1


def test_root_path_is_not_flagged(tmp_path: Path) -> None:
    src = tmp_path / "root_only.py"
    src.write_text('value = Path("/")\n', encoding="utf-8")
    assert checker.check_file(src) == []


def test_url_literal_in_path_call_is_not_flagged(tmp_path: Path) -> None:
    src = tmp_path / "url.py"
    src.write_text('value = Path("https://example.com/a/b")\n', encoding="utf-8")
    assert checker.check_file(src) == []


def test_syntax_error_returns_empty(tmp_path: Path) -> None:
    src = tmp_path / "broken.py"
    src.write_text("def bad_syntax(:\n", encoding="utf-8")
    assert checker.check_file(src) == []


def test_check_file_returns_line_number(tmp_path: Path) -> None:
    src = tmp_path / "lineno.py"
    src.write_text('x = 1\ny = Path("docs/report.pdf")\n', encoding="utf-8")
    violations = checker.check_file(src)
    assert len(violations) == 1
    lineno, msg, line = violations[0]
    assert lineno == 2
    assert "docs/report.pdf" in msg  # noqa: test-separator-paths
    assert line == 'y = Path("docs/report.pdf")'
