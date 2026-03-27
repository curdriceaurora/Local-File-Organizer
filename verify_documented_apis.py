#!/usr/bin/env python3
"""Verify all documented APIs match source code exactly."""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

# ANSI color codes for output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"
BOLD = "\033[1m"


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
    content = source_file.read_text()
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
    content = source_file.read_text()
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
    content = source_file.read_text()
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
    content = source_file.read_text()
    tree = ast.parse(content)

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == enum_name:
            values = []
            for item in node.body:
                if isinstance(item, ast.Assign):
                    for target in item.targets:
                        if isinstance(target, ast.Name):
                            values.append(target.id)
            return values

    return []


def extract_constants(source_file: Path, constant_names: list[str]) -> dict[str, Any]:
    """Extract constant values."""
    content = source_file.read_text()
    tree = ast.parse(content)

    constants = {}

    # Walk the module body directly to preserve top-level assignments
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in constant_names:
                    # Try to evaluate the value
                    try:
                        value = ast.literal_eval(node.value)
                        constants[target.id] = value
                    except (ValueError, TypeError, SyntaxError):
                        # Can't evaluate, store the unparsed representation
                        constants[target.id] = ast.unparse(node.value)

    return constants


def verify_plugin_class() -> bool:
    """Verify Plugin base class exists with correct methods."""
    print_section("1. Plugin Base Class")

    base_file = Path("src/file_organizer/plugins/base.py")
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
    for method_name, _expected_args, _expected_return in required_methods:
        method = next((m for m in class_info["methods"] if m["name"] == method_name), None)
        if not method:
            print_error(f"  Method '{method_name}' not found")
            all_methods_found = False
        else:
            # Check if it's abstract
            if not method["is_abstract"]:
                print_warning(f"  Method '{method_name}' exists but is not abstract")
            else:
                print_success(f"  Method '{method_name}' found (abstract)")

    return all_methods_found


def verify_hook_decorator() -> bool:
    """Verify @hook decorator exists with correct signature."""
    print_section("2. Hook Decorator")

    decorators_file = Path("src/file_organizer/plugins/sdk/decorators.py")
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

    if args and args[0] == "event: HookEvent | str":
        print_success("  Parameter 'event' has correct type hint (HookEvent | str)")
    else:
        print_error(f"  Parameter 'event' signature: {args or 'missing'}")
        all_correct = False

    if kwonlyargs and "priority" in kwonlyargs[0]:
        print_success("  Parameter 'priority' is keyword-only with default")
    else:
        print_error(f"  Parameter 'priority' signature: {kwonlyargs or 'missing'}")
        all_correct = False

    return all_correct


def verify_hook_event_enum() -> bool:
    """Verify HookEvent enum exists with correct values."""
    print_section("3. HookEvent Enum")

    hooks_file = Path("src/file_organizer/plugins/api/hooks.py")
    if not hooks_file.exists():
        print_error(f"Source file not found: {hooks_file}")
        return False

    enum_values = extract_enum_values(hooks_file, "HookEvent")
    if not enum_values:
        print_error("HookEvent enum not found")
        return False

    print_success(f"HookEvent enum found in {hooks_file}")
    print_success(f"  Found {len(enum_values)} events: {', '.join(enum_values)}")

    # Check for events used in documentation
    documented_events = ["FILE_ORGANIZED", "FILE_SCANNED"]
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

    base_file = Path("src/file_organizer/plugins/base.py")
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

    base_file = Path("src/file_organizer/plugins/base.py")
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

    print_success("MANIFEST_REQUIRED_FIELDS found in base.py")

    # Extract the fields from MANIFEST_REQUIRED_FIELDS
    required_pattern = r"MANIFEST_REQUIRED_FIELDS.*?{([^}]+)}"
    required_match = re.search(required_pattern, content, re.DOTALL)
    if required_match:
        required_fields = re.findall(r'"([^"]+)":\s*\w+', required_match.group(1))
        for field in required_fields:
            print_success(f"  {field}")

    print_success("\nMANIFEST_OPTIONAL_FIELDS found in base.py")

    # Extract the fields from MANIFEST_OPTIONAL_FIELDS
    optional_pattern = r"MANIFEST_OPTIONAL_FIELDS.*?{([^}]+)}"
    optional_match = re.search(optional_pattern, content, re.DOTALL)
    if optional_match:
        optional_fields = re.findall(r'"([^"]+)":', optional_match.group(1))
        for field in optional_fields:
            print_success(f"  {field}")

    return True


def verify_documentation_usage() -> bool:
    """Verify that documented code uses correct API names."""
    print_section("6. Documentation API Usage")

    doc_file = Path("docs/developer/plugin-development.md")
    if not doc_file.exists():
        print_error(f"Documentation file not found: {doc_file}")
        return False

    content = doc_file.read_text()

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
        exit(0)
    else:
        print(f"\n{RED}{BOLD}✗ {total - passed}/{total} checks failed{RESET}\n")
        exit(1)


if __name__ == "__main__":
    main()
