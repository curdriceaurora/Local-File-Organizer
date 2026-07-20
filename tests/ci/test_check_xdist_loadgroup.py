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


def test_bare_noqa_does_not_suppress_violation(tmp_path: Path) -> None:
    src = tmp_path / "bare.py"
    src.write_text(
        "def test_x(tmp_path_factory):  # noqa\n"
        "    base = tmp_path_factory.getbasetemp()\n"
        "    assert base.exists()\n",
        encoding="utf-8",
    )
    assert len(checker.check_file(src)) == 1


def test_unrelated_noqa_code_does_not_suppress_violation(tmp_path: Path) -> None:
    src = tmp_path / "unrelated_noqa.py"
    src.write_text(
        "def test_x(tmp_path_factory):  # noqa: some-other-rail\n"
        "    base = tmp_path_factory.getbasetemp()\n"
        "    assert base.exists()\n",
        encoding="utf-8",
    )
    assert len(checker.check_file(src)) == 1


def test_marker_text_in_comment_does_not_count_as_marker(tmp_path: Path) -> None:
    src = tmp_path / "comment_text.py"
    src.write_text(
        "# This test should use xdist_group but doesn't.\n"
        "def test_x(tmp_path_factory):\n"
        "    base = tmp_path_factory.getbasetemp()\n"
        "    assert base.exists()\n",
        encoding="utf-8",
    )
    assert len(checker.check_file(src)) == 1


def test_unrelated_marker_does_not_count_as_safe(tmp_path: Path) -> None:
    src = tmp_path / "unrelated_marker.py"
    src.write_text(
        "import pytest\n"
        "@pytest.mark.slow\n"
        "def test_x(tmp_path_factory):\n"
        "    base = tmp_path_factory.getbasetemp()\n"
        "    assert base.exists()\n",
        encoding="utf-8",
    )
    assert len(checker.check_file(src)) == 1


def test_marker_on_helper_function_does_not_protect_caller(tmp_path: Path) -> None:
    src = tmp_path / "helper_marker.py"
    src.write_text(
        "import pytest\n"
        "@pytest.mark.xdist_group(name='shared-temp')\n"
        "def helper():\n"
        "    pass\n"
        "def test_x(tmp_path_factory):\n"
        "    base = tmp_path_factory.getbasetemp()\n"
        "    assert base.exists()\n",
        encoding="utf-8",
    )
    assert len(checker.check_file(src)) == 1


def test_flags_call_to_wrapper_around_getbasetemp(tmp_path: Path) -> None:
    src = tmp_path / "wrapper.py"
    src.write_text(
        "def _shared_tmp_root(tmp_path_factory):\n"
        "    return tmp_path_factory.getbasetemp()\n"
        "def test_x(tmp_path_factory):\n"
        "    base = _shared_tmp_root(tmp_path_factory)\n"
        "    assert base.exists()\n",
        encoding="utf-8",
    )
    assert len(checker.check_file(src)) == 1


def test_allows_marker_via_aliased_mark_import(tmp_path: Path) -> None:
    src = tmp_path / "aliased_mark.py"
    src.write_text(
        "from pytest import mark\n"
        "@mark.xdist_group(name='shared-temp')\n"
        "def test_x(tmp_path_factory):\n"
        "    base = tmp_path_factory.getbasetemp()\n"
        "    assert base.exists()\n",
        encoding="utf-8",
    )
    assert checker.check_file(src) == []


def test_allows_marker_via_aliased_xdist_group_import(tmp_path: Path) -> None:
    src = tmp_path / "aliased_xdist_group.py"
    src.write_text(
        "from pytest.mark import xdist_group\n"
        "@xdist_group(name='shared-temp')\n"
        "def test_x(tmp_path_factory):\n"
        "    base = tmp_path_factory.getbasetemp()\n"
        "    assert base.exists()\n",
        encoding="utf-8",
    )
    assert checker.check_file(src) == []


def test_allows_module_level_pytestmark_xdist_group(tmp_path: Path) -> None:
    src = tmp_path / "module_pytestmark.py"
    src.write_text(
        "import pytest\n"
        "pytestmark = [pytest.mark.xdist_group(name='shared-temp')]\n"
        "def test_x(tmp_path_factory):\n"
        "    base = tmp_path_factory.getbasetemp()\n"
        "    assert base.exists()\n",
        encoding="utf-8",
    )
    assert checker.check_file(src) == []


def test_allows_module_level_pytestmark_single_value(tmp_path: Path) -> None:
    src = tmp_path / "module_pytestmark_single.py"
    src.write_text(
        "import pytest\n"
        "pytestmark = pytest.mark.xdist_group(name='shared-temp')\n"
        "def test_x(tmp_path_factory):\n"
        "    base = tmp_path_factory.getbasetemp()\n"
        "    assert base.exists()\n",
        encoding="utf-8",
    )
    assert checker.check_file(src) == []


def test_allows_class_level_pytestmark_attribute(tmp_path: Path) -> None:
    src = tmp_path / "class_pytestmark.py"
    src.write_text(
        "import pytest\n"
        "class TestX:\n"
        "    pytestmark = [pytest.mark.xdist_group(name='shared-temp')]\n"
        "    def test_x(self, tmp_path_factory):\n"
        "        base = tmp_path_factory.getbasetemp()\n"
        "        assert base.exists()\n",
        encoding="utf-8",
    )
    assert checker.check_file(src) == []


def test_unrelated_module_level_pytestmark_does_not_suppress(tmp_path: Path) -> None:
    src = tmp_path / "unrelated_module_pytestmark.py"
    src.write_text(
        "import pytest\n"
        "pytestmark = [pytest.mark.slow]\n"
        "def test_x(tmp_path_factory):\n"
        "    base = tmp_path_factory.getbasetemp()\n"
        "    assert base.exists()\n",
        encoding="utf-8",
    )
    assert len(checker.check_file(src)) == 1


def test_allows_wrapper_call_with_xdist_group_marker(tmp_path: Path) -> None:
    src = tmp_path / "wrapper_marked.py"
    src.write_text(
        "import pytest\n"
        "def _shared_tmp_root(tmp_path_factory):\n"
        "    return tmp_path_factory.getbasetemp()\n"
        "@pytest.mark.xdist_group(name='shared-temp')\n"
        "def test_x(tmp_path_factory):\n"
        "    base = _shared_tmp_root(tmp_path_factory)\n"
        "    assert base.exists()\n",
        encoding="utf-8",
    )
    assert checker.check_file(src) == []


def test_wrapper_name_collision_across_classes_still_detected(tmp_path: Path) -> None:
    src = tmp_path / "collision.py"
    src.write_text(
        "class ClassA:\n"
        "    def helper(self, tmp_path_factory):\n"
        "        return tmp_path_factory.getbasetemp()\n"
        "class ClassB:\n"
        "    def helper(self, x):\n"
        "        return x + 1\n"
        "def test_x(tmp_path_factory):\n"
        "    a = ClassA()\n"
        "    base = a.helper(tmp_path_factory)\n"
        "    assert base.exists()\n",
        encoding="utf-8",
    )
    assert len(checker.check_file(src)) == 1
