"""Tests for the subprocess-returncode CI rail (issue #1408)."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.ci.guardrails import check_subprocess_returncode as checker

pytestmark = [pytest.mark.unit, pytest.mark.ci]


# ---------------------------------------------------------------------------
# True-positive: bare subprocess.run() with no returncode handling
# ---------------------------------------------------------------------------


def test_flags_discarded_result(tmp_path: Path) -> None:
    src = tmp_path / "bad.py"
    src.write_text(
        "import subprocess\nsubprocess.run(['ls'])\n",
        encoding="utf-8",
    )
    violations = checker.check_file(src)
    assert len(violations) == 1
    assert "subprocess.run()" in violations[0][1]


def test_flags_assigned_result_without_returncode_check(tmp_path: Path) -> None:
    src = tmp_path / "bad2.py"
    src.write_text(
        "import subprocess\nresult = subprocess.run(['ls'])\nprint(result.stdout)\n",
        encoding="utf-8",
    )
    violations = checker.check_file(src)
    assert len(violations) == 1


# ---------------------------------------------------------------------------
# Compliant: check=True
# ---------------------------------------------------------------------------


def test_allows_check_true(tmp_path: Path) -> None:
    src = tmp_path / "ok_check.py"
    src.write_text(
        "import subprocess\nsubprocess.run(['ls'], check=True)\n",
        encoding="utf-8",
    )
    assert checker.check_file(src) == []


# ---------------------------------------------------------------------------
# Compliant: returncode inspected on the assigned variable
# ---------------------------------------------------------------------------


def test_allows_returncode_equality_check(tmp_path: Path) -> None:
    src = tmp_path / "ok_rc.py"
    src.write_text(
        "import subprocess\n"
        "result = subprocess.run(['ls'])\n"
        "if result.returncode != 0:\n"
        "    raise RuntimeError('failed')\n",
        encoding="utf-8",
    )
    assert checker.check_file(src) == []


def test_allows_returncode_equality_zero(tmp_path: Path) -> None:
    src = tmp_path / "ok_rc_zero.py"
    src.write_text(
        "import subprocess\nresult = subprocess.run(['ls'])\nok = result.returncode == 0\n",
        encoding="utf-8",
    )
    assert checker.check_file(src) == []


def test_allows_returncode_in_conditional_expression(tmp_path: Path) -> None:
    src = tmp_path / "ok_ternary.py"
    src.write_text(
        "import subprocess\n"
        "r = subprocess.run(['ls'])\n"
        "val = 'ok' if r.returncode == 0 else 'fail'\n",
        encoding="utf-8",
    )
    assert checker.check_file(src) == []


# ---------------------------------------------------------------------------
# Suppression behaviour
# ---------------------------------------------------------------------------


def test_targeted_noqa_suppresses_violation(tmp_path: Path) -> None:
    src = tmp_path / "suppressed.py"
    src.write_text(
        "import subprocess\nsubprocess.run(['ls'])  # noqa: subprocess-returncode\n",
        encoding="utf-8",
    )
    assert checker.check_file(src) == []


def test_bare_noqa_does_not_suppress_violation(tmp_path: Path) -> None:
    src = tmp_path / "bare_noqa.py"
    src.write_text(
        "import subprocess\nsubprocess.run(['ls'])  # noqa\n",
        encoding="utf-8",
    )
    violations = checker.check_file(src)
    assert len(violations) == 1


def test_unrelated_noqa_code_does_not_suppress_violation(tmp_path: Path) -> None:
    src = tmp_path / "wrong_noqa.py"
    src.write_text(
        "import subprocess\nsubprocess.run(['ls'])  # noqa: F401\n",
        encoding="utf-8",
    )
    violations = checker.check_file(src)
    assert len(violations) == 1


def test_mixed_noqa_list_with_correct_code_suppresses_violation(tmp_path: Path) -> None:
    src = tmp_path / "mixed_noqa.py"
    src.write_text(
        "import subprocess\nsubprocess.run(['ls'])  # noqa: F401, subprocess-returncode\n",
        encoding="utf-8",
    )
    assert checker.check_file(src) == []


def test_string_literal_noqa_does_not_suppress_violation(tmp_path: Path) -> None:
    src = tmp_path / "str_noqa.py"
    src.write_text(
        "import subprocess\nmsg = 'noqa: subprocess-returncode'\nsubprocess.run(['ls'])\n",
        encoding="utf-8",
    )
    violations = checker.check_file(src)
    assert len(violations) == 1


# ---------------------------------------------------------------------------
# Function-scope: returncode check anywhere in the function body is compliant
# ---------------------------------------------------------------------------


def test_allows_returncode_check_in_same_function_body(tmp_path: Path) -> None:
    src = tmp_path / "fn_body.py"
    src.write_text(
        "import subprocess\n\n"
        "def run_it():\n"
        "    result = subprocess.run(['ls'])\n"
        "    if result.returncode != 0:\n"
        "        return False\n"
        "    return True\n",
        encoding="utf-8",
    )
    assert checker.check_file(src) == []


def test_flags_subprocess_run_in_function_with_no_returncode_check(tmp_path: Path) -> None:
    src = tmp_path / "fn_bad.py"
    src.write_text(
        "import subprocess\n\n"
        "def run_it():\n"
        "    result = subprocess.run(['ls'])\n"
        "    return result.stdout\n",
        encoding="utf-8",
    )
    violations = checker.check_file(src)
    assert len(violations) == 1


# ---------------------------------------------------------------------------
# Try-block scope: subprocess.run() inside try/except bodies (issue #1408 addendum)
# ---------------------------------------------------------------------------


def test_flags_discarded_result_inside_try_block(tmp_path: Path) -> None:
    """A discarded subprocess.run() inside a try body is a violation."""
    src = tmp_path / "try_discard.py"
    src.write_text(
        "import subprocess\n\n"
        "def run_cmd():\n"
        "    try:\n"
        "        subprocess.run(['ls'])\n"
        "        return True\n"
        "    except Exception:\n"
        "        return False\n",
        encoding="utf-8",
    )
    violations = checker.check_file(src)
    assert len(violations) == 1


def test_flags_assigned_result_in_try_body_without_returncode_check(tmp_path: Path) -> None:
    """Result assigned in try body with no returncode check is a violation."""
    src = tmp_path / "try_assign_no_rc.py"
    src.write_text(
        "import subprocess\n\n"
        "def run_cmd():\n"
        "    try:\n"
        "        result = subprocess.run(['ls'])\n"
        "        return True\n"
        "    except Exception:\n"
        "        return False\n",
        encoding="utf-8",
    )
    violations = checker.check_file(src)
    assert len(violations) == 1


def test_allows_check_true_inside_try_block(tmp_path: Path) -> None:
    """check=True inside a try block is compliant (CalledProcessError propagates)."""
    src = tmp_path / "try_check_true.py"
    src.write_text(
        "import subprocess\n\n"
        "def run_cmd():\n"
        "    try:\n"
        "        subprocess.run(['ls'], check=True)\n"
        "    except subprocess.CalledProcessError:\n"
        "        return False\n"
        "    return True\n",
        encoding="utf-8",
    )
    assert checker.check_file(src) == []


def test_allows_returncode_check_inside_try_body(tmp_path: Path) -> None:
    """returncode inspected within the same try body is compliant."""
    src = tmp_path / "try_rc_in_body.py"
    src.write_text(
        "import subprocess\n\n"
        "def run_cmd():\n"
        "    try:\n"
        "        result = subprocess.run(['ls'])\n"
        "        if result.returncode != 0:\n"
        "            raise RuntimeError('failed')\n"
        "        return True\n"
        "    except RuntimeError:\n"
        "        return False\n",
        encoding="utf-8",
    )
    assert checker.check_file(src) == []


# ---------------------------------------------------------------------------
# Additional Edge Cases: nested scopes, statement order, and match/case blocks
# ---------------------------------------------------------------------------


def test_flags_if_returncode_accessed_only_in_nested_scope(tmp_path: Path) -> None:
    """A subprocess.run() is a violation if the returncode is only checked in a nested scope (like an inner function or lambda)."""
    src = tmp_path / "nested_scope_check.py"
    src.write_text(
        "import subprocess\n\n"
        "def run_cmd():\n"
        "    result = subprocess.run(['ls'])\n"
        "    def check_later():\n"
        "        print(result.returncode)\n"
        "    return result\n",
        encoding="utf-8",
    )
    violations = checker.check_file(src)
    assert len(violations) == 1


def test_flags_if_returncode_accessed_before_subprocess_run(tmp_path: Path) -> None:
    """A subprocess.run() is a violation if the returncode access is earlier in the block (associated with a previous assignment)."""
    src = tmp_path / "before_check.py"
    src.write_text(
        "import subprocess\n\n"
        "def run_cmd():\n"
        "    result = None\n"
        "    print(result.returncode)\n"
        "    result = subprocess.run(['ls'])\n"
        "    return result\n",
        encoding="utf-8",
    )
    violations = checker.check_file(src)
    assert len(violations) == 1


def test_checks_match_case_body(tmp_path: Path) -> None:
    """A subprocess.run() inside a match/case body is checked and flagged if unchecked."""
    src = tmp_path / "match_case.py"
    src.write_text(
        "import subprocess\n\n"
        "def run_cmd(val):\n"
        "    match val:\n"
        "        case 1:\n"
        "            subprocess.run(['ls'])\n"
        "        case 2:\n"
        "            subprocess.run(['ls'], check=True)\n",
        encoding="utf-8",
    )
    violations = checker.check_file(src)
    # The first case has unchecked subprocess.run(), the second is check=True (compliant)
    assert len(violations) == 1
    assert violations[0][0] == 6  # Line 6 should be the failure line


# ---------------------------------------------------------------------------
# End-to-end: the production src/ tree has zero violations after noqa annotations
# ---------------------------------------------------------------------------


def test_production_source_has_no_unchecked_subprocess_run_calls() -> None:
    """All subprocess.run() call sites in src/ are compliant or noqa-annotated."""
    package_root = Path("src") / "file_organizer"
    all_violations: list[tuple[str, int, str, str]] = []
    for path in sorted(package_root.rglob("*.py")):
        for lineno, msg, line in checker.check_file(path):
            all_violations.append((path.as_posix(), lineno, msg, line))

    assert all_violations == [], (
        "Unchecked subprocess.run() call sites found in production source:\n"
        + "\n".join(f"  {f}:{ln}: {m}" for f, ln, m, _ in all_violations)
    )
