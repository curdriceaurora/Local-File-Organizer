"""CI guardrails for src/file_organizer/services/search/.

BLE001 equivalent: any broad except Exception/BaseException handler inside the
search service is flagged, not just silent ones.  This is stricter than the
project-wide silent-broad-except guard and mirrors the Ruff BLE001 rule applied
locally where search correctness is critical.

Search corpus safety (S1/S2): any function in the search service that calls
``rglob()`` or ``os.walk()`` must contain both a symlink filter (``is_symlink()``)
and a hidden-file filter (check against a name starting with ``"."``).  This
prevents symlink traversal and accidental indexing of ``.git``, ``.env``, etc.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

FO_ROOT = Path(__file__).resolve().parents[2]
SEARCH_SRC = FO_ROOT / "src" / "file_organizer" / "services" / "search"

pytestmark = pytest.mark.ci

_BROAD_EXCEPTION_NAMES = {"Exception", "BaseException"}


def _is_broad_handler(handler: ast.ExceptHandler) -> bool:
    """Return True for bare ``except:`` or ``except Exception/BaseException:``."""
    if handler.type is None:
        return True  # bare except:
    if isinstance(handler.type, ast.Name):
        return handler.type.id in _BROAD_EXCEPTION_NAMES
    if isinstance(handler.type, ast.Tuple):
        return any(
            isinstance(elt, ast.Name) and elt.id in _BROAD_EXCEPTION_NAMES
            for elt in handler.type.elts
        )
    return False


def _find_broad_except_handlers(path: Path) -> list[str]:
    """Return ``file:line`` strings for any broad except handler in *path*."""
    source = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return []

    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and _is_broad_handler(node):
            violations.append(f"{path}:{node.lineno}")
    return violations


def test_search_service_has_no_broad_except_handlers() -> None:
    """Search service must use specific exception types (BLE001 equivalent).

    Broad ``except Exception`` handlers mask unexpected errors and make
    debugging search regressions significantly harder.  Use specific types
    such as ``sqlite3.Error``, ``ValueError``, or ``OSError`` instead.
    """
    assert SEARCH_SRC.exists(), (
        f"Search service directory not found: {SEARCH_SRC}\n"
        "This indicates a misconfigured test environment or incorrect path constant."
    )

    violations: list[str] = []
    for path in SEARCH_SRC.rglob("*.py"):
        violations.extend(_find_broad_except_handlers(path))

    assert not violations, (
        "Search service must not use broad except Exception/BaseException handlers "
        "(BLE001 equivalent — use specific exception types):\n" + "\n".join(violations)
    )


# -------------------------------------------------------------------------
# S1/S2: rglob / os.walk calls must filter symlinks and hidden files
# -------------------------------------------------------------------------


def _find_unguarded_traversals(path: Path) -> list[str]:
    """Return ``file:line: name`` for functions that traverse files without S1/S2 guards.

    A function is flagged if it:
    - calls ``.rglob(...)`` or ``os.walk(...)`` (file traversal), AND
    - does NOT call ``is_symlink()`` anywhere in its body (S1 missing), OR
    - does NOT call ``startswith(".")`` anywhere in its body (S2 missing).

    Detection uses AST call-node matching, not string matching, so docstrings
    and comments cannot produce false positives or false negatives.
    """
    source = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return []

    violations: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        # Collect calls from this function's own body only — do not descend into
        # nested functions/classes so inner-scope guards cannot satisfy outer checks.
        calls = [n for child in node.body for n in ast.walk(child) if isinstance(n, ast.Call)]

        # Does the function traverse files? (rglob or os.walk only — not bare walk())
        has_rglob = any(isinstance(c.func, ast.Attribute) and c.func.attr == "rglob" for c in calls)
        has_walk = any(
            isinstance(c.func, ast.Attribute)
            and c.func.attr == "walk"
            and isinstance(c.func.value, ast.Name)
            and c.func.value.id == "os"
            for c in calls
        )
        if not (has_rglob or has_walk):
            continue

        # S1: must call .is_symlink()
        has_symlink_check = any(
            isinstance(c.func, ast.Attribute) and c.func.attr == "is_symlink" for c in calls
        )

        # S2: must call .startswith(".") with a literal "." argument
        has_hidden_check = any(
            isinstance(c.func, ast.Attribute)
            and c.func.attr == "startswith"
            and len(c.args) >= 1
            and isinstance(c.args[0], ast.Constant)
            and c.args[0].value == "."
            for c in calls
        )

        missing: list[str] = []
        if not has_symlink_check:
            missing.append("S1:symlink-filter(is_symlink())")
        if not has_hidden_check:
            missing.append('S2:hidden-file-filter(startswith("."))')

        if missing:
            violations.append(f"{path}:{node.lineno}: {node.name} — missing {', '.join(missing)}")
    return violations


def test_search_service_rglob_filters_symlinks_and_hidden() -> None:
    """File traversal in search service must guard against symlinks and hidden files (S1/S2).

    Any function that calls ``.rglob()`` or ``os.walk()`` must:
    - Filter symlinks via ``if p.is_symlink(): continue`` (prevents traversal into
      untrusted targets such as ``/etc/passwd`` or ``~/.ssh/``).
    - Filter hidden files/dirs via a ``startswith(".")`` check (prevents indexing
      ``.git``, ``.env``, ``.ssh/authorized_keys``, etc.).

    See ``.claude/rules/search-generation-patterns.md`` patterns S1 and S2.
    """
    assert SEARCH_SRC.exists(), (
        f"Search service directory not found: {SEARCH_SRC}\n"
        "This indicates a misconfigured test environment or incorrect path constant."
    )

    violations: list[str] = []
    for path in SEARCH_SRC.rglob("*.py"):
        violations.extend(_find_unguarded_traversals(path))

    assert not violations, (
        "Search service file traversal missing S1/S2 safety guards — add "
        "is_symlink() and startswith('.') filters before indexing:\n" + "\n".join(violations)
    )
