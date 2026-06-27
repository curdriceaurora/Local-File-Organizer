"""Tests for the WP-6.1 TextIOWrapper-without-detach CI rail."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.ci]

_SCRIPT = (
    Path(__file__).resolve().parents[2] / ".claude" / "scripts" / "check_textiowrapper_detach.py"
)


def _load_checker() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_textiowrapper_detach_under_test", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checker = _load_checker()


def test_flags_wrapper_without_detach(tmp_path: Path) -> None:
    src = tmp_path / "bad.py"
    src.write_text(
        "import io\ndef f(buf):\n    wrapper = io.TextIOWrapper(buf)\n    return wrapper.read()\n",
        encoding="utf-8",
    )
    violations = checker.check_file(src)
    assert len(violations) == 1
    assert "detach" in violations[0][1]


def test_allows_wrapper_with_detach(tmp_path: Path) -> None:
    src = tmp_path / "good.py"
    src.write_text(
        "import io\n"
        "def f(buf):\n"
        "    wrapper = io.TextIOWrapper(buf)\n"
        "    text = wrapper.read()\n"
        "    wrapper.detach()\n"
        "    return text\n",
        encoding="utf-8",
    )
    assert checker.check_file(src) == []


def test_allows_direct_import_form(tmp_path: Path) -> None:
    src = tmp_path / "good_direct.py"
    src.write_text(
        "from io import TextIOWrapper\n"
        "def f(buf):\n"
        "    wrapper = TextIOWrapper(buf)\n"
        "    wrapper.detach()\n",
        encoding="utf-8",
    )
    assert checker.check_file(src) == []


def test_nested_function_detach_does_not_mask_outer_leak(tmp_path: Path) -> None:
    src = tmp_path / "nested.py"
    src.write_text(
        "import io\n"
        "def outer(buf, buf2):\n"
        "    wrapper = io.TextIOWrapper(buf)\n"
        "    def helper():\n"
        "        wrapper = io.TextIOWrapper(buf2)\n"
        "        wrapper.detach()\n"
        "        return wrapper\n"
        "    helper()\n"
        "    return wrapper.read()\n",
        encoding="utf-8",
    )
    violations = checker.check_file(src)
    assert len(violations) == 1
    assert violations[0][0] == 3


def test_noqa_suppresses_violation(tmp_path: Path) -> None:
    src = tmp_path / "noqa.py"
    src.write_text(
        "import io\n"
        "def f(buf):\n"
        "    wrapper = io.TextIOWrapper(buf)  # noqa: textiowrapper-detach\n"
        "    return wrapper.read()\n",
        encoding="utf-8",
    )
    assert checker.check_file(src) == []
