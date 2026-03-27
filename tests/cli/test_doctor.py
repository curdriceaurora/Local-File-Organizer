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
                    assert any("dry-run" in call.lower() or "would install" in call.lower() for call in calls)

    def test_successful_installation(self):
        groups = {"audio"}

        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("file_organizer.cli.doctor.console") as mock_console:
            with patch("file_organizer.cli.doctor.confirm_action", return_value=True):
                with patch("file_organizer.cli.doctor._g") as mock_globals:
                    mock_globals.dry_run = False
                    with patch("subprocess.run", return_value=mock_result) as mock_run:
                        install_groups(groups)

                        # Verify subprocess was called with correct command
                        mock_run.assert_called_once()
                        call_args = mock_run.call_args
                        assert call_args[0][0] == ["pip", "install", "file-organizer[audio]"]
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
                    with patch("subprocess.run", return_value=mock_result):
                        install_groups(groups)

                        # Should display failure message
                        calls = [str(call) for call in mock_console.print.call_args_list]
                        assert any("failed" in call.lower() for call in calls)

    def test_installation_exception(self):
        groups = {"audio"}

        with patch("file_organizer.cli.doctor.console") as mock_console:
            with patch("file_organizer.cli.doctor.confirm_action", return_value=True):
                with patch("file_organizer.cli.doctor._g") as mock_globals:
                    mock_globals.dry_run = False
                    with patch("subprocess.run", side_effect=Exception("Test error")):
                        install_groups(groups)

                        # Should display error message
                        calls = [str(call) for call in mock_console.print.call_args_list]
                        assert any("error" in call.lower() for call in calls)

    def test_multiple_groups_installation(self):
        groups = {"audio", "video"}

        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("file_organizer.cli.doctor.console") as mock_console:
            with patch("file_organizer.cli.doctor.confirm_action", return_value=True):
                with patch("file_organizer.cli.doctor._g") as mock_globals:
                    mock_globals.dry_run = False
                    with patch("subprocess.run", return_value=mock_result) as mock_run:
                        install_groups(groups)

                        # Should call subprocess twice (once for each group)
                        assert mock_run.call_count == 2

    def test_partial_installation_failure(self):
        groups = {"audio", "video"}

        def mock_run_side_effect(cmd, **kwargs):
            # Fail for video, succeed for audio
            result = MagicMock()
            if "video" in cmd[2]:
                result.returncode = 1
            else:
                result.returncode = 0
            return result

        with patch("file_organizer.cli.doctor.console") as mock_console:
            with patch("file_organizer.cli.doctor.confirm_action", return_value=True):
                with patch("file_organizer.cli.doctor._g") as mock_globals:
                    mock_globals.dry_run = False
                    with patch("subprocess.run", side_effect=mock_run_side_effect):
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
                        with patch("subprocess.run", return_value=mock_result) as mock_run:
                            # Doctor function completes normally after installation
                            doctor(path=tmp_path, install=True, json_output=False)

                            # Should have attempted installation
                            assert mock_run.called

    def test_compound_extension_detection(self, tmp_path):
        # Test that compound extensions are properly detected
        (tmp_path / "archive.tar.gz").write_text("archive")

        # tar.gz is not in EXTENSION_REGISTRY, so no groups should be detected
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
        groups_in_registry = set(EXTENSION_REGISTRY.values())
        groups_with_checks = set(DEPENDENCY_CHECK_PACKAGES.keys())

        # Some groups in registry might not need dependency checks (like 'dedup')
        # but we should verify the common ones are there
        common_groups = {"audio", "video", "parsers", "archive", "scientific", "cad"}
        assert common_groups.issubset(groups_with_checks)

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
            assert group in groups_with_checks, f"Group {group} has prerequisites but no dependency check"

    def test_extension_registry_lowercase(self):
        # All extensions in registry should be lowercase
        for ext in EXTENSION_REGISTRY.keys():
            assert ext == ext.lower(), f"Extension {ext} should be lowercase"

    def test_extension_registry_has_dot_prefix(self):
        # All extensions should start with a dot (except empty string)
        for ext in EXTENSION_REGISTRY.keys():
            if ext:  # Skip empty string
                assert ext.startswith("."), f"Extension {ext} should start with a dot"
