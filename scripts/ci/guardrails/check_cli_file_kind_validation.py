#!/usr/bin/env python3
"""CI-rail: Ensure CLI file outputs validate file-vs-directory kind (WP-6.1).

Scans CLI command functions to verify that when paths are resolved with
``resolve_cli_path(..., must_be_dir=False)``, a subsequent kind check
(``is_file()`` or ``is_dir()``) validates the expected filesystem type.

This catches violations like resolving a path as "any kind" then writing to
it without checking that a directory wasn't passed instead of a file.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

try:
    from scripts.ci.guardrails.suppressions import has_comment_marker, has_targeted_noqa
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    from suppressions import has_comment_marker, has_targeted_noqa


class CliFileKindValidationVisitor(ast.NodeVisitor):
    """AST visitor to check CLI file-kind validation after resolve_cli_path.

    Pattern: When a path is resolved with must_be_dir=False (accepting any kind),
    the function should have an explicit is_file() or is_dir() check before
    performing I/O operations. This catches the gap where a path resolves
    successfully but the wrong filesystem kind was passed.
    """

    def __init__(self, filepath: Path, lines: list[str]) -> None:
        self.filepath = filepath
        self.lines = lines
        self.violations: list[tuple[int, str, str]] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Check if function is a CLI command and scan for kind validation gaps."""
        # Only check CLI command functions
        if node.name.startswith("_"):
            self.generic_visit(node)
            return

        is_cli_command = False
        for decorator in node.decorator_list:
            dec_name = ""
            if isinstance(decorator, ast.Call):
                func = decorator.func
                if isinstance(func, ast.Attribute):
                    dec_name = func.attr
                elif isinstance(func, ast.Name):
                    dec_name = func.id
            elif isinstance(decorator, ast.Attribute):
                dec_name = decorator.attr
            elif isinstance(decorator, ast.Name):
                dec_name = decorator.id

            if dec_name in ("command", "callback"):
                is_cli_command = True
                break

        if not is_cli_command and node.name != "doctor":
            self.generic_visit(node)
            return

        # Scan function body for resolve_cli_path calls with must_be_dir=False
        self._check_kind_validation(node)
        self.generic_visit(node)

    def _check_kind_validation(self, func_node: ast.FunctionDef) -> None:
        """Find resolve_cli_path calls with must_be_dir=False and check for kind validation."""
        # Find all resolve_cli_path calls with must_be_dir=False
        resolver_calls: list[tuple[int, str]] = []  # (lineno, variable_name)

        class ResolveFinder(ast.NodeVisitor):
            """Find resolve_cli_path calls and extract assigned variable names."""

            def visit_Assign(self, node: ast.Assign) -> None:
                """Track assignments from resolve_cli_path calls."""
                if isinstance(node.value, ast.Call):
                    call = node.value
                    func_name = ""
                    if isinstance(call.func, ast.Name):
                        func_name = call.func.id
                    elif isinstance(call.func, ast.Attribute):
                        func_name = call.func.attr

                    if func_name == "resolve_cli_path":
                        # Check if must_be_dir=False is in the call
                        has_must_be_dir_false = False
                        for kw in call.keywords:
                            if kw.arg == "must_be_dir":
                                if (
                                    isinstance(kw.value, ast.Constant) and kw.value.value is False
                                ) or (
                                    isinstance(kw.value, ast.Constant)
                                    and hasattr(kw.value, "value")
                                    and kw.value.value is False
                                ):
                                    has_must_be_dir_false = True

                        if has_must_be_dir_false:
                            # Extract variable name(s) from assignment
                            for target in node.targets:
                                if isinstance(target, ast.Name):
                                    resolver_calls.append((node.lineno, target.id))

                self.generic_visit(node)

        finder = ResolveFinder()
        finder.visit(func_node)

        # For each resolve_cli_path call with must_be_dir=False,
        # check if the assigned variable is validated for kind shortly after
        for resolve_lineno, var_name in resolver_calls:
            # Check if this call has suppression marker
            line_idx = resolve_lineno - 1
            line_content = self.lines[line_idx] if 0 <= line_idx < len(self.lines) else ""
            if has_comment_marker(line_content, "copilot: wontfix") or has_targeted_noqa(
                line_content, "cli-file-kind-validation"
            ):
                continue

            # Check if variable is validated within next 20 lines
            # (looking for .is_file(), .is_dir(), or validate_* calls)
            kind_validated = self._check_kind_validation_in_block(
                func_node, var_name, resolve_lineno
            )

            if not kind_validated:
                line_content_display = line_content.strip()
                self.violations.append(
                    (
                        resolve_lineno,
                        f"Path '{var_name}' resolved with must_be_dir=False "
                        f"in function '{func_node.name}' without explicit kind validation",
                        line_content_display,
                    )
                )

    def _check_kind_validation_in_block(  # noqa: C901
        self, func_node: ast.FunctionDef, var_name: str, resolve_lineno: int
    ) -> bool:
        """Check if a variable is validated for file/dir kind shortly after resolution.

        Looks for patterns like:
        - var.is_file()
        - var.is_dir()
        - validate_regular_file(var, ...)
        - validate_is_dir(var, ...)
        - if var.exists() and not var.is_file(): raise ...
        """

        class KindValidator(ast.NodeVisitor):
            """Check if variable is validated for file/dir kind."""

            def __init__(self) -> None:
                self.validated = False
                self.current_lineno = resolve_lineno

            def visit_Call(self, node: ast.Call) -> None:
                """Check for unconditional validation helper calls."""
                if self.validated or node.lineno < resolve_lineno:
                    self.generic_visit(node)
                    return

                # Check for too much distance (more than 15 lines away)
                if node.lineno - resolve_lineno > 15:
                    self.generic_visit(node)
                    return

                func_name = ""
                if isinstance(node.func, ast.Attribute):
                    func_name = node.func.attr
                elif isinstance(node.func, ast.Name):
                    func_name = node.func.id

                # Check for kind validation helpers
                if func_name in ("validate_regular_file", "validate_is_dir"):
                    for arg in node.args:
                        if isinstance(arg, ast.Name) and arg.id == var_name:
                            self.validated = True

                self.generic_visit(node)

            def visit_If(self, node: ast.If) -> None:
                """Check for rejecting guards like if not var.is_file(): raise ..."""
                if self.validated or node.lineno < resolve_lineno:
                    self.generic_visit(node)
                    return

                if node.lineno - resolve_lineno > 15:
                    self.generic_visit(node)
                    return

                if self._is_rejecting_kind_guard(node, var_name):
                    self.validated = True

                self.generic_visit(node)

            def _is_rejecting_kind_guard(self, node: ast.If, var_name: str) -> bool:
                """Return True when wrong-kind branch is explicitly rejecting."""
                polarities = self._collect_kind_check_polarities(node.test, var_name)
                if not polarities:
                    return False

                return (True in polarities and self._branch_rejects(node.body)) or (
                    False in polarities and self._branch_rejects(node.orelse)
                )

            def _collect_kind_check_polarities(
                self, test_node: ast.expr, var_name: str, negated: bool = False
            ) -> set[bool]:
                """Collect wrong-kind polarities from kind checks in a test expression.

                True means the "wrong kind" branch is entered when the condition is true
                (e.g. ``if not path.is_file():``). False means wrong kind is on the else
                branch (e.g. ``if path.is_file(): ... else: raise``).
                """
                if isinstance(test_node, ast.UnaryOp) and isinstance(test_node.op, ast.Not):
                    return self._collect_kind_check_polarities(
                        test_node.operand, var_name, not negated
                    )

                if isinstance(test_node, ast.BoolOp):
                    polarities: set[bool] = set()
                    for value in test_node.values:
                        polarities.update(
                            self._collect_kind_check_polarities(value, var_name, negated)
                        )
                    return polarities

                if isinstance(test_node, ast.Compare):
                    polarities = self._collect_kind_check_polarities(
                        test_node.left, var_name, negated
                    )
                    for comparator in test_node.comparators:
                        polarities.update(
                            self._collect_kind_check_polarities(comparator, var_name, negated)
                        )
                    return polarities

                if (
                    isinstance(test_node, ast.Call)
                    and isinstance(test_node.func, ast.Attribute)
                    and test_node.func.attr in ("is_file", "is_dir")
                    and isinstance(test_node.func.value, ast.Name)
                    and test_node.func.value.id == var_name
                ):
                    return {negated}

                return set()

            def _branch_rejects(self, stmts: list[ast.stmt]) -> bool:
                """Return True if the branch rejects execution for wrong-kind input."""
                for stmt in stmts:
                    if isinstance(stmt, (ast.Raise, ast.Return)):
                        return True
                    for nested in ast.walk(stmt):
                        if isinstance(nested, (ast.Raise, ast.Return)):
                            return True
                return False

        validator = KindValidator()
        validator.visit(func_node)
        return validator.validated


def check_file(filepath: Path) -> list[tuple[int, str, str]]:
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

    visitor = CliFileKindValidationVisitor(filepath, lines)
    visitor.visit(tree)
    return visitor.violations


def main() -> int:
    """Scan all source files under src/file_organizer/cli/."""
    cli_dir = Path("src/file_organizer/cli")
    if not cli_dir.exists():
        print("Error: src/file_organizer/cli directory not found. Run from the repository root.")
        return 1

    all_violations = []
    # Scan all python files in the cli directory
    for path in cli_dir.glob("*.py"):
        if path.name in ("__init__.py", "_globals.py", "path_validation.py"):
            continue

        violations = check_file(path)
        for lineno, msg, line in violations:
            all_violations.append((path.as_posix(), lineno, msg, line))

    if all_violations:
        print(
            "❌ [cli-file-kind-validation] Violations found (missing file-kind checks):",
            file=sys.stderr,
        )
        for file_path, lineno, msg, line in all_violations:
            print(f"  {file_path}:{lineno}: {msg} -> `{line}`", file=sys.stderr)
        print(
            "\nFix: After resolve_cli_path(..., must_be_dir=False), add "
            "validate_regular_file() or validate_is_dir() or an explicit kind check. "
            "Add '# copilot: wontfix' (or '# noqa: cli-file-kind-validation') if exempt.",
            file=sys.stderr,
        )
        return 1

    print("✅ [cli-file-kind-validation] No violations found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
