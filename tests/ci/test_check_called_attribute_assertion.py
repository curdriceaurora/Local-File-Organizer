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
        "def test_x(mock_fn):\n"
        "    subject(mock_fn)\n"
        "    assert mock_fn.called  # noqa\n",
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
