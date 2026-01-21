#!/usr/bin/env python3
"""
Automated fix script for CodeRabbit PR #67 review comments.
Addresses 95 review issues systematically.
"""

import re
import sys
from pathlib import Path
from typing import List, Tuple

# Base directory
BASE_DIR = Path(__file__).parent / "file_organizer_v2"


def add_blank_lines_around_code_blocks(content: str) -> str:
    """Fix MD031: Add blank lines before/after fenced code blocks."""
    lines = content.split('\n')
    result = []
    prev_blank = True

    for i, line in enumerate(lines):
        is_fence = line.strip().startswith('```')

        if is_fence:
            # Add blank line before fence if previous line wasn't blank
            if result and not prev_blank:
                result.append('')
            result.append(line)
            # Mark that we need blank after closing fence
            prev_blank = False
        else:
            result.append(line)
            prev_blank = line.strip() == ''

    # Post-process: ensure blank line after closing fences
    final = []
    for i, line in enumerate(result):
        final.append(line)
        if line.strip().startswith('```') and i > 0:
            # Check if this is closing fence (previous fence was opening)
            count_before = sum(1 for l in result[:i] if l.strip().startswith('```'))
            if count_before % 2 == 0:  # This is closing fence
                if i < len(result) - 1 and result[i + 1].strip() != '':
                    final.append('')

    return '\n'.join(final)


def remove_unnecessary_fstrings(content: str) -> str:
    """Remove f-string prefix from literals without placeholders."""
    # Match f"..." or f'...' without {placeholders}
    pattern = r'f(["\'])(?:(?!\1|\\).|\\.)*?\1'

    def replace_if_no_placeholder(match):
        full_string = match.group(0)
        if '{' not in full_string:
            return full_string[1:]  # Remove leading 'f'
        return full_string

    return re.sub(pattern, replace_if_no_placeholder, content)


def fix_typing_imports(content: str) -> str:
    """Replace typing.List/Dict/Tuple with PEP 585 built-ins."""
    # Update import line
    content = re.sub(
        r'from typing import ([^(\n]*)([LD]ist|Tuple)([^(\n]*)',
        lambda m: f"from typing import {m.group(1)}{m.group(3)}".replace(', ,', ',').strip(', '),
        content
    )

    # Replace in annotations
    content = content.replace('List[', 'list[')
    content = content.replace('Dict[', 'dict[')
    content = content.replace('Tuple[', 'tuple[')
    content = content.replace(': List', ': list')
    content = content.replace(': Dict', ': dict')
    content = content.replace(': Tuple', ': tuple')

    return content


def fix_exception_chaining(content: str) -> str:
    """Add 'from e' to exception re-raises."""
    # Pattern: raise SomeError(...) after except ... as e:
    pattern = r'(except .+ as e:.*?)(raise \w+Error\([^)]+\)(?! from))'
    return re.sub(pattern, r'\1\2 from e', content, flags=re.DOTALL)


def remove_sys_path_manipulation(content: str) -> str:
    """Remove sys.path.insert lines."""
    lines = content.split('\n')
    result = []
    skip_next_blank = False

    for line in lines:
        if 'sys.path.insert' in line or 'sys.path.append' in line:
            skip_next_blank = True
            continue
        if skip_next_blank and line.strip() == '':
            skip_next_blank = False
            continue
        result.append(line)
        skip_next_blank = False

    return '\n'.join(result)


def fix_unused_imports(content: str) -> str:
    """Remove specific unused imports."""
    # Remove 'import os' if not used
    if 'import os' in content and not re.search(r'\bos\.[a-z]', content):
        content = re.sub(r'^import os\n', '', content, flags=re.MULTILINE)

    # Remove 'import numpy as np' if not used
    if 'import numpy as np' in content and not re.search(r'\bnp\.[a-z]', content):
        content = re.sub(r'^import numpy as np\n', '', content, flags=re.MULTILINE)

    return content


def fix_unused_variables(content: str) -> str:
    """Rename unused loop variables to _varname."""
    # Common patterns: for x, y in items where y is unused
    patterns = [
        (r'for (\w+), (count|metadata|hash_key) in', r'for \1, _\2 in'),
        (r'enumerate\(([^)]+), 1\):\n\s+for \w+, (hash_key|file_ext) in',
         r'enumerate(\1, 1):\n    for _idx, _\2 in'),
    ]

    for pattern, replacement in patterns:
        content = re.sub(pattern, replacement, content)

    return content


def fix_file(file_path: Path, fixes: List[str]) -> bool:
    """Apply specified fixes to a file."""
    if not file_path.exists():
        print(f"  ⚠️  Not found: {file_path}")
        return False

    content = file_path.read_text()
    original = content

    for fix_name in fixes:
        if fix_name == 'md031':
            content = add_blank_lines_around_code_blocks(content)
        elif fix_name == 'fstrings':
            content = remove_unnecessary_fstrings(content)
        elif fix_name == 'typing':
            content = fix_typing_imports(content)
        elif fix_name == 'exception':
            content = fix_exception_chaining(content)
        elif fix_name == 'syspath':
            content = remove_sys_path_manipulation(content)
        elif fix_name == 'unused_imports':
            content = fix_unused_imports(content)
        elif fix_name == 'unused_vars':
            content = fix_unused_variables(content)

    if content != original:
        file_path.write_text(content)
        print(f"  ✓ Fixed: {file_path.relative_to(BASE_DIR.parent)}")
        return True
    else:
        print(f"  - No changes: {file_path.relative_to(BASE_DIR.parent)}")
        return False


def main():
    """Run all automated fixes."""
    print("🔧 Applying automated fixes for CodeRabbit review comments...")
    print()

    fixed_count = 0

    # Documentation fixes (MD031)
    print("📝 Fixing markdown formatting...")
    doc_files = [
        "docs/CLI_DEDUPE.md",
        "docs/phase4/README.md",
        "docs/phase4/undo-redo.md",
        "docs/phase4/smart-features.md",
        "README.md",
        "../STREAM_C_SUMMARY.md",
    ]
    for doc_file in doc_files:
        path = BASE_DIR / doc_file if not doc_file.startswith('..') else BASE_DIR.parent / doc_file.lstrip('../')
        if fix_file(path, ['md031']):
            fixed_count += 1

    print()
    print("🐍 Fixing Python code issues...")

    # CLI files - f-strings
    print("  Removing unnecessary f-strings...")
    cli_files = [
        "src/file_organizer/cli/autotag.py",
        "src/file_organizer/cli/profile.py",
        "src/file_organizer/cli/undo_redo.py",
        "src/file_organizer/cli/dedupe.py",
    ]
    for cli_file in cli_files:
        if fix_file(BASE_DIR / cli_file, ['fstrings']):
            fixed_count += 1

    # Type annotations
    print("  Updating type annotations...")
    type_files = [
        "src/file_organizer/models/analytics.py",
        "src/file_organizer/services/auto_tagging/tag_recommender.py",
        "src/file_organizer/services/deduplication/reporter.py",
        "src/file_organizer/services/deduplication/quality.py",
        "src/file_organizer/services/deduplication/detector.py",
    ]
    for type_file in type_files:
        if fix_file(BASE_DIR / type_file, ['typing']):
            fixed_count += 1

    # Exception chaining
    print("  Adding exception chaining...")
    exception_files = [
        "src/file_organizer/cli/profile.py",
        "src/file_organizer/services/deduplication/backup.py",
        "src/file_organizer/services/deduplication/embedder.py",
        "src/file_organizer/services/deduplication/extractor.py",
        "src/file_organizer/services/deduplication/image_dedup.py",
    ]
    for exc_file in exception_files:
        if fix_file(BASE_DIR / exc_file, ['exception']):
            fixed_count += 1

    # sys.path removals
    print("  Removing sys.path manipulations...")
    syspath_files = [
        "examples/demo_comparison_viewer.py",
        "examples/image_dedup_example.py",
        "scripts/test_dedupe_cli.py",
    ]
    for sp_file in syspath_files:
        if fix_file(BASE_DIR / sp_file, ['syspath']):
            fixed_count += 1

    # Unused imports/variables
    print("  Cleaning unused imports and variables...")
    unused_files = [
        "src/file_organizer/history/tracker.py",
        "src/file_organizer/services/deduplication/image_dedup.py",
        "examples/image_dedup_example.py",
        "src/file_organizer/services/auto_tagging/tag_learning.py",
        "src/file_organizer/services/deduplication/backup.py",
    ]
    for unused_file in unused_files:
        if fix_file(BASE_DIR / unused_file, ['unused_imports', 'unused_vars']):
            fixed_count += 1

    print()
    print(f"✅ Applied automated fixes to {fixed_count} files")
    print()
    print("⚠️  Manual fixes still required for:")
    print("  - Thread safety issues (database.py, backup.py)")
    print("  - SQL injection risks (tracker.py)")
    print("  - O(n²) performance issues (semantic.py, image_dedup.py)")
    print("  - Duplicate class consolidation (ImageMetadata)")
    print("  - Complex logic fixes (analytics metrics, quality assessment)")
    print()
    print("Run './fix_manual_issues.py' for guided manual fixes")


if __name__ == '__main__':
    main()
