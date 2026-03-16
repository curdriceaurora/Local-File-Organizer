"""CI guardrails for src/file_organizer/services/search/.

BLE001 equivalent: any broad except Exception/BaseException handler inside the
search service is flagged, not just silent ones.  This is stricter than the
project-wide silent-broad-except guard and mirrors the Ruff BLE001 rule applied
locally where search correctness is critical.
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
