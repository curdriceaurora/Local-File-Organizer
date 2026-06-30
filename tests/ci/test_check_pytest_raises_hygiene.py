"""Tests for the WP-6.2 pytest-raises-hygiene CI rail."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.ci.guardrails import check_pytest_raises_hygiene as checker

pytestmark = [pytest.mark.unit, pytest.mark.ci]


def test_flags_generic_pytest_raises_without_match(tmp_path: Path) -> None:
    src = tmp_path / "bad.py"
    src.write_text(
        "import pytest\n\n"
        "def test_x():\n"
        "    with pytest.raises(ValueError):\n"
        "        raise ValueError('boom')\n",
        encoding="utf-8",
    )
    violations = checker.check_file(src)
    assert len(violations) == 1
    assert "missing 'match' parameter" in violations[0][1]


def test_allows_generic_pytest_raises_with_match(tmp_path: Path) -> None:
    src = tmp_path / "good.py"
    src.write_text(
        "import pytest\n\n"
        "def test_x():\n"
        "    with pytest.raises(ValueError, match='boom'):\n"
        "        raise ValueError('boom')\n",
        encoding="utf-8",
    )
    assert checker.check_file(src) == []


def test_allows_targeted_noqa_suppression(tmp_path: Path) -> None:
    src = tmp_path / "targeted.py"
    src.write_text(
        "import pytest\n\n"
        "def test_x():\n"
        "    with pytest.raises(ValueError):  # noqa: pytest-raises-hygiene\n"
        "        raise ValueError('boom')\n",
        encoding="utf-8",
    )
    assert checker.check_file(src) == []


def test_bare_noqa_does_not_suppress(tmp_path: Path) -> None:
    src = tmp_path / "bare.py"
    src.write_text(
        "import pytest\n\n"
        "def test_x():\n"
        "    with pytest.raises(ValueError):  # noqa\n"
        "        raise ValueError('boom')\n",
        encoding="utf-8",
    )
    assert len(checker.check_file(src)) == 1


def test_unrelated_noqa_code_does_not_suppress(tmp_path: Path) -> None:
    src = tmp_path / "other.py"
    src.write_text(
        "import pytest\n\n"
        "def test_x():\n"
        "    with pytest.raises(ValueError):  # noqa: F401\n"
        "        raise ValueError('boom')\n",
        encoding="utf-8",
    )
    assert len(checker.check_file(src)) == 1


def test_string_literal_noqa_does_not_suppress(tmp_path: Path) -> None:
    src = tmp_path / "string_literal.py"
    src.write_text(
        "import pytest\n\n"
        "def test_x():\n"
        "    marker = 'noqa: pytest-raises-hygiene'\n"
        "    with pytest.raises(ValueError):\n"
        "        raise ValueError('boom')\n",
        encoding="utf-8",
    )
    assert len(checker.check_file(src)) == 1
