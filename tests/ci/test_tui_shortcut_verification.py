"""Verify that *global* TUI keyboard shortcuts in docs/tui.md match app bindings.

This script checks the Global shortcuts table in ``docs/tui.md`` against
``FileOrganizerApp.BINDINGS``. It can run standalone
(``python tests/ci/test_tui_shortcut_verification.py``) when the package is
installed (e.g. ``pip install -e .``), or via pytest as part of the regular suite.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

DOCS_TUI = PROJECT_ROOT / "docs" / "tui.md"

# Map human-readable doc keys to Textual binding key strings.
_KEY_MAP: dict[str, str] = {
    "q": "q",
    "?": "question_mark",
    "tab": "tab",
    "ctrl+c": "ctrl+c",
}

# Keys that are documented but handled by Textual internally (not in BINDINGS).
_BUILTIN_KEYS: set[str] = {"ctrl+c"}

# Range patterns in shortcut tables — expands to individual numeric keys.
# F-key notation (e.g. `F1`–`F7`) is considered stale and triggers a failure.
_FKEY_RANGE_PATTERN = re.compile(r"`F\d+`")
_NUM_RANGE_PATTERN = re.compile(r"`(\d+)`\s*[–-]\s*`(\d+)`")


def _parse_global_shortcuts(text: str) -> set[str]:
    """Extract shortcut keys from the Global shortcuts table in *text*.

    Returns normalised lowercase key names (e.g. ``{"q", "?", "tab"}``).
    """
    # Find the Global shortcuts table (between "### Global" and next "###").
    match = re.search(r"### Global\s*\n(.*?)(?=\n### |\n## |\Z)", text, re.DOTALL)
    if not match:
        return set()

    table_text = match.group(1)
    keys: set[str] = set()

    for line in table_text.splitlines():
        # Match table rows like "| `q` / `Ctrl+c` | Quit |"
        cell_match = re.match(r"\|\s*(.+?)\s*\|", line)
        if not cell_match or cell_match.group(1).strip().startswith("-"):
            continue

        cell = cell_match.group(1)
        # Fail fast if stale F-key notation (e.g. `F1`) is present
        if _FKEY_RANGE_PATTERN.search(cell):
            raise ValueError(
                "F-key notation (e.g. `F1`–`F7`) detected in Global shortcuts "
                "table. Use numeric key ranges instead (e.g. `1`–`7`) so that "
                "the documentation matches the actual TUI bindings."
            )

        # Handle numeric ranges like "`1`–`8`"
        nrange = _NUM_RANGE_PATTERN.search(cell)
        if nrange:
            start, end = int(nrange.group(1)), int(nrange.group(2))
            for n in range(start, end + 1):
                keys.add(str(n))
            continue

        # Split on "/" to handle "q / Ctrl+c"
        for part in cell.split("/"):
            part = part.strip().strip("`").strip()
            if part and part.lower() != "key":
                keys.add(part.lower())

    return keys


def _get_app_binding_keys() -> set[str]:
    """Import FileOrganizerApp and return its binding key strings."""
    from file_organizer.tui.app import FileOrganizerApp

    return {b.key for b in FileOrganizerApp.BINDINGS}


@pytest.mark.ci
class TestTuiShortcutVerification:
    """Ensure documented TUI shortcuts have matching code bindings."""

    def test_docs_tui_exists(self) -> None:
        """The TUI documentation file must exist."""
        assert DOCS_TUI.exists(), f"docs/tui.md not found at {DOCS_TUI}"

    def test_global_shortcuts_documented(self) -> None:
        """Every global shortcut in docs/tui.md must be present in BINDINGS."""
        doc_text = DOCS_TUI.read_text(encoding="utf-8")
        doc_keys = _parse_global_shortcuts(doc_text)
        assert doc_keys, "Failed to parse any shortcuts from docs/tui.md"

        binding_keys = _get_app_binding_keys()

        missing: list[str] = []
        for doc_key in sorted(doc_keys):
            if doc_key in _BUILTIN_KEYS:
                continue
            mapped = _KEY_MAP.get(doc_key, doc_key)
            if mapped not in binding_keys:
                missing.append(f"{doc_key!r} (expected binding key {mapped!r})")

        assert not missing, (
            f"Documented shortcuts missing from FileOrganizerApp.BINDINGS: {', '.join(missing)}"
        )

    def test_bindings_documented(self) -> None:
        """Every BINDINGS key should appear in the Global shortcuts table."""
        doc_text = DOCS_TUI.read_text(encoding="utf-8")
        doc_keys = _parse_global_shortcuts(doc_text)
        binding_keys = _get_app_binding_keys()

        # Build reverse map: binding key -> doc key
        reverse_map: dict[str, str] = {v: k for k, v in _KEY_MAP.items()}

        undocumented: list[str] = []
        for bk in sorted(binding_keys):
            doc_equiv = reverse_map.get(bk, bk)
            if doc_equiv not in doc_keys and bk not in doc_keys:
                undocumented.append(f"{bk!r} (doc equivalent: {doc_equiv!r})")

        assert not undocumented, (
            f"BINDINGS keys not documented in docs/tui.md Global table: {', '.join(undocumented)}"
        )


def main() -> int:
    """Run verification standalone (for CI job)."""
    doc_text = DOCS_TUI.read_text(encoding="utf-8")
    try:
        doc_keys = _parse_global_shortcuts(doc_text)
    except ValueError as e:
        print(f"FAIL: {e}")
        return 1
    if not doc_keys:
        print("FAIL: Could not parse any shortcuts from docs/tui.md")
        return 1

    binding_keys = _get_app_binding_keys()

    print(f"Documented global shortcuts: {sorted(doc_keys)}")
    print(f"App BINDINGS keys:           {sorted(binding_keys)}")

    errors = 0

    # Check doc -> code
    for doc_key in sorted(doc_keys):
        if doc_key in _BUILTIN_KEYS:
            print(f"  SKIP {doc_key!r} (built-in)")
            continue
        mapped = _KEY_MAP.get(doc_key, doc_key)
        if mapped in binding_keys:
            print(f"  OK   {doc_key!r} -> {mapped!r}")
        else:
            print(f"  FAIL {doc_key!r} -> {mapped!r} NOT in BINDINGS")
            errors += 1

    # Check code -> doc
    reverse_map: dict[str, str] = {v: k for k, v in _KEY_MAP.items()}
    for bk in sorted(binding_keys):
        doc_equiv = reverse_map.get(bk, bk)
        if doc_equiv not in doc_keys and bk not in doc_keys:
            print(f"  FAIL BINDINGS key {bk!r} not documented")
            errors += 1

    if errors:
        print(f"\nFAIL: {errors} shortcut(s) out of sync")
        return 1

    print("\nOK: All shortcuts in sync")
    return 0


if __name__ == "__main__":
    sys.exit(main())
