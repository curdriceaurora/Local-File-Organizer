#!/usr/bin/env python3
"""Pre-push diff-coverage gate (mirrors CI's 3.11-leg "Diff coverage gate" step).

Called by the diff-cover hook in .pre-commit-config.yaml.

Behaviour (issue #1767 item 3 -- moved from pre-commit to pre-push, and
scoped to the diff instead of re-running the near-full suite):
  1. Exits 0 immediately if no src/ or tests/ Python files changed since
     origin/main (deletions excluded -- a deleted file has no lines left
     to check coverage on, and re-including it broke `git diff`'s own
     rename/delete bookkeeping for the pytest invocation below).
  2. Exits 0 with a warning if origin/main merge base is unavailable
     (shallow clone, offline, no remote). Never blocks in that case.
  3. Maps each changed src/ file to related test files: same-named test
     directory (e.g. src/file_organizer/services/deduplication/extractor.py
     -> tests/services/deduplication/) filtered by substring match on stem
     (test_dedup_extractor*.py, not an exact-stem match), plus any test
     files changed directly.
  4. Fails OPEN, not closed: if NO related tests are found for ANY changed
     file, this hook warns and skips entirely rather than blocking the
     push. If SOME files are unmapped, diff-cover's own `--include` is
     scoped to just the src/ files we did map -- an unmapped file's lines
     are never locally evaluated at all (not "evaluated against no
     evidence and failed"), matching the promise that its coverage is
     left entirely to CI's diff-cover step.
  5. Runs the mapped tests with the local-hook's marker exclusions
     ("not benchmark and not e2e and not integration"). If that excludes
     every selected test (e.g. the only changed file has just an
     integration-marked test), this warns and skips rather than letting
     pytest's "no tests collected" exit blow up the push.
  6. Runs diff-cover, scoped per (4); exits non-zero if changed lines in
     the mapped files are <80% covered.

This is a Python script rather than the bash it replaces (issue #1767 PR
review) so the file-mapping/selection logic is portable (no bash-version
dependency -- the prior version broke on macOS's Bash 3.2) and unit
testable (see tests/ci/test_run_diff_cover.py).

Prerequisites:
  git fetch-depth: 0  (full history so origin/main is resolvable as a
  merge base). Shallow-clone users: run `git fetch --unshallow` once.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LOCAL_MARKER_EXCLUSIONS = "not benchmark and not e2e and not integration"


def merge_base(repo_root: Path = REPO_ROOT) -> str | None:
    """origin/main merge base for HEAD, or None if unavailable."""
    result = subprocess.run(
        ["git", "merge-base", "HEAD", "origin/main"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def changed_python_files(base: str, repo_root: Path = REPO_ROOT) -> list[str]:
    """Files under src/ or tests/ changed since *base*, excluding deletions.

    --diff-filter=d excludes deleted paths -- otherwise a deleted test file
    both has nothing left to run and can't be passed to pytest as a path.
    """
    result = subprocess.run(
        [
            "git",
            "diff",
            "--name-only",
            "--diff-filter=d",
            f"{base}...HEAD",
            "--",
            "src/*.py",
            "src/**/*.py",
            "tests/*.py",
            "tests/**/*.py",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def map_to_tests(changed: list[str], repo_root: Path = REPO_ROOT) -> tuple[set[str], list[str]]:
    """Map changed files to related test paths.

    Returns (test_paths, unmapped_src_files). A changed test file is
    directly in scope. A changed src/ file is mapped by directory (same
    directory *name* under tests/, wherever it occurs -- e.g.
    "deduplication" under tests/services/deduplication/) filtered by
    substring match on stem, so "extractor.py" maps to
    "test_dedup_extractor*.py" without a whole-tree substring search
    pulling in every unrelated "*extractor*" test in the suite.
    """
    test_paths: set[str] = set()
    unmapped: list[str] = []

    for file in changed:
        path = Path(file)
        if path.parts[0] == "tests" and path.name.startswith("test_") and path.suffix == ".py":
            test_paths.add(file)
            continue
        if not (path.parts[0] == "src" and path.suffix == ".py"):
            continue
        if path.stem == "__init__":
            continue

        parent_name = path.parent.name
        candidate_dirs = [d for d in (repo_root / "tests").rglob(parent_name) if d.is_dir()]
        matches = [
            str(t.relative_to(repo_root))
            for d in candidate_dirs
            for t in d.glob("test_*.py")
            if path.stem in t.stem
        ]
        if matches:
            test_paths.update(matches)
        else:
            unmapped.append(file)

    return test_paths, unmapped


def mapped_src_files(changed: list[str], unmapped: list[str]) -> list[str]:
    """Changed src/ files that DID map to a test -- diff-cover's scope."""
    unmapped_set = set(unmapped)
    return [
        f for f in changed if f.startswith("src/") and f.endswith(".py") and f not in unmapped_set
    ]


def main() -> int:
    """Run the pre-push diff-coverage gate; return the process exit code."""
    # REPO_ROOT is read here (a live global lookup), not baked into the
    # helpers' own default arguments -- so tests can monkeypatch
    # run_diff_cover.REPO_ROOT and have it actually take effect.
    repo_root = REPO_ROOT
    base = merge_base(repo_root)
    if base is None:
        print(
            "diff-cover: skipping — origin/main merge base unavailable "
            "(shallow clone or offline). Run 'git fetch --unshallow' to enable.",
            file=sys.stderr,
        )
        return 0

    changed = changed_python_files(base, repo_root)
    if not changed:
        return 0

    test_paths, unmapped = map_to_tests(changed, repo_root)

    if not test_paths:
        print(
            f"diff-cover: skipping — no related test files found for the changed "
            f"diff (checked: {', '.join(changed)}). CI's diff-cover step on the "
            "3.11 leg remains the enforced gate.",
            file=sys.stderr,
        )
        return 0

    include = mapped_src_files(changed, unmapped)
    if unmapped:
        print(
            "diff-cover: no test-file match found by naming convention for: "
            f"{', '.join(unmapped)} — running the tests found for the rest of "
            "the diff; these files' coverage is scoped OUT of this local check "
            "and will only be checked by CI.",
            file=sys.stderr,
        )

    pytest_result = subprocess.run(
        [
            "pytest",
            *sorted(test_paths),
            "-q",
            "--override-ini=addopts=",
            "--cov=file_organizer",
            "--cov-report=xml:coverage.xml",
            "--no-header",
            "-m",
            LOCAL_MARKER_EXCLUSIONS,
        ],
        cwd=repo_root,
    )
    if pytest_result.returncode == 5:
        # ExitCode.NO_TESTS_COLLECTED: every selected test was excluded by
        # LOCAL_MARKER_EXCLUSIONS (e.g. the only related test is
        # integration-marked). Skip rather than block the push on it.
        print(
            "diff-cover: skipping — every related test was excluded by this "
            f"hook's local marker filter ({LOCAL_MARKER_EXCLUSIONS!r}). CI's "
            "diff-cover step on the 3.11 leg remains the enforced gate.",
            file=sys.stderr,
        )
        return 0
    if pytest_result.returncode != 0:
        return pytest_result.returncode

    if not include:
        # Every changed src/ file was unmapped (only test files mapped, e.g.
        # a change confined to test files themselves); nothing for
        # diff-cover to check against source coverage.
        return 0

    diff_cover_result = subprocess.run(
        [
            "diff-cover",
            "coverage.xml",
            f"--compare-branch={base}",
            "--fail-under=80",
            "--quiet",
            "--include",
            *include,
        ],
        cwd=repo_root,
    )
    return diff_cover_result.returncode


if __name__ == "__main__":
    sys.exit(main())
