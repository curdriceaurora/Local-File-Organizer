"""Guardrails based on recent PR review learnings."""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

FO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = FO_ROOT / "src"
API_ROUTER_ROOT = SRC_ROOT / "file_organizer" / "api" / "routers"
TESTS_ROOT = FO_ROOT / "tests"

pytestmark = pytest.mark.ci

_LOGURU_METHODS = {
    "debug",
    "info",
    "warning",
    "error",
    "exception",
    "critical",
}


def _imports_loguru(source: str) -> bool:
    return "loguru" in source and "logger" in source


def _find_loguru_percent_formatting(path: Path) -> list[str]:
    """Return list of messages that use % formatting with loguru logger."""
    source = path.read_text(encoding="utf-8")
    if not _imports_loguru(source):
        return []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    violations: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            if func.value.id != "logger" or func.attr not in _LOGURU_METHODS:
                continue
        else:
            continue

        if not node.args:
            continue
        first = node.args[0]
        if not isinstance(first, ast.Constant) or not isinstance(first.value, str):
            continue
        message = first.value
        if "%" in message and len(node.args) > 1:
            if re.search(r"%[sd]\b", message):
                violations.append(f"{path}: {message}")
    return violations


def test_loguru_formatting_uses_braces() -> None:
    violations: list[str] = []
    for path in SRC_ROOT.rglob("*.py"):
        violations.extend(_find_loguru_percent_formatting(path))
    assert not violations, "Loguru format strings should use '{}' placeholders:\n" + "\n".join(
        violations
    )


def test_api_routers_do_not_call_get_settings_directly() -> None:
    offenders = []
    for path in API_ROUTER_ROOT.glob("*.py"):
        if path.name == "__init__.py":
            continue
        content = path.read_text(encoding="utf-8")
        if "get_settings()" in content:
            offenders.append(str(path))
    assert not offenders, (
        "Routers should use Depends(get_settings) instead of direct calls:\n" + "\n".join(offenders)
    )


def test_api_tests_marked_ci() -> None:
    offenders = []
    for path in TESTS_ROOT.glob("test_api_*.py"):
        content = path.read_text(encoding="utf-8")
        if "pytestmark = pytest.mark.ci" not in content:
            offenders.append(str(path))
    assert not offenders, "API tests must include pytestmark = pytest.mark.ci:\n" + "\n".join(
        offenders
    )
