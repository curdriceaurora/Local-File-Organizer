"""CI guardrails for weak mock call-count assertions in changed tests."""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import pytest

FO_ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.ci


def _is_literal_int(node: ast.AST, value: int) -> bool:
    return isinstance(node, ast.Constant) and node.value == value


def _is_mock_call_count_attr(node: ast.AST) -> bool:
    return isinstance(node, ast.Attribute) and node.attr == "call_count"


def _find_weak_call_count_assertions(source: str, path: str = "<string>") -> list[str]:
    """Return weak lower-bound mock call-count assertions found in *source*.

    High-confidence patterns only:
    - assert mock.call_count >= 1
    - assert mock.call_count > 0
    - assert 1 <= mock.call_count
    """
    tree = ast.parse(source, filename=path)
    violations: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Assert):
            continue
        test = node.test
        if not isinstance(test, ast.Compare):
            continue
        if len(test.ops) != 1 or len(test.comparators) != 1:
            continue

        left = test.left
        op = test.ops[0]
        right = test.comparators[0]

        is_weak_forward = _is_mock_call_count_attr(left) and (
            (isinstance(op, ast.GtE) and _is_literal_int(right, 1))
            or (isinstance(op, ast.Gt) and _is_literal_int(right, 0))
        )
        is_weak_reverse = _is_mock_call_count_attr(right) and (
            (isinstance(op, ast.LtE) and _is_literal_int(left, 1))
            or (isinstance(op, ast.Lt) and _is_literal_int(left, 0))
        )

        if is_weak_forward or is_weak_reverse:
            violations.append(f"{path}:{node.lineno}")

    return violations


def _changed_test_files() -> list[Path]:
    """Return changed test files relative to origin/main...HEAD."""
    merge_base = subprocess.run(
        ["git", "merge-base", "HEAD", "origin/main"],
        cwd=FO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    diff_output = subprocess.run(
        [
            "git",
            "diff",
            "--name-only",
            "--diff-filter=ACM",
            f"{merge_base}...HEAD",
            "--",
            "tests/**/*.py",
            "tests/*.py",
        ],
        cwd=FO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout

    return [
        FO_ROOT / rel_path
        for rel_path in diff_output.splitlines()
        if rel_path and (FO_ROOT / rel_path).is_file()
    ]


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("assert mock.call_count >= 1\n", ["<string>:1"]),
        ("assert mock.call_count > 0\n", ["<string>:1"]),
        ("assert 1 <= mock.call_count\n", ["<string>:1"]),
    ],
)
def test_detector_flags_weak_mock_call_count_lower_bounds(source: str, expected: list[str]) -> None:
    assert _find_weak_call_count_assertions(source) == expected


@pytest.mark.parametrize(
    "source",
    [
        "assert mock.call_count == 2\n",
        "assert limiter.check_call_count >= expected_min_checks\n",
        "call_count = 0\nassert call_count >= 1\n",
    ],
)
def test_detector_ignores_exact_counts_and_non_mock_counters(source: str) -> None:
    assert _find_weak_call_count_assertions(source) == []


def test_changed_test_files_have_no_weak_mock_call_count_assertions() -> None:
    """Changed test files must avoid weak mock call-count lower bounds."""
    violations: list[str] = []
    for path in _changed_test_files():
        violations.extend(
            _find_weak_call_count_assertions(path.read_text(encoding="utf-8"), str(path))
        )

    assert not violations, (
        "Weak mock call-count lower bounds found in changed tests:\n" + "\n".join(violations)
    )
