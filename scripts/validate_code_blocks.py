#!/usr/bin/env python3
"""Validate Python code blocks in markdown documentation."""

from __future__ import annotations

import argparse
import ast
import sys
import textwrap
from pathlib import Path


def extract_python_code_blocks(markdown_content: str) -> list[tuple[int, str]]:
    """Extract all Python code blocks from markdown content.

    Returns:
        List of tuples (line_number, code_content)
    """
    code_blocks = []
    lines = markdown_content.split("\n")
    in_code_block = False
    is_python_block = False
    current_block = []
    block_start_line = 0

    for i, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped == "```python" or stripped.startswith("```python "):
            in_code_block = True
            is_python_block = True
            current_block = []
            block_start_line = i
        elif stripped.startswith("```") and in_code_block:
            in_code_block = False
            if is_python_block and current_block:
                code_blocks.append((block_start_line, "\n".join(current_block)))
            is_python_block = False
            current_block = []
        elif in_code_block and is_python_block:
            current_block.append(line)

    if in_code_block and is_python_block and current_block:
        print(
            f"Error: Unclosed Python code block starting at line {block_start_line}",
            file=sys.stderr,
        )
        sys.exit(1)

    return code_blocks


def validate_python_code(code: str, line_number: int) -> tuple[bool, str]:
    """Validate Python code syntax using ast.parse.

    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        ast.parse(textwrap.dedent(code))
        return True, ""
    except SyntaxError as e:
        error_msg = f"Syntax error at line {line_number + (e.lineno or 1)}: {e.msg}"
        if e.text:
            error_msg += f"\n  {e.text.strip()}"
        return False, error_msg
    except (ValueError, RecursionError) as e:
        return False, f"Validation error at line {line_number}: {e!s}"


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Validate Python code blocks in markdown documentation."
    )
    parser.add_argument(
        "doc_path",
        nargs="?",
        default="./docs/developer/plugin-development.md",
        help="Markdown file to validate (default: %(default)s)",
    )
    return parser.parse_args()


def main() -> None:
    """Main validation function."""
    args = parse_args()
    doc_path = Path(args.doc_path)

    if not doc_path.exists():
        print(f"Error: Documentation file not found: {doc_path}")
        sys.exit(1)

    print(f"Validating Python code blocks in {doc_path}...")
    print()

    content = doc_path.read_text(encoding="utf-8")
    code_blocks = extract_python_code_blocks(content)

    print(f"Found {len(code_blocks)} Python code block(s)")
    print()

    errors = []

    for i, (line_num, code) in enumerate(code_blocks, start=1):
        print(f"Block {i} (starting at line {line_num})...", end=" ")
        is_valid, error_msg = validate_python_code(code, line_num)

        if is_valid:
            print("✓ Valid")
        else:
            print("✗ Invalid")
            errors.append((i, line_num, error_msg))

    print()

    if errors:
        print("=" * 70)
        print("VALIDATION FAILED")
        print("=" * 70)
        print()
        for block_num, line_num, error_msg in errors:
            print(f"Block {block_num} (line {line_num}):")
            print(f"  {error_msg}")
            print()
        sys.exit(1)
    else:
        print("=" * 70)
        print("ALL CODE BLOCKS ARE VALID ✓")
        print("=" * 70)
        sys.exit(0)


if __name__ == "__main__":
    main()
