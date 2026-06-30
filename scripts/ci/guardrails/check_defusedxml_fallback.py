#!/usr/bin/env python3
"""CI-rail: Ensure defusedxml is used instead of standard library xml (WP-6.1).

Flags any standard library xml imports (e.g., xml.etree, xml.dom) to prevent
XML External Entity (XXE) injection vulnerabilities.
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass, field
from pathlib import Path

try:
    from scripts.ci.guardrails.ast_helpers import extract_name_targets
    from scripts.ci.guardrails.suppressions import has_targeted_noqa
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    from ast_helpers import extract_name_targets
    from suppressions import has_targeted_noqa


@dataclass
class _Scope:
    stdlib_xml_aliases: set[str] = field(default_factory=set)
    string_bindings: dict[str, str] = field(default_factory=dict)
    importlib_aliases: set[str] = field(default_factory=lambda: {"importlib"})
    import_module_aliases: set[str] = field(default_factory=set)
    xml_alias_factories: set[str] = field(default_factory=set)


class DefusedXmlVisitor(ast.NodeVisitor):
    """AST visitor to find standard xml module imports."""

    def __init__(self, filepath: Path, lines: list[str]) -> None:
        self.filepath = filepath
        self.lines = lines
        self.violations: list[tuple[int, str, str]] = []
        self.scopes: list[_Scope] = [_Scope()]
        self._reported_dynamic_imports: set[int] = set()

    @property
    def scope(self) -> _Scope:
        return self.scopes[-1]

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.name == "xml" or alias.name.startswith("xml."):
                self.scope.stdlib_xml_aliases.add(
                    alias.asname or alias.name.split(".", maxsplit=1)[0]
                )
                self.add_violation(node, f"standard library import '{alias.name}' is unsafe")
            elif alias.name == "importlib" or alias.name.startswith("importlib."):
                self.scope.importlib_aliases.add(alias.asname or alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module == "xml" or (node.module and node.module.startswith("xml.")):
            for alias in node.names:
                self.scope.stdlib_xml_aliases.add(alias.asname or alias.name)
            self.add_violation(node, f"standard library import from '{node.module}' is unsafe")
        elif node.module == "importlib":
            for alias in node.names:
                if alias.name == "import_module":
                    self.scope.import_module_aliases.add(alias.asname or alias.name)
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        string_value = self._literal_string_value(node.value)
        if string_value is not None:
            for target in node.targets:
                for name in extract_name_targets(target):
                    self.scope.string_bindings[name] = string_value

        xml_module = self._stdlib_xml_dynamic_import(node.value)
        if xml_module is not None:
            for target in node.targets:
                self.scope.stdlib_xml_aliases.update(self._target_keys(target))
            self._reported_dynamic_imports.add(id(node.value))
            self.add_violation(node, f"dynamic standard library import '{xml_module}' is unsafe")
        elif self._expr_uses_stdlib_xml_alias(node.value) or self._returns_stdlib_xml_alias(
            node.value
        ):
            for target in node.targets:
                self.scope.stdlib_xml_aliases.update(self._target_keys(target))
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None:
            string_value = self._literal_string_value(node.value)
            if string_value is not None:
                for name in extract_name_targets(node.target):
                    self.scope.string_bindings[name] = string_value

            xml_module = self._stdlib_xml_dynamic_import(node.value)
            if xml_module is not None:
                self.scope.stdlib_xml_aliases.update(self._target_keys(node.target))
                self._reported_dynamic_imports.add(id(node.value))
                self.add_violation(
                    node, f"dynamic standard library import '{xml_module}' is unsafe"
                )
            elif self._expr_uses_stdlib_xml_alias(node.value) or self._returns_stdlib_xml_alias(
                node.value
            ):
                self.scope.stdlib_xml_aliases.update(self._target_keys(node.target))
        self.generic_visit(node)

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
        string_value = self._literal_string_value(node.value)
        if string_value is not None:
            for name in extract_name_targets(node.target):
                self.scope.string_bindings[name] = string_value

        xml_module = self._stdlib_xml_dynamic_import(node.value)
        if xml_module is not None:
            self.scope.stdlib_xml_aliases.update(self._target_keys(node.target))
            self._reported_dynamic_imports.add(id(node.value))
            self.add_violation(node, f"dynamic standard library import '{xml_module}' is unsafe")
        elif self._expr_uses_stdlib_xml_alias(node.value) or self._returns_stdlib_xml_alias(
            node.value
        ):
            self.scope.stdlib_xml_aliases.update(self._target_keys(node.target))
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if self._function_returns_stdlib_xml_alias(node):
            self.scope.xml_alias_factories.add(node.name)
        self._visit_function_scope(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        if self._function_returns_stdlib_xml_alias(node):
            self.scope.xml_alias_factories.add(node.name)
        self._visit_function_scope(node)

    def visit_Call(self, node: ast.Call) -> None:
        xml_module = self._stdlib_xml_dynamic_import(node)
        if xml_module is not None and id(node) not in self._reported_dynamic_imports:
            self.add_violation(node, f"dynamic standard library import '{xml_module}' is unsafe")
        elif self._uses_stdlib_xml_parser_alias(node):
            self.add_violation(
                node, "standard library XML parser constructed through alias is unsafe"
            )
        self.generic_visit(node)

    def _stdlib_xml_dynamic_import(self, node: ast.AST) -> str | None:
        if not isinstance(node, ast.Call):
            return None

        module_arg: ast.AST | None = None
        if isinstance(node.func, ast.Name) and node.func.id == "__import__":
            module_arg = self._module_argument(node)
        elif isinstance(node.func, ast.Name) and node.func.id in self.scope.import_module_aliases:
            module_arg = self._module_argument(node)
        elif (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "import_module"
            and self._expr_key(node.func.value) in self.scope.importlib_aliases
        ):
            module_arg = self._module_argument(node)

        module_name = self._literal_string_value(module_arg)
        if module_name is None:
            return None
        if module_name == "xml" or module_name.startswith("xml."):
            return module_name
        return None

    def _module_argument(self, node: ast.Call) -> ast.AST | None:
        if node.args:
            return node.args[0]
        for keyword in node.keywords:
            if keyword.arg == "name":
                return keyword.value
        return None

    def _literal_string_value(self, node: ast.AST | None) -> str | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Name):
            return self.scope.string_bindings.get(node.id)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            left = self._literal_string_value(node.left)
            right = self._literal_string_value(node.right)
            if left is not None and right is not None:
                return left + right
        if isinstance(node, ast.JoinedStr):
            parts: list[str] = []
            for value in node.values:
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    parts.append(value.value)
                elif isinstance(value, ast.FormattedValue):
                    formatted = self._literal_string_value(value.value)
                    if formatted is None:
                        return None
                    parts.append(formatted)
                else:
                    return None
            return "".join(parts)
        return None

    def _uses_stdlib_xml_parser_alias(self, node: ast.Call) -> bool:
        if not isinstance(node.func, ast.Attribute):
            return False
        if node.func.attr not in {"XMLParser", "XML", "fromstring", "parse", "iterparse"}:
            return False
        return self._expr_uses_stdlib_xml_alias(node.func.value)

    def _function_returns_stdlib_xml_alias(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> bool:
        for child in ast.walk(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                if child is not node:
                    continue
            if isinstance(child, ast.Return) and child.value is not None:
                if self._expr_uses_stdlib_xml_alias(child.value):
                    return True
        return False

    def _returns_stdlib_xml_alias(self, node: ast.AST) -> bool:
        return (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in self.scope.xml_alias_factories
        )

    def _expr_uses_stdlib_xml_alias(self, node: ast.AST) -> bool:
        keys = self._expr_key_prefixes(node)
        return any(key in self.scope.stdlib_xml_aliases for key in keys)

    def _visit_function_scope(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        inherited = self.scope
        local_binders = self._function_local_binders(node)
        self.scopes.append(
            _Scope(
                stdlib_xml_aliases={
                    alias
                    for alias in inherited.stdlib_xml_aliases
                    if self._root_name(alias) not in local_binders
                },
                string_bindings={
                    name: value
                    for name, value in inherited.string_bindings.items()
                    if name not in local_binders
                },
                importlib_aliases={
                    alias
                    for alias in inherited.importlib_aliases
                    if self._root_name(alias) not in local_binders
                },
                import_module_aliases=inherited.import_module_aliases - local_binders,
                xml_alias_factories=inherited.xml_alias_factories - local_binders,
            )
        )
        try:
            for child in node.body:
                self.visit(child)
        finally:
            self.scopes.pop()

    def _function_local_binders(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
        binders: set[str] = set()
        args = (
            node.args.posonlyargs
            + node.args.args
            + node.args.kwonlyargs
            + ([node.args.vararg] if node.args.vararg else [])
            + ([node.args.kwarg] if node.args.kwarg else [])
        )
        binders.update(arg.arg for arg in args)
        for child in node.body:
            for nested in ast.walk(child):
                if isinstance(nested, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                    continue
                if isinstance(nested, ast.Assign):
                    for target in nested.targets:
                        binders.update(extract_name_targets(target))
                elif isinstance(nested, ast.AnnAssign):
                    binders.update(extract_name_targets(nested.target))
                elif isinstance(nested, ast.NamedExpr):
                    binders.update(extract_name_targets(nested.target))
                elif isinstance(nested, (ast.For, ast.AsyncFor)):
                    binders.update(extract_name_targets(nested.target))
                elif isinstance(nested, (ast.With, ast.AsyncWith)):
                    for item in nested.items:
                        if item.optional_vars is not None:
                            binders.update(extract_name_targets(item.optional_vars))
        return binders

    def _target_keys(self, target: ast.AST) -> set[str]:
        if isinstance(target, (ast.Name, ast.Attribute)):
            key = self._expr_key(target)
            return {key} if key is not None else set()
        if isinstance(target, ast.NamedExpr):
            return self._target_keys(target.target)
        if isinstance(target, ast.Starred):
            return self._target_keys(target.value)
        if isinstance(target, (ast.Tuple, ast.List)):
            keys: set[str] = set()
            for element in target.elts:
                keys.update(self._target_keys(element))
            return keys
        return set()

    def _expr_key_prefixes(self, node: ast.AST) -> list[str]:
        key = self._expr_key(node)
        if key is None:
            return []
        parts = key.split(".")
        return [".".join(parts[:idx]) for idx in range(1, len(parts) + 1)]

    def _expr_key(self, node: ast.AST) -> str | None:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            parent = self._expr_key(node.value)
            if parent is not None:
                return f"{parent}.{node.attr}"
        return None

    def _root_name(self, key: str) -> str:
        return key.split(".", maxsplit=1)[0]

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
