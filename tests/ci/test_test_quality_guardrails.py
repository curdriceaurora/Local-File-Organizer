"""CI guardrails for test quality anti-patterns.

Covers two regression classes identified in PR #846 review:

1. ``time.sleep()`` in tests — wall-clock sleeps make tests flaky under
   load and mask real timing bugs.  Use ``os.utime()`` for mtime bumps or
   event-based polling instead.

2. ``assert len(results) <= N`` patterns — when a corpus is guaranteed to
   produce at least N matches (e.g. ``top_k=N`` with enough documents),
   the upper-bound assertion is vacuous: it passes even when the index
   returns zero matches.  Use ``assert len(results) == N`` instead.

Both guardrails apply only to *changed* test files (diff against merge base),
following the same strategy as ``test_weak_test_assertions.py``.  This keeps
CI green against a pre-existing baseline while preventing regressions in new
and modified tests.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
from pathlib import Path
from urllib import error, request

import pytest

FO_ROOT = Path(__file__).resolve().parents[2]
TESTS_ROOT = FO_ROOT / "tests"

pytestmark = pytest.mark.ci

_LAST_DIFF_BASE_ERROR: str | None = None


# -------------------------------------------------------------------------
# CI-aware diff-base resolver (mirrors test_weak_test_assertions.py)
# -------------------------------------------------------------------------


def _git_stdout(*args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=FO_ROOT,
        check=check,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _is_guarded_test_path(rel_path: str) -> bool:
    return (
        rel_path.startswith("tests/")
        and rel_path.endswith(".py")
        and not rel_path.startswith("tests/fixtures/")
    )


def _candidate_base_refs() -> list[str]:
    base_branch = os.environ.get("GITHUB_BASE_REF")
    candidates: list[str] = []
    if base_branch:
        candidates.extend(
            [f"origin/{base_branch}", f"refs/remotes/origin/{base_branch}", base_branch]
        )
    candidates.extend(["origin/main", "refs/remotes/origin/main", "main"])
    return list(dict.fromkeys(candidates))


def _git_ref_exists(ref: str) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],
        cwd=FO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _fetch_base_ref(base_branch: str) -> str | None:
    try:
        subprocess.run(
            ["git", "fetch", "--depth=1000", "origin", base_branch],
            cwd=FO_ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except subprocess.TimeoutExpired:
        return f"git fetch origin {base_branch!r} timed out after 5 seconds"
    return None


def _merge_base_from_candidates() -> str:
    for candidate in _candidate_base_refs():
        if not _git_ref_exists(candidate):
            continue
        base = _git_stdout("merge-base", "HEAD", candidate, check=False)
        if base:
            return base
    return ""


def _github_pr_base_parent() -> str:
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        return ""
    try:
        event = json.loads(Path(event_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    pull_request = event.get("pull_request")
    if not isinstance(pull_request, dict):
        return ""
    head_sha = pull_request.get("head", {}).get("sha")
    if not isinstance(head_sha, str) or not head_sha:
        return ""
    parents = _git_stdout("rev-list", "--parents", "-n", "1", "HEAD", check=False).split()
    if len(parents) < 3:
        return ""
    _, first_parent, second_parent, *_ = parents
    if first_parent == head_sha:
        return second_parent
    if second_parent == head_sha:
        return first_parent
    return ""


def _github_pr_changed_test_files() -> list[Path] | None:
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        return None
    try:
        event = json.loads(Path(event_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    pull_request = event.get("pull_request")
    if not isinstance(pull_request, dict):
        return None
    pr_url = pull_request.get("url")
    if not isinstance(pr_url, str) or not pr_url:
        return None
    rel_paths: set[str] = set()
    page = 1
    while True:
        try:
            api_request = request.Request(f"{pr_url}/files?per_page=100&page={page}")
            token = os.environ.get("GITHUB_TOKEN")
            if token:
                api_request.add_header("Authorization", f"token {token}")
            with request.urlopen(api_request, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (OSError, json.JSONDecodeError, error.URLError):
            return None
        if not isinstance(payload, list):
            return None
        if not payload:
            break
        for file_info in payload:
            if not isinstance(file_info, dict):
                continue
            filename = file_info.get("filename")
            if isinstance(filename, str) and _is_guarded_test_path(filename):
                rel_paths.add(filename)
        if len(payload) < 100:
            break
        page += 1
    return [FO_ROOT / rp for rp in sorted(rel_paths) if (FO_ROOT / rp).is_file()]


def _resolve_diff_base() -> str | None:
    global _LAST_DIFF_BASE_ERROR
    _LAST_DIFF_BASE_ERROR = None
    base_branch = os.environ.get("GITHUB_BASE_REF")
    merge_base = _merge_base_from_candidates()
    if merge_base:
        return merge_base
    if base_branch:
        base_parent = _github_pr_base_parent()
        if base_parent and _git_ref_exists(base_parent):
            return base_parent
        _LAST_DIFF_BASE_ERROR = _fetch_base_ref(base_branch)
        merge_base = _merge_base_from_candidates()
        if merge_base:
            return merge_base
        fetch_head = _git_stdout("rev-parse", "--verify", "--quiet", "FETCH_HEAD", check=False)
        if fetch_head:
            merge_base = _git_stdout("merge-base", "HEAD", "FETCH_HEAD", check=False)
            if merge_base:
                return merge_base
        return None
    head_parent = _git_stdout("rev-parse", "--verify", "--quiet", "HEAD^1", check=False)
    if head_parent:
        return head_parent
    return _git_stdout("rev-parse", "HEAD")


def _changed_test_files() -> list[Path]:
    """Return test files changed relative to the merge base.

    Fails closed in CI when no diff base can be resolved and the GitHub PR
    API cannot provide a fallback — prevents the guardrail from silently
    passing on shallow checkouts.
    """
    diff_base = _resolve_diff_base()
    if diff_base is None:
        changed_files = _github_pr_changed_test_files()
        if changed_files is not None:
            return changed_files
        if _LAST_DIFF_BASE_ERROR:
            pytest.fail(
                "Unable to determine changed test files for guardrail checks. "
                f"Git-based diff-base resolution failed: {_LAST_DIFF_BASE_ERROR}"
            )
        pytest.fail(
            "Unable to determine changed test files for guardrail checks. "
            "Git-based diff-base resolution failed and GitHub PR API was unavailable."
        )

    head_sha = _git_stdout("rev-parse", "HEAD")
    rel_paths: set[str] = set()

    if diff_base != head_sha:
        diff = _git_stdout(
            "diff",
            "--name-only",
            "--diff-filter=ACMR",
            f"{diff_base}...HEAD",
            "--",
            "tests/**/*.py",
            "tests/*.py",
        )
        rel_paths.update(p for p in diff.splitlines() if p)

    for extra_flags in (["--cached"], []):
        diff = _git_stdout(
            "diff",
            *extra_flags,
            "--name-only",
            "--diff-filter=ACMR",
            "--",
            "tests/**/*.py",
            "tests/*.py",
        )
        rel_paths.update(p for p in diff.splitlines() if p)

    return [
        FO_ROOT / rp
        for rp in sorted(rel_paths)
        if rp and _is_guarded_test_path(rp) and (FO_ROOT / rp).is_file()
    ]


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
