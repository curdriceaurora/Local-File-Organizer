"""Tests for the WP-6.1 SafeDir ValueError-swallowing CI rail."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.ci.guardrails import check_safedir_valueerror as checker

pytestmark = [pytest.mark.unit, pytest.mark.ci]


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
        "def f():\n    try:\n        return 1 / 0\n    except Exception:\n        return None\n",
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


def test_bare_noqa_does_not_suppress_violation(tmp_path: Path) -> None:
    src = tmp_path / "bare.py"
    src.write_text(
        "def f(safedir: SafeDir):\n"
        "    try:\n"
        "        return safedir.open_child('x')\n"
        "    except Exception:  # noqa\n"
        "        return None\n",
        encoding="utf-8",
    )
    assert len(checker.check_file(src)) == 1


def test_string_literal_noqa_does_not_suppress_violation(tmp_path: Path) -> None:
    src = tmp_path / "string_literal.py"
    src.write_text(
        "msg = 'noqa: safedir-valueerror'\n"
        "def f(safedir: SafeDir):\n"
        "    try:\n"
        "        return safedir.open_child('x')\n"
        "    except Exception:\n"
        "        return None\n",
        encoding="utf-8",
    )
    assert len(checker.check_file(src)) == 1


def test_flags_safedir_alias_import(tmp_path: Path) -> None:
    src = tmp_path / "alias.py"
    src.write_text(
        "from file_organizer.utils.safedir import SafeDir as SD\n"
        "def f(sd: SD):\n"
        "    try:\n"
        "        return sd.open_child('x')\n"
        "    except Exception:\n"
        "        return None\n",
        encoding="utf-8",
    )
    violations = checker.check_file(src)
    assert len(violations) == 1


def test_flags_nested_function_swallowing(tmp_path: Path) -> None:
    src = tmp_path / "nested.py"
    src.write_text(
        "def f(safedir: SafeDir):\n"
        "    def inner():\n"
        "        try:\n"
        "            return safedir.open_child('x')\n"
        "            # swallowing ValueError in nested function\n"
        "        except Exception:\n"
        "            return None\n"
        "    return inner\n",
        encoding="utf-8",
    )
    violations = checker.check_file(src)
    assert len(violations) == 1


def test_allows_nested_function_shadowing(tmp_path: Path) -> None:
    src = tmp_path / "nested_shadow.py"
    src.write_text(
        "def f(safedir: SafeDir):\n"
        "    def inner():\n"
        "        safedir = 'not_a_safedir'\n"
        "        try:\n"
        "            # safedir is now just a string, so mkdir() is not SafeDir's\n"
        "            return safedir.mkdir()\n"
        "        except Exception:\n"
        "            return None\n"
        "    return inner\n",
        encoding="utf-8",
    )
    violations = checker.check_file(src)
    assert len(violations) == 0


def test_flags_tuple_with_broad_and_valueerror(tmp_path: Path) -> None:
    src = tmp_path / "tuple_broad.py"
    src.write_text(
        "def f(safedir: SafeDir):\n"
        "    try:\n"
        "        return safedir.open_child('x')\n"
        "    except (ValueError, Exception):\n"
        "        return None\n",
        encoding="utf-8",
    )
    violations = checker.check_file(src)
    assert len(violations) == 1


def test_allows_tuple_with_specific_exceptions(tmp_path: Path) -> None:
    src = tmp_path / "tuple_specific.py"
    src.write_text(
        "def f(safedir: SafeDir):\n"
        "    try:\n"
        "        return safedir.open_child('x')\n"
        "    except (TypeError, ValueError):\n"
        "        return None\n",
        encoding="utf-8",
    )
    violations = checker.check_file(src)
    assert len(violations) == 0


def test_allows_explicit_and_broad_handlers(tmp_path: Path) -> None:
    src = tmp_path / "multi_handlers.py"
    src.write_text(
        "def f(safedir: SafeDir):\n"
        "    try:\n"
        "        return safedir.open_child('x')\n"
        "    except ValueError:\n"
        "        return 'val_err'\n"
        "    except Exception:\n"
        "        return 'other_err'\n",
        encoding="utf-8",
    )
    violations = checker.check_file(src)
    assert len(violations) == 0
