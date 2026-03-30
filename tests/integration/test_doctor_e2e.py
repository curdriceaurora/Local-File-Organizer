"""Integration tests for doctor command end-to-end workflow.

Tests the complete flow from CLI invocation through directory scanning,
dependency detection, recommendation display, and installation.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

import file_organizer.cli._globals as _cli_globals
from file_organizer.cli.main import app

pytestmark = [pytest.mark.integration]

runner = CliRunner()


# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def doctor_test_dir(tmp_path: Path) -> Path:
    """Create a temporary directory for doctor tests.

    Returns:
        Path to the temporary directory.
    """
    test_dir = tmp_path / "doctor_test"
    test_dir.mkdir()
    return test_dir


@pytest.fixture
def audio_files_dir(tmp_path: Path) -> Path:
    """Create a directory with various audio file types.

    Returns:
        Path to directory containing audio files.
    """
    audio_dir = tmp_path / "audio_collection"
    audio_dir.mkdir()

    # Create audio files with different extensions
    (audio_dir / "song1.mp3").write_text("fake audio data")
    (audio_dir / "song2.wav").write_text("fake audio data")
    (audio_dir / "track.flac").write_text("fake audio data")
    (audio_dir / "podcast.m4a").write_text("fake audio data")

    return audio_dir


@pytest.fixture
def mixed_media_dir(tmp_path: Path) -> Path:
    """Create a directory with mixed file types requiring multiple groups.

    Returns:
        Path to directory containing mixed media files.
    """
    media_dir = tmp_path / "mixed_media"
    media_dir.mkdir()

    # Audio files
    (media_dir / "music.mp3").write_text("audio")
    (media_dir / "voice.wav").write_text("audio")

    # Video files
    (media_dir / "movie.mp4").write_text("video")
    (media_dir / "clip.avi").write_text("video")

    # Documents
    (media_dir / "report.pdf").write_text("document")
    (media_dir / "presentation.pptx").write_text("document")

    # Archives
    (media_dir / "backup.7z").write_text("archive")
    (media_dir / "data.rar").write_text("archive")

    # Scientific data
    (media_dir / "experiment.h5").write_text("data")
    (media_dir / "results.hdf5").write_text("data")

    # CAD files
    (media_dir / "blueprint.dxf").write_text("cad")

    return media_dir


@pytest.fixture
def nested_structure_dir(tmp_path: Path) -> Path:
    """Create a directory with nested subdirectories containing various files.

    Returns:
        Path to directory with nested structure.
    """
    root = tmp_path / "nested_project"
    root.mkdir()

    # Create nested structure
    music_dir = root / "media" / "music"
    music_dir.mkdir(parents=True)
    (music_dir / "track1.mp3").write_text("audio")
    (music_dir / "track2.flac").write_text("audio")

    video_dir = root / "media" / "videos"
    video_dir.mkdir(parents=True)
    (video_dir / "movie.mp4").write_text("video")

    docs_dir = root / "documents"
    docs_dir.mkdir(parents=True)
    (docs_dir / "manual.pdf").write_text("pdf")
    (docs_dir / "specs.docx").write_text("docx")

    # Add hidden directory (should be skipped)
    hidden_dir = root / ".hidden"
    hidden_dir.mkdir()
    (hidden_dir / "secret.mp3").write_text("hidden audio")

    return root


# ============================================================================
# Basic Command Invocation Tests
# ============================================================================


class TestDoctorCommandInvocation:
    """Tests for basic doctor command invocation and argument handling."""

    def test_doctor_requires_path_argument(self) -> None:
        """Doctor command requires a path argument."""
        result = runner.invoke(app, ["doctor"])
        assert result.exit_code != 0
        # Should show error about missing argument
        assert "path" in result.output.lower() or "argument" in result.output.lower()

    def test_doctor_rejects_nonexistent_path(self) -> None:
        """Doctor command rejects non-existent directories."""
        result = runner.invoke(app, ["doctor", "/nonexistent/path/xyz"])
        assert result.exit_code != 0

    def test_doctor_rejects_file_path(self, tmp_path: Path) -> None:
        """Doctor command requires a directory, not a file."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test")
        result = runner.invoke(app, ["doctor", str(test_file)])
        assert result.exit_code != 0

    def test_doctor_accepts_valid_directory(self, doctor_test_dir: Path) -> None:
        """Doctor command accepts a valid directory path."""
        result = runner.invoke(app, ["doctor", str(doctor_test_dir)])
        # Should exit cleanly (even if directory is empty)
        assert result.exit_code == 0


# ============================================================================
# Empty and Minimal Directory Tests
# ============================================================================


class TestDoctorEmptyDirectories:
    """Tests for doctor command with empty or minimal directories."""

    def test_empty_directory_exits_gracefully(self, doctor_test_dir: Path) -> None:
        """Doctor command exits gracefully with empty directory."""
        result = runner.invoke(app, ["doctor", str(doctor_test_dir)])
        assert result.exit_code == 0
        assert "no files" in result.output.lower()

    def test_empty_directory_json_output(self, doctor_test_dir: Path) -> None:
        """Doctor command produces valid JSON for empty directory."""
        result = runner.invoke(app, ["doctor", str(doctor_test_dir), "--json"])
        assert result.exit_code == 0

        output = json.loads(result.output)
        assert output["files_found"] == 0
        assert output["detected_groups"] == []
        assert output["missing_groups"] == []

    def test_directory_with_unsupported_files_only(self, doctor_test_dir: Path) -> None:
        """Doctor command handles directory with only unsupported file types."""
        # Create files that don't map to any dependency group
        (doctor_test_dir / "notes.txt").write_text("text")
        (doctor_test_dir / "config.json").write_text("{}")
        (doctor_test_dir / "script.sh").write_text("#!/bin/bash")

        result = runner.invoke(app, ["doctor", str(doctor_test_dir)])
        assert result.exit_code == 0
        assert "no optional dependencies needed" in result.output.lower()


# ============================================================================
# File Detection and Group Recommendation Tests
# ============================================================================


class TestDoctorFileDetection:
    """Tests for file type detection and dependency group recommendations."""

    def test_detect_audio_files(self, audio_files_dir: Path) -> None:
        """Doctor detects audio files and recommends audio group."""
        with patch("file_organizer.cli.doctor.is_group_installed", return_value=False):
            result = runner.invoke(app, ["doctor", str(audio_files_dir), "--json"])
            assert result.exit_code == 0

            output = json.loads(result.output)
            assert "audio" in output["missing_groups"]
            assert output["files_found"] == 4

    def test_detect_multiple_groups(self, mixed_media_dir: Path) -> None:
        """Doctor detects multiple file types and recommends multiple groups."""
        with patch("file_organizer.cli.doctor.is_group_installed", return_value=False):
            result = runner.invoke(app, ["doctor", str(mixed_media_dir), "--json"])
            assert result.exit_code == 0

            output = json.loads(result.output)
            missing = set(output["missing_groups"])
            assert "audio" in missing
            assert "video" in missing
            assert "parsers" in missing
            assert "archive" in missing
            assert "scientific" in missing
            assert "cad" in missing

    def test_recursive_scanning(self, nested_structure_dir: Path) -> None:
        """Doctor recursively scans subdirectories."""
        with patch("file_organizer.cli.doctor.is_group_installed", return_value=False):
            result = runner.invoke(app, ["doctor", str(nested_structure_dir), "--json"])
            assert result.exit_code == 0

            output = json.loads(result.output)
            missing = set(output["missing_groups"])
            # Should find audio, video, and parsers in nested directories
            assert "audio" in missing
            assert "video" in missing
            assert "parsers" in missing

    def test_hidden_files_excluded(self, nested_structure_dir: Path) -> None:
        """Doctor excludes hidden files and directories from scan."""
        with patch("file_organizer.cli.doctor.is_group_installed", return_value=False):
            result = runner.invoke(app, ["doctor", str(nested_structure_dir), "--json"])
            assert result.exit_code == 0

            output = json.loads(result.output)
            # Should find 2 audio files (not the hidden one)
            extensions = output["extensions"]
            assert extensions.get(".mp3", 0) == 1  # Only track1.mp3, not .hidden/secret.mp3
            assert extensions.get(".flac", 0) == 1

    def test_case_insensitive_extensions(self, doctor_test_dir: Path) -> None:
        """Doctor handles uppercase and mixed-case extensions."""
        (doctor_test_dir / "song.MP3").write_text("audio")
        (doctor_test_dir / "video.Mp4").write_text("video")
        (doctor_test_dir / "doc.PDF").write_text("pdf")

        with patch("file_organizer.cli.doctor.is_group_installed", return_value=False):
            result = runner.invoke(app, ["doctor", str(doctor_test_dir), "--json"])
            assert result.exit_code == 0

            output = json.loads(result.output)
            missing = set(output["missing_groups"])
            assert "audio" in missing
            assert "video" in missing
            assert "parsers" in missing


# ============================================================================
# Dependency Detection Tests
# ============================================================================


class TestDoctorDependencyDetection:
    """Tests for dependency installation status detection."""

    def test_all_dependencies_installed(self, audio_files_dir: Path) -> None:
        """Doctor detects when all dependencies are already installed."""
        with patch("file_organizer.cli.doctor.is_group_installed", return_value=True):
            result = runner.invoke(app, ["doctor", str(audio_files_dir)])
            assert result.exit_code == 0
            assert "already installed" in result.output.lower()

    def test_partial_installation_detected(self, mixed_media_dir: Path) -> None:
        """Doctor correctly identifies partially installed groups."""

        def mock_is_installed(group: str) -> bool:
            # Simulate audio and video installed, others not
            return group in {"audio", "video"}

        with patch("file_organizer.cli.doctor.is_group_installed", side_effect=mock_is_installed):
            result = runner.invoke(app, ["doctor", str(mixed_media_dir), "--json"])
            assert result.exit_code == 0

            output = json.loads(result.output)
            missing = set(output["missing_groups"])
            # Should only recommend non-installed groups
            assert "audio" not in missing
            assert "video" not in missing
            assert "parsers" in missing
            assert "archive" in missing

    def test_json_shows_installation_status(self, mixed_media_dir: Path) -> None:
        """JSON output includes installation status for each group."""

        def mock_is_installed(group: str) -> bool:
            return group == "audio"

        with patch("file_organizer.cli.doctor.is_group_installed", side_effect=mock_is_installed):
            result = runner.invoke(app, ["doctor", str(mixed_media_dir), "--json"])
            assert result.exit_code == 0

            output = json.loads(result.output)
            groups_info = output["detected_groups"]

            # Find audio group info
            audio_info = next((g for g in groups_info if g["group"] == "audio"), None)
            assert audio_info is not None
            assert audio_info["installed"] is True

            # Find video group info
            video_info = next((g for g in groups_info if g["group"] == "video"), None)
            assert video_info is not None
            assert video_info["installed"] is False


# ============================================================================
# Installation Flow Tests
# ============================================================================


class TestDoctorInstallation:
    """Tests for the --install flag and installation workflow."""

    def test_install_flag_without_confirmation_prompts(
        self, audio_files_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--install flag triggers installation flow."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        monkeypatch.setattr(_cli_globals, "dry_run", False)

        with patch("file_organizer.cli.doctor.is_group_installed", return_value=False):
            with patch("file_organizer.cli.doctor.confirm_action", return_value=True):
                with patch("subprocess.run", return_value=mock_result) as mock_run:
                    result = runner.invoke(app, ["doctor", str(audio_files_dir), "--install"])
                    assert result.exit_code == 0
                    # Should have called subprocess to install
                    assert mock_run.called

    def test_install_with_yes_flag_auto_confirms(
        self, audio_files_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Global --yes flag auto-confirms installation."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        monkeypatch.setattr(_cli_globals, "dry_run", False)

        with patch("file_organizer.cli.doctor.is_group_installed", return_value=False):
            with patch("subprocess.run", return_value=mock_result) as mock_run:
                result = runner.invoke(app, ["--yes", "doctor", str(audio_files_dir), "--install"])
                # Should succeed without prompting
                assert result.exit_code == 0
                assert mock_run.called

    def test_install_with_dry_run_flag(self, audio_files_dir: Path) -> None:
        """Global --dry-run flag prevents actual installation."""
        with patch("file_organizer.cli.doctor.is_group_installed", return_value=False):
            with patch("file_organizer.cli.doctor.confirm_action", return_value=True):
                with patch("subprocess.run") as mock_run:
                    result = runner.invoke(
                        app, ["--dry-run", "doctor", str(audio_files_dir), "--install"]
                    )
                    assert result.exit_code == 0
                    # Should NOT call subprocess in dry-run mode
                    assert not mock_run.called
                    assert (
                        "dry-run" in result.output.lower()
                        or "would install" in result.output.lower()
                    )

    def test_user_cancels_installation(self, audio_files_dir: Path) -> None:
        """User can cancel installation at confirmation prompt."""
        with patch("file_organizer.cli.doctor.is_group_installed", return_value=False):
            with patch("file_organizer.cli.doctor.confirm_action", return_value=False):
                with patch("subprocess.run") as mock_run:
                    result = runner.invoke(app, ["doctor", str(audio_files_dir), "--install"])
                    assert result.exit_code == 0
                    # Should not proceed with installation
                    assert not mock_run.called
                    assert "cancelled" in result.output.lower()

    def test_install_handles_subprocess_failure(
        self, audio_files_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Installation handles subprocess failures gracefully."""
        mock_result = MagicMock()
        mock_result.returncode = 1  # Failure
        monkeypatch.setattr(_cli_globals, "dry_run", False)

        with patch("file_organizer.cli.doctor.is_group_installed", return_value=False):
            with patch("file_organizer.cli.doctor.confirm_action", return_value=True):
                with patch("subprocess.run", return_value=mock_result):
                    result = runner.invoke(app, ["doctor", str(audio_files_dir), "--install"])
                    # Command should complete even if installation fails
                    assert result.exit_code == 0
                    assert "failed" in result.output.lower()

    def test_install_multiple_groups_sequentially(
        self, mixed_media_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Installation processes multiple groups sequentially."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        monkeypatch.setattr(_cli_globals, "dry_run", False)

        with patch("file_organizer.cli.doctor.is_group_installed", return_value=False):
            with patch("file_organizer.cli.doctor.confirm_action", return_value=True):
                with patch("subprocess.run", return_value=mock_result) as mock_run:
                    result = runner.invoke(app, ["doctor", str(mixed_media_dir), "--install"])
                    assert result.exit_code == 0
                    # Should have called pip install for each detected group
                    assert mock_run.call_count >= 2  # At least audio and video


# ============================================================================
# JSON Output Tests
# ============================================================================


class TestDoctorJSONOutput:
    """Tests for --json flag and structured output."""

    def test_json_output_structure(self, mixed_media_dir: Path) -> None:
        """JSON output contains all required fields."""
        with patch("file_organizer.cli.doctor.is_group_installed", return_value=False):
            result = runner.invoke(app, ["doctor", str(mixed_media_dir), "--json"])
            assert result.exit_code == 0

            output = json.loads(result.output)
            # Verify required top-level fields
            assert "directory" in output
            assert "files_found" in output
            assert "extensions" in output
            assert "detected_groups" in output
            assert "missing_groups" in output

    def test_json_detected_groups_structure(self, audio_files_dir: Path) -> None:
        """JSON detected_groups contains complete group information."""
        with patch("file_organizer.cli.doctor.is_group_installed", return_value=False):
            result = runner.invoke(app, ["doctor", str(audio_files_dir), "--json"])
            assert result.exit_code == 0

            output = json.loads(result.output)
            groups_info = output["detected_groups"]
            assert len(groups_info) > 0

            # Verify group info structure
            for group_info in groups_info:
                assert "group" in group_info
                assert "files_found" in group_info
                assert "installed" in group_info
                assert "install_command" in group_info
                assert "prerequisites" in group_info

    def test_json_extension_counts(self, mixed_media_dir: Path) -> None:
        """JSON output includes accurate extension counts."""
        with patch("file_organizer.cli.doctor.is_group_installed", return_value=False):
            result = runner.invoke(app, ["doctor", str(mixed_media_dir), "--json"])
            assert result.exit_code == 0

            output = json.loads(result.output)
            extensions = output["extensions"]
            # Verify some expected counts
            assert extensions[".mp3"] >= 1
            assert extensions[".mp4"] >= 1
            assert extensions[".pdf"] >= 1

    def test_json_valid_syntax(self, audio_files_dir: Path) -> None:
        """JSON output is valid and parseable."""
        with patch("file_organizer.cli.doctor.is_group_installed", return_value=False):
            result = runner.invoke(app, ["doctor", str(audio_files_dir), "--json"])
            assert result.exit_code == 0
            # Should not raise JSONDecodeError
            output = json.loads(result.output)
            assert isinstance(output, dict)


# ============================================================================
# Global Flags Integration Tests
# ============================================================================


class TestDoctorGlobalFlags:
    """Tests for integration with global CLI flags."""

    def test_verbose_flag_accepted(self, audio_files_dir: Path) -> None:
        """Global --verbose flag is accepted without error."""
        with patch("file_organizer.cli.doctor.is_group_installed", return_value=False):
            result = runner.invoke(app, ["--verbose", "doctor", str(audio_files_dir)])
            assert result.exit_code == 0

    def test_json_flag_at_global_level(self, audio_files_dir: Path) -> None:
        """Global --json flag produces JSON output with expected structure."""
        with patch("file_organizer.cli.doctor.is_group_installed", return_value=False):
            result = runner.invoke(app, ["--json", "doctor", str(audio_files_dir)])
            assert result.exit_code == 0
            # Parse output as JSON and verify structure keys
            data = json.loads(result.output)
            assert "directory" in data
            assert "files_found" in data
            assert "detected_groups" in data
            assert "missing_groups" in data

    def test_no_interactive_flag_with_install(
        self, audio_files_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Global --no-interactive flag is handled properly."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        monkeypatch.setattr(_cli_globals, "dry_run", False)

        with patch("file_organizer.cli.doctor.is_group_installed", return_value=False):
            with patch("subprocess.run", return_value=mock_result):
                result = runner.invoke(
                    app, ["--no-interactive", "doctor", str(audio_files_dir), "--install"]
                )
                # Should handle non-interactive mode gracefully
                assert result.exit_code == 0


# ============================================================================
# Edge Cases and Error Handling Tests
# ============================================================================


class TestDoctorEdgeCases:
    """Tests for edge cases and error handling."""

    def test_deeply_nested_directories(self, tmp_path: Path) -> None:
        """Doctor handles deeply nested directory structures."""
        # Create deeply nested structure
        deep_path = tmp_path / "a" / "b" / "c" / "d" / "e" / "f"
        deep_path.mkdir(parents=True)
        (deep_path / "song.mp3").write_text("audio")

        with patch("file_organizer.cli.doctor.is_group_installed", return_value=False):
            result = runner.invoke(app, ["doctor", str(tmp_path), "--json"])
            assert result.exit_code == 0
            output = json.loads(result.output)
            assert "audio" in output["missing_groups"]

    def test_many_files_same_type(self, tmp_path: Path) -> None:
        """Doctor handles directories with many files efficiently."""
        test_dir = tmp_path / "many_files"
        test_dir.mkdir()

        # Create 100 audio files
        for i in range(100):
            (test_dir / f"song{i}.mp3").write_text("audio")

        with patch("file_organizer.cli.doctor.is_group_installed", return_value=False):
            result = runner.invoke(app, ["doctor", str(test_dir), "--json"])
            assert result.exit_code == 0
            output = json.loads(result.output)
            assert output["extensions"][".mp3"] == 100

    def test_special_characters_in_filenames(self, tmp_path: Path) -> None:
        """Doctor handles files with special characters in names."""
        test_dir = tmp_path / "special_chars"
        test_dir.mkdir()

        (test_dir / "song with spaces.mp3").write_text("audio")
        (test_dir / "file-with-dashes.mp4").write_text("video")
        (test_dir / "file_with_underscores.pdf").write_text("pdf")
        (test_dir / "file[brackets].docx").write_text("docx")

        with patch("file_organizer.cli.doctor.is_group_installed", return_value=False):
            result = runner.invoke(app, ["doctor", str(test_dir), "--json"])
            assert result.exit_code == 0
            output = json.loads(result.output)
            assert output["files_found"] == 4

    def test_symlinks_handled_safely(self, tmp_path: Path) -> None:
        """Doctor handles symlinks without infinite loops."""
        test_dir = tmp_path / "symlink_test"
        test_dir.mkdir()

        # Create a regular file
        (test_dir / "song.mp3").write_text("audio")

        # Create a symlink to parent directory (potential loop)
        # Note: This may not work on all systems
        try:
            (test_dir / "loop").symlink_to(test_dir)
        except (OSError, NotImplementedError):
            # Skip symlink test if not supported
            pytest.skip("Symlinks not supported on this system")

        with patch("file_organizer.cli.doctor.is_group_installed", return_value=False):
            result = runner.invoke(app, ["doctor", str(test_dir), "--json"])
            # Should complete without hanging
            assert result.exit_code == 0


# ============================================================================
# Recommendation Display Tests
# ============================================================================


class TestDoctorRecommendations:
    """Tests for recommendation display and formatting."""

    def test_recommendations_show_file_counts(self, mixed_media_dir: Path) -> None:
        """Recommendations display shows file counts per group."""
        with patch("file_organizer.cli.doctor.is_group_installed", return_value=False):
            result = runner.invoke(app, ["doctor", str(mixed_media_dir)])
            assert result.exit_code == 0
            # Should show numeric counts in output
            assert any(char.isdigit() for char in result.output)

    def test_recommendations_show_install_commands(self, audio_files_dir: Path) -> None:
        """Recommendations include pip install commands."""
        with patch("file_organizer.cli.doctor.is_group_installed", return_value=False):
            result = runner.invoke(app, ["doctor", str(audio_files_dir)])
            assert result.exit_code == 0
            assert "pip install" in result.output.lower()
            assert "file-organizer[audio]" in result.output

    def test_recommendations_show_prerequisites(self, audio_files_dir: Path) -> None:
        """Recommendations display system prerequisites."""
        with patch("file_organizer.cli.doctor.is_group_installed", return_value=False):
            result = runner.invoke(app, ["doctor", str(audio_files_dir)])
            assert result.exit_code == 0
            # Audio group has FFmpeg prerequisite — verify it appears in output
            assert "FFmpeg" in result.output or "ffmpeg" in result.output.lower()

    def test_installed_groups_marked_differently(self, mixed_media_dir: Path) -> None:
        """Installed groups are visually distinguished from missing ones."""

        def mock_is_installed(group: str) -> bool:
            return group == "audio"

        with patch("file_organizer.cli.doctor.is_group_installed", side_effect=mock_is_installed):
            result = runner.invoke(app, ["doctor", str(mixed_media_dir)])
            assert result.exit_code == 0
            # Installed groups show checkmark; non-installed don't get "already installed"
            output = result.output.lower()
            assert "already installed" in output or "\u2713" in result.output
            assert "missing" in output


# ============================================================================
# End-to-End Workflow Tests
# ============================================================================


class TestDoctorEndToEndWorkflows:
    """Comprehensive end-to-end workflow tests."""

    def test_first_time_user_workflow(
        self, mixed_media_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Simulate first-time user discovering and installing dependencies."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        monkeypatch.setattr(_cli_globals, "dry_run", False)

        # Step 1: Run doctor without install to see recommendations
        with patch("file_organizer.cli.doctor.is_group_installed", return_value=False):
            result = runner.invoke(app, ["doctor", str(mixed_media_dir)])
            assert result.exit_code == 0
            assert "missing" in result.output.lower()

        # Step 2: Run doctor with --install to install dependencies
        with patch("file_organizer.cli.doctor.is_group_installed", return_value=False):
            with patch("file_organizer.cli.doctor.confirm_action", return_value=True):
                with patch("subprocess.run", return_value=mock_result) as mock_run:
                    result = runner.invoke(app, ["doctor", str(mixed_media_dir), "--install"])
                    assert result.exit_code == 0
                    assert mock_run.called

    def test_ci_automation_workflow(self, audio_files_dir: Path) -> None:
        """Simulate CI/automation usage with --dry-run and --json flags."""
        with patch("file_organizer.cli.doctor.is_group_installed", return_value=False):
            result = runner.invoke(app, ["--dry-run", "doctor", str(audio_files_dir), "--json"])
            assert result.exit_code == 0

            # Should produce JSON output
            output = json.loads(result.output)
            assert output["directory"] == str(audio_files_dir)
            assert "audio" in output["missing_groups"]

            # Should not have performed any installations
            # (verified by lack of subprocess calls in other tests)

    def test_already_configured_user_workflow(self, audio_files_dir: Path) -> None:
        """User with all dependencies installed sees confirmation."""
        with patch("file_organizer.cli.doctor.is_group_installed", return_value=True):
            result = runner.invoke(app, ["doctor", str(audio_files_dir)])
            assert result.exit_code == 0
            assert "already installed" in result.output.lower()

    def test_incremental_installation_workflow(self, mixed_media_dir: Path) -> None:
        """User with some dependencies installs remaining ones."""

        def mock_is_installed(group: str) -> bool:
            # Simulate audio and video already installed
            return group in {"audio", "video"}

        with patch("file_organizer.cli.doctor.is_group_installed", side_effect=mock_is_installed):
            result = runner.invoke(app, ["doctor", str(mixed_media_dir), "--json"])
            assert result.exit_code == 0

            output = json.loads(result.output)
            missing = set(output["missing_groups"])

            # Should only recommend groups that aren't installed
            assert "audio" not in missing
            assert "video" not in missing
            assert "parsers" in missing
            assert "archive" in missing
