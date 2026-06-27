"""Tests for the WP-6.2 changed-file -> test-file selector helper."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.ci]

_SCRIPT = (
    Path(__file__).resolve().parents[2] / ".claude" / "scripts" / "select_tests_for_changes.py"
)


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("select_tests_for_changes_under_test", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


selector = _load_module()


def test_maps_src_file_to_matching_test_file(tmp_path: Path) -> None:
    (tmp_path / "tests" / "core").mkdir(parents=True)
    test_file = tmp_path / "tests" / "core" / "test_organizer.py"
    test_file.write_text("def test_x(): pass\n", encoding="utf-8")

    result = selector.select_tests(
        changed_files=["src/file_organizer/core/organizer.py"], tests_root=tmp_path / "tests"
    )
    assert result == [str(test_file.relative_to(tmp_path))]


def test_maps_test_file_change_to_itself(tmp_path: Path) -> None:
    (tmp_path / "tests" / "core").mkdir(parents=True)
    test_file = tmp_path / "tests" / "core" / "test_organizer.py"
    test_file.write_text("def test_x(): pass\n", encoding="utf-8")

    result = selector.select_tests(
        changed_files=["tests/core/test_organizer.py"], tests_root=tmp_path / "tests"
    )
    assert result == [str(test_file.relative_to(tmp_path))]


def test_unmapped_src_file_returns_nothing(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    result = selector.select_tests(
        changed_files=["src/file_organizer/core/no_such_module.py"], tests_root=tmp_path / "tests"
    )
    assert result == []


def test_ignores_non_python_files(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    result = selector.select_tests(
        changed_files=["README.md", "pyproject.toml"], tests_root=tmp_path / "tests"
    )
    assert result == []


def test_deduplicates_and_sorts(tmp_path: Path) -> None:
    (tmp_path / "tests" / "core").mkdir(parents=True)
    test_file = tmp_path / "tests" / "core" / "test_organizer.py"
    test_file.write_text("def test_x(): pass\n", encoding="utf-8")

    result = selector.select_tests(
        changed_files=[
            "src/file_organizer/core/organizer.py",
            "src/file_organizer/core/organizer.py",
        ],
        tests_root=tmp_path / "tests",
    )
    assert result == [str(test_file.relative_to(tmp_path))]
