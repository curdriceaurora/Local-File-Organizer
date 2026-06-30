#!/usr/bin/env python3
"""CI-rail: Flag broad except blocks that swallow SafeDir's ValueError (WP-6.1).

SafeDir.open_child() / open_for_reader() / open_subdir() /
open_anchored_reader() / open_anchored_writer() / lstat() / mkdir() /
unlink() / rename_into() raise ValueError when a caller-supplied path
attempts traversal or symlink escape (WP-1.1,
src/file_organizer/utils/safedir.py). A try/except that wraps a call to
one of these methods in a broad `except Exception` (or bare `except:`)
without re-raising and without an explicit ValueError handler silently
discards that path-safety signal.

Several of these method names (`mkdir`, `unlink`, `lstat`, `rename_into`)
also exist on `pathlib.Path` and other unrelated types, so a bare
method-name match would produce false positives on ordinary `Path`
calls. To narrow the heuristic, within each function body we first
collect the set of local names that are plausibly `SafeDir` instances:

1. Names assigned directly from `SafeDir(...)`.
2. Names assigned from `<tracked SafeDir name>.open_subdir(...)`, since
   `open_subdir` returns a `SafeDir` (one level of propagation only).
3. Parameters annotated literally as `SafeDir`.

Only calls whose receiver is one of these tracked names are counted as
SafeDir-method calls.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

try:
    from scripts.ci.guardrails.suppressions import has_targeted_noqa
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    from suppressions import has_targeted_noqa

_SAFEDIR_METHODS = {
    "open_child",
    "open_for_reader",
    "open_subdir",
    "open_anchored_reader",
    "open_anchored_writer",
    "lstat",
    "mkdir",
    "unlink",
    "rename_into",
}


def _is_safedir_constructor_call(call: ast.Call, aliases: set[str]) -> bool:
    return isinstance(call.func, ast.Name) and call.func.id in aliases


def _is_annotated_safedir(annotation: ast.expr | None, aliases: set[str]) -> bool:
    return isinstance(annotation, ast.Name) and annotation.id in aliases


def _collect_safedir_aliases(tree: ast.AST) -> set[str]:
    aliases = {"SafeDir"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "SafeDir":
                    aliases.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "SafeDir":
                    aliases.add(alias.asname or alias.name)
    return aliases


def _collect_safedir_and_other_names(
    func: ast.FunctionDef | ast.AsyncFunctionDef, aliases: set[str]
) -> tuple[set[str], set[str]]:
    """Collect local names within `func` that are SafeDir instances and other assigned names."""
    safedir_names: set[str] = set()
    other_assigned_names: set[str] = set()

    # Parameters annotated as SafeDir.
    all_args = (
        func.args.posonlyargs
        + func.args.args
        + func.args.kwonlyargs
        + ([func.args.vararg] if func.args.vararg else [])
        + ([func.args.kwarg] if func.args.kwarg else [])
    )
    for arg in all_args:
        if _is_annotated_safedir(arg.annotation, aliases):
            safedir_names.add(arg.arg)
        else:
            other_assigned_names.add(arg.arg)

    # Assignments: `x = SafeDir(...)` or `x = <tracked>.open_subdir(...)`.
    # First, collect all names assigned in this function scope (excluding nested functions)
    assigned_names: set[str] = set()
    for node in _walk_excluding_nested_functions(func):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    assigned_names.add(target.id)

    # Walk repeatedly so one level of open_subdir() propagation from a
    # newly discovered name is picked up regardless of statement order.
    changed = True
    while changed:
        changed = False
        for node in _walk_excluding_nested_functions(func):
            if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                continue
            target = node.targets[0]
            if not isinstance(target, ast.Name):
                continue
            if target.id in safedir_names:
                continue
            value = node.value
            if isinstance(value, ast.Call):
                if _is_safedir_constructor_call(value, aliases):
                    safedir_names.add(target.id)
                    changed = True
                elif (
                    isinstance(value.func, ast.Attribute)
                    and value.func.attr == "open_subdir"
                    and isinstance(value.func.value, ast.Name)
                    and value.func.value.id in safedir_names
                ):
                    safedir_names.add(target.id)
                    changed = True

    other_assigned_names.update(assigned_names - safedir_names)
    return safedir_names, other_assigned_names


def _walk_excluding_nested_functions(func: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.AST]:
    """Like ast.walk(func), but does not descend into nested function defs.

    Prevents a nested function's `try` blocks from being attributed to (and
    checked against) the *outer* function's SafeDir-name tracking, and from
    being visited twice (once here, once when the nested def is visited
    directly by the NodeVisitor).
    """
    seen: list[ast.AST] = []
    stack: list[ast.AST] = list(ast.iter_child_nodes(func))
    while stack:
        node = stack.pop()
        seen.append(node)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        stack.extend(ast.iter_child_nodes(node))
    return seen


def _calls_safedir_method(node: ast.AST, safedir_names: set[str]) -> bool:
    for child in ast.walk(node):
        if (
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Attribute)
            and child.func.attr in _SAFEDIR_METHODS
            and isinstance(child.func.value, ast.Name)
            and child.func.value.id in safedir_names
        ):
            return True
    return False


def _handler_names(handler: ast.ExceptHandler) -> set[str]:
    if handler.type is None:
        return {"bare"}
    if isinstance(handler.type, ast.Tuple):
        names: set[str] = set()
        for elt in handler.type.elts:
            if isinstance(elt, ast.Name):
                names.add(elt.id)
        return names
    if isinstance(handler.type, ast.Name):
        return {handler.type.id}
    return set()


def _handler_reraises(handler: ast.ExceptHandler) -> bool:
    return bool(handler.body) and isinstance(handler.body[0], ast.Raise)


def _has_explicit_valueerror_handler(try_node: ast.Try) -> bool:
    for handler in try_node.handlers:
        names = _handler_names(handler)
        if "ValueError" in names and "Exception" not in names and "bare" not in names:
            return True
    return False


class _Visitor(ast.NodeVisitor):
    def __init__(self, lines: list[str], aliases: set[str]) -> None:
        self.lines = lines
        self.aliases = aliases
        self.violations: list[tuple[int, str]] = []
        self.safedir_scopes: list[set[str]] = []

    def _visit_function(self, func: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        local_safedir, local_other = _collect_safedir_and_other_names(func, self.aliases)

        # Inherit from outer/enclosing scopes
        inherited_safedir: set[str] = set()
        for scope_set in self.safedir_scopes:
            inherited_safedir.update(scope_set)

        # Subtract local shadowed variables and union with local SafeDir variables
        active_safedir_names = (inherited_safedir - local_other) | local_safedir

        for node in _walk_excluding_nested_functions(func):
            if isinstance(node, ast.Try) and _calls_safedir_method(
                ast.Module(body=node.body, type_ignores=[]), active_safedir_names
            ):
                has_explicit_val_err = _has_explicit_valueerror_handler(node)
                for handler in node.handlers:
                    names = _handler_names(handler)
                    catches_broadly = "Exception" in names or "bare" in names
                    if (
                        catches_broadly
                        and not _handler_reraises(handler)
                        and not has_explicit_val_err
                    ):
                        line_idx = handler.lineno - 1
                        if 0 <= line_idx < len(self.lines):
                            line_content = self.lines[line_idx]
                            if has_targeted_noqa(line_content, "safedir-valueerror"):
                                continue
                        self.violations.append(
                            (
                                handler.lineno,
                                "except clause around a SafeDir call may silently "
                                "swallow ValueError (path-safety signal) — catch "
                                "ValueError explicitly or re-raise",
                            )
                        )
        # Recurse with current active_safedir_names pushed on the stack
        self.safedir_scopes.append(active_safedir_names)
        for child in ast.iter_child_nodes(func):
            self.visit(child)
        self.safedir_scopes.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)


def check_file(filepath: Path) -> list[tuple[int, str]]:
    """Parse and check a single Python file."""
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

    aliases = _collect_safedir_aliases(tree)
    visitor = _Visitor(lines, aliases)
    visitor.visit(tree)
    return visitor.violations


def main() -> int:
    """Scan all source files under src/file_organizer/."""
    package_root = Path("src/file_organizer")
    if not package_root.exists():
        print("Error: src/file_organizer directory not found. Run from the repository root.")
        return 1

    all_violations = []
    for path in package_root.rglob("*.py"):
        for lineno, msg in check_file(path):
            all_violations.append((path.as_posix(), lineno, msg))

    if all_violations:
        print("❌ [safedir-valueerror] Violations found:", file=sys.stderr)
        for file_path, lineno, msg in all_violations:
            print(f"  {file_path}:{lineno}: {msg}", file=sys.stderr)
        print(
            "\nFix: catch ValueError explicitly, re-raise, or add "
            "'# noqa: safedir-valueerror' if exempt.",
            file=sys.stderr,
        )
        return 1

    print("✅ [safedir-valueerror] No violations found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
