"""Guardrails for stdlib logging that must preserve traceback context.

Approved patterns in exception handlers:
- ``logger.exception(...)``
- ``logger.warning/error/critical(..., exc_info=True)``

Disallowed high-confidence pattern:
- caught exception object passed to stdlib ``logger.warning/error/critical``
  without ``exc_info=True``
"""

from __future__ import annotations

import ast
import textwrap
from pathlib import Path

import pytest

FO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = FO_ROOT / "src"
ORCHESTRATOR_PATH = SRC_ROOT / "file_organizer" / "pipeline" / "orchestrator.py"

pytestmark = pytest.mark.ci

_GUARDED_METHODS = {"warning", "error", "critical"}


def _stdlib_logging_names(tree: ast.AST) -> tuple[set[str], set[str]]:
    """Return imported logging module aliases and getLogger callables."""
    logging_modules: set[str] = set()
    get_logger_names: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "logging":
                    logging_modules.add(alias.asname or "logging")
        elif isinstance(node, ast.ImportFrom) and node.module == "logging":
            for alias in node.names:
                if alias.name == "getLogger":
                    get_logger_names.add(alias.asname or "getLogger")

    return logging_modules, get_logger_names


def _stdlib_logger_names(tree: ast.AST) -> set[str]:
    """Return local names bound from stdlib ``logging.getLogger(...)`` calls."""
    logging_modules, get_logger_names = _stdlib_logging_names(tree)
    logger_names: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            value = node.value
            if not isinstance(value, ast.Call):
                continue

            func = value.func
            is_stdlib_get_logger = False
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                is_stdlib_get_logger = func.attr == "getLogger" and func.value.id in logging_modules
            elif isinstance(func, ast.Name):
                is_stdlib_get_logger = func.id in get_logger_names

            if not is_stdlib_get_logger:
                continue

            targets: list[ast.expr]
            if isinstance(node, ast.Assign):
                targets = node.targets
            else:
                targets = [node.target]

            for target in targets:
                if isinstance(target, ast.Name):
                    logger_names.add(target.id)

    return logger_names


def _uses_exception_arg(call: ast.Call, exception_name: str) -> bool:
    """Return whether the call passes the caught exception as a logger argument."""
    return any(isinstance(arg, ast.Name) and arg.id == exception_name for arg in call.args[1:])


def _has_exc_info(call: ast.Call) -> bool:
    """Return whether the call preserves traceback context."""
    for keyword in call.keywords:
        if keyword.arg != "exc_info":
            continue
        if isinstance(keyword.value, ast.Constant) and not bool(keyword.value.value):
            return False
        return True
    return False


def _find_missing_traceback_logging(source: str, path: str = "<string>") -> list[str]:
    """Return stdlib logging calls that drop traceback context in except blocks."""
    source = textwrap.dedent(source)
    tree = ast.parse(source, filename=path)
    logger_names = _stdlib_logger_names(tree)
    violations: list[str] = []

    class Visitor(ast.NodeVisitor):
        def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
            exception_name = node.name if isinstance(node.name, str) else None
            if not exception_name:
                self.generic_visit(node)
                return

            scoped_body = ast.Module(body=node.body, type_ignores=[])
            for child in ast.walk(scoped_body):
                if not isinstance(child, ast.Call):
                    continue
                if not isinstance(child.func, ast.Attribute):
                    continue
                if not isinstance(child.func.value, ast.Name):
                    continue
                if child.func.value.id not in logger_names:
                    continue
                if child.func.attr not in _GUARDED_METHODS:
                    continue
                if _has_exc_info(child):
                    continue
                if _uses_exception_arg(child, exception_name):
                    violations.append(f"{path}:{child.lineno}")

            self.generic_visit(node)

    Visitor().visit(tree)
    return violations


@pytest.mark.parametrize(
    "source",
    [
        """
import logging
logger = logging.getLogger(__name__)

try:
    work()
except Exception as exc:
    logger.warning("failed: %s", exc)
""",
        """
import logging
logger = logging.getLogger(__name__)

try:
    work()
except RuntimeError as exc:
    logger.error("job %s failed: %s", job_id, exc)
""",
        """
import logging
logger = logging.getLogger(__name__)

try:
    work()
except RuntimeError as exc:
    logger.error("job %s failed: %s", job_id, exc, exc_info=0)
""",
        """
import logging
logger = logging.getLogger(__name__)

try:
    work()
except RuntimeError as exc:
    logger.error("job %s failed: %s", job_id, exc, exc_info=None)
""",
        """
from logging import getLogger
logger = getLogger(__name__)

try:
    work()
except ValueError as exc:
    logger.critical("%s", exc)
""",
    ],
)
def test_traceback_guard_finds_missing_exc_info(source: str) -> None:
    violations = _find_missing_traceback_logging(source)
    assert len(violations) == 1


@pytest.mark.parametrize(
    "source",
    [
        """
import logging
logger = logging.getLogger(__name__)

try:
    work()
except Exception:
    logger.exception("failed")
""",
        """
import logging
logger = logging.getLogger(__name__)

try:
    work()
except Exception as exc:
    logger.warning("failed: %s", exc, exc_info=True)
""",
        """
import logging
logger = logging.getLogger(__name__)

try:
    work()
except Exception as exc:
    logger.warning("retrying later")
""",
    ],
)
def test_traceback_guard_allows_compliant_logging(source: str) -> None:
    assert _find_missing_traceback_logging(source) == []


def test_repository_has_no_missing_traceback_logging() -> None:
    violations: list[str] = []
    for path in SRC_ROOT.rglob("*.py"):
        violations.extend(
            _find_missing_traceback_logging(path.read_text(encoding="utf-8"), str(path))
        )
    assert not violations, "Caught exceptions logged without traceback preservation:\n" + "\n".join(
        violations
    )


def test_orchestrator_prefetch_failure_logs_with_exc_info() -> None:
    source = ORCHESTRATOR_PATH.read_text(encoding="utf-8")
    assert _find_missing_traceback_logging(source, str(ORCHESTRATOR_PATH)) == []
