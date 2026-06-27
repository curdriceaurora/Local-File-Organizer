"""Tests for the WP-6.1 SafeDir ValueError-swallowing CI rail."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.ci]

_SCRIPT = Path(__file__).resolve().parents[2] / ".claude" / "scripts" / "check_safedir_valueerror.py"


def _load_checker() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_safedir_valueerror_under_test", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checker = _load_checker()


def test_flags_broad_except_around_open_child(tmp_path: Path) -> None:
    src = tmp_path / "bad.py"
    src.write_text(
        "def f(safedir: SafeDir):\n"
        "    try:\n"
        "        return safedir.open_child('x')\n"
        "    except Exception:\n"
        "        return None\n",
        encoding="utf-8",
    )
    violations = checker.check_file(src)
    assert len(violations) == 1
    assert "ValueError" in violations[0][1]


def test_allows_explicit_valueerror_handler(tmp_path: Path) -> None:
    src = tmp_path / "good.py"
    src.write_text(
        "def f(safedir: SafeDir):\n"
        "    try:\n"
        "        return safedir.open_child('x')\n"
        "    except ValueError:\n"
        "        return None\n",
        encoding="utf-8",
    )
    assert checker.check_file(src) == []


def test_allows_bare_except_that_reraises(tmp_path: Path) -> None:
    src = tmp_path / "good_reraise.py"
    src.write_text(
        "def f(safedir: SafeDir):\n"
        "    try:\n"
        "        return safedir.open_child('x')\n"
        "    except Exception:\n"
        "        raise\n",
        encoding="utf-8",
    )
    assert checker.check_file(src) == []


def test_ignores_unrelated_try_blocks(tmp_path: Path) -> None:
    src = tmp_path / "unrelated.py"
    src.write_text(
        "def f():\n"
        "    try:\n"
        "        return 1 / 0\n"
        "    except Exception:\n"
        "        return None\n",
        encoding="utf-8",
    )
    assert checker.check_file(src) == []


def test_ignores_path_mkdir_with_no_safedir_in_scope(tmp_path: Path) -> None:
    """Path.mkdir() (and other pathlib methods sharing a name with SafeDir's)

    must not be flagged when there is no SafeDir instance in scope — only
    the receiver's tracked SafeDir-ness should trigger the rail, not the
    method name alone.
    """
    src = tmp_path / "path_mkdir.py"
    src.write_text(
        "def f(file_path):\n"
        "    try:\n"
        "        file_path.mkdir(parents=True, exist_ok=True)\n"
        "    except Exception:\n"
        "        return None\n",
        encoding="utf-8",
    )
    assert checker.check_file(src) == []


def test_flags_safedir_constructed_inline(tmp_path: Path) -> None:
    src = tmp_path / "constructed.py"
    src.write_text(
        "def f(path):\n"
        "    safedir = SafeDir(path)\n"
        "    try:\n"
        "        return safedir.mkdir('x')\n"
        "    except Exception:\n"
        "        return None\n",
        encoding="utf-8",
    )
    violations = checker.check_file(src)
    assert len(violations) == 1


def test_flags_safedir_propagated_via_open_subdir(tmp_path: Path) -> None:
    src = tmp_path / "propagated.py"
    src.write_text(
        "def f(root: SafeDir):\n"
        "    sub = root.open_subdir('x')\n"
        "    try:\n"
        "        return sub.unlink('y')\n"
        "    except Exception:\n"
        "        return None\n",
        encoding="utf-8",
    )
    violations = checker.check_file(src)
    assert len(violations) == 1


def test_noqa_suppresses_violation(tmp_path: Path) -> None:
    src = tmp_path / "noqa.py"
    src.write_text(
        "def f(safedir: SafeDir):\n"
        "    try:\n"
        "        return safedir.open_child('x')\n"
        "    except Exception:  # noqa: safedir-valueerror\n"
        "        return None\n",
        encoding="utf-8",
    )
    assert checker.check_file(src) == []
