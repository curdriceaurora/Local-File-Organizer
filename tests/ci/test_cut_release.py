"""Tests for release-cut scaffolding."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))

from cut_release import ensure_changelog_section, normalize_version, release_commands, tag_for

pytestmark = pytest.mark.ci


def test_normalize_version_accepts_optional_tag_prefix() -> None:
    assert normalize_version("v2.0.3") == "2.0.3"
    assert tag_for("2.0.3") == "v2.0.3"


def test_normalize_version_rejects_invalid_text() -> None:
    with pytest.raises(ValueError, match="Invalid version"):
        normalize_version("release-two")


def test_ensure_changelog_section_inserts_after_unreleased(tmp_path: Path) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n\n## [Unreleased]\n\n## [2.0.2] - old\n", encoding="utf-8")

    changed = ensure_changelog_section(
        "2.0.3",
        changelog=changelog,
        today=date(2026, 7, 15),
    )

    assert changed is True
    text = changelog.read_text(encoding="utf-8")
    assert "## [Unreleased]\n\n## [2.0.3] - 2026-07-15" in text
    assert "TODO: summarize" in text


def test_ensure_changelog_section_is_idempotent(tmp_path: Path) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n\n## [Unreleased]\n\n## [2.0.3] - old\n", encoding="utf-8")

    assert ensure_changelog_section("2.0.3", changelog=changelog) is False


def test_release_commands_point_to_tag_triggered_build_flow() -> None:
    commands = "\n".join(release_commands("2.0.3"))
    assert "scripts/bump_version.py --check" in commands
    assert "local-file-organizer-v2.0.3-notes.md" in commands
    assert "git tag -a v2.0.3" in commands
    assert "git push origin v2.0.3" in commands
