#!/usr/bin/env python3
"""CI-rail: Ensure all CLI commands validate Path arguments (WP-6.1).

Scans CLI command functions to verify that any path parameters are run through
resolve_cli_path or validate_within_roots/validate_pair before being used.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

VALIDATION_FUNCTIONS = {
    "resolve_cli_path",
    "validate_within_roots",
    "validate_path",
    "validate_pair",
}


def _is_cli_command(node: ast.FunctionDef) -> bool:
    """Check if the function is a CLI command entrypoint."""
    if node.name == "doctor":
        return True
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
            return True
    return False


class PathTypeChecker(ast.NodeVisitor):
    """Visitor to check if type annotation AST uses Path."""

    def __init__(self) -> None:
        self.has_path = False

    def visit_Name(self, node: ast.Name) -> None:
        if node.id == "Path":
            self.has_path = True
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr == "Path":
            self.has_path = True
        self.generic_visit(node)


class CliPathValidationVisitor(ast.NodeVisitor):
    """AST visitor to check CLI path argument validation."""

    def __init__(self, filepath: Path, lines: list[str]) -> None:
        self.filepath = filepath
        self.lines = lines
        self.violations: list[tuple[int, str, str]] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: C901
        # We only care about CLI command entrypoints.
        if node.name.startswith("_") or not _is_cli_command(node):
            self.generic_visit(node)
            return

        # Find all parameters that are Path arguments/options
        path_params: list[str] = []
        param_lines: dict[str, int] = {}

        for arg in node.args.args:
            is_path = False
            # Check annotation (e.g., Path, Path | None, Optional[Path])
            if arg.annotation:
                checker = PathTypeChecker()
                checker.visit(arg.annotation)
                if checker.has_path:
                    is_path = True

            # If it's a path parameter, record it
            if is_path:
                path_params.append(arg.arg)
                param_lines[arg.arg] = arg.lineno

        if not path_params:
            self.generic_visit(node)
            return

        # Scan the function body for validation calls on these parameters
        validated_params: set[str] = set()

        class ValidationCallScanner(ast.NodeVisitor):
            """Scanner to find where parameters are passed to validation functions."""

            def visit_Call(self, inner_node: ast.Call) -> None:
                # Get the name of the function being called
                func_name = ""
                if isinstance(inner_node.func, ast.Name):
                    func_name = inner_node.func.id
                elif isinstance(inner_node.func, ast.Attribute):
                    func_name = inner_node.func.attr

                if func_name in VALIDATION_FUNCTIONS:
                    # Find which parameters are passed to this validation function
                    for arg_val in inner_node.args:
                        if isinstance(arg_val, ast.Name) and arg_val.id in path_params:
                            validated_params.add(arg_val.id)
                    for kw in inner_node.keywords:
                        if isinstance(kw.value, ast.Name) and kw.value.id in path_params:
                            validated_params.add(kw.value.id)

                self.generic_visit(inner_node)

        scanner = ValidationCallScanner()
        scanner.visit(node)

        # Flag any parameter that wasn't validated
        for param in path_params:
            if param not in validated_params:
                lineno = param_lines[param]
                line_idx = lineno - 1
                line_content = self.lines[line_idx] if 0 <= line_idx < len(self.lines) else ""

                # Check for noqa override
                if "noqa: cli-path-validation" in line_content or "noqa" in line_content:
                    continue

                self.violations.append(
                    (
                        lineno,
                        f"CLI path parameter '{param}' in function '{node.name}' is not validated",
                        line_content.strip(),
                    )
                )

        self.generic_visit(node)


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

    visitor = CliPathValidationVisitor(filepath, lines)
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
        print("❌ [cli-path-validation] Violations found (unvalidated CLI paths):", file=sys.stderr)
        for file_path, lineno, msg, line in all_violations:
            print(f"  {file_path}:{lineno}: {msg} -> `{line}`", file=sys.stderr)
        print(
            "\nFix: Wrap the CLI Path argument in resolve_cli_path() or add '# noqa: cli-path-validation' if exempt.",
            file=sys.stderr,
        )
        return 1

    print("✅ [cli-path-validation] No violations found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
