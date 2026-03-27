#!/usr/bin/env python3
"""Verify all documented APIs match source code exactly."""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path
from typing import Any

# ANSI color codes for output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"
BOLD = "\033[1m"
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def print_success(message: str) -> None:
    """Print success message in green."""
    print(f"{GREEN}✓{RESET} {message}")


def print_error(message: str) -> None:
    """Print error message in red."""
    print(f"{RED}✗{RESET} {message}")


def print_warning(message: str) -> None:
    """Print warning message in yellow."""
    print(f"{YELLOW}⚠{RESET} {message}")


def print_section(title: str) -> None:
    """Print section header."""
    print(f"\n{BOLD}{title}{RESET}")
    print("=" * len(title))


def extract_class_info(source_file: Path, class_name: str) -> dict[str, Any]:
    """Extract class definition and methods from source file."""
    content = source_file.read_text(encoding="utf-8")
    tree = ast.parse(content)

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            methods = []
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    # Get method signature
                    args = []
                    for arg in item.args.args:
                        arg_str = arg.arg
                        if arg.annotation:
                            arg_str += f": {ast.unparse(arg.annotation)}"
                        args.append(arg_str)

                    return_type = None
                    if item.returns:
                        return_type = ast.unparse(item.returns)

                    methods.append(
                        {
                            "name": item.name,
                            "args": args,
                            "return_type": return_type,
                            "is_abstract": any(
                                isinstance(dec, ast.Name) and dec.id == "abstractmethod"
                                for dec in item.decorator_list
                            ),
                        }
                    )

            return {
                "name": class_name,
                "methods": methods,
                "bases": [ast.unparse(base) for base in node.bases],
            }

    return {}


def extract_function_signature(source_file: Path, func_name: str) -> dict[str, Any] | None:
    """Extract function signature from source file."""
    content = source_file.read_text(encoding="utf-8")
    tree = ast.parse(content)

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            args = []
            for arg in node.args.args:
                arg_str = arg.arg
                if arg.annotation:
                    arg_str += f": {ast.unparse(arg.annotation)}"
                args.append(arg_str)

            # Get keyword-only args
            kwonlyargs = []
            for arg in node.args.kwonlyargs:
                arg_str = arg.arg
                if arg.annotation:
                    arg_str += f": {ast.unparse(arg.annotation)}"
                kwonlyargs.append(arg_str)

            return_type = None
            if node.returns:
                return_type = ast.unparse(node.returns)

            return {
                "name": func_name,
                "args": args,
                "kwonlyargs": kwonlyargs,
                "defaults": [ast.unparse(d) for d in node.args.kw_defaults if d is not None],
                "return_type": return_type,
            }

    return None


def extract_dataclass_fields(source_file: Path, class_name: str) -> dict[str, Any]:
    """Extract dataclass fields."""
    content = source_file.read_text(encoding="utf-8")
    tree = ast.parse(content)

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            fields = []
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    field_name = item.target.id
                    field_type = ast.unparse(item.annotation)
                    default_value = ast.unparse(item.value) if item.value else None
                    fields.append(
                        {
                            "name": field_name,
                            "type": field_type,
                            "default": default_value,
                        }
                    )

            return {"name": class_name, "fields": fields}

    return {}


def extract_enum_values(source_file: Path, enum_name: str) -> list[str]:
    """Extract enum member values."""
    content = source_file.read_text(encoding="utf-8")
    tree = ast.parse(content)

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == enum_name:
            values = []
            for item in node.body:
                if isinstance(item, ast.Assign):
                    # Extract the literal value, not the name
                    if isinstance(item.value, ast.Constant):
                        values.append(item.value.value)
                    elif isinstance(item.value, ast.Str):  # Python 3.7 compatibility
                        values.append(item.value.s)
            return values

    return []


def _convert_constant_node(node: ast.AST) -> Any:
    """Convert simple AST literals/containers into Python values."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Tuple):
        return tuple(_convert_constant_node(elt) for elt in node.elts)
    if isinstance(node, ast.List):
        return [_convert_constant_node(elt) for elt in node.elts]
    if isinstance(node, ast.Set):
        return {_convert_constant_node(elt) for elt in node.elts}
    if isinstance(node, ast.Dict):
        return _convert_constant_dict(node)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_convert_constant_node(node.operand)
    raise ValueError(f"Unsupported constant node: {ast.dump(node, include_attributes=False)}")


def _convert_constant_dict(node: ast.Dict) -> dict[Any, Any]:
    """Convert an AST dictionary node into a Python dictionary."""
    return {
        _convert_constant_node(key): _convert_constant_node(value)
        for key, value in zip(node.keys, node.values, strict=True)
    }


def _store_constant(
    constants: dict[str, Any],
    name: str,
    value_node: ast.AST,
) -> None:
    """Store a parsed constant, falling back to source text on unsupported nodes."""
    try:
        constants[name] = _convert_constant_node(value_node)
    except (ValueError, TypeError, SyntaxError):
        constants[name] = ast.unparse(value_node)


def extract_constants(source_file: Path, constant_names: list[str] | None = None) -> dict[str, Any]:
    """Extract top-level constant values from a source file."""
    content = source_file.read_text(encoding="utf-8")
    tree = ast.parse(content)

    constants = {}

    # Walk the module body directly to preserve top-level assignments
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and (
                    constant_names is None or target.id in constant_names
                ):
                    _store_constant(constants, target.id, node.value)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if constant_names is not None and node.target.id not in constant_names:
                continue
            if node.value is None:
                continue
            _store_constant(constants, node.target.id, node.value)

    return constants


def verify_plugin_class() -> bool:
    """Verify Plugin base class exists with correct methods."""
    print_section("1. Plugin Base Class")

    base_file = PROJECT_ROOT / "src/file_organizer/plugins/base.py"
    if not base_file.exists():
        print_error(f"Source file not found: {base_file}")
        return False

    # Check if Plugin class exists
    class_info = extract_class_info(base_file, "Plugin")
    if not class_info:
        print_error("Plugin class not found in base.py")
        return False

    print_success(f"Plugin class found in {base_file}")

    # Check required lifecycle methods
    required_methods = [
        ("on_load", [], "None"),
        ("on_enable", [], "None"),
        ("on_disable", [], "None"),
        ("on_unload", [], "None"),
        ("get_metadata", [], "PluginMetadata"),
    ]

    all_methods_found = True
    for method_name, expected_args, expected_return in required_methods:
        method = next((m for m in class_info["methods"] if m["name"] == method_name), None)
        if not method:
            print_error(f"  Method '{method_name}' not found")
            all_methods_found = False
        else:
            # Check if it's abstract
            if not method["is_abstract"]:
                print_warning(f"  Method '{method_name}' exists but is not abstract")
                all_methods_found = False
            else:
                # Validate signature
                # Remove 'self' from args for comparison
                method_args = [arg for arg in method["args"] if arg != "self"]

                # Check argument list
                if method_args != expected_args:
                    print_error(
                        f"  Method '{method_name}' has incorrect arguments: "
                        f"expected {expected_args}, got {method_args}"
                    )
                    all_methods_found = False
                # Check return type
                elif method["return_type"] != expected_return:
                    print_error(
                        f"  Method '{method_name}' has incorrect return type: "
                        f"expected '{expected_return}', got '{method['return_type']}'"
                    )
                    all_methods_found = False
                else:
                    print_success(f"  Method '{method_name}' found (abstract, signature correct)")

    return all_methods_found


def verify_hook_decorator() -> bool:
    """Verify @hook decorator exists with correct signature."""
    print_section("2. Hook Decorator")

    decorators_file = PROJECT_ROOT / "src/file_organizer/plugins/sdk/decorators.py"
    if not decorators_file.exists():
        print_error(f"Source file not found: {decorators_file}")
        return False

    func_info = extract_function_signature(decorators_file, "hook")
    if not func_info:
        print_error("hook() decorator function not found")
        return False

    print_success(f"hook() decorator found in {decorators_file}")

    # Check signature: hook(event: HookEvent | str, *, priority: int = 10)
    all_correct = True
    args = func_info.get("args", [])
    kwonlyargs = func_info.get("kwonlyargs", [])
    defaults = func_info.get("defaults", [])
    return_type = func_info.get("return_type")

    if args and args[0] == "event: HookEvent | str":
        print_success("  Parameter 'event' has correct type hint (HookEvent | str)")
    else:
        print_error(f"  Parameter 'event' signature: {args or 'missing'}")
        all_correct = False

    if (
        kwonlyargs
        and len(kwonlyargs) > 0
        and kwonlyargs[0] == "priority: int"
        and defaults
        and len(defaults) > 0
        and defaults[0] == "10"
    ):
        print_success("  Parameter 'priority' is keyword-only with default")
    else:
        print_error(
            f"  Parameter 'priority' signature: kwonlyargs={kwonlyargs or 'missing'}, "
            f"defaults={defaults or 'missing'}"
        )
        all_correct = False

    if return_type == "Callable[[F], F]":
        print_success("  Return type is Callable[[F], F]")
    else:
        print_error(f"  Return type: expected 'Callable[[F], F]', got '{return_type}'")
        all_correct = False

    return all_correct


def verify_hook_event_enum() -> bool:
    """Verify HookEvent enum exists with correct values."""
    print_section("3. HookEvent Enum")

    hooks_file = PROJECT_ROOT / "src/file_organizer/plugins/api/hooks.py"
    if not hooks_file.exists():
        print_error(f"Source file not found: {hooks_file}")
        return False

    enum_values = extract_enum_values(hooks_file, "HookEvent")
    if not enum_values:
        print_error("HookEvent enum not found")
        return False

    print_success(f"HookEvent enum found in {hooks_file}")
    print_success(f"  Found {len(enum_values)} events: {', '.join(enum_values)}")

    # Check for event values used in documentation
    documented_events = ["file.organized", "file.scanned"]
    for event in documented_events:
        if event in enum_values:
            print_success(f"  Event '{event}' exists")
        else:
            print_error(f"  Event '{event}' not found in enum")
            return False

    return True


def verify_plugin_metadata() -> bool:
    """Verify PluginMetadata dataclass fields."""
    print_section("4. PluginMetadata Dataclass")

    base_file = PROJECT_ROOT / "src/file_organizer/plugins/base.py"
    if not base_file.exists():
        print_error(f"Source file not found: {base_file}")
        return False

    dataclass_info = extract_dataclass_fields(base_file, "PluginMetadata")
    if not dataclass_info:
        print_error("PluginMetadata dataclass not found")
        return False

    print_success(f"PluginMetadata dataclass found in {base_file}")

    # Check required fields
    required_fields = ["name", "version", "author", "description"]
    optional_fields = [
        "homepage",
        "license",
        "dependencies",
        "min_organizer_version",
        "max_organizer_version",
    ]

    field_names = [f["name"] for f in dataclass_info["fields"]]

    all_found = True
    for field in required_fields:
        if field in field_names:
            field_info = next(f for f in dataclass_info["fields"] if f["name"] == field)
            print_success(f"  Required field '{field}': {field_info['type']}")
        else:
            print_error(f"  Required field '{field}' not found")
            all_found = False

    for field in optional_fields:
        if field in field_names:
            field_info = next(f for f in dataclass_info["fields"] if f["name"] == field)
            default = f" (default: {field_info['default']})" if field_info["default"] else ""
            print_success(f"  Optional field '{field}': {field_info['type']}{default}")
        else:
            print_warning(f"  Optional field '{field}' not found")

    return all_found


def verify_manifest_schema() -> bool:
    """Verify plugin.json manifest schema constants."""
    print_section("5. Manifest Schema Constants")

    base_file = PROJECT_ROOT / "src/file_organizer/plugins/base.py"
    if not base_file.exists():
        print_error(f"Source file not found: {base_file}")
        return False

    content = base_file.read_text()

    # Check if constants are defined
    if "MANIFEST_REQUIRED_FIELDS" not in content:
        print_error("MANIFEST_REQUIRED_FIELDS not found in base.py")
        return False

    if "MANIFEST_OPTIONAL_FIELDS" not in content:
        print_error("MANIFEST_OPTIONAL_FIELDS not found in base.py")
        return False

    constants = extract_constants(
        base_file,
        ["MANIFEST_REQUIRED_FIELDS", "MANIFEST_OPTIONAL_FIELDS"],
    )
    required_fields = constants.get("MANIFEST_REQUIRED_FIELDS")
    optional_fields = constants.get("MANIFEST_OPTIONAL_FIELDS")

    if not isinstance(required_fields, dict):
        print_error("MANIFEST_REQUIRED_FIELDS could not be parsed as a dictionary")
        return False

    if not isinstance(optional_fields, dict):
        print_error("MANIFEST_OPTIONAL_FIELDS could not be parsed as a dictionary")
        return False

    # Define authoritative schema
    expected_required = {"name", "version", "author", "description", "entry_point"}
    expected_optional = {
        "homepage",
        "license",
        "dependencies",
        "min_organizer_version",
        "max_organizer_version",
        "allowed_paths",
    }

    # Validate MANIFEST_REQUIRED_FIELDS
    actual_required_keys = set(required_fields.keys())
    missing_required = expected_required - actual_required_keys
    extra_required = actual_required_keys - expected_required

    all_valid = True

    if missing_required:
        print_error(
            f"MANIFEST_REQUIRED_FIELDS missing expected keys: {', '.join(sorted(missing_required))}"
        )
        all_valid = False
    if extra_required:
        print_error(
            f"MANIFEST_REQUIRED_FIELDS has unexpected keys: {', '.join(sorted(extra_required))}"
        )
        all_valid = False

    if not missing_required and not extra_required:
        print_success("MANIFEST_REQUIRED_FIELDS found in base.py")
        for field in sorted(required_fields.keys()):
            print_success(f"  {field}")
    else:
        print_error("MANIFEST_REQUIRED_FIELDS has schema drift")

    # Validate MANIFEST_OPTIONAL_FIELDS
    actual_optional_keys = set(optional_fields.keys())
    missing_optional = expected_optional - actual_optional_keys
    extra_optional = actual_optional_keys - expected_optional

    if missing_optional:
        print_error(
            f"MANIFEST_OPTIONAL_FIELDS missing expected keys: {', '.join(sorted(missing_optional))}"
        )
        all_valid = False
    if extra_optional:
        print_error(
            f"MANIFEST_OPTIONAL_FIELDS has unexpected keys: {', '.join(sorted(extra_optional))}"
        )
        all_valid = False

    if not missing_optional and not extra_optional:
        print_success("\nMANIFEST_OPTIONAL_FIELDS found in base.py")
        for field in sorted(optional_fields.keys()):
            print_success(f"  {field}")
    else:
        print_error("MANIFEST_OPTIONAL_FIELDS has schema drift")

    return all_valid


def verify_documentation_usage() -> bool:
    """Verify that documented code uses correct API names."""
    print_section("6. Documentation API Usage")

    doc_file = PROJECT_ROOT / "docs/developer/plugin-development.md"
    if not doc_file.exists():
        print_error(f"Documentation file not found: {doc_file}")
        return False

    content = doc_file.read_text(encoding="utf-8")

    checks = [
        ("class.*Plugin", "Plugin class usage"),
        ("def on_load", "on_load() lifecycle method"),
        ("def on_enable", "on_enable() lifecycle method"),
        ("def on_disable", "on_disable() lifecycle method"),
        ("def on_unload", "on_unload() lifecycle method"),
        ("def get_metadata", "get_metadata() method"),
        ("PluginMetadata", "PluginMetadata dataclass"),
        ("@hook", "@hook decorator usage"),
        ('"file\\.organized"', "HookEvent.FILE_ORGANIZED usage"),
        ("entry_point", "plugin.json entry_point field"),
    ]

    all_found = True
    for pattern, description in checks:
        if re.search(pattern, content, re.IGNORECASE):
            print_success(f"  {description} found in documentation")
        else:
            print_error(f"  {description} NOT found in documentation")
            all_found = False

    return all_found


def main() -> None:
    """Run all verification checks."""
    print(f"\n{BOLD}API Verification Report{RESET}")
    print("=" * 50)

    results = [
        verify_plugin_class(),
        verify_hook_decorator(),
        verify_hook_event_enum(),
        verify_plugin_metadata(),
        verify_manifest_schema(),
        verify_documentation_usage(),
    ]

    print_section("Summary")

    passed = sum(results)
    total = len(results)

    if passed == total:
        print(f"\n{GREEN}{BOLD}✓ All {total} verification checks passed!{RESET}\n")
        sys.exit(0)
    else:
        print(f"\n{RED}{BOLD}✗ {total - passed}/{total} checks failed{RESET}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
