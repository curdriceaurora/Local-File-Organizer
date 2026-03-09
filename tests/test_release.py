"""Tests for release automation script.

Covers changelog generation, release notes creation, version bumping
via the release module, and release validation.
"""

from __future__ import annotations

# Import the release module by path since it's in scripts/
import importlib.util
import re
import sys
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
_release_spec = importlib.util.spec_from_file_location("release", _SCRIPTS_DIR / "release.py")
assert _release_spec is not None
assert _release_spec.loader is not None
release_mod = importlib.util.module_from_spec(_release_spec)
sys.modules["release"] = release_mod
_release_spec.loader.exec_module(release_mod)

generate_changelog = release_mod.generate_changelog
create_release_notes = release_mod.create_release_notes
validate_release = release_mod.validate_release
bump_version = release_mod.bump_version
_read_current_version_from_pyproject = release_mod._read_current_version_from_pyproject


@pytest.mark.unit
class TestGenerateChangelog:
    """Tests for changelog generation from git log."""

    @patch("release._run_command")
    def test_generates_changelog_from_commits(self, mock_run: MagicMock) -> None:
        """Generate changelog with categorized commits."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=(
                "feat: Add user authentication|abc1234|Dev A\n"
                "fix: Resolve login timeout|def5678|Dev B\n"
                "refactor: Clean up database layer|ghi9012|Dev A"
            ),
        )
        result = generate_changelog("v1.0.0", "v1.1.0")
        assert "### Added" in result
        assert "Add user authentication" in result
        assert "### Fixed" in result
        assert "Resolve login timeout" in result
        assert "### Changed" in result
        assert "Clean up database layer" in result

    @patch("release._run_command")
    def test_no_commits_returns_message(self, mock_run: MagicMock) -> None:
        """Empty git log returns appropriate message."""
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        result = generate_changelog("v1.0.0", "v1.0.0")
        assert "No changes found" in result

    @patch("release._run_command")
    def test_git_error_returns_error_message(self, mock_run: MagicMock) -> None:
        """Git error returns an error message."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stderr="fatal: bad revision",
        )
        result = generate_changelog("nonexistent", "HEAD")
        assert "Error" in result

    @patch("release._run_command")
    def test_issue_prefix_commits_categorized(self, mock_run: MagicMock) -> None:
        """Commits with Issue # prefix are categorized by content."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Issue #42: Add new feature|abc1234|Dev\n",
        )
        result = generate_changelog("v1.0.0", "HEAD")
        assert "Add new feature" in result

    @patch("release._run_command")
    def test_uncategorized_commits_go_to_other(self, mock_run: MagicMock) -> None:
        """Commits without conventional prefix go to Other category."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Random commit message|abc1234|Dev\n",
        )
        result = generate_changelog("v1.0.0", "HEAD")
        assert "### Other" in result
        assert "Random commit message" in result

    @patch("release._run_command")
    def test_changelog_includes_commit_hashes(self, mock_run: MagicMock) -> None:
        """Changelog entries include short commit hashes."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="feat: Add something|abc1234|Dev\n",
        )
        result = generate_changelog("v1.0.0", "HEAD")
        assert "abc1234" in result

    @patch("release._run_command")
    def test_security_prefix_categorized(self, mock_run: MagicMock) -> None:
        """Commits with security prefix go to Security category."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="security: Fix XSS vulnerability|abc1234|Dev\n",
        )
        result = generate_changelog("v1.0.0", "HEAD")
        assert "### Security" in result

    @patch("release._run_command")
    def test_remove_prefix_categorized(self, mock_run: MagicMock) -> None:
        """Commits with remove/delete prefix go to Removed category."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="remove: Drop legacy API|abc1234|Dev\n",
        )
        result = generate_changelog("v1.0.0", "HEAD")
        assert "### Removed" in result

    @patch("release._run_command")
    def test_multiple_commits_same_category(self, mock_run: MagicMock) -> None:
        """Multiple commits in same category are grouped."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=("feat: Add feature A|aaa1111|Dev\nfeat: Add feature B|bbb2222|Dev\n"),
        )
        result = generate_changelog("v1.0.0", "HEAD")
        assert result.count("### Added") == 1
        assert "feature A" in result
        assert "feature B" in result


@pytest.mark.unit
class TestCreateReleaseNotes:
    """Tests for release notes creation."""

    def test_release_notes_contain_version(self) -> None:
        """Release notes header contains the version."""
        notes = create_release_notes("2.1.0", "### Added\n- New feature")
        assert "v2.1.0" in notes

    def test_release_notes_contain_date(self) -> None:
        """Release notes contain a date stamp."""
        notes = create_release_notes("2.1.0", "### Added\n- New feature")
        # Check for YYYY-MM-DD pattern
        assert re.search(r"\d{4}-\d{2}-\d{2}", notes)

    def test_release_notes_contain_changelog(self) -> None:
        """Release notes include the provided changelog."""
        changelog = "### Added\n- Wonderful new feature"
        notes = create_release_notes("1.0.0", changelog)
        assert "Wonderful new feature" in notes

    def test_release_notes_contain_install_instructions(self) -> None:
        """Release notes include pip install command."""
        notes = create_release_notes("2.1.0", "changelog")
        assert "pip install local-file-organizer==2.1.0" in notes

    def test_release_notes_contain_changelog_link(self) -> None:
        """Release notes reference CHANGELOG.md."""
        notes = create_release_notes("1.0.0", "changes")
        assert "CHANGELOG.md" in notes


@pytest.mark.unit
class TestValidateRelease:
    """Tests for release validation."""

    @patch("release._run_command")
    def test_uncommitted_changes_reported(self, mock_run: MagicMock) -> None:
        """Uncommitted changes produce a validation error."""
        mock_run.return_value = MagicMock(returncode=0, stdout="M file.py\n")
        errors = validate_release()
        assert any("Uncommitted changes" in e for e in errors)

    @patch("release._run_command")
    @patch("release._CHANGELOG", new=Path("/nonexistent/CHANGELOG.md"))
    def test_missing_changelog_reported(self, mock_run: MagicMock) -> None:
        """Missing CHANGELOG.md produces a validation error."""
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        errors = validate_release()
        assert any("CHANGELOG.md" in e for e in errors)

    @patch("release._run_command")
    def test_wrong_branch_reported(self, mock_run: MagicMock) -> None:
        """Being on a non-release branch produces a validation error."""

        def side_effect(cmd: list[str], **kwargs: object) -> MagicMock:
            if "status" in cmd and "--porcelain" in cmd:
                return MagicMock(returncode=0, stdout="")
            if "branch" in cmd and "--show-current" in cmd:
                return MagicMock(returncode=0, stdout="feature/something\n")
            # For the test run and version checks, return failures
            # to avoid file I/O issues in tests
            return MagicMock(returncode=1, stdout="", stderr="skip")

        mock_run.side_effect = side_effect
        errors = validate_release()
        assert any("Not on a release branch" in e for e in errors)

    @patch("release._run_command")
    def test_release_branch_accepted(self, mock_run: MagicMock) -> None:
        """Release branch names are accepted."""

        def side_effect(cmd: list[str], **kwargs: object) -> MagicMock:
            if "status" in cmd and "--porcelain" in cmd:
                return MagicMock(returncode=0, stdout="")
            if "branch" in cmd and "--show-current" in cmd:
                return MagicMock(returncode=0, stdout="release/2.1.0\n")
            return MagicMock(returncode=1, stdout="", stderr="skip")

        mock_run.side_effect = side_effect
        errors = validate_release()
        assert not any("Not on a release branch" in e for e in errors)

    @patch("release._run_command")
    def test_main_branch_accepted(self, mock_run: MagicMock) -> None:
        """Main branch is accepted for releases."""

        def side_effect(cmd: list[str], **kwargs: object) -> MagicMock:
            if "status" in cmd and "--porcelain" in cmd:
                return MagicMock(returncode=0, stdout="")
            if "branch" in cmd and "--show-current" in cmd:
                return MagicMock(returncode=0, stdout="main\n")
            return MagicMock(returncode=1, stdout="", stderr="skip")

        mock_run.side_effect = side_effect
        errors = validate_release()
        assert not any("Not on a release branch" in e for e in errors)


@pytest.mark.unit
class TestBumpVersionIntegration:
    """Tests for the release module's bump_version function."""

    def test_bump_version_invalid_part_raises(self) -> None:
        """Invalid bump part raises ValueError."""
        with pytest.raises(ValueError, match="Invalid version part"):
            bump_version("invalid")

    @patch("release._update_init_py")
    @patch("release._update_version_py")
    @patch("release._update_file_version")
    @patch("release._read_current_version_from_pyproject")
    def test_bump_patch_calls_update_functions(
        self,
        mock_read: MagicMock,
        mock_update_file: MagicMock,
        mock_update_ver: MagicMock,
        mock_update_init: MagicMock,
    ) -> None:
        """Bumping patch updates all version files."""
        mock_read.return_value = "2.0.0"
        result = bump_version("patch")
        assert result == "2.0.1"
        assert mock_update_file.called
        assert mock_update_ver.called
        assert mock_update_init.called

    @patch("release._update_init_py")
    @patch("release._update_version_py")
    @patch("release._update_file_version")
    @patch("release._read_current_version_from_pyproject")
    def test_bump_minor_resets_patch(
        self,
        mock_read: MagicMock,
        mock_update_file: MagicMock,
        mock_update_ver: MagicMock,
        mock_update_init: MagicMock,
    ) -> None:
        """Bumping minor resets patch to 0."""
        mock_read.return_value = "2.0.5"
        result = bump_version("minor")
        assert result == "2.1.0"

    @patch("release._update_init_py")
    @patch("release._update_version_py")
    @patch("release._update_file_version")
    @patch("release._read_current_version_from_pyproject")
    def test_bump_strips_pre_release(
        self,
        mock_read: MagicMock,
        mock_update_file: MagicMock,
        mock_update_ver: MagicMock,
        mock_update_init: MagicMock,
    ) -> None:
        """Bumping a pre-release version strips the suffix."""
        mock_read.return_value = "2.0.0-alpha.1"
        result = bump_version("patch")
        assert result == "2.0.1"
        assert "alpha" not in result


@pytest.mark.unit
class TestReadCurrentVersion:
    """Tests for reading version from pyproject.toml."""

    @patch("release._PYPROJECT_TOML")
    def test_reads_version_from_pyproject(self, mock_path: MagicMock) -> None:
        """Version is correctly extracted from pyproject.toml content."""
        mock_path.read_text.return_value = textwrap.dedent("""\
            [project]
            name = "file-organizer"
            version = "2.0.0"
        """)
        version = _read_current_version_from_pyproject()
        assert version == "2.0.0"

    @patch("release._PYPROJECT_TOML")
    def test_reads_pre_release_version(self, mock_path: MagicMock) -> None:
        """Pre-release version is correctly extracted."""
        mock_path.read_text.return_value = 'version = "3.1.0-beta.2"\n'
        version = _read_current_version_from_pyproject()
        assert version == "3.1.0-beta.2"

    @patch("release._PYPROJECT_TOML")
    def test_missing_version_raises(self, mock_path: MagicMock) -> None:
        """Missing version in pyproject.toml raises RuntimeError."""
        mock_path.read_text.return_value = "[project]\nname = 'test'\n"
        with pytest.raises(RuntimeError, match="Could not find version"):
            _read_current_version_from_pyproject()
