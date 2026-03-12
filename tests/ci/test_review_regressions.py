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


# ---------------------------------------------------------------------------
# Regression: StageContext validated-setter bypass (PR #749)
# __post_init__ only runs at construction; stages that assign context.category
# or context.filename AFTER construction bypassed the path-traversal guard
# until __setattr__ was added.  These tests catch any reversion.
# ---------------------------------------------------------------------------


def test_stage_context_assignment_enforces_path_traversal_guard() -> None:
    """Direct field assignment must go through __setattr__ validation, not just __post_init__."""
    from pathlib import Path

    from file_organizer.interfaces.pipeline import StageContext

    ctx = StageContext(file_path=Path("input/file.txt"))

    # Post-construction assignments must also validate
    with pytest.raises(ValueError, match="Invalid category"):
        ctx.category = "../etc/passwd"

    with pytest.raises(ValueError, match="Invalid filename"):
        ctx.filename = "/absolute/path"

    with pytest.raises(ValueError, match="Invalid category"):
        ctx.category = "safe\\escape"

    # Valid assignments must succeed
    ctx.category = "Documents"
    ctx.filename = "my_report"
    assert ctx.category == "Documents"
    assert ctx.filename == "my_report"


def test_no_object_setattr_bypass_in_source() -> None:
    """No source file should bypass StageContext validation via object.__setattr__."""
    pattern = re.compile(
        r"object\.__setattr__\s*\(.*StageContext|object\.__setattr__\s*\(\s*context"
    )
    violations: list[str] = []
    for path in SRC_ROOT.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        if pattern.search(source):
            violations.append(str(path))
    assert not violations, (
        "object.__setattr__ bypass found — StageContext mutations must go through "
        "__setattr__ to enforce path-traversal validation:\n" + "\n".join(violations)
    )


# ---------------------------------------------------------------------------
# Regression: ModelManager._active_models storing model IDs (PR #749)
# When model_factory=None, old code stored new_model_id (a str) into
# _active_models so get_active_model() returned a str instead of an instance.
# ---------------------------------------------------------------------------


def test_get_active_model_never_returns_primitive() -> None:
    """get_active_model() must never return a str/int/float — only instances or None."""
    from file_organizer.models.model_manager import ModelManager

    mgr = ModelManager()
    # Factory-less swap records the ID but must NOT store a str in _active_models
    mgr.swap_model("text", "some-model-id")
    result = mgr.get_active_model("text")
    assert result is None or not isinstance(result, (str, int, float)), (
        f"get_active_model() returned a primitive ({result!r}); "
        "_active_models must only hold model instances"
    )
