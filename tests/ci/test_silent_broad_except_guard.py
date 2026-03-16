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
_TRACEBACK_LOGGING_ENFORCED_PATHS = {
    "src/file_organizer/api/routers/realtime.py",
    "src/file_organizer/cli/autotag_v2.py",
    "src/file_organizer/cli/benchmark.py",
    "src/file_organizer/plugins/executor.py",
    "src/file_organizer/services/deduplication/backup.py",
    "src/file_organizer/tui/analytics_view.py",
    "src/file_organizer/tui/audio_view.py",
    "src/file_organizer/tui/copilot_view.py",
    "src/file_organizer/tui/file_preview.py",
    "src/file_organizer/tui/methodology_view.py",
    "src/file_organizer/tui/organization_preview.py",
    "src/file_organizer/tui/undo_history_view.py",
    "src/file_organizer/utils/readers/cad.py",
}

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
    if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant):
        if statement.value.value is Ellipsis:
            return True
        if isinstance(statement.value.value, (str, bytes)):
            return True
    return False


def _is_logging_call(node: ast.Call) -> bool:
    """Return whether a call targets a common logger method."""
    return isinstance(node.func, ast.Attribute) and node.func.attr in {
        "debug",
        "info",
        "warning",
        "error",
        "critical",
        "exception",
    }


def _is_logging_statement(statement: ast.stmt) -> bool:
    """Return whether a statement is a direct logging call expression."""
    return (
        isinstance(statement, ast.Expr)
        and isinstance(statement.value, ast.Call)
        and _is_logging_call(statement.value)
    )


def _keyword_is_truthy(keyword: ast.keyword) -> bool:
    """Return whether a logging keyword argument should be treated as truthy."""
    value = keyword.value
    if isinstance(value, ast.Constant):
        return bool(value.value)
    return True


def _preserves_traceback_context(call: ast.Call) -> bool:
    """Return whether a logging call preserves traceback context."""
    if isinstance(call.func, ast.Attribute) and call.func.attr == "exception":
        return True
    if any(keyword.arg == "exc_info" and _keyword_is_truthy(keyword) for keyword in call.keywords):
        return True

    # Support loguru-style logger.opt(exception=True).<level>(...)
    if (
        isinstance(call.func, ast.Attribute)
        and isinstance(call.func.value, ast.Call)
        and isinstance(call.func.value.func, ast.Attribute)
        and call.func.value.func.attr == "opt"
    ):
        return any(
            keyword.arg == "exception" and _keyword_is_truthy(keyword)
            for keyword in call.func.value.keywords
        )

    return False


def _find_silent_broad_except_handlers(
    source: str,
    path: str = "<string>",
    *,
    enforce_traceback_logging: bool = True,
) -> list[str]:
    """Return broad exception handlers that suppress diagnostics.

    The guard enforces two regression classes:
    - silent no-op broad handlers (pass/break/continue/return None)
    - logging-only broad handlers that do not preserve traceback context
    """
    tree = ast.parse(textwrap.dedent(source), filename=path)
    violations: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        if not _is_broad_exception(node.type):
            continue
        if node.body and all(_is_silent_statement(statement) for statement in node.body):
            violations.append(f"{path}:{node.lineno}")
            continue

        logging_calls = [
            statement.value
            for statement in node.body
            if isinstance(statement, ast.Expr)
            and isinstance(statement.value, ast.Call)
            and _is_logging_call(statement.value)
        ]
        non_silent_statements = [
            statement for statement in node.body if not _is_silent_statement(statement)
        ]
        if (
            enforce_traceback_logging
            and logging_calls
            and non_silent_statements
            and all(_is_logging_statement(statement) for statement in non_silent_statements)
            and not any(_preserves_traceback_context(call) for call in logging_calls)
        ):
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
        """
import logging
logger = logging.getLogger(__name__)

try:
    run()
except Exception:
    logger.debug("recovering")
""",
        """
try:
    run()
except Exception:
    ...
""",
        """
try:
    run()
except Exception:
    "ignored"
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
        relative_path = path.relative_to(FO_ROOT).as_posix()
        violations.extend(
            _find_silent_broad_except_handlers(
                path.read_text(encoding="utf-8"),
                str(path),
                enforce_traceback_logging=relative_path in _TRACEBACK_LOGGING_ENFORCED_PATHS,
            )
        )

    assert not violations, (
        "Broad exception handlers must not silently swallow failures:\n" + "\n".join(violations)
    )
