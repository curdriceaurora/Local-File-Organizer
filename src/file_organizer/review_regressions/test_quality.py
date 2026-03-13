"""Test-quality detector pack for legacy review-regression audits."""

from __future__ import annotations

import ast
import logging
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from file_organizer.review_regressions.framework import (
    ReviewRegressionDetector,
    Violation,
    fingerprint_ast_node,
    iter_python_files,
)

ScanMode = Literal["full_repo", "changed_test_files"]
_RULE_ID = "weak-mock-call-count-lower-bound"
_RULE_MESSAGE = (
    "Weak lower-bound call_count assertion; use an exact call assertion or assert concrete "
    "arguments/order/effects."
)
_LOGGER = logging.getLogger(__name__)


def _is_literal_int(node: ast.AST, value: int) -> bool:
    return isinstance(node, ast.Constant) and type(node.value) is int and node.value == value


def _is_call_count_attr(node: ast.AST) -> bool:
    if not isinstance(node, ast.Attribute) or node.attr != "call_count":
        return False
    value = node.value
    if isinstance(value, ast.Name):
        base = value.id.lower()
        return any(token in base for token in ("mock", "spy", "stub", "patch"))
    if isinstance(value, ast.Attribute):
        chain = value.attr.lower()
        if any(token in chain for token in ("mock", "spy", "stub", "patch")):
            return True
        if isinstance(value.value, ast.Name):
            base = value.value.id.lower()
            return any(token in base for token in ("mock", "spy", "stub", "patch", "mocker"))
    if isinstance(value, ast.Call):
        func = value.func
        if isinstance(func, ast.Name):
            return func.id in {"Mock", "MagicMock", "AsyncMock", "create_autospec"}
        if isinstance(func, ast.Attribute):
            return func.attr in {"Mock", "MagicMock", "AsyncMock", "patch", "spy"}
    return False


def _is_test_python_path(root: Path, path: Path) -> bool:
    try:
        rel = path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return False
    name = Path(rel).name
    if rel.startswith("tests/fixtures/") or name == "conftest.py":
        return False
    return (
        rel.startswith("tests/")
        and name.endswith(".py")
        and (name.startswith("test_") or name.endswith("_test.py"))
    )


def _iter_test_python_files(root: Path) -> list[Path]:
    tests_root = root / "tests"
    if not tests_root.exists():
        return []
    return [path for path in iter_python_files(tests_root) if _is_test_python_path(root, path)]


def _git_stdout(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _git_ref_exists(root: Path, ref: str) -> bool:
    return bool(_git_stdout(root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"))


def _resolve_diff_base(root: Path) -> str:
    """Return the widest practical base for changed-test detection.

    Prefer merge-base against main-like refs so multi-commit branches include all
    changed tests, then fall back to HEAD parent for detached/local cases.
    """
    for ref in ("origin/main", "refs/remotes/origin/main", "main"):
        if not _git_ref_exists(root, ref):
            continue
        merge_base = _git_stdout(root, "merge-base", "HEAD", ref)
        if merge_base:
            return merge_base

    head_parent = _git_stdout(root, "rev-parse", "--verify", "--quiet", "HEAD^1")
    if head_parent:
        return head_parent
    return _git_stdout(root, "rev-parse", "HEAD")


def discover_changed_test_files(root: Path) -> list[Path]:
    """Best-effort changed-test discovery for local audit runs."""
    head_sha = _git_stdout(root, "rev-parse", "HEAD")
    if not head_sha:
        return []

    base_sha = _resolve_diff_base(root)
    rel_paths: set[str] = set()

    if base_sha and base_sha != head_sha:
        rel_paths.update(
            path
            for path in _git_stdout(
                root,
                "diff",
                "--name-only",
                "--diff-filter=ACMR",
                f"{base_sha}...HEAD",
                "--",
                "tests/**/*.py",
                "tests/*.py",
            ).splitlines()
            if path
        )

    rel_paths.update(
        path
        for path in _git_stdout(
            root,
            "diff",
            "--cached",
            "--name-only",
            "--diff-filter=ACMR",
            "--",
            "tests/**/*.py",
            "tests/*.py",
        ).splitlines()
        if path
    )

    rel_paths.update(
        path
        for path in _git_stdout(
            root,
            "diff",
            "--name-only",
            "--diff-filter=ACMR",
            "--",
            "tests/**/*.py",
            "tests/*.py",
        ).splitlines()
        if path
    )

    rel_paths.update(
        path
        for path in _git_stdout(
            root,
            "ls-files",
            "--others",
            "--exclude-standard",
            "--",
            "tests/**/*.py",
            "tests/*.py",
        ).splitlines()
        if path
    )

    return [
        root / rel_path
        for rel_path in sorted(rel_paths)
        if rel_path and (root / rel_path).is_file() and _is_test_python_path(root, root / rel_path)
    ]


def _weak_assert_nodes(source: str, filename: str) -> list[ast.Assert]:
    tree = ast.parse(source, filename=filename)
    weak_nodes: list[ast.Assert] = []
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

        is_forward = _is_call_count_attr(left) and (
            (isinstance(op, ast.GtE) and _is_literal_int(right, 1))
            or (isinstance(op, ast.Gt) and _is_literal_int(right, 0))
        )
        is_reverse = _is_call_count_attr(right) and (
            (isinstance(op, ast.LtE) and _is_literal_int(left, 1))
            or (isinstance(op, ast.Lt) and _is_literal_int(left, 0))
        )

        if is_forward or is_reverse:
            weak_nodes.append(node)
    return weak_nodes


class WeakMockCallCountAssertionDetector:
    """Detect weak mock call-count lower bounds in test files."""

    detector_id = "test-quality.weak-mock-call-count-lower-bound"
    rule_class = "test-quality"
    description = "Flags weak lower-bound call_count assertions in tests (>= 1, > 0, 1 <=, 0 <)."

    def __init__(
        self,
        *,
        scan_mode: ScanMode = "full_repo",
        changed_files_provider: Callable[[Path], list[Path]] | None = None,
    ) -> None:
        """Initialize detector with either full-repo or changed-test-file scan mode."""
        self._scan_mode = scan_mode
        self._changed_files_provider = changed_files_provider or discover_changed_test_files

    def _candidate_files(self, root: Path) -> list[Path]:
        if self._scan_mode == "full_repo":
            return _iter_test_python_files(root)
        return self._changed_files_provider(root)

    def find_violations(self, root: Path) -> list[Violation]:
        """Return weak call-count assertions for the configured scan mode."""
        findings: list[Violation] = []
        for path in sorted({candidate.resolve() for candidate in self._candidate_files(root)}):
            if not path.is_file() or not _is_test_python_path(root, path):
                continue
            try:
                source = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                _LOGGER.warning(
                    "Skipping weak call-count scan for unreadable test file %s: %s",
                    path,
                    exc,
                    exc_info=True,
                )
                continue

            try:
                weak_nodes = _weak_assert_nodes(source, str(path))
            except (SyntaxError, ValueError) as exc:
                _LOGGER.warning(
                    "Skipping weak call-count scan for unparsable test file %s: %s",
                    path,
                    exc,
                    exc_info=True,
                )
                continue

            for node in weak_nodes:
                findings.append(
                    Violation.from_path(
                        detector_id=self.detector_id,
                        rule_class=self.rule_class,
                        rule_id=_RULE_ID,
                        root=root,
                        path=path,
                        line=node.lineno,
                        message=_RULE_MESSAGE,
                        fingerprint_basis=fingerprint_ast_node(node),
                    )
                )
        return sorted(findings, key=lambda finding: finding.sort_key())


TEST_QUALITY_DETECTORS: tuple[ReviewRegressionDetector, ...] = (
    WeakMockCallCountAssertionDetector(scan_mode="full_repo"),
)


def changed_test_quality_detectors() -> tuple[ReviewRegressionDetector, ...]:
    """Factory for changed-test-file detector mode."""
    return (WeakMockCallCountAssertionDetector(scan_mode="changed_test_files"),)
