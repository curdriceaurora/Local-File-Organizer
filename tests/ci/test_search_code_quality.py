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


def _func_source_lines(func: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    """Return the source lines of a function node (best-effort via ast.unparse)."""
    try:
        return ast.unparse(func).splitlines()
    except Exception:
        return []


def _find_unguarded_traversals(path: Path) -> list[str]:
    """Return ``file:line: name`` for functions that traverse files without S1/S2 guards.

    A function is flagged if it:
    - calls ``.rglob(...)`` or ``os.walk(...)`` (file traversal), AND
    - does NOT contain ``is_symlink()`` anywhere in its body (S1 missing), OR
    - does NOT contain a hidden-file check (``startswith(".")`` or ``"."`` prefix
      check against a path part) anywhere in its body (S2 missing).
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

        unparsed = ast.unparse(node)

        # Does the function traverse files?
        has_rglob = ".rglob(" in unparsed
        has_walk = "os.walk(" in unparsed or "walk(" in unparsed
        if not (has_rglob or has_walk):
            continue

        # S1: must contain symlink check
        has_symlink_check = "is_symlink()" in unparsed

        # S2: must contain hidden-file check
        has_hidden_check = 'startswith(".")' in unparsed or "startswith('.')" in unparsed

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
