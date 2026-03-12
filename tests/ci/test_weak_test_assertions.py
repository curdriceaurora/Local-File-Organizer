"""CI guardrails for weak mock call-count assertions in changed tests."""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

FO_ROOT = Path(__file__).resolve().parents[2]
MODULE = sys.modules[__name__]

pytestmark = pytest.mark.ci


def _is_literal_int(node: ast.AST, value: int) -> bool:
    return isinstance(node, ast.Constant) and type(node.value) is int and node.value == value


def _is_call_count_attr(node: ast.AST) -> bool:
    return isinstance(node, ast.Attribute) and node.attr == "call_count"


def _git_stdout(*args: str, check: bool = True) -> str:
    """Run git and return stripped stdout."""
    result = subprocess.run(
        ["git", *args],
        cwd=FO_ROOT,
        check=check,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _candidate_base_refs() -> list[str]:
    """Return ordered base-ref candidates for local and GitHub PR environments."""
    base_branch = os.environ.get("GITHUB_BASE_REF")
    candidates: list[str] = []

    if base_branch:
        candidates.extend(
            [f"origin/{base_branch}", f"refs/remotes/origin/{base_branch}", base_branch]
        )

    candidates.extend(["origin/main", "refs/remotes/origin/main", "main"])

    # Preserve order while dropping duplicates.
    return list(dict.fromkeys(candidates))


def _git_ref_exists(ref: str) -> bool:
    """Return whether *ref* resolves to a commit in the local checkout."""
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],
        cwd=FO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _resolve_diff_base() -> str:
    """Resolve a commit-ish usable as the changed-files diff base."""
    base_branch = os.environ.get("GITHUB_BASE_REF")

    for candidate in _candidate_base_refs():
        if not _git_ref_exists(candidate):
            continue

        merge_base = _git_stdout("merge-base", "HEAD", candidate, check=False)
        if merge_base:
            return merge_base

    # In GitHub PR jobs, HEAD is often a synthetic merge commit even when the
    # base branch ref itself is not available locally.
    head_parent = _git_stdout("rev-parse", "--verify", "--quiet", "HEAD^1", check=False)
    if head_parent:
        return head_parent

    if base_branch:
        pytest.fail(
            "Unable to resolve a git diff base for PR guardrail checks. "
            f"GITHUB_BASE_REF={base_branch!r} is set, but no suitable base ref "
            "or HEAD^1 commit could be found in the checkout. Ensure the base "
            "ref is fetched or increase actions/checkout.fetch-depth so "
            "changed-test detection is reliable."
        )

    return _git_stdout("rev-parse", "HEAD")


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

        is_weak_forward = _is_call_count_attr(left) and (
            (isinstance(op, ast.GtE) and _is_literal_int(right, 1))
            or (isinstance(op, ast.Gt) and _is_literal_int(right, 0))
        )
        is_weak_reverse = _is_call_count_attr(right) and (
            (isinstance(op, ast.LtE) and _is_literal_int(left, 1))
            or (isinstance(op, ast.Lt) and _is_literal_int(left, 0))
        )

        if is_weak_forward or is_weak_reverse:
            violations.append(f"{path}:{node.lineno}")

    return violations


def _changed_test_files() -> list[Path]:
    """Return changed test files relative to the best available diff base."""
    diff_base = _resolve_diff_base()
    head_sha = _git_stdout("rev-parse", "HEAD")
    if diff_base == head_sha:
        return []

    diff_output = _git_stdout(
        "diff",
        "--name-only",
        "--diff-filter=ACMR",
        f"{diff_base}...HEAD",
        "--",
        "tests/**/*.py",
        "tests/*.py",
    )

    return [
        FO_ROOT / rel_path
        for rel_path in diff_output.splitlines()
        if rel_path and (FO_ROOT / rel_path).is_file()
    ]


@pytest.mark.parametrize(
    ("base_branch", "expected"),
    [
        ("main", ["origin/main", "refs/remotes/origin/main", "main"]),
        (
            "release",
            [
                "origin/release",
                "refs/remotes/origin/release",
                "release",
                "origin/main",
                "refs/remotes/origin/main",
                "main",
            ],
        ),
    ],
)
def test_candidate_base_refs_cover_local_and_github_pr_context(
    monkeypatch: pytest.MonkeyPatch, base_branch: str, expected: list[str]
) -> None:
    monkeypatch.setenv("GITHUB_BASE_REF", base_branch)
    assert _candidate_base_refs() == expected


def test_candidate_base_refs_default_to_main_when_github_base_ref_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITHUB_BASE_REF", raising=False)
    assert _candidate_base_refs() == ["origin/main", "refs/remotes/origin/main", "main"]


def test_resolve_diff_base_falls_back_to_head_parent_when_remote_base_ref_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        MODULE,
        "_candidate_base_refs",
        lambda: ["origin/main", "main"],
    )
    monkeypatch.setattr(MODULE, "_git_ref_exists", lambda ref: False)
    monkeypatch.setattr(
        MODULE,
        "_git_stdout",
        lambda *args, check=True: (
            "parent-sha" if args == ("rev-parse", "--verify", "--quiet", "HEAD^1") else "head-sha"
        ),
    )
    assert _resolve_diff_base() == "parent-sha"


def test_resolve_diff_base_fails_loudly_in_pr_context_when_no_base_is_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_BASE_REF", "main")
    monkeypatch.setattr(MODULE, "_candidate_base_refs", lambda: ["origin/main", "main"])
    monkeypatch.setattr(MODULE, "_git_ref_exists", lambda ref: False)
    monkeypatch.setattr(
        MODULE,
        "_git_stdout",
        lambda *args, check=True: "",
    )

    with pytest.raises(pytest.fail.Exception, match="Unable to resolve a git diff base"):
        _resolve_diff_base()


def test_changed_test_files_returns_empty_when_no_distinct_diff_base(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(MODULE, "_resolve_diff_base", lambda: "head-sha")
    monkeypatch.setattr(MODULE, "_git_stdout", lambda *args, check=True: "head-sha")
    assert _changed_test_files() == []


def test_changed_test_files_includes_renames_in_diff_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded_calls: list[tuple[str, ...]] = []

    def fake_git_stdout(*args: str, check: bool = True) -> str:
        recorded_calls.append(args)
        if args == ("rev-parse", "HEAD"):
            return "head-sha"
        if args[:2] == ("diff", "--name-only"):
            return ""
        return "base-sha"

    monkeypatch.setattr(MODULE, "_resolve_diff_base", lambda: "base-sha")
    monkeypatch.setattr(MODULE, "_git_stdout", fake_git_stdout)

    assert _changed_test_files() == []
    assert (
        "diff",
        "--name-only",
        "--diff-filter=ACMR",
        "base-sha...HEAD",
        "--",
        "tests/**/*.py",
        "tests/*.py",
    ) in recorded_calls


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
        "assert mock.call_count >= True\n",
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
