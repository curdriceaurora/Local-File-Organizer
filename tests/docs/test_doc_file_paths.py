"""Test that file paths referenced in documentation exist in the repository.

Extracts backtick-wrapped paths starting with src/, core/, tests/, scripts/,
or .github/ from all docs/**/*.md files and asserts each path exists relative
to the repo root.

Catches content drift where docs reference renamed/moved files, e.g.:
  core/file_organizer.py renamed to core/organizer.py
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
DOCS_DIR = REPO_ROOT / "docs"

# Match backtick-wrapped repo-relative paths such as:
#   `src/file_organizer/utils/text_processing.py`
#   `tests/docs/conftest.py`
#   `.github/workflows/ci.yml`
# Requires a file extension to avoid matching bare directory references.
PATH_PATTERN = re.compile(r"`((?:src|core|tests|scripts|\.github)/[^`\s]+\.[a-zA-Z]+)`")

# Directories under docs/ that contain design/planning documents.
# These files list files-to-be-created or modified as future work and are
# intentionally allowed to reference paths that do not yet exist.
EXCLUDED_DOC_DIRS = {
    "plans",
}

# Known paths that are referenced in docs but do not exist in the repository.
# Add a path here (with a comment) when it is an intentional code example or
# when the documentation itself needs to be updated separately.
#
# Format: frozenset of strings matching exactly what the regex captures.
ALLOWLIST: frozenset[str] = frozenset()


def _is_glob_pattern(path: str) -> bool:
    """Return True if path contains shell glob characters."""
    return "*" in path or "?" in path or "[" in path


def _excluded_doc_dir(md_file: Path) -> bool:
    """Return True if md_file lives inside one of the excluded doc directories."""
    try:
        rel = md_file.relative_to(DOCS_DIR)
    except ValueError:
        return False
    # Check whether the first path component is an excluded directory name.
    return rel.parts[0] in EXCLUDED_DOC_DIRS if rel.parts else False


def _get_doc_path_params() -> list[tuple[str, str]]:
    """Collect (doc_file_str, referenced_path) pairs from all docs.

    Returns only pairs that:
    - Are not from excluded doc directories (e.g. docs/plans/)
    - Do not contain glob wildcards
    - Are not in the ALLOWLIST
    """
    params: list[tuple[str, str]] = []
    for md_file in sorted(DOCS_DIR.rglob("*.md")):
        if _excluded_doc_dir(md_file):
            continue
        text = md_file.read_text(encoding="utf-8")
        doc_label = str(md_file.relative_to(REPO_ROOT))
        for match in PATH_PATTERN.finditer(text):
            ref_path = match.group(1)
            if _is_glob_pattern(ref_path):
                continue
            if ref_path in ALLOWLIST:
                continue
            params.append((doc_label, ref_path))
    # Deduplicate: same (doc, path) from multiple matches should appear once.
    seen: set[tuple[str, str]] = set()
    unique: list[tuple[str, str]] = []
    for pair in params:
        if pair not in seen:
            seen.add(pair)
            unique.append(pair)
    return unique


@pytest.mark.unit
@pytest.mark.parametrize("doc_file,ref_path", _get_doc_path_params())
def test_referenced_path_exists(doc_file: str, ref_path: str) -> None:
    """Paths referenced in docs must exist in the repository.

    If this test fails the documentation references a file that no longer
    exists (or never did).  Either:
      1. Update the documentation to use the current path, or
      2. Add the path to ALLOWLIST with a comment explaining why.
    """
    assert (REPO_ROOT / ref_path).exists(), (
        f"{doc_file}: references non-existent path '{ref_path}'\n"
        f"  Full path checked: {REPO_ROOT / ref_path}\n"
        f"  Fix: update the doc to use the correct path, or add to ALLOWLIST."
    )
