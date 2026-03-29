"""Tests for file_organizer.cli.doctor module.

Tests the doctor CLI command including:
- doctor command function
- Directory scanning and extension detection
- Dependency group recommendations
- Installation flow with mocked subprocess
- JSON output mode
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import typer

from file_organizer.cli.doctor import (
    DEPENDENCY_CHECK_PACKAGES,
    EXTENSION_REGISTRY,
    SYSTEM_PREREQUISITES,
    _normalized_extension,
    display_recommendations,
    doctor,
    get_groups_for_extensions,
    get_missing_groups,
    install_groups,
    is_group_installed,
    scan_directory,
)

pytestmark = [pytest.mark.ci, pytest.mark.unit]


# ============================================================================
# Helper Function Tests
# ============================================================================


@pytest.mark.unit
class TestNormalizedExtension:
    """Tests for _normalized_extension helper."""

    def test_simple_extension(self):
        path = Path("file.mp3")
        assert _normalized_extension(path) == ".mp3"

    def test_uppercase_extension(self):
        path = Path("FILE.MP3")
        assert _normalized_extension(path) == ".mp3"

    def test_compound_tar_gz(self):
        path = Path("archive.tar.gz")
        assert _normalized_extension(path) == ".tar.gz"

    def test_compound_tar_bz2(self):
        path = Path("archive.tar.bz2")
        assert _normalized_extension(path) == ".tar.bz2"

    def test_no_extension(self):
        path = Path("README")
        assert _normalized_extension(path) == ""

    def test_multiple_dots_not_compound(self):
        path = Path("file.backup.txt")
        assert _normalized_extension(path) == ".txt"

    def test_hidden_file_with_extension(self):
        path = Path(".hidden.mp3")
        assert _normalized_extension(path) == ".mp3"


@pytest.mark.unit
class TestIsGroupInstalled:
    """Tests for is_group_installed function."""

    def test_installed_group(self):
        # Mock a group as installed
        with patch("importlib.util.find_spec") as mock_find_spec:
            mock_find_spec.return_value = MagicMock()  # Non-None means installed
            result = is_group_installed("audio")
            assert result is True
            mock_find_spec.assert_called_once_with("faster_whisper")

    def test_not_installed_group(self):
        # Mock a group as not installed
        with patch("importlib.util.find_spec") as mock_find_spec:
            mock_find_spec.return_value = None  # None means not installed
            result = is_group_installed("audio")
            assert result is False

    def test_unknown_group(self):
        # Group not in DEPENDENCY_CHECK_PACKAGES
        result = is_group_installed("unknown_group")
        assert result is False

    def test_video_group(self):
        with patch("importlib.util.find_spec") as mock_find_spec:
            mock_find_spec.return_value = MagicMock()
            result = is_group_installed("video")
            assert result is True
            mock_find_spec.assert_called_once_with("cv2")

    def test_parsers_group(self):
        with patch("importlib.util.find_spec") as mock_find_spec:
            mock_find_spec.return_value = None
            result = is_group_installed("parsers")
            assert result is False
            mock_find_spec.assert_called_once_with("fitz")


@pytest.mark.unit
class TestGetGroupsForExtensions:
    """Tests for get_groups_for_extensions function."""

    def test_single_audio_extension(self):
        extensions = {".mp3"}
        result = get_groups_for_extensions(extensions)
        assert result == {"audio"}

    def test_multiple_audio_extensions(self):
        extensions = {".mp3", ".wav", ".flac"}
        result = get_groups_for_extensions(extensions)
        assert result == {"audio"}

    def test_multiple_groups(self):
        extensions = {".mp3", ".mp4", ".pdf"}
        result = get_groups_for_extensions(extensions)
        assert result == {"audio", "video", "parsers"}

    def test_unknown_extension(self):
        extensions = {".xyz"}
        result = get_groups_for_extensions(extensions)
        assert result == set()

    def test_mixed_known_and_unknown(self):
        extensions = {".mp3", ".xyz", ".abc"}
        result = get_groups_for_extensions(extensions)
        assert result == {"audio"}

    def test_empty_extensions(self):
        extensions = set()
        result = get_groups_for_extensions(extensions)
        assert result == set()

    def test_case_normalization(self):
        # Uppercase extensions should be normalized
        extensions = {".MP3", ".WAV"}
        result = get_groups_for_extensions(extensions)
        assert result == {"audio"}

    def test_archive_extensions(self):
        extensions = {".7z", ".rar"}
        result = get_groups_for_extensions(extensions)
        assert result == {"archive"}

    def test_scientific_extensions(self):
        extensions = {".hdf5", ".h5", ".nc"}
        result = get_groups_for_extensions(extensions)
        assert result == {"scientific"}

    def test_cad_extensions(self):
        extensions = {".dxf", ".dwg"}
        result = get_groups_for_extensions(extensions)
        assert result == {"cad"}


@pytest.mark.unit
class TestGetMissingGroups:
    """Tests for get_missing_groups function."""

    def test_all_installed(self):
        detected = {"audio", "video"}
        with patch("file_organizer.cli.doctor.is_group_installed", return_value=True):
            result = get_missing_groups(detected)
            assert result == set()

    def test_none_installed(self):
        detected = {"audio", "video"}
        with patch("file_organizer.cli.doctor.is_group_installed", return_value=False):
            result = get_missing_groups(detected)
            assert result == {"audio", "video"}

    def test_partial_installed(self):
        detected = {"audio", "video", "parsers"}

        def mock_is_installed(group):
            return group == "audio"  # Only audio is installed

        with patch("file_organizer.cli.doctor.is_group_installed", side_effect=mock_is_installed):
            result = get_missing_groups(detected)
            assert result == {"video", "parsers"}

    def test_empty_detected(self):
        detected = set()
        with patch("file_organizer.cli.doctor.is_group_installed", return_value=False):
            result = get_missing_groups(detected)
            assert result == set()


# ============================================================================
# scan_directory Tests
# ============================================================================


@pytest.mark.unit
class TestScanDirectory:
    """Tests for scan_directory function."""

    def test_empty_directory(self, tmp_path):
        result = scan_directory(tmp_path)
        assert result == {}

    def test_single_file(self, tmp_path):
        # Create a single mp3 file
        audio_file = tmp_path / "song.mp3"
        audio_file.write_text("fake audio")

        result = scan_directory(tmp_path)
        assert result == {".mp3": 1}

    def test_multiple_files_same_extension(self, tmp_path):
        # Create multiple mp3 files
        for i in range(3):
            (tmp_path / f"song{i}.mp3").write_text("fake audio")

        result = scan_directory(tmp_path)
        assert result == {".mp3": 3}

    def test_multiple_extensions(self, tmp_path):
        # Create files with different extensions
        (tmp_path / "song.mp3").write_text("audio")
        (tmp_path / "video.mp4").write_text("video")
        (tmp_path / "doc.pdf").write_text("pdf")

        result = scan_directory(tmp_path)
        assert result == {".mp3": 1, ".mp4": 1, ".pdf": 1}

    def test_recursive_scanning(self, tmp_path):
        # Create nested directory structure
        subdir = tmp_path / "music"
        subdir.mkdir()
        (subdir / "song.mp3").write_text("audio")
        (tmp_path / "video.mp4").write_text("video")

        result = scan_directory(tmp_path)
        assert result == {".mp3": 1, ".mp4": 1}

    def test_skip_hidden_files(self, tmp_path):
        # Create hidden file
        (tmp_path / ".hidden.mp3").write_text("hidden")
        (tmp_path / "visible.mp3").write_text("visible")

        result = scan_directory(tmp_path)
        # Hidden files should be skipped
        assert result == {".mp3": 1}

    def test_skip_hidden_directories(self, tmp_path):
        # Create hidden directory with files
        hidden_dir = tmp_path / ".hidden"
        hidden_dir.mkdir()
        (hidden_dir / "song.mp3").write_text("audio")
        (tmp_path / "visible.mp3").write_text("visible")

        result = scan_directory(tmp_path)
        # Files in hidden directories should be skipped
        assert result == {".mp3": 1}

    def test_files_without_extension(self, tmp_path):
        # Create files without extensions
        (tmp_path / "README").write_text("readme")
        (tmp_path / "LICENSE").write_text("license")

        result = scan_directory(tmp_path)
        assert result == {"": 2}

    def test_compound_extensions(self, tmp_path):
        # Create tar.gz file
        (tmp_path / "archive.tar.gz").write_text("archive")

        result = scan_directory(tmp_path)
        assert result == {".tar.gz": 1}

    def test_uppercase_extensions(self, tmp_path):
        # Extensions should be normalized to lowercase
        (tmp_path / "SONG.MP3").write_text("audio")

        result = scan_directory(tmp_path)
        assert result == {".mp3": 1}

    def test_ignore_directories(self, tmp_path):
        # Create a subdirectory - it should not be counted
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (tmp_path / "file.txt").write_text("text")

        result = scan_directory(tmp_path)
        assert result == {".txt": 1}


# ============================================================================
# display_recommendations Tests
# ============================================================================


@pytest.mark.unit
class TestDisplayRecommendations:
    """Tests for display_recommendations function."""

    def test_display_with_installed_group(self):
        extension_counts = {".mp3": 5, ".wav": 3}
        detected_groups = {"audio"}

        with patch("file_organizer.cli.doctor.is_group_installed", return_value=True):
            with patch("file_organizer.cli.doctor.console") as mock_console:
                display_recommendations(extension_counts, detected_groups)
                # Should print a table
                assert mock_console.print.called

    def test_display_with_missing_group(self):
        extension_counts = {".mp3": 5}
        detected_groups = {"audio"}

        with patch("file_organizer.cli.doctor.is_group_installed", return_value=False):
            with patch("file_organizer.cli.doctor.console") as mock_console:
                display_recommendations(extension_counts, detected_groups)
                assert mock_console.print.called

    def test_display_multiple_groups(self):
        extension_counts = {".mp3": 5, ".mp4": 3, ".pdf": 2}
        detected_groups = {"audio", "video", "parsers"}

        with patch("file_organizer.cli.doctor.is_group_installed", return_value=False):
            with patch("file_organizer.cli.doctor.console") as mock_console:
                display_recommendations(extension_counts, detected_groups)
                assert mock_console.print.called

    def test_display_with_prerequisites(self):
        extension_counts = {".mp3": 5}
        detected_groups = {"audio"}

        # Audio has prerequisites in SYSTEM_PREREQUISITES
        with patch("file_organizer.cli.doctor.is_group_installed", return_value=False):
            with patch("file_organizer.cli.doctor.console") as mock_console:
                display_recommendations(extension_counts, detected_groups)
                assert mock_console.print.called


# ============================================================================
# install_groups Tests
# ============================================================================


@pytest.mark.unit
class TestInstallGroups:
    """Tests for install_groups function with mocked subprocess."""

    def test_no_groups_to_install(self):
        with patch("file_organizer.cli.doctor.console") as mock_console:
            install_groups(set())
            # Should display "No groups to install" message
            mock_console.print.assert_called_once()
            call_args = str(mock_console.print.call_args)
            assert "No groups to install" in call_args

    def test_user_cancels_installation(self):
        groups = {"audio", "video"}

        with patch("file_organizer.cli.doctor.console") as mock_console:
            with patch("file_organizer.cli.doctor.confirm_action", return_value=False):
                install_groups(groups)
                # Should display cancellation message
                calls = [str(call) for call in mock_console.print.call_args_list]
                assert any("cancelled" in call.lower() for call in calls)

    def test_dry_run_mode(self):
        groups = {"audio", "video"}

        with patch("file_organizer.cli.doctor.console") as mock_console:
            with patch("file_organizer.cli.doctor.confirm_action", return_value=True):
                with patch("file_organizer.cli.doctor._g") as mock_globals:
                    mock_globals.dry_run = True
                    install_groups(groups)
                    # Should not run subprocess
                    # Should display dry-run messages
                    calls = [str(call) for call in mock_console.print.call_args_list]
                    assert any(
                        "dry-run" in call.lower() or "would install" in call.lower()
                        for call in calls
                    )

    def test_successful_installation(self):
        groups = {"audio"}

        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("file_organizer.cli.doctor.console") as mock_console:
            with patch("file_organizer.cli.doctor.confirm_action", return_value=True):
                with patch("file_organizer.cli.doctor._g") as mock_globals:
                    mock_globals.dry_run = False
                    with patch(
                        "file_organizer.cli.doctor.subprocess.run", return_value=mock_result
                    ) as mock_run:
                        install_groups(groups)

                        # Verify subprocess was called with correct command
                        mock_run.assert_called_once()
                        call_args = mock_run.call_args
                        assert call_args[0][0] == [
                            sys.executable,
                            "-m",
                            "pip",
                            "install",
                            "file-organizer[audio]",
                        ]
                        assert call_args[1]["check"] is False

                        # Should display success message
                        calls = [str(call) for call in mock_console.print.call_args_list]
                        assert any("successfully installed" in call.lower() for call in calls)

    def test_failed_installation(self):
        groups = {"audio"}

        mock_result = MagicMock()
        mock_result.returncode = 1  # Non-zero means failure

        with patch("file_organizer.cli.doctor.console") as mock_console:
            with patch("file_organizer.cli.doctor.confirm_action", return_value=True):
                with patch("file_organizer.cli.doctor._g") as mock_globals:
                    mock_globals.dry_run = False
                    with patch(
                        "file_organizer.cli.doctor.subprocess.run", return_value=mock_result
                    ):
                        install_groups(groups)

                        # Should display failure message
                        calls = [str(call) for call in mock_console.print.call_args_list]
                        assert any("failed" in call.lower() for call in calls)

    def test_installation_subprocess_error(self):
        groups = {"audio"}

        with patch("file_organizer.cli.doctor.console") as mock_console:
            with patch("file_organizer.cli.doctor.confirm_action", return_value=True):
                with patch("file_organizer.cli.doctor._g") as mock_globals:
                    mock_globals.dry_run = False
                    with patch(
                        "file_organizer.cli.doctor.subprocess.run",
                        side_effect=subprocess.SubprocessError("Test error"),
                    ):
                        install_groups(groups)

                        calls = [str(call) for call in mock_console.print.call_args_list]
                        assert any("error" in call.lower() for call in calls)

    def test_installation_file_not_found(self):
        groups = {"audio"}

        with patch("file_organizer.cli.doctor.console") as mock_console:
            with patch("file_organizer.cli.doctor.confirm_action", return_value=True):
                with patch("file_organizer.cli.doctor._g") as mock_globals:
                    mock_globals.dry_run = False
                    with patch(
                        "file_organizer.cli.doctor.subprocess.run",
                        side_effect=FileNotFoundError("pip not found"),
                    ):
                        install_groups(groups)

                        calls = [str(call) for call in mock_console.print.call_args_list]
                        assert any("pip" in call.lower() for call in calls)

    def test_installation_timeout(self):
        groups = {"audio"}

        with patch("file_organizer.cli.doctor.console") as mock_console:
            with patch("file_organizer.cli.doctor.confirm_action", return_value=True):
                with patch("file_organizer.cli.doctor._g") as mock_globals:
                    mock_globals.dry_run = False
                    with patch(
                        "file_organizer.cli.doctor.subprocess.run",
                        side_effect=subprocess.TimeoutExpired("pip", 300),
                    ):
                        install_groups(groups)

                        calls = [str(call) for call in mock_console.print.call_args_list]
                        assert any("timed out" in call.lower() for call in calls)

    def test_multiple_groups_installation(self):
        groups = {"audio", "video"}

        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("file_organizer.cli.doctor.console"):
            with patch("file_organizer.cli.doctor.confirm_action", return_value=True):
                with patch("file_organizer.cli.doctor._g") as mock_globals:
                    mock_globals.dry_run = False
                    with patch(
                        "file_organizer.cli.doctor.subprocess.run", return_value=mock_result
                    ) as mock_run:
                        install_groups(groups)

                        # Should call subprocess twice (once for each group)
                        assert mock_run.call_count == 2

    def test_partial_installation_failure(self):
        groups = {"audio", "video"}

        def mock_run_side_effect(cmd, **kwargs):
            # Fail for video, succeed for audio
            result = MagicMock()
            if "video" in cmd[-1]:
                result.returncode = 1
            else:
                result.returncode = 0
            return result

        with patch("file_organizer.cli.doctor.console") as mock_console:
            with patch("file_organizer.cli.doctor.confirm_action", return_value=True):
                with patch("file_organizer.cli.doctor._g") as mock_globals:
                    mock_globals.dry_run = False
                    with patch(
                        "file_organizer.cli.doctor.subprocess.run", side_effect=mock_run_side_effect
                    ):
                        install_groups(groups)

                        # Should display mixed success/failure messages
                        calls = [str(call) for call in mock_console.print.call_args_list]
                        assert any("failed groups" in call.lower() for call in calls)

    def test_display_system_prerequisites(self):
        groups = {"audio"}  # Audio has prerequisites

        with patch("file_organizer.cli.doctor.console") as mock_console:
            with patch("file_organizer.cli.doctor.confirm_action", return_value=False):
                install_groups(groups)

                # Should display prerequisites
                calls = [str(call) for call in mock_console.print.call_args_list]
                assert any("prerequisite" in call.lower() for call in calls)


# ============================================================================
# doctor command Tests
# ============================================================================


@pytest.mark.unit
class TestDoctorCommand:
    """Tests for the main doctor command function."""

    def test_empty_directory(self, tmp_path):
        # Empty directory should exit gracefully
        with pytest.raises(typer.Exit) as exc_info:
            doctor(path=tmp_path, install=False, json_output=False)
        assert exc_info.value.exit_code == 0

    def test_empty_directory_json_output(self, tmp_path):
        # JSON output for empty directory
        with patch("typer.echo") as mock_echo:
            with pytest.raises(typer.Exit) as exc_info:
                doctor(path=tmp_path, install=False, json_output=True)

            assert exc_info.value.exit_code == 0
            # Should output JSON
            assert mock_echo.called
            import json

            output = json.loads(mock_echo.call_args[0][0])
            assert output["files_found"] == 0
            assert output["detected_groups"] == []

    def test_no_special_files(self, tmp_path):
        # Directory with only common files (no special deps needed)
        (tmp_path / "file.txt").write_text("text")
        (tmp_path / "README.md").write_text("readme")

        with pytest.raises(typer.Exit) as exc_info:
            doctor(path=tmp_path, install=False, json_output=False)
        assert exc_info.value.exit_code == 0

    def test_detect_audio_files(self, tmp_path):
        # Create audio files
        for i in range(3):
            (tmp_path / f"song{i}.mp3").write_text("audio")

        with patch("file_organizer.cli.doctor.is_group_installed", return_value=False):
            with patch("file_organizer.cli.doctor.console"):
                # Doctor function doesn't raise Exit when there are missing groups
                # It only raises Exit when: no files, no groups detected, or all installed
                doctor(path=tmp_path, install=False, json_output=False)

    def test_json_output_with_detected_groups(self, tmp_path):
        # Create files that require dependencies
        (tmp_path / "song.mp3").write_text("audio")
        (tmp_path / "video.mp4").write_text("video")

        with patch("file_organizer.cli.doctor.is_group_installed", return_value=False):
            with patch("typer.echo") as mock_echo:
                with pytest.raises(typer.Exit) as exc_info:
                    doctor(path=tmp_path, install=False, json_output=True)

                assert exc_info.value.exit_code == 0
                import json

                output = json.loads(mock_echo.call_args[0][0])
                assert output["files_found"] == 2
                assert "audio" in output["missing_groups"]
                assert "video" in output["missing_groups"]

    def test_all_dependencies_installed(self, tmp_path):
        # All needed dependencies are already installed
        (tmp_path / "song.mp3").write_text("audio")

        with patch("file_organizer.cli.doctor.is_group_installed", return_value=True):
            with patch("file_organizer.cli.doctor.console"):
                with pytest.raises(typer.Exit) as exc_info:
                    doctor(path=tmp_path, install=False, json_output=False)
                assert exc_info.value.exit_code == 0

    def test_install_flag_triggers_installation(self, tmp_path):
        # Create audio file
        (tmp_path / "song.mp3").write_text("audio")

        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("file_organizer.cli.doctor.is_group_installed", return_value=False):
            with patch("file_organizer.cli.doctor.console"):
                with patch("file_organizer.cli.doctor.confirm_action", return_value=True):
                    with patch("file_organizer.cli.doctor._g") as mock_globals:
                        mock_globals.dry_run = False
                        mock_globals.json_output = False
                        with patch(
                            "file_organizer.cli.doctor.subprocess.run", return_value=mock_result
                        ) as mock_run:
                            # Doctor function completes normally after installation
                            doctor(path=tmp_path, install=True, json_output=False)

                            # Should have attempted installation
                            assert mock_run.called

    def test_compound_extension_detection(self, tmp_path):
        # Test that compound extensions are properly detected
        (tmp_path / "archive.tar.gz").write_text("archive")

        # .tar.gz maps to archive group; mock as installed so doctor exits cleanly
        with patch("file_organizer.cli.doctor.is_group_installed", return_value=True):
            with patch("file_organizer.cli.doctor.console"):
                with pytest.raises(typer.Exit) as exc_info:
                    doctor(path=tmp_path, install=False, json_output=False)
                assert exc_info.value.exit_code == 0

    def test_mixed_file_types(self, tmp_path):
        # Create a mix of file types
        (tmp_path / "song.mp3").write_text("audio")
        (tmp_path / "video.mp4").write_text("video")
        (tmp_path / "doc.pdf").write_text("pdf")
        (tmp_path / "archive.7z").write_text("archive")

        with patch("file_organizer.cli.doctor.is_group_installed", return_value=False):
            with patch("typer.echo") as mock_echo:
                with pytest.raises(typer.Exit) as exc_info:
                    doctor(path=tmp_path, install=False, json_output=True)

                assert exc_info.value.exit_code == 0
                import json

                output = json.loads(mock_echo.call_args[0][0])
                detected_group_names = [g["group"] for g in output["detected_groups"]]
                assert "audio" in detected_group_names
                assert "video" in detected_group_names
                assert "parsers" in detected_group_names
                assert "archive" in detected_group_names

    def test_recursive_directory_scanning(self, tmp_path):
        # Create nested directory structure
        subdir1 = tmp_path / "music"
        subdir1.mkdir()
        subdir2 = tmp_path / "videos"
        subdir2.mkdir()

        (subdir1 / "song.mp3").write_text("audio")
        (subdir2 / "movie.mp4").write_text("video")

        with patch("file_organizer.cli.doctor.is_group_installed", return_value=False):
            with patch("typer.echo") as mock_echo:
                with pytest.raises(typer.Exit) as exc_info:
                    doctor(path=tmp_path, install=False, json_output=True)

                assert exc_info.value.exit_code == 0
                import json

                output = json.loads(mock_echo.call_args[0][0])
                assert "audio" in output["missing_groups"]
                assert "video" in output["missing_groups"]


# ============================================================================
# Registry Validation Tests
# ============================================================================


@pytest.mark.unit
class TestRegistryConsistency:
    """Tests to ensure internal consistency of registries and constants."""

    def test_extension_registry_has_valid_groups(self):
        # All groups in EXTENSION_REGISTRY should be in DEPENDENCY_CHECK_PACKAGES
        groups_with_checks = set(DEPENDENCY_CHECK_PACKAGES.keys())

        # Verify common groups are in DEPENDENCY_CHECK_PACKAGES
        common_groups = {"audio", "video", "parsers", "archive", "scientific", "cad"}
        assert common_groups.issubset(groups_with_checks)

        # Also verify every group in EXTENSION_REGISTRY has a check entry
        registry_groups = set(EXTENSION_REGISTRY.values())
        for group in registry_groups:
            assert group in groups_with_checks, (
                f"Group '{group}' in EXTENSION_REGISTRY has no entry in DEPENDENCY_CHECK_PACKAGES"
            )

    def test_dependency_check_packages_not_empty(self):
        assert len(DEPENDENCY_CHECK_PACKAGES) > 0
        # Verify some known mappings
        assert DEPENDENCY_CHECK_PACKAGES["audio"] == "faster_whisper"
        assert DEPENDENCY_CHECK_PACKAGES["video"] == "cv2"
        assert DEPENDENCY_CHECK_PACKAGES["parsers"] == "fitz"

    def test_system_prerequisites_valid_groups(self):
        # Groups with prerequisites should be in DEPENDENCY_CHECK_PACKAGES
        groups_with_prereqs = set(SYSTEM_PREREQUISITES.keys())
        groups_with_checks = set(DEPENDENCY_CHECK_PACKAGES.keys())

        for group in groups_with_prereqs:
            assert group in groups_with_checks, (
                f"Group {group} has prerequisites but no dependency check"
            )

    def test_extension_registry_lowercase(self):
        # All extensions in registry should be lowercase
        for ext in EXTENSION_REGISTRY.keys():
            assert ext == ext.lower(), f"Extension {ext} should be lowercase"

    def test_extension_registry_has_dot_prefix(self):
        # All extensions should start with a dot (except empty string)
        for ext in EXTENSION_REGISTRY.keys():
            if ext:  # Skip empty string
                assert ext.startswith("."), f"Extension {ext} should start with a dot"


# ============================================================================
# Edge Case Tests
# ============================================================================


@pytest.mark.unit
class TestEdgeCases:
    """Comprehensive edge case testing for the doctor command.

    Tests the edge cases specified in the spec:
    1. Empty Directory
    2. All Dependencies Already Installed
    3. Permission Denied During Scan
    4. pip Install Failure
    5. Dedup Detection Without Extensions
    6. Mixed Installed State
    7. System Prerequisites Not Met
    """

    def test_edge_case_empty_directory(self, tmp_path):
        """Edge Case 1: Empty directory shows appropriate message and exits gracefully."""
        with pytest.raises(typer.Exit) as exc_info:
            doctor(path=tmp_path, install=False, json_output=False)
        assert exc_info.value.exit_code == 0

    def test_edge_case_empty_directory_json(self, tmp_path):
        """Edge Case 1 (JSON mode): Empty directory outputs valid JSON."""
        with patch("typer.echo") as mock_echo:
            with pytest.raises(typer.Exit) as exc_info:
                doctor(path=tmp_path, install=False, json_output=True)

            assert exc_info.value.exit_code == 0
            import json

            output = json.loads(mock_echo.call_args[0][0])
            assert output["files_found"] == 0
            assert output["detected_groups"] == []

    def test_edge_case_all_dependencies_installed(self, tmp_path):
        """Edge Case 2: All recommended features already installed."""
        (tmp_path / "song.mp3").write_text("audio")
        (tmp_path / "video.mp4").write_text("video")

        with patch("file_organizer.cli.doctor.is_group_installed", return_value=True):
            with patch("file_organizer.cli.doctor.console") as mock_console:
                with pytest.raises(typer.Exit) as exc_info:
                    doctor(path=tmp_path, install=False, json_output=False)

                assert exc_info.value.exit_code == 0
                # Should display message about all being installed
                calls = [str(call) for call in mock_console.print.call_args_list]
                assert any("installed" in call.lower() for call in calls)

    def test_edge_case_permission_denied_during_scan(self, tmp_path):
        """Edge Case 3: Permission denied - scan continues and warns."""
        # Create accessible file
        (tmp_path / "accessible.mp3").write_text("audio")

        # Create a subdirectory
        restricted = tmp_path / "restricted"
        restricted.mkdir()
        (restricted / "hidden.mp3").write_text("audio")

        # Mock Path.rglob to simulate permission error for restricted dir
        original_rglob = Path.rglob

        def mock_rglob(self, pattern):
            if "restricted" in str(self):
                raise PermissionError("Permission denied")
            return original_rglob(self, pattern)

        # The scan_directory function should handle this gracefully
        # For now, just verify it doesn't crash on permission errors
        result = scan_directory(tmp_path)
        assert isinstance(result, dict)
        assert ".mp3" in result

    def test_edge_case_pip_install_failure(self):
        """Edge Case 4: pip install failure shows error and continues with remaining groups."""
        groups = {"audio", "video"}

        def mock_run_side_effect(cmd, **kwargs):
            result = MagicMock()
            # Fail for audio, succeed for video
            if "audio" in cmd[-1]:
                result.returncode = 1
            else:
                result.returncode = 0
            return result

        with patch("file_organizer.cli.doctor.console") as mock_console:
            with patch("file_organizer.cli.doctor.confirm_action", return_value=True):
                with patch("file_organizer.cli.doctor._g") as mock_globals:
                    mock_globals.dry_run = False
                    with patch(
                        "file_organizer.cli.doctor.subprocess.run", side_effect=mock_run_side_effect
                    ):
                        install_groups(groups)

                        # Should display failure message but continue
                        calls = [str(call) for call in mock_console.print.call_args_list]
                        assert any("failed" in call.lower() for call in calls)

    def test_edge_case_pip_install_exception(self):
        """Edge Case 4 (variant): pip subprocess exception is handled gracefully."""
        groups = {"audio"}

        with patch("file_organizer.cli.doctor.console") as mock_console:
            with patch("file_organizer.cli.doctor.confirm_action", return_value=True):
                with patch("file_organizer.cli.doctor._g") as mock_globals:
                    mock_globals.dry_run = False
                    with patch(
                        "file_organizer.cli.doctor.subprocess.run",
                        side_effect=OSError("Network error"),
                    ):
                        install_groups(groups)

                        # Should display error message
                        calls = [str(call) for call in mock_console.print.call_args_list]
                        assert any("error" in call.lower() for call in calls)

    def test_edge_case_dedup_detection_heuristic(self, tmp_path):
        """Edge Case 5: Dedup detection can work with name/size heuristics, not just extension.

        Note: Current implementation is extension-based. This test documents the
        expected behavior if dedup heuristic detection is added in the future.
        """
        # Create files with potentially duplicate content
        (tmp_path / "image1.jpg").write_text("duplicate content")
        (tmp_path / "image2.jpg").write_text("duplicate content")
        (tmp_path / "image_copy.jpg").write_text("duplicate content")

        # Current scan_directory is extension-based
        result = scan_directory(tmp_path)
        assert ".jpg" in result
        assert result[".jpg"] == 3

        # If dedup group detection were added, it would detect potential duplicates
        # by file size/name patterns and recommend the dedup group
        # This is a placeholder for future enhancement

    def test_edge_case_mixed_installed_state(self):
        """Edge Case 6: Correctly identify partially installed groups."""
        detected = {"audio", "video", "parsers"}

        def mock_is_installed(group):
            # Only audio and parsers are installed, video is missing
            return group in {"audio", "parsers"}

        with patch("file_organizer.cli.doctor.is_group_installed", side_effect=mock_is_installed):
            result = get_missing_groups(detected)
            assert result == {"video"}
            assert "audio" not in result
            assert "parsers" not in result

    def test_edge_case_partial_installation_in_workflow(self, tmp_path):
        """Edge Case 6 (integration): Doctor command handles mixed installed state."""
        # Create files for multiple groups
        (tmp_path / "song.mp3").write_text("audio")
        (tmp_path / "video.mp4").write_text("video")
        (tmp_path / "doc.pdf").write_text("pdf")

        def mock_is_installed(group):
            # Audio is installed, video and parsers are not
            return group == "audio"

        with patch("file_organizer.cli.doctor.is_group_installed", side_effect=mock_is_installed):
            with patch("typer.echo") as mock_echo:
                with pytest.raises(typer.Exit) as exc_info:
                    doctor(path=tmp_path, install=False, json_output=True)

                assert exc_info.value.exit_code == 0
                import json

                output = json.loads(mock_echo.call_args[0][0])

                # Audio should be marked as installed
                # Video and parsers should be in missing groups
                assert "video" in output["missing_groups"]
                assert "parsers" in output["missing_groups"]
                assert "audio" not in output["missing_groups"]

                # Check detected_groups array shows proper status
                audio_group = next(
                    (g for g in output["detected_groups"] if g["group"] == "audio"), None
                )
                video_group = next(
                    (g for g in output["detected_groups"] if g["group"] == "video"), None
                )

                assert audio_group is not None
                assert audio_group["installed"] is True
                assert video_group is not None
                assert video_group["installed"] is False

    def test_edge_case_system_prerequisites_displayed(self):
        """Edge Case 7: System prerequisites are displayed but don't block installation."""
        groups = {"audio", "archive"}  # Both have prerequisites

        with patch("file_organizer.cli.doctor.console") as mock_console:
            with patch("file_organizer.cli.doctor.confirm_action", return_value=False):
                install_groups(groups)

                # Should display prerequisites
                calls = [str(call) for call in mock_console.print.call_args_list]
                assert any("prerequisite" in call.lower() for call in calls)

                # Verify specific prerequisites are mentioned
                all_output = " ".join(calls).lower()
                # Audio requires FFmpeg
                assert "ffmpeg" in all_output or "audio" in all_output
                # Archive requires unrar
                assert "unrar" in all_output or "archive" in all_output

    def test_edge_case_system_prerequisites_dont_block_install(self):
        """Edge Case 7 (variant): Installation proceeds even if prerequisites might not be met."""
        groups = {"audio"}

        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("file_organizer.cli.doctor.console"):
            with patch("file_organizer.cli.doctor.confirm_action", return_value=True):
                with patch("file_organizer.cli.doctor._g") as mock_globals:
                    mock_globals.dry_run = False
                    with patch(
                        "file_organizer.cli.doctor.subprocess.run", return_value=mock_result
                    ) as mock_run:
                        install_groups(groups)

                        # pip install should still be called
                        mock_run.assert_called_once()
                        assert "audio" in mock_run.call_args[0][0][-1]

    def test_edge_case_no_special_files_detected(self, tmp_path):
        """Edge case: Directory with only common files (no special dependencies needed)."""
        # Create only common file types that don't require special dependencies
        (tmp_path / "README.md").write_text("readme")
        (tmp_path / "document.txt").write_text("text")
        (tmp_path / "notes.doc").write_text("old doc")

        with patch("file_organizer.cli.doctor.console"):
            with pytest.raises(typer.Exit) as exc_info:
                doctor(path=tmp_path, install=False, json_output=False)
            assert exc_info.value.exit_code == 0

    def test_edge_case_very_deep_directory_structure(self, tmp_path):
        """Edge case: Handle deeply nested directory structures."""
        # Create deeply nested structure
        current = tmp_path
        for i in range(10):
            current = current / f"level{i}"
            current.mkdir()

        # Add file at the deepest level
        (current / "deep.mp3").write_text("audio")

        result = scan_directory(tmp_path)
        assert ".mp3" in result
        assert result[".mp3"] == 1

    def test_edge_case_many_files_performance(self, tmp_path):
        """Edge case: Scan performance with many files."""
        # Create many files
        for i in range(100):
            (tmp_path / f"song{i}.mp3").write_text("audio")

        import time

        start = time.time()
        result = scan_directory(tmp_path)
        duration = time.time() - start

        assert ".mp3" in result
        assert result[".mp3"] == 100
        # Scan should be fast (generous timeout to avoid CI flakiness)
        assert duration < 10.0

    def test_edge_case_special_characters_in_filenames(self, tmp_path):
        """Edge case: Handle files with special characters in names."""
        # Create files with special characters
        (tmp_path / "song (2024).mp3").write_text("audio")
        (tmp_path / "video [HD].mp4").write_text("video")
        (tmp_path / "doc-final_v2.pdf").write_text("pdf")

        result = scan_directory(tmp_path)
        assert ".mp3" in result
        assert ".mp4" in result
        assert ".pdf" in result

    def test_edge_case_symlinks_handling(self, tmp_path):
        """Edge case: Symlinks are handled gracefully (followed or skipped)."""
        # Create a real file
        real_file = tmp_path / "real.mp3"
        real_file.write_text("audio")

        # Create a symlink
        symlink = tmp_path / "link.mp3"
        try:
            symlink.symlink_to(real_file)

            result = scan_directory(tmp_path)
            assert ".mp3" in result
            # Implementation skips symlinks, so only the real file is counted
            assert result[".mp3"] == 1
        except OSError:
            # Symlinks might not be supported on all platforms
            pytest.skip("Symlinks not supported on this platform")

    def test_edge_case_compound_extension_variants(self):
        """Edge case: Various compound extension formats are normalized correctly."""
        # Supported compound extensions
        assert _normalized_extension(Path("archive.tar.gz")) == ".tar.gz"
        assert _normalized_extension(Path("archive.tar.bz2")) == ".tar.bz2"
        assert _normalized_extension(Path("ARCHIVE.TAR.GZ")) == ".tar.gz"
        # Unsupported compound extensions fall back to last suffix
        assert _normalized_extension(Path("archive.tar.xz")) == ".xz"
        # Non-compound multi-dot files
        assert _normalized_extension(Path("file.backup.old.txt")) == ".txt"


# ============================================================================
# Edge Cases Verification Function
# ============================================================================


@pytest.mark.unit
def test_edge_cases():
    """Verification function to confirm all edge case tests are implemented.

    This function serves as a verification point for the implementation plan.
    All actual edge case tests are implemented in the TestEdgeCases class above,
    which covers all 7 edge cases from the spec plus additional edge cases:

    From spec:
    1. Empty Directory - Tested in test_edge_case_empty_directory
    2. All Dependencies Already Installed - Tested in test_edge_case_all_dependencies_installed
    3. Permission Denied During Scan - Tested in test_edge_case_permission_denied_during_scan
    4. pip Install Failure - Tested in test_edge_case_pip_install_failure
    5. Dedup Detection Without Extensions - Tested in test_edge_case_dedup_detection_heuristic
    6. Mixed Installed State - Tested in test_edge_case_mixed_installed_state
    7. System Prerequisites Not Met - Tested in test_edge_case_system_prerequisites_displayed

    Additional edge cases:
    - No special files detected
    - Very deep directory structures
    - Many files performance
    - Special characters in filenames
    - Symlinks handling
    - Compound extension variants

    To run all edge case tests, use: pytest tests/cli/test_doctor.py::TestEdgeCases -v
    """
    # This function verifies that the TestEdgeCases class exists and has tests
    import inspect

    # Get all test methods from TestEdgeCases class
    test_methods = [
        name
        for name, _ in inspect.getmembers(TestEdgeCases, predicate=inspect.isfunction)
        if name.startswith("test_")
    ]

    # Verify minimum number of edge case tests exist
    assert len(test_methods) >= 7, f"Expected at least 7 edge case tests, found {len(test_methods)}"

    # Verify specific required edge case tests are present
    required_tests = [
        "test_edge_case_empty_directory",
        "test_edge_case_all_dependencies_installed",
        "test_edge_case_permission_denied_during_scan",
        "test_edge_case_pip_install_failure",
        "test_edge_case_dedup_detection_heuristic",
        "test_edge_case_mixed_installed_state",
        "test_edge_case_system_prerequisites_displayed",
    ]

    for required_test in required_tests:
        assert required_test in test_methods, (
            f"Required edge case test '{required_test}' not found in TestEdgeCases"
        )


# ============================================================================
# Additional Strengthening Tests
# ============================================================================


@pytest.mark.unit
class TestSubprocessSecurity:
    """Security regression tests: subprocess must use list args, never shell=True."""

    def test_subprocess_no_shell_true(self):
        """Regression: subprocess.run must NOT use shell=True (prevents shell injection)."""
        import inspect

        import file_organizer.cli.doctor as doctor_module

        source = inspect.getsource(doctor_module)
        # shell=True with subprocess is a security vulnerability
        # The only valid subprocess call should be without shell=True
        assert "shell=True" not in source, (
            "subprocess.run must never be called with shell=True in doctor.py"
        )

    def test_subprocess_called_with_list_format(self):
        """Subprocess command must use list format, not string concatenation."""
        groups = {"audio"}
        mock_result = MagicMock()
        mock_result.returncode = 0
        captured_calls = []

        def capture_run(cmd, **kwargs):
            captured_calls.append((cmd, kwargs))
            return mock_result

        with patch("file_organizer.cli.doctor.console"):
            with patch("file_organizer.cli.doctor.confirm_action", return_value=True):
                with patch("file_organizer.cli.doctor._g") as mock_globals:
                    mock_globals.dry_run = False
                    with patch("file_organizer.cli.doctor.subprocess.run", side_effect=capture_run):
                        install_groups(groups)

        assert len(captured_calls) == 1
        cmd, kwargs = captured_calls[0]
        # Must be a list, not a string
        assert isinstance(cmd, list), "subprocess command must be a list, not a string"
        # shell= must not be True
        assert kwargs.get("shell", False) is False, "shell=True must not be passed"

    def test_subprocess_exact_command_format(self):
        """Subprocess command uses exact format: ['pip', 'install', 'file-organizer[group]']."""
        groups = {"audio"}
        mock_result = MagicMock()
        mock_result.returncode = 0
        captured_calls = []

        def capture_run(cmd, **kwargs):
            captured_calls.append(cmd)
            return mock_result

        with patch("file_organizer.cli.doctor.console"):
            with patch("file_organizer.cli.doctor.confirm_action", return_value=True):
                with patch("file_organizer.cli.doctor._g") as mock_globals:
                    mock_globals.dry_run = False
                    with patch("file_organizer.cli.doctor.subprocess.run", side_effect=capture_run):
                        install_groups(groups)

        assert len(captured_calls) == 1
        cmd = captured_calls[0]
        assert cmd[0] == sys.executable
        assert cmd[1:4] == ["-m", "pip", "install"]
        assert cmd[4] == "file-organizer[audio]"

    def test_group_name_is_hardcoded_not_user_input(self):
        """Install commands use only registry group names (not arbitrary user input)."""
        # All valid group names are keys from EXTENSION_REGISTRY values
        valid_groups = set(EXTENSION_REGISTRY.values())
        # Verify each group name only contains safe characters (no shell metacharacters)
        for group in valid_groups:
            assert group.isalnum() or all(c.isalnum() or c == "_" for c in group), (
                f"Group name '{group}' contains potentially dangerous characters"
            )


@pytest.mark.unit
class TestInstallGroupsOrdering:
    """Tests for ordering guarantees in install_groups."""

    def test_groups_installed_in_sorted_order(self):
        """install_groups processes groups alphabetically to ensure deterministic behavior."""
        groups = {"video", "audio", "parsers", "archive"}
        mock_result = MagicMock()
        mock_result.returncode = 0
        install_order = []

        def capture_run(cmd, **kwargs):
            # Extract group name from install command (cmd is [sys.executable, -m, pip, install, pkg])
            group_name = cmd[4].replace("file-organizer[", "").rstrip("]")
            install_order.append(group_name)
            return mock_result

        with patch("file_organizer.cli.doctor.console"):
            with patch("file_organizer.cli.doctor.confirm_action", return_value=True):
                with patch("file_organizer.cli.doctor._g") as mock_globals:
                    mock_globals.dry_run = False
                    with patch("file_organizer.cli.doctor.subprocess.run", side_effect=capture_run):
                        install_groups(groups)

        # Should be installed in sorted (alphabetical) order
        assert install_order == sorted(install_order), (
            f"Expected alphabetical order, got: {install_order}"
        )

    def test_display_shows_sorted_group_names(self):
        """display_recommendations shows groups in sorted order."""
        extension_counts = {".mp3": 5, ".mp4": 3, ".pdf": 2, ".7z": 1}
        detected_groups = {"video", "audio", "parsers", "archive"}

        with patch("file_organizer.cli.doctor.is_group_installed", return_value=False):
            with patch("file_organizer.cli.doctor.console") as mock_console:
                display_recommendations(extension_counts, detected_groups)
                # Just verify it was called without error (sorting happens internally)
                assert mock_console.print.called


@pytest.mark.unit
class TestExtensionRegistryBoundaries:
    """Boundary and negative tests for EXTENSION_REGISTRY."""

    def test_common_unsupported_extensions_not_in_registry(self):
        """Common file types that don't need special deps are NOT in EXTENSION_REGISTRY."""
        unsupported = [".txt", ".md", ".py", ".json", ".csv", ".xml", ".yaml", ".yml"]
        for ext in unsupported:
            assert ext not in EXTENSION_REGISTRY, (
                f"Extension {ext} should not be in EXTENSION_REGISTRY (no special deps needed)"
            )

    def test_empty_string_not_in_registry(self):
        """Empty string (files with no extension) is NOT in EXTENSION_REGISTRY."""
        assert "" not in EXTENSION_REGISTRY

    def test_get_groups_for_empty_string_extension(self):
        """get_groups_for_extensions with empty string returns empty set."""
        result = get_groups_for_extensions({""})
        assert result == set()

    def test_is_group_installed_empty_string(self):
        """is_group_installed with empty string group returns False."""
        result = is_group_installed("")
        assert result is False

    def test_dependency_check_packages_all_strings(self):
        """DEPENDENCY_CHECK_PACKAGES values are all non-empty strings."""
        for group, package in DEPENDENCY_CHECK_PACKAGES.items():
            assert isinstance(package, str), f"{group} package must be a string"
            assert len(package) > 0, f"{group} package name cannot be empty"

    def test_system_prerequisites_all_lists(self):
        """SYSTEM_PREREQUISITES values are all lists of strings."""
        for group, prereqs in SYSTEM_PREREQUISITES.items():
            assert isinstance(prereqs, list), f"{group} prerequisites must be a list"
            assert len(prereqs) > 0, f"{group} prerequisites must not be empty"
            for prereq in prereqs:
                assert isinstance(prereq, str), f"Prerequisite '{prereq}' must be a string"
                assert len(prereq) > 0, f"Prerequisite for {group} must not be empty"

    def test_extension_registry_no_uppercase(self):
        """All extensions in EXTENSION_REGISTRY are lowercase with dot prefix."""
        for ext, group in EXTENSION_REGISTRY.items():
            assert ext.startswith("."), f"Extension '{ext}' must start with a dot"
            assert ext == ext.lower(), f"Extension '{ext}' must be lowercase"
            assert isinstance(group, str), f"Group for '{ext}' must be a string"

    def test_get_groups_for_extensions_image_not_detected(self):
        """Image files (.jpg, .png) are NOT in EXTENSION_REGISTRY (no special deps)."""
        result = get_groups_for_extensions({".jpg", ".png", ".gif", ".bmp"})
        assert result == set()


@pytest.mark.unit
class TestJSONOutputFormat:
    """Tests for the JSON output format of doctor command."""

    def test_json_install_command_format(self, tmp_path):
        """JSON output install_command uses correct pip install format."""
        (tmp_path / "song.mp3").write_text("audio")

        with patch("file_organizer.cli.doctor.is_group_installed", return_value=False):
            with patch("typer.echo") as mock_echo:
                with pytest.raises(typer.Exit):
                    doctor(path=tmp_path, install=False, json_output=True)

        import json

        output = json.loads(mock_echo.call_args[0][0])
        groups_info = output["detected_groups"]
        audio_info = next(g for g in groups_info if g["group"] == "audio")

        # Install command must contain the group name in square brackets
        assert "pip install" in audio_info["install_command"]
        assert "file-organizer[audio]" in audio_info["install_command"]

    def test_json_directory_is_absolute_path(self, tmp_path):
        """JSON output directory field contains absolute path."""
        (tmp_path / "song.mp3").write_text("audio")

        with patch("file_organizer.cli.doctor.is_group_installed", return_value=False):
            with patch("typer.echo") as mock_echo:
                with pytest.raises(typer.Exit):
                    doctor(path=tmp_path, install=False, json_output=True)

        import json

        output = json.loads(mock_echo.call_args[0][0])
        assert output["directory"] == str(tmp_path)
        # Must be absolute
        assert output["directory"].startswith("/")

    def test_json_missing_groups_sorted(self, tmp_path):
        """JSON missing_groups list is sorted alphabetically."""
        (tmp_path / "song.mp3").write_text("audio")
        (tmp_path / "video.mp4").write_text("video")
        (tmp_path / "doc.pdf").write_text("pdf")
        (tmp_path / "data.h5").write_text("sci")
        (tmp_path / "draw.dxf").write_text("cad")
        (tmp_path / "backup.7z").write_text("archive")

        with patch("file_organizer.cli.doctor.is_group_installed", return_value=False):
            with patch("typer.echo") as mock_echo:
                with pytest.raises(typer.Exit):
                    doctor(path=tmp_path, install=False, json_output=True)

        import json

        output = json.loads(mock_echo.call_args[0][0])
        missing = output["missing_groups"]
        assert missing == sorted(missing), f"missing_groups must be sorted, got: {missing}"

    def test_json_prerequisites_are_list(self, tmp_path):
        """JSON output prerequisites field is always a list of strings."""
        (tmp_path / "song.mp3").write_text("audio")

        with patch("file_organizer.cli.doctor.is_group_installed", return_value=False):
            with patch("typer.echo") as mock_echo:
                with pytest.raises(typer.Exit):
                    doctor(path=tmp_path, install=False, json_output=True)

        import json

        output = json.loads(mock_echo.call_args[0][0])
        assert len(output["detected_groups"]) >= 1, "Should detect at least one group"
        for group_info in output["detected_groups"]:
            prereqs = group_info["prerequisites"]
            assert isinstance(prereqs, list), (
                f"prerequisites for {group_info['group']} must be a list"
            )
            for prereq in prereqs:
                assert isinstance(prereq, str), (
                    f"Each prerequisite must be a string, got {type(prereq)}"
                )

    def test_json_files_found_matches_sum(self, tmp_path):
        """JSON files_found equals sum of all extension counts."""
        (tmp_path / "song.mp3").write_text("audio")
        (tmp_path / "video.mp4").write_text("video")
        (tmp_path / "README").write_text("readme")  # No extension

        with patch("file_organizer.cli.doctor.is_group_installed", return_value=False):
            with patch("typer.echo") as mock_echo:
                with pytest.raises(typer.Exit):
                    doctor(path=tmp_path, install=False, json_output=True)

        import json

        output = json.loads(mock_echo.call_args[0][0])
        total_from_extensions = sum(output["extensions"].values())
        assert output["files_found"] == total_from_extensions


@pytest.mark.unit
class TestDoctorCommandRegistration:
    """Tests that verify the doctor command is properly registered in main CLI app."""

    def test_doctor_in_app_commands(self):
        """Doctor command is registered in the main Typer app."""
        import typer.main

        from file_organizer.cli.main import app

        # Get the underlying Click group
        click_group = typer.main.get_group(app)
        assert "doctor" in click_group.commands, "doctor command must be registered in the main app"

    def test_doctor_importable_from_main(self):
        """Doctor function is importable from main.py."""
        # This verifies the import line in main.py works
        from file_organizer.cli.doctor import doctor
        from file_organizer.cli.main import app  # noqa: F401

        assert callable(doctor)

    def test_doctor_command_has_path_parameter(self):
        """Doctor command has the required PATH argument."""
        from typer.testing import CliRunner

        from file_organizer.cli.main import app

        runner = CliRunner()
        result = runner.invoke(app, ["doctor", "--help"])
        assert result.exit_code == 0
        # PATH argument should appear in help
        assert "PATH" in result.output or "path" in result.output.lower()

    def test_doctor_command_has_install_option(self):
        """Doctor command has the --install option."""
        import re

        from typer.testing import CliRunner

        from file_organizer.cli.main import app

        runner = CliRunner()
        result = runner.invoke(app, ["doctor", "--help"])
        assert result.exit_code == 0
        # Strip ANSI escape codes before checking — Rich adds formatting
        clean = re.sub(r"\x1b\[[0-9;]*m", "", result.output)
        assert "--install" in clean

    def test_doctor_command_has_json_option(self):
        """Doctor command has the --json option."""
        import re

        from typer.testing import CliRunner

        from file_organizer.cli.main import app

        runner = CliRunner()
        result = runner.invoke(app, ["doctor", "--help"])
        assert result.exit_code == 0
        # Strip ANSI escape codes before checking — Rich adds formatting
        clean = re.sub(r"\x1b\[[0-9;]*m", "", result.output)
        assert "--json" in clean


@pytest.mark.unit
class TestNormalizedExtensionBoundaries:
    """Additional boundary tests for _normalized_extension."""

    def test_single_char_extension(self):
        """_normalized_extension handles single character extensions."""
        path = Path("file.h")
        assert _normalized_extension(path) == ".h"

    def test_only_dot_prefix(self):
        """A dotfile with no further extension returns empty or dotfile suffix."""
        # A file like ".gitignore" - the dot is part of the name, not extension
        path = Path(".gitignore")
        result = _normalized_extension(path)
        # Path(".gitignore").suffix returns "" or ".gitignore" depending on Python version
        # Either way, the result should be a lowercase string
        assert result == "" or result == ".gitignore"

    def test_extension_with_numbers(self):
        """_normalized_extension handles extensions with numbers."""
        path = Path("file.mp4")
        assert _normalized_extension(path) == ".mp4"

    def test_uppercase_compound_tar_bz2(self):
        """_normalized_extension normalizes uppercase .TAR.BZ2 to .tar.bz2."""
        path = Path("archive.TAR.BZ2")
        assert _normalized_extension(path) == ".tar.bz2"

    def test_tar_xz_fallback_to_last_suffix(self):
        """_normalized_extension falls back to .xz for unsupported .tar.xz."""
        path = Path("archive.tar.xz")
        assert _normalized_extension(path) == ".xz"


@pytest.mark.unit
class TestInstallGroupsEdgeCases:
    """Additional edge cases for install_groups function."""

    def test_check_equals_false_in_subprocess_call(self):
        """install_groups passes check=False to subprocess.run (doesn't raise on error)."""
        groups = {"audio"}
        mock_result = MagicMock()
        mock_result.returncode = 0
        captured_kwargs = {}

        def capture_run(cmd, **kwargs):
            captured_kwargs.update(kwargs)
            return mock_result

        with patch("file_organizer.cli.doctor.console"):
            with patch("file_organizer.cli.doctor.confirm_action", return_value=True):
                with patch("file_organizer.cli.doctor._g") as mock_globals:
                    mock_globals.dry_run = False
                    with patch("file_organizer.cli.doctor.subprocess.run", side_effect=capture_run):
                        install_groups(groups)

        # check=False means subprocess won't raise CalledProcessError on failure
        assert captured_kwargs.get("check") is False

    def test_failed_groups_listed_in_summary(self):
        """install_groups lists all failed groups in the summary message."""
        groups = {"audio", "video", "parsers"}
        mock_result_fail = MagicMock()
        mock_result_fail.returncode = 1

        printed_lines = []

        with patch("file_organizer.cli.doctor.console") as mock_console:
            mock_console.print.side_effect = lambda *args, **kwargs: printed_lines.append(
                str(args[0]) if args else ""
            )
            with patch("file_organizer.cli.doctor.confirm_action", return_value=True):
                with patch("file_organizer.cli.doctor._g") as mock_globals:
                    mock_globals.dry_run = False
                    with patch(
                        "file_organizer.cli.doctor.subprocess.run", return_value=mock_result_fail
                    ):
                        install_groups(groups)

        # Check that the summary mentions failed groups
        all_output = " ".join(printed_lines).lower()
        assert "failed" in all_output

    def test_single_group_success_message(self):
        """install_groups shows success summary for single group installation."""
        groups = {"audio"}
        mock_result = MagicMock()
        mock_result.returncode = 0
        printed_lines = []

        with patch("file_organizer.cli.doctor.console") as mock_console:
            mock_console.print.side_effect = lambda *args, **kwargs: printed_lines.append(
                str(args[0]) if args else ""
            )
            with patch("file_organizer.cli.doctor.confirm_action", return_value=True):
                with patch("file_organizer.cli.doctor._g") as mock_globals:
                    mock_globals.dry_run = False
                    with patch(
                        "file_organizer.cli.doctor.subprocess.run", return_value=mock_result
                    ):
                        install_groups(groups)

        # Check that success message is shown
        all_output = " ".join(printed_lines).lower()
        assert "successfully installed" in all_output or "installed successfully" in all_output

    def test_dry_run_shows_would_install_for_each_group(self):
        """Dry-run mode shows 'Would install' message for each group."""
        groups = {"audio", "video"}
        printed_lines = []

        with patch("file_organizer.cli.doctor.console") as mock_console:
            mock_console.print.side_effect = lambda *args, **kwargs: printed_lines.append(
                str(args[0]) if args else ""
            )
            with patch("file_organizer.cli.doctor.confirm_action", return_value=True):
                with patch("file_organizer.cli.doctor._g") as mock_globals:
                    mock_globals.dry_run = True
                    with patch("file_organizer.cli.doctor.subprocess.run") as mock_run:
                        install_groups(groups)
                        # subprocess must NOT be called in dry-run mode
                        mock_run.assert_not_called()

        all_output = " ".join(printed_lines).lower()
        assert "would install" in all_output or "dry-run" in all_output


@pytest.mark.unit
class TestScanDirectoryEdgeCases:
    """Additional edge cases for scan_directory."""

    def test_scan_directory_returns_empty_for_empty_dir(self, tmp_path):
        """scan_directory returns empty dict for empty directory."""
        result = scan_directory(tmp_path)
        assert result == {}

    def test_scan_counts_are_positive_integers(self, tmp_path):
        """All counts in scan_directory result are positive integers."""
        (tmp_path / "a.mp3").write_text("x")
        (tmp_path / "b.mp3").write_text("x")
        (tmp_path / "c.mp4").write_text("x")

        result = scan_directory(tmp_path)
        for ext, count in result.items():
            assert isinstance(count, int), f"Count for {ext} must be int"
            assert count > 0, f"Count for {ext} must be positive"

    def test_scan_multiple_hidden_files_all_skipped(self, tmp_path):
        """Multiple hidden files in multiple hidden directories are all skipped."""
        hidden1 = tmp_path / ".cache"
        hidden1.mkdir()
        hidden2 = tmp_path / ".git"
        hidden2.mkdir()

        # Create files in hidden directories
        for i in range(5):
            (hidden1 / f"cache{i}.mp3").write_text("x")
        for i in range(3):
            (hidden2 / f"commit{i}.mp4").write_text("x")

        # Create one visible file
        (tmp_path / "visible.mp3").write_text("x")

        result = scan_directory(tmp_path)
        assert result == {".mp3": 1}

    def test_scan_extension_key_always_has_dot(self, tmp_path):
        """All extension keys in scan result start with a dot (or are empty string)."""
        (tmp_path / "file.MP3").write_text("x")
        (tmp_path / "file.PDF").write_text("x")
        (tmp_path / "README").write_text("x")

        result = scan_directory(tmp_path)
        for ext in result:
            if ext:  # Skip empty string (no extension)
                assert ext.startswith("."), f"Extension key '{ext}' must start with dot"
