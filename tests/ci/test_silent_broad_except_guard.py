"""Guardrail for broad exception handlers that silently swallow failures.

Issue #822 requires non-fatal broad catches to keep diagnostics visible.
"""

from __future__ import annotations

import ast
import textwrap
from pathlib import Path

import pytest

FO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = FO_ROOT / "src" / "file_organizer"

pytestmark = pytest.mark.ci


def _is_broad_exception(exc_type: ast.expr | None) -> bool:
    """Return whether the exception type is broad enough to hide real failures."""
    if exc_type is None:
        return True
    if isinstance(exc_type, ast.Name):
        return exc_type.id in {"Exception", "BaseException"}
    if isinstance(exc_type, ast.Tuple):
        return any(_is_broad_exception(item) for item in exc_type.elts)
    return False


def _is_silent_statement(statement: ast.stmt) -> bool:
    """Return whether a statement suppresses errors without breadcrumbs."""
    if isinstance(statement, ast.Pass):
        return True
    if isinstance(statement, (ast.Break, ast.Continue)):
        return True
    if isinstance(statement, ast.Return) and statement.value is None:
        return True
    return False


def _find_silent_broad_except_handlers(source: str, path: str = "<string>") -> list[str]:
    """Return broad exception handlers that resolve to silent no-op bodies."""
    tree = ast.parse(textwrap.dedent(source), filename=path)
    violations: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        if not _is_broad_exception(node.type):
            continue
        if node.body and all(_is_silent_statement(statement) for statement in node.body):
            violations.append(f"{path}:{node.lineno}")

    return violations


@pytest.mark.parametrize(
    "source",
    [
        """
try:
    run()
except Exception:
    pass
""",
        """
try:
    run()
except BaseException:
    pass
""",
        """
for _ in range(1):
    try:
        run()
    except Exception:
        continue
""",
        """
try:
    run()
except:
    pass
""",
    ],
)
def test_guard_detects_silent_broad_exception_handlers(source: str) -> None:
    assert len(_find_silent_broad_except_handlers(source)) == 1


@pytest.mark.parametrize(
    "source",
    [
        """
import logging
logger = logging.getLogger(__name__)

try:
    run()
except Exception:
    logger.debug("retrying", exc_info=True)
""",
        """
try:
    run()
except ValueError:
    pass
""",
        """
try:
    run()
except Exception:
    recover()
""",
    ],
)
def test_guard_allows_visible_or_narrow_handlers(source: str) -> None:
    assert _find_silent_broad_except_handlers(source) == []


def test_repository_has_no_silent_broad_exception_handlers() -> None:
    violations: list[str] = []
    for path in SRC_ROOT.rglob("*.py"):
        violations.extend(
            _find_silent_broad_except_handlers(path.read_text(encoding="utf-8"), str(path))
        )

    assert not violations, (
        "Broad exception handlers must not silently swallow failures:\n" + "\n".join(violations)
    )
