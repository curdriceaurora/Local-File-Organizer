"""Test that file paths referenced in documentation exist in the repository.

Extracts backtick-wrapped paths starting with src/, core/, tests/, scripts/,
or .github/ from all docs/**/*.md files and asserts each path exists relative
to the repo root.

Catches content drift where docs reference renamed/moved files, e.g.:
  core/file_organizer.py renamed to core/organizer.py

Exclusion Strategy
------------------
Not every backtick-wrapped path in documentation is meant to reference a real
file.  The test filters out non-assertable references at three levels:

1. **Directory-level exclusions** (``EXCLUDED_DOC_DIRS``):
   Entire directories under ``docs/`` whose purpose is to describe *future*
   work.  Every path inside these directories is skipped because the files
   they reference may not exist yet by design.

2. **Glob-pattern exclusions** (``_is_glob_pattern``):
   Paths containing ``*``, ``?``, or ``[`` are shell-glob examples (e.g.
   ``src/**/*.py``) and cannot be resolved to a single file.  They are
   silently skipped.

3. **Per-path allowlist** (``ALLOWLIST``):
   Individual paths that appear in docs as intentional examples, illustrative
   placeholders, or references whose corresponding doc update is tracked
   separately.  Each entry must include a comment explaining *why* it is
   allowlisted so the list stays auditable.

When a new false-positive surfaces in CI, prefer fixing the doc first.
Only add to ``ALLOWLIST`` when the reference is genuinely intentional.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
DOCS_DIR = REPO_ROOT / "docs"

# ---------------------------------------------------------------------------
# Path extraction pattern
# ---------------------------------------------------------------------------
# Match backtick-wrapped repo-relative paths such as:
#   `src/file_organizer/utils/text_processing.py`
#   `tests/docs/conftest.py`
#   `.github/workflows/ci.yml`
# Requires a file extension to avoid matching bare directory references.
PATH_PATTERN = re.compile(r"`((?:src|core|tests|scripts|\.github)/[^`\s]+\.[a-zA-Z]+)`")

# ---------------------------------------------------------------------------
# Exclusion layer 1 of 3: directory-level exclusions
# ---------------------------------------------------------------------------
# Directories under docs/ that contain design/planning documents.
# These files describe work-in-progress or future features and intentionally
# reference paths that do not yet exist.
#
# To add a new excluded directory:
#   1. Add the directory name (relative to docs/) to the set below.
#   2. Include a comment explaining what kind of content lives there.
EXCLUDED_DOC_DIRS: set[str] = {
    # Design and planning specs that list files-to-be-created.
    "plans",
}

# ---------------------------------------------------------------------------
# Exclusion layer 3 of 3: per-path allowlist
# (Layer 2 is the _is_glob_pattern() filter applied in _get_doc_path_params)
# ---------------------------------------------------------------------------
# Individual paths referenced in docs that are *not* expected to exist on disk.
# Every entry MUST have an inline comment stating the reason for allowlisting.
#
# Categories of valid allowlist entries:
#   - Illustrative examples:  paths used in code-block tutorials that show
#     hypothetical usage rather than real file locations.
#   - Tracked doc debt:  paths whose docs need updating in a separate PR;
#     link the tracking issue in the comment.
#   - Template placeholders:  paths inside doc templates (e.g. _template.md)
#     that show the expected format but don't map to real files.
#
# To add a new entry:
#   1. Append the exact string the regex captures.
#   2. Add an inline ``# reason`` comment on the same line.
#   3. Open a tracking issue if the root cause is a stale doc reference.
#
# Format: frozenset of strings matching exactly what PATH_PATTERN captures.
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
