"""Tests for the WP-6.2 weak called-attribute-assertion CI rail."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.ci.guardrails import check_called_attribute_assertion as checker

pytestmark = [pytest.mark.unit, pytest.mark.ci]


def test_flags_assert_called(tmp_path: Path) -> None:
    src = tmp_path / "bad.py"
    src.write_text(
        "def test_x(mock_fn):\n    subject(mock_fn)\n    assert mock_fn.called\n",
        encoding="utf-8",
    )
    violations = checker.check_file(src)
    assert len(violations) == 1


def test_flags_bare_call_count(tmp_path: Path) -> None:
    src = tmp_path / "bad_count.py"
    src.write_text(
        "def test_x(mock_fn):\n    subject(mock_fn)\n    assert mock_fn.call_count\n",
        encoding="utf-8",
    )
    assert len(checker.check_file(src)) == 1


def test_allows_call_count_comparison(tmp_path: Path) -> None:
    src = tmp_path / "good.py"
    src.write_text(
        "def test_x(mock_fn):\n    subject(mock_fn)\n    assert mock_fn.call_count == 2\n",
        encoding="utf-8",
    )
    assert checker.check_file(src) == []


def test_allows_called_with(tmp_path: Path) -> None:
    src = tmp_path / "good_with.py"
    src.write_text(
        "def test_x(mock_fn):\n    subject(mock_fn)\n    mock_fn.assert_called_with(1, 2)\n",
        encoding="utf-8",
    )
    assert checker.check_file(src) == []


def test_noqa_suppresses_violation(tmp_path: Path) -> None:
    src = tmp_path / "noqa.py"
    src.write_text(
        "def test_x(mock_fn):\n"
        "    subject(mock_fn)\n"
        "    assert mock_fn.called  # noqa: called-attribute-assertion\n",
        encoding="utf-8",
    )
    assert checker.check_file(src) == []


def test_bare_noqa_does_not_suppress_violation(tmp_path: Path) -> None:
    src = tmp_path / "bare.py"
    src.write_text(
        "def test_x(mock_fn):\n    subject(mock_fn)\n    assert mock_fn.called  # noqa\n",
        encoding="utf-8",
    )
    assert len(checker.check_file(src)) == 1


def test_string_literal_noqa_does_not_suppress_violation(tmp_path: Path) -> None:
    src = tmp_path / "string_literal.py"
    src.write_text(
        "def test_x(mock_fn):\n"
        "    msg = 'noqa: called-attribute-assertion'\n"
        "    subject(mock_fn)\n"
        "    assert mock_fn.called\n",
        encoding="utf-8",
    )
    assert len(checker.check_file(src)) == 1


# ---------------------------------------------------------------------------
# Multi-line assertion suppressions
# ---------------------------------------------------------------------------


def test_multiline_noqa_first_line(tmp_path: Path) -> None:
    src = tmp_path / "multiline_first.py"
    src.write_text(
        "def test_x(mock_fn):\n"
        "    assert (  # noqa: called-attribute-assertion\n"
        "        mock_fn.called\n"
        "    )\n",
        encoding="utf-8",
    )
    assert checker.check_file(src) == []


def test_multiline_noqa_last_line(tmp_path: Path) -> None:
    src = tmp_path / "multiline_last.py"
    src.write_text(
        "def test_x(mock_fn):\n"
        "    assert (\n"
        "        mock_fn.called\n"
        "    )  # noqa: called-attribute-assertion\n",
        encoding="utf-8",
    )
    assert checker.check_file(src) == []


def test_multiline_noqa_middle_line(tmp_path: Path) -> None:
    src = tmp_path / "multiline_middle.py"
    src.write_text(
        "def test_x(mock_fn):\n"
        "    assert (\n"
        "        mock_fn.called  # noqa: called-attribute-assertion\n"
        "    )\n",
        encoding="utf-8",
    )
    assert checker.check_file(src) == []


# ---------------------------------------------------------------------------
# Nested / Boolean expressions
# ---------------------------------------------------------------------------


def test_flags_nested_bool_and(tmp_path: Path) -> None:
    src = tmp_path / "bool_and.py"
    src.write_text(
        "def test_x(mock_fn):\n    assert x == 1 and mock_fn.called\n",
        encoding="utf-8",
    )
    violations = checker.check_file(src)
    assert len(violations) == 1
    assert ".called" in violations[0][1]


def test_flags_nested_bool_or(tmp_path: Path) -> None:
    src = tmp_path / "bool_or.py"
    src.write_text(
        "def test_x(mock_fn):\n    assert mock_fn.called or y == 2\n",
        encoding="utf-8",
    )
    violations = checker.check_file(src)
    assert len(violations) == 1
    assert ".called" in violations[0][1]


def test_flags_nested_tuple(tmp_path: Path) -> None:
    src = tmp_path / "tuple.py"
    src.write_text(
        "def test_x(mock_fn):\n    assert (mock_fn.called,)\n",
        encoding="utf-8",
    )
    violations = checker.check_file(src)
    assert len(violations) == 1


def test_allows_negative_assertion(tmp_path: Path) -> None:
    src = tmp_path / "negative.py"
    src.write_text(
        "def test_x(mock_fn):\n    assert not mock_fn.called\n",
        encoding="utf-8",
    )
    assert checker.check_file(src) == []


def test_flags_non_direct_negative_assertion(tmp_path: Path) -> None:
    src = tmp_path / "non_direct_negative.py"
    src.write_text(
        "def test_x(mock_fn):\n    assert not (mock_fn.called and x)\n",
        encoding="utf-8",
    )
    violations = checker.check_file(src)
    assert len(violations) == 1
    assert ".called" in violations[0][1]


def test_allows_comparison_operations(tmp_path: Path) -> None:
    src = tmp_path / "comparison.py"
    src.write_text(
        "def test_x(mock_fn):\n"
        "    assert mock_fn.called is True\n"
        "    assert mock_fn.called == True\n"
        "    assert mock_fn.called is False\n"
        "    assert mock_fn.called == False\n"
        "    assert mock_fn.call_count >= 1\n",
        encoding="utf-8",
    )
    assert checker.check_file(src) == []


def test_noqa_suppresses_nested_multiline(tmp_path: Path) -> None:
    src = tmp_path / "nested_multiline.py"
    src.write_text(
        "def test_x(mock_fn):\n"
        "    assert (\n"
        "        x == 1 and mock_fn.called\n"
        "    )  # noqa: called-attribute-assertion\n",
        encoding="utf-8",
    )
    assert checker.check_file(src) == []
