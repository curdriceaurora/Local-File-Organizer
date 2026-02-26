"""Test that all internal links in documentation resolve to existing files.

Validates:
- Internal markdown links [text](path) resolve to existing files
- mkdocs.yml nav entries point to existing files
- No case-mismatch issues (troubleshooting.md vs TROUBLESHOOTING.md)
"""

from __future__ import annotations
import pytest

import re
from pathlib import Path

from tests.docs.conftest import DOCS_DIR, MKDOCS_FILE


@pytest.mark.unit
class TestMkdocsNavIntegrity:
    """Validate that mkdocs.yml nav entries exist as files."""

    def _extract_nav_paths(self, nav: list | dict | str, paths: list[str]) -> None:
        """Recursively extract all file paths from nav structure."""
        if isinstance(nav, str):
            paths.append(nav)
        elif isinstance(nav, list):
            for item in nav:
                self._extract_nav_paths(item, paths)
        elif isinstance(nav, dict):
            for value in nav.values():
                self._extract_nav_paths(value, paths)

    def test_mkdocs_yaml_exists(self) -> None:
        """mkdocs.yml must exist."""
        assert MKDOCS_FILE.exists(), f"mkdocs.yml not found at {MKDOCS_FILE}"

    def test_mkdocs_nav_files_exist(self, mkdocs_config: dict, docs_dir: Path) -> None:
        """Every file referenced in the mkdocs.yml nav must exist."""
        nav = mkdocs_config.get("nav", [])
        nav_paths: list[str] = []
        self._extract_nav_paths(nav, nav_paths)

        missing = []
        for nav_path in nav_paths:
            # nav paths are relative to docs_dir
            full_path = docs_dir / nav_path
            if not full_path.exists():
                missing.append(nav_path)

        assert not missing, (
            f"mkdocs.yml nav references {len(missing)} file(s) that don't exist:\n"
            + "\n".join(f"  - {p}" for p in sorted(missing))
        )

    def test_no_case_mismatch_in_nav(self, mkdocs_config: dict, docs_dir: Path) -> None:
        """Nav entries must use exact case matching the filesystem."""
        nav = mkdocs_config.get("nav", [])
        nav_paths: list[str] = []
        self._extract_nav_paths(nav, nav_paths)

        # Build a set of actual filenames (lowercase → actual)
        actual_files_lower = {
            str(f.relative_to(docs_dir)).lower(): f.relative_to(docs_dir)
            for f in docs_dir.rglob("*.md")
        }

        mismatched = []
        for nav_path in nav_paths:
            nav_lower = nav_path.lower()
            if nav_lower in actual_files_lower:
                actual = str(actual_files_lower[nav_lower])
                if nav_path != actual:
                    mismatched.append(f"  nav: '{nav_path}' → actual: '{actual}'")

        assert not mismatched, "Case mismatches found in mkdocs.yml nav:\n" + "\n".join(mismatched)


@pytest.mark.unit
class TestInternalLinkIntegrity:
    """Validate that internal links in markdown files resolve to existing files."""

    def _resolve_link(self, source_file: Path, link: str) -> Path:
        """Resolve a relative link from a source markdown file."""
        # Strip anchor fragments
        link = link.split("#")[0]
        if not link:
            return source_file  # Anchor-only link, always valid

        if link.startswith("/"):
            # Absolute path relative to docs dir
            return DOCS_DIR / link.lstrip("/")
        else:
            # Relative to source file's directory
            return (source_file.parent / link).resolve()

    def test_internal_links_resolve(self, all_doc_files: list[Path]) -> None:
        """All internal markdown links must resolve to existing files."""
        broken = []

        for md_file in all_doc_files:
            content = md_file.read_text(encoding="utf-8")
            links = []

            # Extract [text](path) links
            for match in re.finditer(r"\[(?:[^\]]+)\]\(([^)]+)\)", content):
                href = match.group(1)
                # Skip external links
                if href.startswith("http://") or href.startswith("https://"):
                    continue
                # Skip mailto
                if href.startswith("mailto:"):
                    continue
                links.append(href)

            for link in links:
                target = self._resolve_link(md_file, link)
                if not target.exists():
                    rel_source = md_file.relative_to(DOCS_DIR)
                    broken.append(f"  {rel_source}: [{link}] → {target} (not found)")

        assert not broken, (
            f"Found {len(broken)} broken internal link(s):\n"
            + "\n".join(broken[:20])
            + ("\n  ... (truncated)" if len(broken) > 20 else "")
        )
