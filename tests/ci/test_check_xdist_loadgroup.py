"""Tests for the WP-6.2 xdist-loadgroup-reminder CI rail."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.ci.guardrails import check_xdist_loadgroup as checker

pytestmark = [pytest.mark.unit, pytest.mark.ci]


def test_flags_getbasetemp_without_xdist_group(tmp_path: Path) -> None:
    src = tmp_path / "bad.py"
    src.write_text(
        "def test_x(tmp_path_factory):\n"
        "    base = tmp_path_factory.getbasetemp()\n"
        "    assert base.exists()\n",
        encoding="utf-8",
    )
    violations = checker.check_file(src)
    assert len(violations) == 1


def test_allows_getbasetemp_with_function_marker(tmp_path: Path) -> None:
    src = tmp_path / "good.py"
    src.write_text(
        "import pytest\n"
        "@pytest.mark.xdist_group(name='shared-temp')\n"
        "def test_x(tmp_path_factory):\n"
        "    base = tmp_path_factory.getbasetemp()\n"
        "    assert base.exists()\n",
        encoding="utf-8",
    )
    assert checker.check_file(src) == []


def test_allows_getbasetemp_with_class_marker(tmp_path: Path) -> None:
    src = tmp_path / "good_class.py"
    src.write_text(
        "import pytest\n"
        "@pytest.mark.xdist_group(name='shared-temp')\n"
        "class TestX:\n"
        "    def test_x(self, tmp_path_factory):\n"
        "        base = tmp_path_factory.getbasetemp()\n"
        "        assert base.exists()\n",
        encoding="utf-8",
    )
    assert checker.check_file(src) == []


def test_ignores_plain_tmp_path(tmp_path: Path) -> None:
    src = tmp_path / "unrelated.py"
    src.write_text(
        "def test_x(tmp_path):\n    assert tmp_path.exists()\n",
        encoding="utf-8",
    )
    assert checker.check_file(src) == []


def test_noqa_suppresses_violation(tmp_path: Path) -> None:
    src = tmp_path / "noqa.py"
    src.write_text(
        "def test_x(tmp_path_factory):  # noqa: xdist-loadgroup\n"
        "    base = tmp_path_factory.getbasetemp()\n"
        "    assert base.exists()\n",
        encoding="utf-8",
    )
    assert checker.check_file(src) == []
