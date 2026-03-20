"""CI guardrail: test files that import optional dependencies must use pytest.importorskip.

When an optional package (rank_bm25, sklearn, fitz, etc.) is not installed, a module-level
import crashes the entire test file at collection time — silencing all tests, including ones
that don't need the optional dep.  The fix is a class-level autouse fixture that calls
``pytest.importorskip("<package>")``.

This guardrail:

1. Reads ``[project.optional-dependencies]`` from ``pyproject.toml`` to discover the
   canonical set of optional packages (excluding ``dev``, ``web``, ``docs``, ``build``
   groups that are always installed in CI).

2. Applies a hardcoded name-mapping table to translate distribution names
   (e.g. ``scikit-learn``) to their importable names (e.g. ``sklearn``).

3. AST-parses each test file (excluding ``conftest.py``, ``tests/fixtures/``,
   ``tests/ci/``) and flags any top-level ``import`` or ``from X import Y`` that
   references an optional package when no ``pytest.importorskip(...)`` call exists
   anywhere in the file.

Scope: diff-based (changed files only) — broadened to full suite once all pre-existing
violations are resolved.
"""

from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

import pytest

FO_ROOT = Path(__file__).resolve().parents[2]
TESTS_ROOT = FO_ROOT / "tests"
PYPROJECT = FO_ROOT / "pyproject.toml"

pytestmark = pytest.mark.ci

_SELF = Path(__file__).resolve()

# Optional-dep groups to scan for package names.
# Excluded groups (always installed in CI / dev): dev, web, docs, build, all
_OPTIONAL_GROUP_EXCLUDES = frozenset({"dev", "web", "docs", "build", "all"})

# Distribution name → importable module name.
# Only entries that differ from the dist name (with hyphens replaced by underscores) are listed.
_DIST_TO_IMPORT: dict[str, str] = {
    "rank-bm25": "rank_bm25",
    "scikit-learn": "sklearn",
    "PyMuPDF": "fitz",
    "python-docx": "docx",
    "python-pptx": "pptx",
    "beautifulsoup4": "bs4",
    "opencv-python": "cv2",
    "faster-whisper": "faster_whisper",
    "scenedetect[opencv]": "scenedetect",
    "llama-cpp-python": "llama_cpp",
    "mlx-lm": "mlx_lm",
    "striprtf": "striprtf",
}


def _dist_to_import_name(dist: str) -> str:
    """Convert a distribution name (from pyproject.toml) to its importable name."""
    if dist in _DIST_TO_IMPORT:
        return _DIST_TO_IMPORT[dist]
    return dist.replace("-", "_")


def _load_optional_dep_names() -> set[str]:
    """Return importable names for all optional deps (excluding always-installed groups)."""
    text = PYPROJECT.read_text(encoding="utf-8")

    import_names: set[str] = set()
    current_group: str | None = None
    in_optional = False

    for line in text.splitlines():
        stripped = line.strip()

        if stripped == "[project.optional-dependencies]":
            in_optional = True
            continue

        if (
            in_optional
            and stripped.startswith("[")
            and stripped != "[project.optional-dependencies]"
        ):
            if not stripped.startswith("[project.optional-dependencies"):
                in_optional = False
            continue

        if not in_optional:
            continue

        # Detect group header: "group-name = ["
        group_match = re.match(r"^(\w+)\s*=\s*\[", stripped)
        if group_match:
            current_group = group_match.group(1)
            continue

        if current_group is None or current_group in _OPTIONAL_GROUP_EXCLUDES:
            continue

        # Extract package name from requirement string, e.g. "rank-bm25>=0.2.0"
        pkg_match = re.match(r'"([A-Za-z0-9_.[\]-]+)', stripped)
        if pkg_match:
            raw = pkg_match.group(1)
            # Strip markers like "; platform_system == 'Darwin'"
            raw = raw.split(";")[0].strip()
            # Strip version specifiers
            base = re.split(r"[>=<!~\[]", raw)[0].strip()
            if base:
                import_names.add(_dist_to_import_name(base))

    return import_names


def _has_importorskip(tree: ast.Module) -> bool:
    """Return True if any ``pytest.importorskip(...)`` call exists anywhere in the file."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        # pytest.importorskip(...)
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "importorskip"
            and isinstance(func.value, ast.Name)
            and func.value.id == "pytest"
        ):
            return True
        # importorskip(...) — from pytest import importorskip
        if isinstance(func, ast.Name) and func.id == "importorskip":
            return True
    return False


def _find_unguarded_optional_imports(
    source: str,
    optional_deps: set[str],
    path: str = "<string>",
) -> list[str]:
    """Return ``file:line: module`` for top-level optional-dep imports with no importorskip guard.

    Only checks module-level (depth-0) import statements — imports inside functions or
    class bodies are already guarded by their enclosing scope.
    """
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError:
        return []

    if _has_importorskip(tree):
        return []

    violations: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                root_module = alias.name.split(".")[0]
                if root_module in optional_deps:
                    violations.append(f"{path}:{node.lineno}: {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                root_module = node.module.split(".")[0]
                if root_module in optional_deps:
                    violations.append(f"{path}:{node.lineno}: {node.module}")

    return violations


def _git_changed_test_files() -> list[Path]:
    """Return test files modified relative to main (diff-based subset)."""
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
        and "ci" not in p.parts
        and p.name != "conftest.py"
        and str(p.relative_to(FO_ROOT)) in changed
    )


# -------------------------------------------------------------------------
# Self-tests: verify detector logic before running enforcement
# -------------------------------------------------------------------------

_OPTIONAL_DEPS_FIXTURE = {"rank_bm25", "sklearn", "fitz"}


@pytest.mark.parametrize(
    ("source", "expected_violations"),
    [
        # Top-level import without guard — should flag
        ("import rank_bm25\n\ndef test_foo(): pass\n", 1),
        ("from rank_bm25 import BM25Okapi\n\ndef test_foo(): pass\n", 1),
        (
            "from sklearn.feature_extraction.text import TfidfVectorizer\n\ndef test_foo(): pass\n",
            1,
        ),
        # importorskip present anywhere — should NOT flag
        (
            "import pytest\nimport rank_bm25\n\nclass TestBM25:\n"
            "    @pytest.fixture(autouse=True)\n"
            "    def _guard(self):\n"
            "        pytest.importorskip('rank_bm25')\n",
            0,
        ),
        (
            "import pytest\nfrom pytest import importorskip\n"
            "importorskip('rank_bm25')\nimport rank_bm25\n",
            0,
        ),
        # Standard library / always-installed dep — should NOT flag
        ("import os\nimport json\ndef test_foo(): pass\n", 0),
        ("import pytest\ndef test_foo(): pass\n", 0),
        # Import inside a function — should NOT flag (not module-level)
        (
            "def test_foo():\n    import rank_bm25\n    pass\n",
            0,
        ),
    ],
)
def test_detector_parametrized(source: str, expected_violations: int) -> None:
    violations = _find_unguarded_optional_imports(source, _OPTIONAL_DEPS_FIXTURE)
    assert len(violations) == expected_violations, (
        f"Expected {expected_violations} violations, got {len(violations)}:\n"
        + "\n".join(violations)
    )


# -------------------------------------------------------------------------
# Enforcement: changed test files must guard optional-dep imports
# -------------------------------------------------------------------------


def test_test_files_guard_optional_deps() -> None:
    """Changed test files must use ``pytest.importorskip`` when importing optional packages.

    A module-level ``import rank_bm25`` or ``from sklearn import ...`` crashes the entire
    test file at collection time when the package is absent.  The correct pattern is a
    class-level autouse fixture:

    .. code-block:: python

        class TestBM25Search:
            @pytest.fixture(autouse=True)
            def _require_rank_bm25(self) -> None:
                pytest.importorskip("rank_bm25")

    Applies to changed files only (diff-scoped until full-suite cleanup is complete).
    """
    optional_deps = _load_optional_dep_names()
    if not optional_deps:
        pytest.skip("No optional deps found in pyproject.toml — check parser logic")

    violations: list[str] = []
    for path in _git_changed_test_files():
        source = path.read_text(encoding="utf-8")
        violations.extend(_find_unguarded_optional_imports(source, optional_deps, str(path)))

    assert not violations, (
        "Optional-dep imports without pytest.importorskip guard found in changed tests.\n"
        "Add a class-level autouse fixture: pytest.importorskip('<package>')\n"
        + "\n".join(violations)
    )
