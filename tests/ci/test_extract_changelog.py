"""Tests for scripts/extract_changelog.py (release-notes extraction)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add scripts dir to path so we can import extract_changelog.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))

from extract_changelog import extract_section, main

SAMPLE = """# Changelog

## [Unreleased]

## [2.0.0] - 2026-07-05

First stable release.

### Security

- Hardened copy paths.

## [2.0.0-beta.1] - 2026-07-04

### Added

- Beta stuff.
"""


@pytest.mark.unit
class TestExtractSection:
    def test_extracts_named_version(self) -> None:
        section = extract_section(SAMPLE, "2.0.0")
        assert "First stable release." in section
        assert "Hardened copy paths." in section

    def test_stops_at_next_heading(self) -> None:
        section = extract_section(SAMPLE, "2.0.0")
        # Must not bleed into the beta.1 section.
        assert "Beta stuff." not in section
        assert "## [2.0.0-beta.1]" not in section

    def test_does_not_confuse_prefix_versions(self) -> None:
        # "2.0.0" must not match the "2.0.0-beta.1" heading.
        beta = extract_section(SAMPLE, "2.0.0-beta.1")
        assert "Beta stuff." in beta
        assert "First stable release." not in beta

    def test_strips_leading_v_from_tag(self) -> None:
        assert extract_section(SAMPLE, "v2.0.0") == extract_section(SAMPLE, "2.0.0")

    def test_missing_version_raises(self) -> None:
        with pytest.raises(KeyError):
            extract_section(SAMPLE, "9.9.9")

    def test_heading_not_included(self) -> None:
        section = extract_section(SAMPLE, "2.0.0")
        assert not section.lstrip().startswith("## [")


@pytest.mark.unit
class TestMainCLI:
    def test_main_prints_section(self, capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
        changelog = tmp_path / "CHANGELOG.md"
        changelog.write_text(SAMPLE, encoding="utf-8")
        rc = main(["2.0.0", "--changelog", str(changelog)])
        out = capsys.readouterr().out
        assert rc == 0
        assert "First stable release." in out

    def test_main_missing_version_returns_1(self, tmp_path: Path) -> None:
        changelog = tmp_path / "CHANGELOG.md"
        changelog.write_text(SAMPLE, encoding="utf-8")
        assert main(["9.9.9", "--changelog", str(changelog)]) == 1

    def test_main_missing_file_returns_2(self, tmp_path: Path) -> None:
        assert main(["2.0.0", "--changelog", str(tmp_path / "nope.md")]) == 2


@pytest.mark.unit
class TestAgainstRealChangelog:
    def test_real_changelog_has_ga_section(self) -> None:
        changelog = (
            Path(__file__).resolve().parent.parent.parent / "CHANGELOG.md"
        ).read_text(encoding="utf-8")
        section = extract_section(changelog, "2.0.0")
        assert section.strip()
        # The GA section's prose may reference "2.0.0-beta.1", but the next
        # section's heading must not be included.
        assert "## [2.0.0-beta.1]" not in section
