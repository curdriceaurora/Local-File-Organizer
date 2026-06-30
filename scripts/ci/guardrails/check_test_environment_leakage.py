#!/usr/bin/env python3
"""CI-rail: Flag test environment mutations that can leak across tests.

This advisory rail catches direct mutations of shared test process state when
the mutation is not structurally scoped by pytest's ``monkeypatch``, unittest
``patch`` helpers, fixture finalizers, or a ``try/finally`` restoration block.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

try:
    from scripts.ci.guardrails.suppressions import has_targeted_noqa
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    from suppressions import has_targeted_noqa

RAIL_ID = "test-environment-leakage"


def _is_fixture(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for decorator in node.decorator_list:
        call = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(call, ast.Attribute) and call.attr == "fixture":
            return True
        if isinstance(call, ast.Name) and call.id == "fixture":
            return True
    return False


def _is_test_scope(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return node.name.startswith("test_") or _is_fixture(node)


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _call_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


def _is_patch_context(expr: ast.AST) -> bool:
    if not isinstance(expr, ast.Call):
        return False
    name = _call_name(expr.func)
    return (
        name
        in {
            "patch",
            "patch.object",
            "patch.multiple",
            "mock.patch",
            "mock.patch.object",
            "mock.patch.multiple",
            "unittest.mock.patch",
            "unittest.mock.patch.object",
            "unittest.mock.patch.multiple",
        }
        or name.endswith(".patch")
        or name.endswith(".patch.object")
        or name.endswith(".patch.multiple")
    )


def _is_patch_dict_context(expr: ast.AST) -> bool:
    return isinstance(expr, ast.Call) and _call_name(expr.func).endswith("patch.dict")


def _patch_object_target(expr: ast.AST) -> str | None:
    if not isinstance(expr, ast.Call):
        return None
    if not _call_name(expr.func).endswith("patch.object"):
        return None
    if len(expr.args) < 2:
        return None
    obj_key = _target_key(expr.args[0])
    attr_arg = expr.args[1]
    if obj_key is None or not isinstance(attr_arg, ast.Constant):
        return None
    if not isinstance(attr_arg.value, str):
        return None
    return f"{obj_key}.{attr_arg.value}"


def _is_addfinalizer_call(stmt: ast.stmt) -> bool:
    if not isinstance(stmt, ast.Expr) or not isinstance(stmt.value, ast.Call):
        return False
    return _call_name(stmt.value.func).endswith(".addfinalizer")


def _is_sys_modules(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "modules"
        and isinstance(node.value, ast.Name)
        and node.value.id == "sys"
    )


def _target_key(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return f"name:{node.id}"
    if isinstance(node, ast.Attribute):
        value = _target_key(node.value)
        if value is None:
            return None
        return f"{value}.{node.attr}"
    if isinstance(node, ast.Subscript):
        value = _target_key(node.value)
        if value is None:
            return None
        try:
            index = ast.unparse(node.slice)
        except Exception:  # pragma: no cover - ast.unparse is best effort only
            index = "*"
        return f"{value}[{index}]"
    if isinstance(node, ast.Call) and _call_name(node.func) == "globals":
        return "globals()"
    return None


def _is_class_or_global_attribute(target: ast.AST, imported_names: set[str]) -> bool:
    if not isinstance(target, ast.Attribute):
        return False
    if isinstance(target.value, ast.Name):
        base = target.value.id
        return base[:1].isupper() or base in imported_names
    if isinstance(target.value, ast.Attribute):
        return _attribute_root(target.value) in imported_names
    return False


def _attribute_root(node: ast.Attribute) -> str | None:
    current: ast.AST = node
    while isinstance(current, ast.Attribute):
        current = current.value
    return current.id if isinstance(current, ast.Name) else None


def _is_sys_modules_target(target: ast.AST) -> bool:
    return isinstance(target, ast.Subscript) and _is_sys_modules(target.value)


def _is_globals_target(target: ast.AST) -> bool:
    return (
        isinstance(target, ast.Subscript)
        and isinstance(target.value, ast.Call)
        and _call_name(target.value.func) == "globals"
    )


def _mutation_kind(target: ast.AST, imported_names: set[str]) -> str | None:
    if _is_sys_modules_target(target):
        return "sys.modules mutation without patch.dict or guaranteed cleanup"
    if _is_globals_target(target):
        return "globals() mutation without scoped restoration"
    if _is_class_or_global_attribute(target, imported_names):
        return "class/global attribute mutation without scoped restoration"
    return None


def _stmt_targets(stmt: ast.stmt) -> list[ast.AST]:
    if isinstance(stmt, ast.Assign):
        return list(stmt.targets)
    if isinstance(stmt, ast.AnnAssign):
        return [stmt.target]
    if isinstance(stmt, ast.AugAssign):
        return [stmt.target]
    if isinstance(stmt, ast.Delete):
        return list(stmt.targets)
    return []


def _restores_target(finalbody: list[ast.stmt], target: ast.AST) -> bool:
    expected = _target_key(target)
    if expected is None:
        return False
    for stmt in finalbody:
        for final_target in _stmt_targets(stmt):
            if _target_key(final_target) == expected:
                return True
    return False


class TestEnvironmentLeakageVisitor(ast.NodeVisitor):
    """Collect unscoped test-environment mutations."""

    def __init__(self, lines: list[str]) -> None:
        self.lines = lines
        self.violations: list[tuple[int, str, str]] = []
        self._test_scope_depth = 0
        self._patch_dict_depth = 0
        self._safe_target_stack: list[set[str]] = []
        self._finalizer_registered_stack: list[bool] = []
        self._fixture_yield_mutation_lines: set[int] = set()
        self._imported_names: set[str] = set()

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self._imported_names.add(alias.asname or alias.name.split(".", maxsplit=1)[0])

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            self._imported_names.add(alias.asname or alias.name)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if _is_test_scope(node):
            patch_targets = {
                target
                for decorator in node.decorator_list
                if (target := _patch_object_target(decorator)) is not None
            }
            patch_dict_count = sum(
                1 for decorator in node.decorator_list if _is_patch_dict_context(decorator)
            )
            self._test_scope_depth += 1
            self._patch_dict_depth += patch_dict_count
            self._safe_target_stack.append(patch_targets)
            self._finalizer_registered_stack.append(False)
            try:
                self._check_fixture_yield_cleanup(node)
                self._visit_block(node.body)
            finally:
                self._finalizer_registered_stack.pop()
                self._safe_target_stack.pop()
                self._patch_dict_depth -= patch_dict_count
                self._test_scope_depth -= 1
            return
        self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Global(self, node: ast.Global) -> None:
        if self._test_scope_depth:
            self._add_violation(
                node,
                "global statement in test mutates module state without scoped restoration",
            )

    def visit_With(self, node: ast.With) -> None:
        patch_targets = {
            target
            for item in node.items
            if (target := _patch_object_target(item.context_expr)) is not None
        }
        patch_dict_count = sum(
            1 for item in node.items if _is_patch_dict_context(item.context_expr)
        )
        self._patch_dict_depth += patch_dict_count
        self._safe_target_stack.append(patch_targets)
        try:
            self._visit_block(node.body)
        finally:
            self._safe_target_stack.pop()
            self._patch_dict_depth -= patch_dict_count

    visit_AsyncWith = visit_With

    def visit_Try(self, node: ast.Try) -> None:
        restored = {
            key
            for stmt in node.body
            for target in _stmt_targets(stmt)
            if (key := _target_key(target)) is not None and _restores_target(node.finalbody, target)
        }
        self._safe_target_stack.append(restored)
        try:
            self._visit_block(node.body)
        finally:
            self._safe_target_stack.pop()
        for handler in node.handlers:
            self._visit_block(handler.body)
        self._visit_block(node.orelse)
        finalbody_restorations = {
            key
            for stmt in node.finalbody
            for target in _stmt_targets(stmt)
            if (key := _target_key(target)) is not None
        }
        self._safe_target_stack.append(restored | finalbody_restorations)
        try:
            self._visit_block(node.finalbody)
        finally:
            self._safe_target_stack.pop()

    def visit_Expr(self, node: ast.Expr) -> None:
        if self._test_scope_depth and _is_addfinalizer_call(node):
            self._finalizer_registered_stack[-1] = True
        self.generic_visit(node)

    visit_TryStar = visit_Try

    def visit_Assign(self, node: ast.Assign) -> None:
        self._check_assignment(node, node.targets)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self._check_assignment(node, [node.target])
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self._check_assignment(node, [node.target])
        self.generic_visit(node)

    def _visit_block(self, block: list[ast.stmt]) -> None:
        for idx, stmt in enumerate(block):
            next_stmt = block[idx + 1] if idx + 1 < len(block) else None
            if isinstance(next_stmt, (ast.Try, ast.TryStar)):
                restored = {
                    key
                    for target in _stmt_targets(stmt)
                    if (key := _target_key(target)) is not None
                    and _restores_target(next_stmt.finalbody, target)
                }
                self._safe_target_stack.append(restored)
                try:
                    self.visit(stmt)
                finally:
                    self._safe_target_stack.pop()
                continue
            self.visit(stmt)

    def _check_fixture_yield_cleanup(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> None:
        if not _is_fixture(node):
            return
        for idx, stmt in enumerate(node.body):
            if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Yield):
                for prior in node.body[:idx]:
                    if _stmt_has_direct_mutation(prior, self._imported_names):
                        self._fixture_yield_mutation_lines.update(
                            child.lineno
                            for child in ast.walk(prior)
                            if isinstance(child, (ast.Assign, ast.AnnAssign, ast.AugAssign))
                        )
                        self._add_violation(
                            prior,
                            "fixture mutates shared state before yield without try/finally or pre-registered finalizer",
                        )
                for later in node.body[idx + 1 :]:
                    self._fixture_yield_mutation_lines.update(
                        child.lineno
                        for child in ast.walk(later)
                        if isinstance(child, (ast.Assign, ast.AnnAssign, ast.AugAssign))
                    )
                return
            if _is_addfinalizer_call(stmt):
                return
            if isinstance(stmt, ast.Try):
                continue

    def _check_assignment(self, node: ast.AST, targets: list[ast.AST]) -> None:
        if not self._test_scope_depth:
            return
        if getattr(node, "lineno", 0) in self._fixture_yield_mutation_lines:
            return
        if self._finalizer_registered_stack and self._finalizer_registered_stack[-1]:
            return
        for target in targets:
            kind = _mutation_kind(target, self._imported_names)
            if kind is None:
                continue
            if _is_sys_modules_target(target) and self._patch_dict_depth:
                continue
            key = _target_key(target)
            if key is not None and any(key in safe for safe in self._safe_target_stack):
                continue
            self._add_violation(node, kind)

    def _add_violation(self, node: ast.AST, message: str) -> None:
        lineno = getattr(node, "lineno", 0)
        line = self.lines[lineno - 1] if 0 < lineno <= len(self.lines) else ""
        if has_targeted_noqa(line, RAIL_ID):
            return
        self.violations.append((lineno, message, line.strip()))


def _stmt_has_direct_mutation(stmt: ast.stmt, imported_names: set[str]) -> bool:
    if isinstance(stmt, (ast.With, ast.AsyncWith)):
        if any(_is_patch_context(item.context_expr) for item in stmt.items):
            return False
        if any(_is_patch_dict_context(item.context_expr) for item in stmt.items):
            return False
    for child in ast.walk(stmt):
        if isinstance(child, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            if any(
                _mutation_kind(target, imported_names) is not None
                for target in _stmt_targets(child)
            ):
                return True
    return False


def check_file(filepath: Path) -> list[tuple[int, str, str]]:
    """Parse and check a single Python test file."""
    try:
        content = filepath.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"Error reading {filepath}: {exc}", file=sys.stderr)
        return []

    lines = content.splitlines()
    try:
        tree = ast.parse(content, filename=str(filepath))
    except SyntaxError as exc:
        print(f"Syntax error in {filepath}: {exc}", file=sys.stderr)
        return []

    visitor = TestEnvironmentLeakageVisitor(lines)
    visitor.visit(tree)
    return visitor.violations


def main(argv: list[str] | None = None) -> int:
    """Scan test files for process-global mutation leaks."""
    paths = [Path(arg) for arg in (argv if argv is not None else sys.argv[1:])]
    if not paths:
        test_dir = Path("tests")
        if not test_dir.exists():
            print("Error: tests directory not found. Run from the repository root.")
            return 1
        paths = [test_dir]

    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            files.extend(sorted(path.rglob("*.py")))
        elif path.suffix == ".py":
            files.append(path)

    all_violations: list[tuple[str, int, str, str]] = []
    for path in files:
        for lineno, msg, line in check_file(path):
            all_violations.append((path.as_posix(), lineno, msg, line))

    if all_violations:
        print(
            f"❌ [{RAIL_ID}] Violations found (test environment mutation can leak):",
            file=sys.stderr,
        )
        for file_path, lineno, msg, line in all_violations:
            print(f"  {file_path}:{lineno}: {msg} -> `{line}`", file=sys.stderr)
        print(
            "\nFix: use monkeypatch, patch/patch.dict, fixture finalizers, "
            f"try/finally restoration, or add '# noqa: {RAIL_ID}' for a documented exception.",
            file=sys.stderr,
        )
        return 1

    print(f"✅ [{RAIL_ID}] No violations found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
