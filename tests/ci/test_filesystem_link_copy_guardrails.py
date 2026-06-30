"""CI guardrails for filesystem link/copy/move race safety."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.ci

FO_ROOT = Path(__file__).resolve().parents[2]
ACTIONS_MODULE = (
    FO_ROOT / "src" / "file_organizer" / "services" / "copilot" / "rules" / "actions.py"
)
EXECUTOR_MODULE = (
    FO_ROOT / "src" / "file_organizer" / "services" / "copilot" / "rules" / "executor.py"
)
ROLLBACK_MODULE = FO_ROOT / "src" / "file_organizer" / "undo" / "rollback.py"
DURABLE_MOVE_MODULE = FO_ROOT / "src" / "file_organizer" / "undo" / "durable_move.py"


def _method_node(path: Path, method_name: str, *, class_name: str | None = None) -> ast.FunctionDef:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if class_name is None and isinstance(node, ast.FunctionDef) and node.name == method_name:
            return node
        if class_name is not None and isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == method_name:
                    return item
    raise AssertionError(f"Missing {method_name} in {path}")


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


def test_resolve_conflict_rechecks_symlink_and_directory_state_before_unlink() -> None:
    method = _method_node(ACTIONS_MODULE, "resolve_conflict")

    has_exists_and_symlink_guard = any(
        isinstance(node, ast.If)
        and isinstance(node.test, ast.BoolOp)
        and isinstance(node.test.op, ast.And)
        and len(node.test.values) == 2
        and all(
            isinstance(part, ast.UnaryOp) and isinstance(part.op, ast.Not)
            for part in node.test.values
        )
        and isinstance(node.test.values[0].operand, ast.Call)
        and isinstance(node.test.values[1].operand, ast.Call)
        and isinstance(node.test.values[0].operand.func, ast.Attribute)
        and isinstance(node.test.values[1].operand.func, ast.Attribute)
        and _is_name(node.test.values[0].operand.func.value, "path")
        and _is_name(node.test.values[1].operand.func.value, "path")
        and node.test.values[0].operand.func.attr == "exists"
        and node.test.values[1].operand.func.attr == "is_symlink"
        for node in ast.walk(method)
    )
    assert has_exists_and_symlink_guard

    has_dir_guard = any(
        isinstance(node, ast.If)
        and isinstance(node.test, ast.BoolOp)
        and isinstance(node.test.op, ast.And)
        and len(node.test.values) == 2
        and isinstance(node.test.values[0], ast.Call)
        and isinstance(node.test.values[0].func, ast.Attribute)
        and _is_name(node.test.values[0].func.value, "path")
        and node.test.values[0].func.attr == "is_dir"
        and isinstance(node.test.values[1], ast.UnaryOp)
        and isinstance(node.test.values[1].op, ast.Not)
        and isinstance(node.test.values[1].operand, ast.Call)
        and isinstance(node.test.values[1].operand.func, ast.Attribute)
        and _is_name(node.test.values[1].operand.func.value, "path")
        and node.test.values[1].operand.func.attr == "is_symlink"
        for node in ast.walk(method)
    )
    assert has_dir_guard

    has_unlink = any(
        isinstance(call.func, ast.Attribute)
        and _is_name(call.func.value, "path")
        and call.func.attr == "unlink"
        for call in _iter_calls(method)
    )
    assert has_unlink


def test_copy_file_reserves_destination_atomically() -> None:
    method = _method_node(ACTIONS_MODULE, "copy_file")

    has_safedir_root_open = any(
        isinstance(call.func, ast.Attribute)
        and isinstance(call.func.value, ast.Name)
        and call.func.value.id == "SafeDir"
        and call.func.attr == "open_root"
        and len(call.args) == 1
        and isinstance(call.args[0], ast.Attribute)
        and _is_name(call.args[0].value, "source")
        and call.args[0].attr == "parent"
        for call in _iter_calls(method)
    )
    assert has_safedir_root_open

    has_atomic_open_flags = any(
        isinstance(call.func, ast.Attribute)
        and _is_name(call.func.value, "os")
        and call.func.attr == "open"
        and len(call.args) >= 2
        and {"O_CREAT", "O_EXCL", "O_WRONLY"} <= _flag_members(call.args[1])
        for call in _iter_calls(method)
    )
    assert has_atomic_open_flags

    has_copyfileobj = any(
        _is_attr(call.func, "shutil", "copyfileobj")
        and len(call.args) == 2
        and _is_name(call.args[0], "src_file")
        and _is_name(call.args[1], "dst_file")
        for call in _iter_calls(method)
    )
    assert has_copyfileobj


def test_link_helpers_route_mutations_through_conflict_resolution() -> None:
    hardlink = _method_node(ACTIONS_MODULE, "apply_hardlink")
    symlink = _method_node(ACTIONS_MODULE, "apply_symlink")

    has_hardlink_conflict_routing = any(
        _is_name(call.func, "resolve_conflict")
        and len(call.args) == 2
        and _is_name(call.args[0], "destination")
        and _is_name(call.args[1], "strategy")
        for call in _iter_calls(hardlink)
    )
    assert has_hardlink_conflict_routing
    has_hardlink_call = any(
        _is_attr(call.func, "os", "link")
        and len(call.args) == 2
        and _is_name(call.args[0], "source")
        and _is_name(call.args[1], "resolved")
        for call in _iter_calls(hardlink)
    )
    assert has_hardlink_call

    has_symlink_conflict_routing = any(
        _is_name(call.func, "resolve_conflict")
        and len(call.args) == 2
        and _is_name(call.args[0], "destination")
        and _is_name(call.args[1], "strategy")
        for call in _iter_calls(symlink)
    )
    assert has_symlink_conflict_routing
    has_symlink_call = any(
        isinstance(call.func, ast.Attribute)
        and _is_name(call.func.value, "resolved")
        and call.func.attr == "symlink_to"
        and len(call.args) == 1
        and _is_name(call.args[0], "source")
        for call in _iter_calls(symlink)
    )
    assert has_symlink_call


def test_rule_executor_revalidates_destination_root_containment() -> None:
    method = _method_node(EXECUTOR_MODULE, "_target_path", class_name="RuleExecutor")

    has_absolute_guard = any(
        isinstance(node, ast.If)
        and isinstance(node.test, ast.Call)
        and isinstance(node.test.func, ast.Attribute)
        and _is_name(node.test.func.value, "raw")
        and node.test.func.attr == "is_absolute"
        and any(
            isinstance(stmt, ast.Raise)
            and isinstance(stmt.exc, ast.Call)
            and _is_name(stmt.exc.func, "ValueError")
            for stmt in node.body
        )
        for node in ast.walk(method)
    )
    assert has_absolute_guard

    has_relative_to_check = any(
        isinstance(call.func, ast.Attribute)
        and _is_name(call.func.value, "resolved_candidate")
        and call.func.attr == "relative_to"
        and len(call.args) == 1
        and _is_name(call.args[0], "resolved_base")
        for call in _iter_calls(method)
    )
    assert has_relative_to_check


def test_rollback_move_revalidates_identity_close_to_mutation() -> None:
    method = _method_node(ROLLBACK_MODULE, "_durable_move", class_name="RollbackExecutor")

    has_src_symlink_guard = any(
        _is_attr(call.func, "stat_mod", "S_ISLNK")
        and len(call.args) == 1
        and isinstance(call.args[0], ast.Attribute)
        and _is_name(call.args[0].value, "src_stat")
        and call.args[0].attr == "st_mode"
        for call in _iter_calls(method)
    )
    assert has_src_symlink_guard

    has_exdev_recheck = any(
        _is_attr(call.func, "stat_mod", "S_ISLNK")
        and len(call.args) == 1
        and isinstance(call.args[0], ast.Attribute)
        and call.args[0].attr == "st_mode"
        and isinstance(call.args[0].value, ast.Call)
        and _is_attr(call.args[0].value.func, "os", "lstat")
        and len(call.args[0].value.args) == 1
        and _is_name(call.args[0].value.args[0], "src")
        for call in _iter_calls(method)
    )
    assert has_exdev_recheck

    has_shutil_move = any(
        _is_attr(call.func, "shutil", "move")
        and len(call.args) == 2
        and isinstance(call.args[0], ast.Call)
        and isinstance(call.args[1], ast.Call)
        and _is_name(call.args[0].func, "str")
        and _is_name(call.args[1].func, "str")
        and len(call.args[0].args) == 1
        and len(call.args[1].args) == 1
        and _is_name(call.args[0].args[0], "src")
        and _is_name(call.args[1].args[0], "dst")
        for call in _iter_calls(method)
    )
    assert has_shutil_move

    has_inode_identity_compare = any(
        isinstance(node, ast.If)
        and isinstance(node.test, ast.BoolOp)
        and isinstance(node.test.op, ast.And)
        and len(node.test.values) == 2
        and isinstance(node.test.values[0], ast.UnaryOp)
        and isinstance(node.test.values[0].op, ast.Not)
        and _is_name(node.test.values[0].operand, "cross_device")
        and isinstance(node.test.values[1], ast.Compare)
        and len(node.test.values[1].ops) == 1
        and isinstance(node.test.values[1].ops[0], ast.NotEq)
        and isinstance(node.test.values[1].left, ast.Tuple)
        and len(node.test.values[1].left.elts) == 2
        and isinstance(node.test.values[1].left.elts[0], ast.Attribute)
        and isinstance(node.test.values[1].left.elts[1], ast.Attribute)
        and _is_name(node.test.values[1].left.elts[0].value, "dst_stat")
        and _is_name(node.test.values[1].left.elts[1].value, "dst_stat")
        and node.test.values[1].left.elts[0].attr == "st_dev"
        and node.test.values[1].left.elts[1].attr == "st_ino"
        and len(node.test.values[1].comparators) == 1
        and _is_name(node.test.values[1].comparators[0], "src_identity")
        for node in ast.walk(method)
    )
    assert has_inode_identity_compare


def test_durable_move_preserves_inode_identity_and_symlink_handling() -> None:
    method = _method_node(DURABLE_MOVE_MODULE, "_capture_dst_inode")

    has_lstat_call = any(
        _is_attr(call.func, "os", "lstat") and len(call.args) == 1 and _is_name(call.args[0], "dst")
        for call in _iter_calls(method)
    )
    assert has_lstat_call

    has_inode_return = any(
        isinstance(node, ast.Return)
        and isinstance(node.value, ast.Tuple)
        and len(node.value.elts) == 3
        and all(
            isinstance(elt, ast.Attribute) and _is_name(elt.value, "st") for elt in node.value.elts
        )
        and [elt.attr for elt in node.value.elts] == ["st_dev", "st_ino", "st_size"]
        for node in ast.walk(method)
    )
    assert has_inode_return
