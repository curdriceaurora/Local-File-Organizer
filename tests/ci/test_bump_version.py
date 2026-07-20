"""Tests for scripts/bump_version.py (doc version-stamp sync, see #1540)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

# Add scripts dir to path so we can import bump_version.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))

from bump_version import (
    _DOC_VERSION_STAMP,
    _DOCS_SUPPORT_VERSION,
    _FILE_ORGANIZER_V_VERSION,
    _README_BADGE_VERSION,
    Touchpoint,
    _shields_badge_version,
    find_drift,
    main,
)

from file_organizer.version import __version__

pytestmark = pytest.mark.ci


def _make_touchpoint(tmp_path: Path, name: str, stamp_line: str) -> Touchpoint:
    doc = tmp_path / name
    doc.write_text(f"# Some doc\n\n{stamp_line}\n", encoding="utf-8")
    return Touchpoint(doc, _DOC_VERSION_STAMP)


class TestFindDrift:
    """Tests for find_drift()."""

    def test_reports_nothing_when_up_to_date(self, tmp_path: Path) -> None:
        tp = _make_touchpoint(tmp_path, "a.md", f"**Version**: {__version__}")
        assert find_drift(fix=False, touchpoints=[tp]) == []

    def test_reports_stale_touchpoint_without_writing(self, tmp_path: Path) -> None:
        tp = _make_touchpoint(tmp_path, "a.md", "**Version**: 0.0.1")
        stale = find_drift(fix=False, touchpoints=[tp])
        assert len(stale) == 1
        assert "0.0.1" in stale[0]
        assert __version__ in stale[0]
        # Check mode must not have touched the file.
        assert "0.0.1" in tp.path.read_text(encoding="utf-8")

    def test_fix_rewrites_stale_touchpoint_in_place(self, tmp_path: Path) -> None:
        tp = _make_touchpoint(tmp_path, "a.md", "**Version**: 0.0.1")
        stale = find_drift(fix=True, touchpoints=[tp])
        assert len(stale) == 1
        assert f"**Version**: {__version__}" in tp.path.read_text(encoding="utf-8")

    def test_fix_preserves_surrounding_text(self, tmp_path: Path) -> None:
        tp = _make_touchpoint(tmp_path, "a.md", "> **Version**: 0.0.1")
        find_drift(fix=True, touchpoints=[tp])
        assert f"> **Version**: {__version__}" in tp.path.read_text(encoding="utf-8")

    def test_missing_stamp_raises(self, tmp_path: Path) -> None:
        doc = tmp_path / "a.md"
        doc.write_text("# No stamp here\n", encoding="utf-8")
        tp = Touchpoint(doc, _DOC_VERSION_STAMP)
        with pytest.raises(SystemExit):
            find_drift(fix=False, touchpoints=[tp])

    def test_multiple_touchpoints_all_checked(self, tmp_path: Path) -> None:
        stale_tp = _make_touchpoint(tmp_path, "a.md", "**Version**: 0.0.1")
        fresh_tp = _make_touchpoint(tmp_path, "b.md", f"**Version**: {__version__}")
        stale = find_drift(fix=False, touchpoints=[stale_tp, fresh_tp])
        assert len(stale) == 1
        assert "a.md" in stale[0]

    def test_custom_expected_formatter_is_used_for_comparison_and_rewrite(
        self, tmp_path: Path
    ) -> None:
        """A touchpoint with a non-identity `expected()` (e.g. a 4-part Windows
        version) should compare and rewrite against the formatted value, not
        the raw __version__."""
        doc = tmp_path / "app.manifest"
        doc.write_text('version="0.0.0.0"\n', encoding="utf-8")
        tp = Touchpoint(
            doc,
            re.compile(r'version="(?P<version>[\d.]+)"'),
            lambda v: f"{v}.0",
        )
        stale = find_drift(fix=True, touchpoints=[tp])
        assert len(stale) == 1
        assert f"expected {__version__}.0" in stale[0]
        assert f'version="{__version__}.0"' in doc.read_text(encoding="utf-8")

    def test_custom_expected_formatter_reports_no_drift_when_matching(self, tmp_path: Path) -> None:
        doc = tmp_path / "app.manifest"
        doc.write_text(f'version="{__version__}.0"\n', encoding="utf-8")
        tp = Touchpoint(
            doc,
            re.compile(r'version="(?P<version>[\d.]+)"'),
            lambda v: f"{v}.0",
        )
        assert find_drift(fix=False, touchpoints=[tp]) == []

    def test_readme_badge_version_is_rewritten(self, tmp_path: Path) -> None:
        doc = tmp_path / "README.md"
        doc.write_text(
            "[![Version](https://img.shields.io/badge/version-0.0.1-blue)](CHANGELOG.md)\n",
            encoding="utf-8",
        )
        tp = Touchpoint(doc, _README_BADGE_VERSION)

        stale = find_drift(fix=True, touchpoints=[tp])

        assert len(stale) == 1
        assert f"version-{__version__}-blue" in doc.read_text(encoding="utf-8")

    def test_readme_badge_prerelease_version_is_rewritten(self, tmp_path: Path) -> None:
        doc = tmp_path / "README.md"
        doc.write_text(
            "[![Version](https://img.shields.io/badge/version-0.0.1--rc1-blue)](CHANGELOG.md)\n",
            encoding="utf-8",
        )
        tp = Touchpoint(doc, _README_BADGE_VERSION)

        stale = find_drift(fix=True, touchpoints=[tp])

        assert len(stale) == 1
        text = doc.read_text(encoding="utf-8")
        assert f"version-{__version__}-blue" in text
        assert "--rc1-blue" not in text

    def test_readme_badge_expected_formatter_uses_shields_hyphen_encoding(self) -> None:
        assert _shields_badge_version("2.2.0-rc1") == "2.2.0--rc1"

    def test_docs_support_version_is_rewritten(self, tmp_path: Path) -> None:
        doc = tmp_path / "index.md"
        doc.write_text(
            "This documentation supports File Organizer `0.0.1`. To read older versions.\n",
            encoding="utf-8",
        )
        tp = Touchpoint(doc, _DOCS_SUPPORT_VERSION)

        stale = find_drift(fix=True, touchpoints=[tp])

        assert len(stale) == 1
        assert f"This documentation supports File Organizer `{__version__}`." in doc.read_text(
            encoding="utf-8"
        )

    def test_docs_support_prerelease_version_is_rewritten(self, tmp_path: Path) -> None:
        doc = tmp_path / "index.md"
        doc.write_text(
            "This documentation supports File Organizer `0.0.1-rc1`. To read older versions.\n",
            encoding="utf-8",
        )
        tp = Touchpoint(doc, _DOCS_SUPPORT_VERSION)

        stale = find_drift(fix=True, touchpoints=[tp])

        assert len(stale) == 1
        text = doc.read_text(encoding="utf-8")
        assert f"This documentation supports File Organizer `{__version__}`." in text
        assert "-rc1`" not in text

    def test_file_organizer_v_version_is_rewritten(self, tmp_path: Path) -> None:
        doc = tmp_path / "__init__.py"
        doc.write_text('"""File Organizer v0.0.1 - package docstring."""\n', encoding="utf-8")
        tp = Touchpoint(doc, _FILE_ORGANIZER_V_VERSION, lambda version: f"v{version}")

        stale = find_drift(fix=True, touchpoints=[tp])

        assert len(stale) == 1
        assert f"File Organizer v{__version__}" in doc.read_text(encoding="utf-8")

    def test_file_organizer_v_prerelease_version_is_rewritten(self, tmp_path: Path) -> None:
        doc = tmp_path / "__init__.py"
        doc.write_text('"""File Organizer v0.0.1-rc1 - package docstring."""\n', encoding="utf-8")
        tp = Touchpoint(doc, _FILE_ORGANIZER_V_VERSION, lambda version: f"v{version}")

        stale = find_drift(fix=True, touchpoints=[tp])

        assert len(stale) == 1
        text = doc.read_text(encoding="utf-8")
        assert f"File Organizer v{__version__}" in text
        assert "-rc1 - package" not in text


class TestMain:
    """Tests for the CLI entry point."""

    def test_check_mode_exits_1_on_drift(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        tp = _make_touchpoint(tmp_path, "a.md", "**Version**: 0.0.1")
        monkeypatch.setattr("bump_version.TOUCHPOINTS", [tp])
        assert main(["--check"]) == 1

    def test_check_mode_exits_0_when_clean(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        tp = _make_touchpoint(tmp_path, "a.md", f"**Version**: {__version__}")
        monkeypatch.setattr("bump_version.TOUCHPOINTS", [tp])
        assert main(["--check"]) == 0

    def test_default_mode_fixes_and_exits_0(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        tp = _make_touchpoint(tmp_path, "a.md", "**Version**: 0.0.1")
        monkeypatch.setattr("bump_version.TOUCHPOINTS", [tp])
        assert main([]) == 0
        assert f"**Version**: {__version__}" in tp.path.read_text(encoding="utf-8")

    def test_default_mode_is_idempotent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        tp = _make_touchpoint(tmp_path, "a.md", f"**Version**: {__version__}")
        monkeypatch.setattr("bump_version.TOUCHPOINTS", [tp])
        assert main([]) == 0
        assert f"**Version**: {__version__}" in tp.path.read_text(encoding="utf-8")
