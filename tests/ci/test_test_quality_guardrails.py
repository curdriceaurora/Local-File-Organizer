"""CI guardrails for test quality anti-patterns.

Covers four regression classes:

1. ``time.sleep()`` in tests — wall-clock sleeps make tests flaky under
   load and mask real timing bugs.  Use ``os.utime()`` for mtime bumps or
   event-based polling instead.

2. ``assert len(results) <= N`` patterns — when a corpus is guaranteed to
   produce at least N matches (e.g. ``top_k=N`` with enough documents),
   the upper-bound assertion is vacuous: it passes even when the index
   returns zero matches.  Use ``assert len(results) == N`` instead.

3. ``assert len(results) >= 0`` / ``assert 0 <= len(results)`` patterns —
   ``len()`` is always non-negative by definition, so these assertions always
   pass even when the tested code is completely broken.  Use a meaningful
   lower bound (``>= 1``) or exact count (``== N``) instead.

4. Sole ``assert isinstance(x, T)`` in a test function — verifies the return
   type but not the value.  For ``bool`` this is especially weak (only two
   values exist); for ``str`` it misses the actual content.  Use specific
   value assertions instead (``is True``, ``== "high"``, etc.).
   Applies to changed files only.  TODO: broaden to full suite after a
   clean-up sweep analogous to issue #900.

Guardrails 1, 2, and 3 apply to ALL test files under ``tests/``.  Streams
1-4 of issue #900 eliminated every pre-existing violation, so the scope can
be expanded from diff-based (changed files only) to the full test suite.
Guardrail 4 is diff-based until a full-suite clean-up is done.
"""

from __future__ import annotations

import ast
import subprocess
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


def _git_changed_test_files() -> list[Path]:
    """Return test files modified relative to main (diff-based subset).

    Used for guardrails that have known pre-existing violations in the full
    suite.  Only files touched in the current branch are checked, preventing
    failures on historical code while blocking new violations.
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "origin/main...HEAD"],
            capture_output=True,
            text=True,
            cwd=FO_ROOT,
        )
        if not result.stdout.strip():
            result = subprocess.run(
                ["git", "diff", "--name-only", "HEAD"],
                capture_output=True,
                text=True,
                cwd=FO_ROOT,
            )
        changed = {line.strip() for line in result.stdout.splitlines() if line.strip()}
    except Exception:
        changed = set()
    return sorted(
        p
        for p in TESTS_ROOT.rglob("*.py")
        if p.resolve() != _SELF
        and "fixtures" not in p.parts
        and str(p.relative_to(FO_ROOT)) in changed
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


# -------------------------------------------------------------------------
# Fix 5b: vacuous >= 0 assertions (always-true lower bounds)
# -------------------------------------------------------------------------

_GTE_ZERO_NON_NEGATIVE_ATTRS = frozenset({"count", "duration", "total_size", "size", "length"})


def _find_vacuous_len_gte_zero_assertions(source: str, path: str = "<string>") -> list[str]:
    """Return assertions that are always true because the left side is non-negative by definition.

    Detects two forms:

    1. ``assert len(x) >= 0``  (forward) and ``assert 0 <= len(x)``  (reverse)
       ``len()`` always returns a non-negative integer, so ``>= 0`` is tautological.

    2. ``assert x.attr >= 0``  (forward) and ``assert 0 <= x.attr``  (reverse)
       where ``attr`` is one of the known non-negative attribute names
       (``count``, ``duration``, ``total_size``, ``size``, ``length``).

    These pass even when the code under test is completely broken.  Use a
    meaningful bound (``>= 1``, ``== N``, ``< max_val``) instead.
    """
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError:
        return []

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

        def _is_zero(n: ast.AST) -> bool:
            return isinstance(n, ast.Constant) and n.value == 0

        def _is_len_call(n: ast.AST) -> bool:
            return isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "len"

        def _is_non_negative_attr(n: ast.AST) -> bool:
            return isinstance(n, ast.Attribute) and n.attr in _GTE_ZERO_NON_NEGATIVE_ATTRS

        def _is_non_negative_expr(n: ast.AST) -> bool:
            return _is_len_call(n) or _is_non_negative_attr(n)

        # assert len(x) >= 0  or  assert x.count >= 0  (forward)
        forward = _is_non_negative_expr(left) and isinstance(op, ast.GtE) and _is_zero(right)
        # assert 0 <= len(x)  or  assert 0 <= x.count  (reverse)
        reverse = _is_zero(left) and isinstance(op, ast.LtE) and _is_non_negative_expr(right)

        if forward or reverse:
            violations.append(f"{path}:{node.lineno}")

    return violations


@pytest.mark.parametrize(
    ("source", "expected_count"),
    [
        # len >= 0 — always true, should flag
        ("assert len(results) >= 0\n", 1),
        ("assert 0 <= len(results)\n", 1),
        # attribute >= 0 — always true, should flag
        ("assert x.count >= 0\n", 1),
        ("assert x.duration >= 0\n", 1),
        ("assert x.total_size >= 0\n", 1),
        ("assert x.size >= 0\n", 1),
        ("assert x.length >= 0\n", 1),
        ("assert 0 <= x.count\n", 1),
        # Meaningful bounds — should NOT flag
        ("assert len(results) >= 1\n", 0),
        ("assert len(results) > 0\n", 0),
        ("assert len(results) == 0\n", 0),
        ("assert x.count == 0\n", 0),
        ("assert x.duration < 5.0\n", 0),
    ],
)
def test_detector_flags_vacuous_len_gte_zero(source: str, expected_count: int) -> None:
    assert len(_find_vacuous_len_gte_zero_assertions(source)) == expected_count


def test_changed_tests_have_no_vacuous_len_gte_zero_assertions() -> None:
    """Test files must not use ``assert len(x) >= 0`` or ``assert x.attr >= 0`` tautologies.

    ``len()`` is always non-negative by definition, as are counts, durations,
    and sizes.  Asserting ``>= 0`` provides zero signal — the assertion passes
    even when the code under test returns no results or is completely broken.

    Use a meaningful lower bound (``>= 1``), exact count (``== N``), or an
    upper bound (``< max_val``) instead.
    """
    violations: list[str] = []
    for path in _changed_test_files():
        source = path.read_text(encoding="utf-8")
        violations.extend(_find_vacuous_len_gte_zero_assertions(source, str(path)))

    assert not violations, (
        "Vacuous ``>= 0`` assertion found — use a meaningful bound instead:\n"
        + "\n".join(violations)
    )


# -------------------------------------------------------------------------
# Fix 6: sole isinstance assertions
# -------------------------------------------------------------------------

_WEAK_ISINSTANCE_TYPES = frozenset({"bool", "str", "int", "float", "dict", "list", "tuple", "set"})


def _is_isinstance_primitive_assert(node: ast.Assert) -> bool:
    """Return True if node is ``assert isinstance(x, T)`` with T a primitive type."""
    test = node.test
    if not isinstance(test, ast.Call):
        return False
    if not (isinstance(test.func, ast.Name) and test.func.id == "isinstance"):
        return False
    if len(test.args) != 2:
        return False
    type_arg = test.args[1]
    return isinstance(type_arg, ast.Name) and type_arg.id in _WEAK_ISINSTANCE_TYPES


def _collect_asserts_no_nested_defs(body: list[ast.stmt]) -> list[ast.Assert]:
    """Collect Assert nodes from body without descending into nested func/class defs."""
    result: list[ast.Assert] = []
    for stmt in body:
        if isinstance(stmt, ast.Assert):
            result.append(stmt)
        elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        else:
            for _field, value in ast.iter_fields(stmt):
                if isinstance(value, list):
                    for item in value:
                        if isinstance(item, ast.stmt):
                            result.extend(_collect_asserts_no_nested_defs([item]))
    return result


def _find_sole_isinstance_assertions(source: str, path: str = "<string>") -> list[str]:
    """Return ``file:line: name`` for test functions whose only assertions are bare isinstance.

    A test like::

        def test_update_rule(self, rm, rule):
            rm.add_rule("default", rule)
            result = rm.update_rule("default", updated)
            assert isinstance(result, bool)   # sole assertion

    verifies only the return type.  Since ``update_rule`` returns ``True`` on
    success, the test should assert ``result is True`` — a bare isinstance
    passes even if the implementation always returns ``False``.

    Flags functions where every ``assert`` in the function body is of the form
    ``assert isinstance(x, T)`` with ``T`` in the primitive-type set.
    """
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError:
        return []

    violations: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not node.name.startswith("test_"):
            continue
        asserts = _collect_asserts_no_nested_defs(node.body)
        if asserts and all(_is_isinstance_primitive_assert(a) for a in asserts):
            violations.append(f"{path}:{node.lineno}: {node.name}")
    return violations


@pytest.mark.parametrize(
    ("source", "expected_count"),
    [
        # Sole isinstance — should flag
        ("def test_foo():\n    assert isinstance(x, bool)\n", 1),
        ("def test_foo():\n    assert isinstance(x, str)\n", 1),
        ("def test_foo():\n    assert isinstance(x, dict)\n", 1),
        # Mixed — should NOT flag (has a real assertion too)
        ("def test_foo():\n    assert isinstance(x, bool)\n    assert x is True\n", 0),
        # Non-primitive type — should NOT flag
        ("def test_foo():\n    assert isinstance(x, MyClass)\n", 0),
        # Non-test function — should NOT flag
        ("def helper():\n    assert isinstance(x, bool)\n", 0),
        # No assertions — should NOT flag
        ("def test_foo():\n    x = 1\n", 0),
    ],
)
def test_detector_flags_sole_isinstance(source: str, expected_count: int) -> None:
    assert len(_find_sole_isinstance_assertions(source)) == expected_count


def test_changed_tests_have_no_sole_isinstance_assertions() -> None:
    """Changed test functions must not use ``assert isinstance(x, T)`` as their only assertion.

    A bare isinstance check verifies the return type but not the value.  This
    masks bugs where the implementation returns the wrong value of the right
    type — e.g. ``update_rule`` returning ``False`` when ``True`` is expected.

    Fix: use a specific value assertion alongside or instead of isinstance:

    - ``bool`` return → ``assert result is True`` or ``assert result is False``
    - ``str`` return  → ``assert result == "expected_string"``
    - ``dict`` return → ``assert result == {...}`` or assert specific keys/values

    Applies to changed files only (TODO: broaden to full suite after clean-up).
    """
    violations: list[str] = []
    for path in _git_changed_test_files():
        source = path.read_text(encoding="utf-8")
        violations.extend(_find_sole_isinstance_assertions(source, str(path)))

    assert not violations, (
        "Sole ``assert isinstance(x, T)`` found — add a specific value assertion:\n"
        + "\n".join(violations)
    )
