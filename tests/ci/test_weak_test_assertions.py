"""CI guardrails for weak mock call-count assertions in changed tests."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from urllib import error, request

import pytest

from file_organizer.review_regressions.test_quality import _weak_assert_nodes

FO_ROOT = Path(__file__).resolve().parents[2]
MODULE = sys.modules[__name__]

pytestmark = pytest.mark.ci

_LAST_DIFF_BASE_ERROR: str | None = None


def _is_guarded_test_path(rel_path: str) -> bool:
    """Return whether rel_path is a test file covered by this guardrail."""
    return (
        rel_path.startswith("tests/")
        and rel_path.endswith(".py")
        and not rel_path.startswith("tests/fixtures/")
    )


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


def _fetch_base_ref(base_branch: str) -> str | None:
    """Fetch the PR base branch into a usable remote-tracking ref."""
    try:
        subprocess.run(
            [
                "git",
                "fetch",
                "--depth=1000",
                "origin",
                base_branch,
            ],
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
    """Return the first merge base found from known base-ref candidates."""
    for candidate in _candidate_base_refs():
        if not _git_ref_exists(candidate):
            continue

        merge_base = _git_stdout("merge-base", "HEAD", candidate, check=False)
        if merge_base:
            return merge_base

    return ""


def _github_pr_base_parent() -> str:
    """Return the base parent of GitHub's synthetic PR merge commit when available."""
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
    """Return changed test files from GitHub's PR files API when available.

    Returns ``None`` when the GitHub PR context or API response is unusable.
    Returns a list, which may be empty, when the API call succeeds.
    """
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

            with request.urlopen(api_request) as response:
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

    return [FO_ROOT / rel_path for rel_path in sorted(rel_paths) if (FO_ROOT / rel_path).is_file()]


def _resolve_diff_base() -> str | None:
    """Resolve a commit-ish usable as the changed-files diff base."""
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

    if base_branch:
        return None

    head_parent = _git_stdout("rev-parse", "--verify", "--quiet", "HEAD^1", check=False)
    if head_parent:
        return head_parent

    return _git_stdout("rev-parse", "HEAD")


def _find_weak_call_count_assertions(source: str, path: str = "<string>") -> list[str]:
    """Return weak lower-bound mock call-count assertions found in *source*.

    High-confidence patterns only:
    - assert mock.call_count >= 1
    - assert mock.call_count > 0
    - assert 1 <= mock.call_count
    - assert 0 < mock.call_count
    """
    return [f"{path}:{node.lineno}" for node in _weak_assert_nodes(source, path)]


def _changed_test_files() -> list[Path]:
    """Return changed test files from CI and local pre-commit contexts."""
    diff_base = _resolve_diff_base()
    if diff_base is None:
        changed_files = _github_pr_changed_test_files()
        if changed_files is not None:
            return changed_files

        if _LAST_DIFF_BASE_ERROR:
            pytest.fail(
                "Unable to determine changed test files for PR guardrail checks. "
                "Git-based diff-base resolution failed, the GitHub PR files API "
                f"did not provide a usable fallback, and the last git error was: {_LAST_DIFF_BASE_ERROR}"
            )

        pytest.fail(
            "Unable to determine changed test files for PR guardrail checks. "
            "Git-based diff-base resolution failed and the GitHub PR files API "
            "did not provide a usable fallback."
        )

    head_sha = _git_stdout("rev-parse", "HEAD")
    rel_paths: set[str] = set()

    if diff_base != head_sha:
        diff_output = _git_stdout(
            "diff",
            "--name-only",
            "--diff-filter=ACMR",
            f"{diff_base}...HEAD",
            "--",
            "tests/**/*.py",
            "tests/*.py",
        )
        rel_paths.update(path for path in diff_output.splitlines() if path)

    staged_diff_output = _git_stdout(
        "diff",
        "--cached",
        "--name-only",
        "--diff-filter=ACMR",
        "--",
        "tests/**/*.py",
        "tests/*.py",
    )
    rel_paths.update(path for path in staged_diff_output.splitlines() if path)

    worktree_diff_output = _git_stdout(
        "diff",
        "--name-only",
        "--diff-filter=ACMR",
        "--",
        "tests/**/*.py",
        "tests/*.py",
    )
    rel_paths.update(path for path in worktree_diff_output.splitlines() if path)

    return [
        FO_ROOT / rel_path
        for rel_path in sorted(rel_paths)
        if rel_path and _is_guarded_test_path(rel_path) and (FO_ROOT / rel_path).is_file()
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
    monkeypatch.delenv("GITHUB_BASE_REF", raising=False)
    monkeypatch.setattr(MODULE, "_merge_base_from_candidates", lambda: "")
    monkeypatch.setattr(MODULE, "_github_pr_base_parent", lambda: "")
    monkeypatch.setattr(
        MODULE,
        "_git_stdout",
        lambda *args, check=True: (
            "parent-sha" if args == ("rev-parse", "--verify", "--quiet", "HEAD^1") else "head-sha"
        ),
    )
    assert _resolve_diff_base() == "parent-sha"


def test_resolve_diff_base_fetches_base_branch_when_missing_locally(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_BASE_REF", "main")
    fetch_calls: list[str] = []
    merge_bases = iter(["", ""])

    monkeypatch.setattr(MODULE, "_merge_base_from_candidates", lambda: next(merge_bases))
    monkeypatch.setattr(
        MODULE,
        "_fetch_base_ref",
        lambda branch: fetch_calls.append(branch),
    )
    monkeypatch.setattr(
        MODULE,
        "_git_stdout",
        lambda *args, check=True: (
            "fetch-head-sha"
            if args == ("rev-parse", "--verify", "--quiet", "FETCH_HEAD")
            else "fetched-base-sha"
            if args == ("merge-base", "HEAD", "FETCH_HEAD")
            else ""
        ),
    )
    assert _resolve_diff_base() == "fetched-base-sha"
    assert fetch_calls == ["main"]


def test_resolve_diff_base_prefers_github_pr_base_parent_before_fetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_BASE_REF", "main")
    fetch_calls: list[str] = []

    monkeypatch.setattr(MODULE, "_merge_base_from_candidates", lambda: "")
    monkeypatch.setattr(MODULE, "_github_pr_base_parent", lambda: "base-parent-sha")
    monkeypatch.setattr(MODULE, "_git_ref_exists", lambda ref: ref == "base-parent-sha")
    monkeypatch.setattr(
        MODULE,
        "_fetch_base_ref",
        lambda branch: fetch_calls.append(branch),
    )

    assert _resolve_diff_base() == "base-parent-sha"
    assert fetch_calls == []


def test_resolve_diff_base_fetches_when_github_pr_base_parent_missing_locally(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_BASE_REF", "main")
    fetch_calls: list[str] = []
    merge_bases = iter(["", "fetched-base-sha"])

    monkeypatch.setattr(MODULE, "_merge_base_from_candidates", lambda: next(merge_bases))
    monkeypatch.setattr(MODULE, "_github_pr_base_parent", lambda: "base-parent-sha")
    monkeypatch.setattr(MODULE, "_git_ref_exists", lambda ref: False)
    monkeypatch.setattr(
        MODULE,
        "_fetch_base_ref",
        lambda branch: fetch_calls.append(branch),
    )

    assert _resolve_diff_base() == "fetched-base-sha"
    assert fetch_calls == ["main"]


def test_github_pr_base_parent_uses_event_payload_to_pick_base_parent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    event_path = tmp_path / "event.json"
    event_path.write_text(
        json.dumps({"pull_request": {"head": {"sha": "feature-sha"}}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))
    monkeypatch.setattr(
        MODULE,
        "_git_stdout",
        lambda *args, check=True: "merge-sha feature-sha base-sha",
    )
    assert _github_pr_base_parent() == "base-sha"


def test_github_pr_changed_test_files_adds_auth_header_when_token_present(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    event_path = tmp_path / "event.json"
    event_path.write_text(
        json.dumps({"pull_request": {"url": "https://api.github.com/repos/o/r/pulls/773"}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))
    monkeypatch.setenv("GITHUB_TOKEN", "secret-token")

    class _FakeResponse:
        def __enter__(self) -> _FakeResponse:
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        def read(self) -> bytes:
            return b"[]"

    captured_headers: dict[str, str] = {}

    def fake_urlopen(req: request.Request) -> _FakeResponse:
        captured_headers.update(dict(req.header_items()))
        return _FakeResponse()

    monkeypatch.setattr(request, "urlopen", fake_urlopen)
    assert _github_pr_changed_test_files() == []
    assert captured_headers["Authorization"] == "token secret-token"


def test_github_pr_changed_test_files_returns_none_for_non_list_payload(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    event_path = tmp_path / "event.json"
    event_path.write_text(
        json.dumps({"pull_request": {"url": "https://api.github.com/repos/o/r/pulls/773"}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))

    class _FakeResponse:
        def __enter__(self) -> _FakeResponse:
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"message": "rate limited"}'

    monkeypatch.setattr(request, "urlopen", lambda req: _FakeResponse())

    assert _github_pr_changed_test_files() is None


def test_changed_test_files_returns_empty_when_pr_api_has_no_test_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(MODULE, "_resolve_diff_base", lambda: None)
    monkeypatch.setattr(MODULE, "_LAST_DIFF_BASE_ERROR", None)
    monkeypatch.setattr(MODULE, "_github_pr_changed_test_files", lambda: [])

    assert _changed_test_files() == []


def test_resolve_diff_base_returns_none_in_pr_context_when_no_base_is_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_BASE_REF", "main")
    monkeypatch.setattr(MODULE, "_merge_base_from_candidates", lambda: "")
    monkeypatch.setattr(MODULE, "_fetch_base_ref", lambda branch: None)
    monkeypatch.setattr(MODULE, "_github_pr_base_parent", lambda: "")
    monkeypatch.setattr(MODULE, "_git_stdout", lambda *args, check=True: "")

    assert _resolve_diff_base() is None


def test_resolve_diff_base_returns_none_when_fetch_times_out_in_pr_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_BASE_REF", "main")
    monkeypatch.setattr(MODULE, "_merge_base_from_candidates", lambda: "")
    monkeypatch.setattr(MODULE, "_github_pr_base_parent", lambda: "")
    monkeypatch.setattr(
        MODULE,
        "_fetch_base_ref",
        lambda branch: "git fetch origin 'main' timed out after 5 seconds",
    )
    monkeypatch.setattr(MODULE, "_git_stdout", lambda *args, check=True: "")

    assert _resolve_diff_base() is None


def test_changed_test_files_returns_empty_when_no_distinct_diff_base(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(MODULE, "_resolve_diff_base", lambda: "head-sha")
    monkeypatch.setattr(
        MODULE,
        "_git_stdout",
        lambda *args, check=True: "head-sha" if args == ("rev-parse", "HEAD") else "",
    )
    assert _changed_test_files() == []


def test_changed_test_files_use_github_pr_api_when_git_diff_base_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fallback_files = [FO_ROOT / "tests" / "ci" / "test_weak_test_assertions.py"]
    monkeypatch.setattr(MODULE, "_resolve_diff_base", lambda: None)
    monkeypatch.setattr(MODULE, "_LAST_DIFF_BASE_ERROR", None)
    monkeypatch.setattr(MODULE, "_github_pr_changed_test_files", lambda: fallback_files)
    assert _changed_test_files() == fallback_files


def test_changed_test_files_reports_fetch_timeout_when_api_fallback_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(MODULE, "_resolve_diff_base", lambda: None)
    monkeypatch.setattr(
        MODULE,
        "_LAST_DIFF_BASE_ERROR",
        "git fetch origin 'main' timed out after 5 seconds",
    )
    monkeypatch.setattr(MODULE, "_github_pr_changed_test_files", lambda: None)

    with pytest.raises(pytest.fail.Exception, match="timed out after 5 seconds"):
        _changed_test_files()


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


def test_changed_test_files_includes_staged_and_worktree_diffs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_git_stdout(*args: str, check: bool = True) -> str:
        if args == ("rev-parse", "HEAD"):
            return "head-sha"
        if args == (
            "diff",
            "--cached",
            "--name-only",
            "--diff-filter=ACMR",
            "--",
            "tests/**/*.py",
            "tests/*.py",
        ):
            return "tests/ci/test_weak_test_assertions.py\n"
        if args == (
            "diff",
            "--name-only",
            "--diff-filter=ACMR",
            "--",
            "tests/**/*.py",
            "tests/*.py",
        ):
            return "tests/ci/test_review_regressions.py\n"
        return ""

    monkeypatch.setattr(MODULE, "_resolve_diff_base", lambda: "head-sha")
    monkeypatch.setattr(MODULE, "_git_stdout", fake_git_stdout)

    assert _changed_test_files() == [
        FO_ROOT / "tests" / "ci" / "test_review_regressions.py",
        FO_ROOT / "tests" / "ci" / "test_weak_test_assertions.py",
    ]


def test_changed_test_files_excludes_fixture_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_git_stdout(*args: str, check: bool = True) -> str:
        if args == ("rev-parse", "HEAD"):
            return "head-sha"
        if args == (
            "diff",
            "--cached",
            "--name-only",
            "--diff-filter=ACMR",
            "--",
            "tests/**/*.py",
            "tests/*.py",
        ):
            return (
                "tests/fixtures/review_regressions/test_quality/tests/weak_assertions_positive.py\n"
                "tests/ci/test_weak_test_assertions.py\n"
            )
        return ""

    monkeypatch.setattr(MODULE, "_resolve_diff_base", lambda: "head-sha")
    monkeypatch.setattr(MODULE, "_git_stdout", fake_git_stdout)

    assert _changed_test_files() == [FO_ROOT / "tests" / "ci" / "test_weak_test_assertions.py"]


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("assert mock.call_count >= 1\n", ["<string>:1"]),
        ("assert mock.call_count > 0\n", ["<string>:1"]),
        ("assert 1 <= mock.call_count\n", ["<string>:1"]),
        ("assert 0 < mock.call_count\n", ["<string>:1"]),
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
