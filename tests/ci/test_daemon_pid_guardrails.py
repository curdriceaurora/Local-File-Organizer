"""CI guardrails for daemon PID lifecycle contracts."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.ci

FO_ROOT = Path(__file__).resolve().parents[2]
PID_MODULE = FO_ROOT / "src" / "file_organizer" / "daemon" / "pid.py"
SERVICE_MODULE = FO_ROOT / "src" / "file_organizer" / "daemon" / "service.py"


def _method_node(path: Path, class_name: str, method_name: str) -> ast.FunctionDef:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != class_name:
            continue
        for item in node.body:
            if isinstance(item, ast.FunctionDef) and item.name == method_name:
                return item
    raise AssertionError(f"Missing {class_name}.{method_name} in {path}")


def _is_name(node: ast.AST, name: str) -> bool:
    return isinstance(node, ast.Name) and node.id == name


def _is_attr(node: ast.AST, base: str, attr: str) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == base
        and node.attr == attr
    )


def _iter_calls(node: ast.AST) -> list[ast.Call]:
    return [item for item in ast.walk(node) if isinstance(item, ast.Call)]


def _flag_members(expr: ast.AST) -> set[str]:
    if isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.BitOr):
        return _flag_members(expr.left) | _flag_members(expr.right)
    if (
        isinstance(expr, ast.Attribute)
        and isinstance(expr.value, ast.Name)
        and expr.value.id == "os"
    ):
        return {expr.attr}
    return set()


def test_pid_record_write_includes_creation_time() -> None:
    method = _method_node(PID_MODULE, "PidFileManager", "write_pid_record")

    has_create_time_assignment = any(
        isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and _is_name(node.targets[0], "create_time")
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Attribute)
        and node.value.func.attr == "create_time"
        and isinstance(node.value.func.value, ast.Call)
        and _is_attr(node.value.func.value.func, "psutil", "Process")
        and len(node.value.func.value.args) == 1
        and _is_name(node.value.func.value.args[0], "pid")
        for node in ast.walk(method)
    )
    assert has_create_time_assignment

    has_json_payload = any(
        _is_attr(call.func, "json", "dumps")
        and call.args
        and isinstance(call.args[0], ast.Dict)
        and {"pid", "create_time"}
        <= {
            key.value
            for key in call.args[0].keys
            if isinstance(key, ast.Constant) and isinstance(key.value, str)
        }
        for call in _iter_calls(method)
    )
    assert has_json_payload


def test_pid_removal_revalidates_expected_record_before_unlink() -> None:
    method = _method_node(PID_MODULE, "PidFileManager", "remove_pid")

    has_read_before_compare = any(
        isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and _is_name(node.targets[0], "current_record")
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Attribute)
        and _is_name(node.value.func.value, "self")
        and node.value.func.attr == "read_pid_record"
        and len(node.value.args) == 1
        and _is_name(node.value.args[0], "pid_file")
        for node in ast.walk(method)
    )
    assert has_read_before_compare

    has_mismatch_guard = any(
        isinstance(node, ast.If)
        and isinstance(node.test, ast.Compare)
        and len(node.test.ops) == 1
        and isinstance(node.test.ops[0], ast.NotEq)
        and _is_name(node.test.left, "current_record")
        and len(node.test.comparators) == 1
        and _is_name(node.test.comparators[0], "expected_record")
        for node in ast.walk(method)
    )
    assert has_mismatch_guard

    has_unlink_call = any(
        isinstance(call.func, ast.Attribute)
        and _is_name(call.func.value, "pid_file")
        and call.func.attr == "unlink"
        for call in _iter_calls(method)
    )
    assert has_unlink_call


def test_pid_claim_uses_atomic_exclusive_create() -> None:
    method = _method_node(PID_MODULE, "PidFileManager", "claim_pid_file")

    open_calls = [
        call
        for call in _iter_calls(method)
        if isinstance(call.func, ast.Attribute)
        and _is_name(call.func.value, "os")
        and call.func.attr == "open"
    ]
    assert open_calls
    assert any(
        len(call.args) >= 2 and {"O_CREAT", "O_EXCL", "O_WRONLY"} <= _flag_members(call.args[1])
        for call in open_calls
    )

    has_cleanup_unlink = any(
        isinstance(call.func, ast.Attribute)
        and _is_name(call.func.value, "pid_file")
        and call.func.attr == "unlink"
        for call in _iter_calls(method)
    )
    assert has_cleanup_unlink


def test_background_startup_failures_propagate_to_callers() -> None:
    method = _method_node(SERVICE_MODULE, "DaemonService", "start_background")

    has_reset_start_exception = any(
        isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Attribute)
        and _is_name(node.targets[0].value, "self")
        and node.targets[0].attr == "_start_exception"
        and isinstance(node.value, ast.Constant)
        and node.value.value is None
        for node in ast.walk(method)
    )
    assert has_reset_start_exception

    has_runtime_reraise = any(
        isinstance(node, ast.Raise)
        and isinstance(node.exc, ast.Call)
        and _is_name(node.exc.func, "RuntimeError")
        and node.exc.args
        and isinstance(node.exc.args[0], ast.Constant)
        and node.exc.args[0].value == "Daemon failed to start"
        and isinstance(node.cause, ast.Name)
        and node.cause.id == "exc"
        for node in ast.walk(method)
    )
    assert has_runtime_reraise
