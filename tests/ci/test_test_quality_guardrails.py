"""CI guardrails for test quality anti-patterns.

Covers two regression classes identified in PR #846 review:

1. ``time.sleep()`` in tests — wall-clock sleeps make tests flaky under
   load and mask real timing bugs.  Use ``os.utime()`` for mtime bumps or
   event-based polling instead.

2. ``assert len(results) <= N`` patterns — when a corpus is guaranteed to
   produce at least N matches (e.g. ``top_k=N`` with enough documents),
   the upper-bound assertion is vacuous: it passes even when the index
   returns zero matches.  Use ``assert len(results) == N`` instead.

Both guardrails apply to ALL test files under ``tests/``.  Streams 1-4 of
issue #900 eliminated every pre-existing violation, so the scope can now be
expanded from diff-based (changed files only) to the full test suite.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

FO_ROOT = Path(__file__).resolve().parents[2]
TESTS_ROOT = FO_ROOT / "tests"

pytestmark = pytest.mark.ci

_SELF = Path(__file__).resolve()


# -------------------------------------------------------------------------
# Full test-suite file enumerator
# -------------------------------------------------------------------------


def _changed_test_files() -> list[Path]:
    """Return all test files under ``tests/``, excluding fixtures and self.

    Scans the entire test suite rather than a diff-based subset.  This is
    safe because streams 1-4 (issue #900) cleaned every pre-existing
    violation before this guardrail was broadened.
    """
    return sorted(
        p for p in TESTS_ROOT.rglob("*.py") if p.resolve() != _SELF and "fixtures" not in p.parts
    )


# -------------------------------------------------------------------------
# Fix 4: time.sleep in tests
# -------------------------------------------------------------------------


def _find_time_sleep(path: Path) -> list[str]:
    """Return ``file:line`` strings for actual ``time.sleep()`` call nodes in *path*.

    Uses AST parsing to detect real calls, not mentions in docstrings or strings.
    Handles all common import forms: ``import time``, ``import time as t``,
    ``from time import sleep``, and ``from time import sleep as delay``.
    """
    source = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return []

    time_aliases: set[str] = set()
    sleep_aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "time":
                    time_aliases.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module == "time":
            for alias in node.names:
                if alias.name == "sleep":
                    sleep_aliases.add(alias.asname or alias.name)

    violations: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        # Match time.sleep(...), import time as t; t.sleep(...),
        # and from time import sleep; sleep(...)
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "sleep"
            and isinstance(func.value, ast.Name)
            and func.value.id in time_aliases
        ) or (isinstance(func, ast.Name) and func.id in sleep_aliases):
            violations.append(f"{path}:{node.lineno}")
    return violations


def test_changed_tests_have_no_time_sleep() -> None:
    """Changed test files must not call ``time.sleep()``.

    Prefer deterministic alternatives:
    - ``os.utime(path, (new_mtime, new_mtime))`` for mtime-based staleness tests
    - Polling loops with a deadline (``while time.time() < deadline: ...``)

    ``time.sleep()`` causes flaky failures on loaded CI runners and hides
    event-ordering bugs that should be caught by the test.
    """
    violations: list[str] = []
    for path in _changed_test_files():
        violations.extend(_find_time_sleep(path))

    assert not violations, (
        "Changed tests must not use time.sleep() — use os.utime() or event-based polling:\n"
        + "\n".join(violations)
    )


# -------------------------------------------------------------------------
# Fix 5: vacuous upper-bound length assertions
# -------------------------------------------------------------------------


def _is_literal_int(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and type(node.value) is int


def _find_vacuous_len_lte_assertions(source: str, path: str = "<string>") -> list[str]:
    """Return assertions of the form ``assert len(...) <= N`` in *source*.

    These are vacuous upper bounds: when a test corpus guarantees N results
    (e.g. ``top_k=N`` with enough documents), ``<=`` always passes even if
    the index returns zero matches.  Use ``==`` for exact-count assertions.

    Also catches named-variable bounds where the variable is assigned a literal
    integer in the same file (e.g. ``expected = 5; assert len(results) <= expected``).
    """
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError:
        return []

    # Collect simple name → literal-int assignments (e.g. ``expected = 5``)
    int_names: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, ast.Constant)
            and type(node.value.value) is int
        ):
            int_names.add(node.targets[0].id)

    def _is_int_bound(n: ast.AST) -> bool:
        return _is_literal_int(n) or (isinstance(n, ast.Name) and n.id in int_names)

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

        # assert len(...) <= N  (forward)
        forward = (
            isinstance(left, ast.Call)
            and isinstance(left.func, ast.Name)
            and left.func.id == "len"
            and isinstance(op, ast.LtE)
            and _is_int_bound(right)
        )
        # assert N >= len(...)  (reverse — less common but still vacuous)
        reverse = (
            isinstance(right, ast.Call)
            and isinstance(right.func, ast.Name)
            and right.func.id == "len"
            and isinstance(op, ast.GtE)
            and _is_int_bound(left)
        )

        if forward or reverse:
            violations.append(f"{path}:{node.lineno}")

    return violations


@pytest.mark.parametrize(
    ("source", "expected_count"),
    [
        ("assert len(results) <= 5\n", 1),
        ("assert len(results) <= 0\n", 1),
        ("assert 5 >= len(results)\n", 1),
        ("assert len(results) == 5\n", 0),
        ("assert len(results) < 5\n", 0),  # strict less-than is intentional
        ("assert len(results) >= 1\n", 0),  # lower bound is fine
        # Named-variable bounds are equally vacuous
        ("expected = 5\nassert len(results) <= expected\n", 1),
        ("expected = 5\nassert expected >= len(results)\n", 1),
    ],
)
def test_detector_flags_vacuous_len_lte(source: str, expected_count: int) -> None:
    assert len(_find_vacuous_len_lte_assertions(source)) == expected_count


def test_changed_tests_have_no_vacuous_len_lte_assertions() -> None:
    """Changed test files must not use ``assert len(x) <= N`` upper-bound assertions.

    When a test corpus is constructed to guarantee at least N matches,
    ``assert len(results) <= N`` is vacuous: it passes even when results is
    empty.  Use ``assert len(results) == N`` to verify the exact count.
    """
    violations: list[str] = []
    for path in _changed_test_files():
        source = path.read_text(encoding="utf-8")
        violations.extend(_find_vacuous_len_lte_assertions(source, str(path)))

    assert not violations, (
        "Vacuous ``assert len(x) <= N`` found in changed tests — use ``== N`` for exact counts:\n"
        + "\n".join(violations)
    )
