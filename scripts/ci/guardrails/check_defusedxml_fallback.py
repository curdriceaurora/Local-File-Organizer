#!/usr/bin/env python3
"""CI-rail: Ensure defusedxml is used instead of standard library xml (WP-6.1).

Flags any standard library xml imports (e.g., xml.etree, xml.dom) to prevent
XML External Entity (XXE) injection vulnerabilities.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

try:
    from scripts.ci.guardrails.suppressions import has_targeted_noqa
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    from suppressions import has_targeted_noqa


class DefusedXmlVisitor(ast.NodeVisitor):
    """AST visitor to find standard xml module imports."""

    def __init__(self, filepath: Path, lines: list[str]) -> None:
        self.filepath = filepath
        self.lines = lines
        self.violations: list[tuple[int, str, str]] = []
        self.stdlib_xml_aliases: set[str] = set()
        self.importlib_aliases: set[str] = {"importlib"}
        self.import_module_aliases: set[str] = set()
        self._reported_dynamic_imports: set[int] = set()

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.name == "xml" or alias.name.startswith("xml."):
                self.stdlib_xml_aliases.add(alias.asname or alias.name.split(".", maxsplit=1)[0])
                self.add_violation(node, f"standard library import '{alias.name}' is unsafe")
            elif alias.name == "importlib":
                self.importlib_aliases.add(alias.asname or alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module == "xml" or (node.module and node.module.startswith("xml.")):
            for alias in node.names:
                self.stdlib_xml_aliases.add(alias.asname or alias.name)
            self.add_violation(node, f"standard library import from '{node.module}' is unsafe")
        elif node.module == "importlib":
            for alias in node.names:
                if alias.name == "import_module":
                    self.import_module_aliases.add(alias.asname or alias.name)
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        xml_module = self._stdlib_xml_dynamic_import(node.value)
        if xml_module is not None:
            for target in node.targets:
                for name in self._target_names(target):
                    self.stdlib_xml_aliases.add(name)
            self._reported_dynamic_imports.add(id(node.value))
            self.add_violation(node, f"dynamic standard library import '{xml_module}' is unsafe")
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None:
            xml_module = self._stdlib_xml_dynamic_import(node.value)
            if xml_module is not None:
                for name in self._target_names(node.target):
                    self.stdlib_xml_aliases.add(name)
                self._reported_dynamic_imports.add(id(node.value))
                self.add_violation(node, f"dynamic standard library import '{xml_module}' is unsafe")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        xml_module = self._stdlib_xml_dynamic_import(node)
        if xml_module is not None and id(node) not in self._reported_dynamic_imports:
            self.add_violation(node, f"dynamic standard library import '{xml_module}' is unsafe")
        elif self._uses_stdlib_xml_parser_alias(node):
            self.add_violation(node, "standard library XML parser constructed through alias is unsafe")
        self.generic_visit(node)

    def _stdlib_xml_dynamic_import(self, node: ast.AST) -> str | None:
        if not isinstance(node, ast.Call):
            return None

        module_arg: ast.AST | None = None
        if isinstance(node.func, ast.Name) and node.func.id == "__import__":
            module_arg = node.args[0] if node.args else None
        elif isinstance(node.func, ast.Name) and node.func.id in self.import_module_aliases:
            module_arg = node.args[0] if node.args else None
        elif (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "import_module"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in self.importlib_aliases
        ):
            module_arg = node.args[0] if node.args else None

        if not isinstance(module_arg, ast.Constant) or not isinstance(module_arg.value, str):
            return None
        module_name = module_arg.value
        if module_name == "xml" or module_name.startswith("xml."):
            return module_name
        return None

    def _uses_stdlib_xml_parser_alias(self, node: ast.Call) -> bool:
        if not isinstance(node.func, ast.Attribute):
            return False
        if node.func.attr not in {"XMLParser", "XML", "fromstring", "parse", "iterparse"}:
            return False
        return isinstance(node.func.value, ast.Name) and node.func.value.id in self.stdlib_xml_aliases

    def _target_names(self, target: ast.AST) -> set[str]:
        if isinstance(target, ast.Name):
            return {target.id}
        if isinstance(target, (ast.Tuple, ast.List)):
            names: set[str] = set()
            for element in target.elts:
                names.update(self._target_names(element))
            return names
        return set()

    def add_violation(self, node: ast.AST, message: str) -> None:
        lineno = node.lineno
        line_idx = lineno - 1
        if 0 <= line_idx < len(self.lines):
            line_content = self.lines[line_idx]
            if has_targeted_noqa(line_content, "defusedxml-fallback"):
                return
            self.violations.append((lineno, message, line_content.strip()))


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

    visitor = DefusedXmlVisitor(filepath, lines)
    visitor.visit(tree)
    return visitor.violations


def main() -> int:
    """Scan all source files under src/file_organizer/."""
    package_root = Path("src/file_organizer")
    if not package_root.exists():
        print("Error: src/file_organizer directory not found. Run from the repository root.")
        return 1

    all_violations = []
    # Scan all python files recursively
    for path in package_root.rglob("*.py"):
        violations = check_file(path)
        for lineno, msg, line in violations:
            all_violations.append((path.as_posix(), lineno, msg, line))

    if all_violations:
        print("❌ [defusedxml-fallback] Violations found (unsafe XML imports):", file=sys.stderr)
        for file_path, lineno, msg, line in all_violations:
            print(f"  {file_path}:{lineno}: {msg} -> `{line}`", file=sys.stderr)
        print(
            "\nFix: Import from 'defusedxml' instead of standard 'xml', or add '# noqa: defusedxml-fallback' if exempt.",
            file=sys.stderr,
        )
        return 1

    print("✅ [defusedxml-fallback] No violations found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
