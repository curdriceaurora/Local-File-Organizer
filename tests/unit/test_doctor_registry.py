"""Unit tests for doctor command registry and dependency checking logic."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from file_organizer.cli.doctor import (
    DEPENDENCY_CHECK_PACKAGES,
    EXTENSION_REGISTRY,
    SYSTEM_PREREQUISITES,
    _normalized_extension,
    get_groups_for_extensions,
    get_missing_groups,
    is_group_installed,
    scan_directory,
)

# -----------------------------------------------------------------------
# Extension Registry Tests
# -----------------------------------------------------------------------


def test_extension_registry_audio_formats():
    """Audio formats map to audio group."""
    audio_extensions = [".mp3", ".wav", ".flac", ".ogg", ".m4a", ".wma", ".aac", ".opus"]
    for ext in audio_extensions:
        assert EXTENSION_REGISTRY[ext] == "audio", f"{ext} should map to audio group"


def test_extension_registry_video_formats():
    """Video formats map to video group."""
    video_extensions = [".mp4", ".avi", ".mkv", ".mov", ".wmv", ".webm"]
    for ext in video_extensions:
        assert EXTENSION_REGISTRY[ext] == "video", f"{ext} should map to video group"


def test_extension_registry_parser_formats():
    """Document formats map to parsers group."""
    parser_extensions = [".pdf", ".docx", ".xlsx", ".pptx", ".epub", ".html"]
    for ext in parser_extensions:
        assert EXTENSION_REGISTRY[ext] == "parsers", f"{ext} should map to parsers group"


def test_extension_registry_archive_formats():
    """Archive formats map to archive group."""
    archive_extensions = [".7z", ".rar", ".tar.gz", ".tar.bz2"]
    for ext in archive_extensions:
        assert EXTENSION_REGISTRY[ext] == "archive", f"{ext} should map to archive group"


def test_extension_registry_scientific_formats():
    """Scientific data formats map to scientific group."""
    scientific_extensions = [".hdf5", ".h5", ".nc", ".mat"]
    for ext in scientific_extensions:
        assert EXTENSION_REGISTRY[ext] == "scientific", f"{ext} should map to scientific group"


def test_extension_registry_cad_formats():
    """CAD formats map to cad group."""
    cad_extensions = [".dxf", ".dwg"]
    for ext in cad_extensions:
        assert EXTENSION_REGISTRY[ext] == "cad", f"{ext} should map to cad group"


def test_extension_registry_completeness():
    """Registry contains all extensions from spec."""
    # From spec.md - verify we have the complete set
    expected_count = 8 + 6 + 6 + 4 + 4 + 2  # audio + video + parsers + archive + scientific + cad
    assert len(EXTENSION_REGISTRY) == expected_count


# -----------------------------------------------------------------------
# Dependency Check Package Tests
# -----------------------------------------------------------------------


def test_dependency_check_packages_mapping():
    """Each group maps to the correct import package name."""
    assert DEPENDENCY_CHECK_PACKAGES["audio"] == "faster_whisper"
    assert DEPENDENCY_CHECK_PACKAGES["video"] == "cv2"
    assert DEPENDENCY_CHECK_PACKAGES["parsers"] == "fitz"
    assert DEPENDENCY_CHECK_PACKAGES["archive"] == "py7zr"
    assert DEPENDENCY_CHECK_PACKAGES["scientific"] == "h5py"
    assert DEPENDENCY_CHECK_PACKAGES["cad"] == "ezdxf"
    assert DEPENDENCY_CHECK_PACKAGES["dedup"] == "imagededup"


def test_dependency_check_packages_completeness():
    """All groups have a check package defined."""
    expected_groups = ["audio", "video", "parsers", "archive", "scientific", "cad", "dedup"]
    for group in expected_groups:
        assert group in DEPENDENCY_CHECK_PACKAGES, f"{group} missing from dependency checks"


# -----------------------------------------------------------------------
# System Prerequisites Tests
# -----------------------------------------------------------------------


def test_system_prerequisites_audio():
    """Audio group has FFmpeg and CUDA prerequisites."""
    prereqs = SYSTEM_PREREQUISITES["audio"]
    assert len(prereqs) == 2
    assert any("FFmpeg" in p for p in prereqs)
    assert any("CUDA" in p for p in prereqs)


def test_system_prerequisites_archive():
    """Archive group has unrar prerequisite."""
    prereqs = SYSTEM_PREREQUISITES["archive"]
    assert len(prereqs) == 1
    assert any("unrar" in p for p in prereqs)


def test_system_prerequisites_optional():
    """Groups without prerequisites are not in the dict."""
    # Video, parsers, scientific, cad, dedup don't have prerequisites
    groups_without_prereqs = ["video", "parsers", "scientific", "cad", "dedup"]
    for group in groups_without_prereqs:
        assert group not in SYSTEM_PREREQUISITES


# -----------------------------------------------------------------------
# is_group_installed Tests
# -----------------------------------------------------------------------


@patch("file_organizer.cli.doctor.importlib.util.find_spec")
def test_is_group_installed_when_present(mock_find_spec):
    """is_group_installed returns True when package is found."""
    mock_find_spec.return_value = MagicMock()  # Non-None spec = installed

    assert is_group_installed("audio") is True
    mock_find_spec.assert_called_once_with("faster_whisper")


@patch("file_organizer.cli.doctor.importlib.util.find_spec")
def test_is_group_installed_when_missing(mock_find_spec):
    """is_group_installed returns False when package is not found."""
    mock_find_spec.return_value = None  # None spec = not installed

    assert is_group_installed("video") is False
    mock_find_spec.assert_called_once_with("cv2")


@patch("file_organizer.cli.doctor.importlib.util.find_spec")
def test_is_group_installed_unknown_group(mock_find_spec):
    """is_group_installed returns False for unknown groups."""
    assert is_group_installed("nonexistent") is False
    mock_find_spec.assert_not_called()


@patch("file_organizer.cli.doctor.importlib.util.find_spec")
def test_is_group_installed_all_groups(mock_find_spec):
    """is_group_installed checks correct package for each group."""
    mock_find_spec.return_value = MagicMock()

    groups_to_packages = {
        "audio": "faster_whisper",
        "video": "cv2",
        "parsers": "fitz",
        "archive": "py7zr",
        "scientific": "h5py",
        "cad": "ezdxf",
        "dedup": "imagededup",
    }

    for group, expected_package in groups_to_packages.items():
        mock_find_spec.reset_mock()
        is_group_installed(group)
        mock_find_spec.assert_called_once_with(expected_package)


# -----------------------------------------------------------------------
# get_groups_for_extensions Tests
# -----------------------------------------------------------------------


def test_get_groups_for_extensions_single_group():
    """get_groups_for_extensions returns single group for related extensions."""
    audio_extensions = {".mp3", ".wav", ".flac"}
    groups = get_groups_for_extensions(audio_extensions)
    assert groups == {"audio"}


def test_get_groups_for_extensions_multiple_groups():
    """get_groups_for_extensions returns multiple groups for mixed extensions."""
    mixed_extensions = {".mp3", ".pdf", ".mp4"}
    groups = get_groups_for_extensions(mixed_extensions)
    assert groups == {"audio", "parsers", "video"}


def test_get_groups_for_extensions_empty_set():
    """get_groups_for_extensions returns empty set for empty input."""
    groups = get_groups_for_extensions(set())
    assert groups == set()


def test_get_groups_for_extensions_unknown_extensions():
    """get_groups_for_extensions ignores unknown extensions."""
    unknown_extensions = {".txt", ".log", ".unknown"}
    groups = get_groups_for_extensions(unknown_extensions)
    assert groups == set()


def test_get_groups_for_extensions_mixed_known_unknown():
    """get_groups_for_extensions handles mix of known and unknown extensions."""
    mixed = {".mp3", ".txt", ".pdf", ".log"}
    groups = get_groups_for_extensions(mixed)
    assert groups == {"audio", "parsers"}


def test_get_groups_for_extensions_case_insensitive():
    """get_groups_for_extensions normalizes extensions to lowercase."""
    uppercase_extensions = {".MP3", ".PDF", ".MP4"}
    groups = get_groups_for_extensions(uppercase_extensions)
    assert groups == {"audio", "parsers", "video"}


def test_get_groups_for_extensions_all_groups():
    """get_groups_for_extensions can detect all groups simultaneously."""
    all_extensions = {".mp3", ".mp4", ".pdf", ".7z", ".h5", ".dxf"}
    groups = get_groups_for_extensions(all_extensions)
    assert groups == {"audio", "video", "parsers", "archive", "scientific", "cad"}


# -----------------------------------------------------------------------
# get_missing_groups Tests
# -----------------------------------------------------------------------


@patch("file_organizer.cli.doctor.is_group_installed")
def test_get_missing_groups_all_missing(mock_is_installed):
    """get_missing_groups returns all groups when none are installed."""
    mock_is_installed.return_value = False

    detected = {"audio", "video", "parsers"}
    missing = get_missing_groups(detected)
    assert missing == {"audio", "video", "parsers"}


@patch("file_organizer.cli.doctor.is_group_installed")
def test_get_missing_groups_all_installed(mock_is_installed):
    """get_missing_groups returns empty set when all are installed."""
    mock_is_installed.return_value = True

    detected = {"audio", "video", "parsers"}
    missing = get_missing_groups(detected)
    assert missing == set()


@patch("file_organizer.cli.doctor.is_group_installed")
def test_get_missing_groups_partial_installation(mock_is_installed):
    """get_missing_groups returns only non-installed groups."""

    def side_effect(group):
        return group in {"audio", "parsers"}  # Only these are installed

    mock_is_installed.side_effect = side_effect

    detected = {"audio", "video", "parsers", "archive"}
    missing = get_missing_groups(detected)
    assert missing == {"video", "archive"}


@patch("file_organizer.cli.doctor.is_group_installed")
def test_get_missing_groups_empty_input(mock_is_installed):
    """get_missing_groups returns empty set for empty input and short-circuits."""
    detected = set()
    missing = get_missing_groups(detected)
    assert missing == set()
    mock_is_installed.assert_not_called()


# -----------------------------------------------------------------------
# _normalized_extension Tests
# -----------------------------------------------------------------------


def test_normalized_extension_simple():
    """_normalized_extension returns lowercase simple extension."""
    path = Path("/test/file.MP3")
    assert _normalized_extension(path) == ".mp3"


def test_normalized_extension_compound_tar_gz():
    """_normalized_extension preserves .tar.gz compound extension."""
    path = Path("/test/archive.tar.gz")
    assert _normalized_extension(path) == ".tar.gz"


def test_normalized_extension_compound_tar_bz2():
    """_normalized_extension preserves .tar.bz2 compound extension."""
    path = Path("/test/archive.tar.bz2")
    assert _normalized_extension(path) == ".tar.bz2"


def test_normalized_extension_no_extension():
    """_normalized_extension returns empty string for files without extension."""
    path = Path("/test/README")
    assert _normalized_extension(path) == ""


def test_normalized_extension_multiple_dots_non_compound():
    """_normalized_extension returns last suffix for non-compound multi-dot files."""
    path = Path("/test/my.file.name.txt")
    assert _normalized_extension(path) == ".txt"


def test_normalized_extension_uppercase_compound():
    """_normalized_extension normalizes compound extensions to lowercase."""
    path = Path("/test/archive.TAR.GZ")
    assert _normalized_extension(path) == ".tar.gz"


def test_normalized_extension_hidden_file():
    """_normalized_extension handles hidden files correctly."""
    path = Path("/test/.hidden")
    # Hidden files without a real extension return empty string
    assert _normalized_extension(path) == ""


def test_normalized_extension_hidden_file_with_extension():
    """_normalized_extension handles hidden files with extensions."""
    path = Path("/test/.gitignore.txt")
    assert _normalized_extension(path) == ".txt"


# -----------------------------------------------------------------------
# scan_directory Tests
# -----------------------------------------------------------------------


def test_scan_directory(tmp_path):
    """scan_directory scans recursively, counts by extension, and skips hidden files."""
    # Create nested structure with mixed file types
    subdir = tmp_path / "music"
    subdir.mkdir()
    hidden_dir = tmp_path / ".hidden"
    hidden_dir.mkdir()

    # Create visible files
    (tmp_path / "song.mp3").touch()
    (tmp_path / "video.mp4").touch()
    (tmp_path / "document.pdf").touch()
    (tmp_path / "another.mp3").touch()
    (subdir / "nested.wav").touch()
    (tmp_path / "README").touch()  # No extension

    # Create hidden files (should be skipped)
    (tmp_path / ".hidden_file.txt").touch()
    (hidden_dir / "secret.mp3").touch()

    # Scan directory
    counts = scan_directory(tmp_path)

    # Verify correct counts
    assert counts[".mp3"] == 2  # song.mp3 + another.mp3 (not .hidden/secret.mp3)
    assert counts[".mp4"] == 1  # video.mp4
    assert counts[".pdf"] == 1  # document.pdf
    assert counts[".wav"] == 1  # music/nested.wav
    assert counts[""] == 1  # README (no extension)

    # Verify hidden files were skipped
    assert counts.get(".txt", 0) == 0  # .hidden_file.txt was skipped

    # Verify total file count (hidden files and dirs excluded)
    total_files = sum(counts.values())
    assert total_files == 6  # 2 mp3 + 1 mp4 + 1 pdf + 1 wav + 1 no-ext


def test_scan_directory_basic(tmp_path):
    """scan_directory counts files by extension."""
    # Create test files
    (tmp_path / "song.mp3").touch()
    (tmp_path / "video.mp4").touch()
    (tmp_path / "document.pdf").touch()
    (tmp_path / "another.mp3").touch()

    counts = scan_directory(tmp_path)

    assert counts[".mp3"] == 2
    assert counts[".mp4"] == 1
    assert counts[".pdf"] == 1


def test_scan_directory_recursive(tmp_path):
    """scan_directory recursively scans subdirectories."""
    # Create nested structure
    subdir = tmp_path / "music"
    subdir.mkdir()
    (tmp_path / "root.mp3").touch()
    (subdir / "nested.mp3").touch()
    (subdir / "another.wav").touch()

    counts = scan_directory(tmp_path)

    assert counts[".mp3"] == 2
    assert counts[".wav"] == 1


def test_scan_directory_empty(tmp_path):
    """scan_directory returns empty dict for empty directory."""
    counts = scan_directory(tmp_path)
    assert counts == {}


def test_scan_directory_files_without_extensions(tmp_path):
    """scan_directory counts files without extensions."""
    (tmp_path / "README").touch()
    (tmp_path / "LICENSE").touch()
    (tmp_path / "Makefile").touch()

    counts = scan_directory(tmp_path)

    assert counts[""] == 3


def test_scan_directory_mixed_extensions_and_no_extensions(tmp_path):
    """scan_directory handles mix of files with and without extensions."""
    (tmp_path / "README").touch()
    (tmp_path / "file.txt").touch()
    (tmp_path / "another.txt").touch()

    counts = scan_directory(tmp_path)

    assert counts[""] == 1
    assert counts[".txt"] == 2


def test_scan_directory_skips_hidden_files(tmp_path):
    """scan_directory skips hidden files and directories."""
    # Create hidden files
    (tmp_path / ".hidden.txt").touch()
    (tmp_path / "visible.txt").touch()

    # Create hidden directory
    hidden_dir = tmp_path / ".hidden_dir"
    hidden_dir.mkdir()
    (hidden_dir / "file.txt").touch()

    counts = scan_directory(tmp_path)

    # Should only count visible.txt
    assert counts.get(".txt", 0) == 1


def test_scan_directory_case_normalization(tmp_path):
    """scan_directory normalizes extensions to lowercase."""
    (tmp_path / "file1.TXT").touch()
    (tmp_path / "file2.txt").touch()
    (tmp_path / "file3.Txt").touch()

    counts = scan_directory(tmp_path)

    assert counts[".txt"] == 3


def test_scan_directory_compound_extensions(tmp_path):
    """scan_directory handles compound extensions like .tar.gz."""
    (tmp_path / "archive1.tar.gz").touch()
    (tmp_path / "archive2.tar.gz").touch()
    (tmp_path / "archive3.tar.bz2").touch()

    counts = scan_directory(tmp_path)

    assert counts[".tar.gz"] == 2
    assert counts[".tar.bz2"] == 1


def test_scan_directory_ignores_directories(tmp_path):
    """scan_directory counts files only, not directories."""
    # Create directories
    (tmp_path / "subdir1").mkdir()
    (tmp_path / "subdir2").mkdir()

    # Create files
    (tmp_path / "file.txt").touch()

    counts = scan_directory(tmp_path)

    # Should only count the file
    assert counts[".txt"] == 1
    assert len(counts) == 1


def test_scan_directory_deeply_nested(tmp_path):
    """scan_directory handles deeply nested directory structures."""
    # Create deep nesting
    deep_path = tmp_path / "a" / "b" / "c" / "d" / "e"
    deep_path.mkdir(parents=True)

    # Create files at different levels
    (tmp_path / "root.txt").touch()
    (tmp_path / "a" / "level1.txt").touch()
    (tmp_path / "a" / "b" / "level2.txt").touch()
    (deep_path / "deep.txt").touch()

    counts = scan_directory(tmp_path)

    assert counts[".txt"] == 4


def test_scan_directory_large_file_count(tmp_path):
    """scan_directory handles directories with many files."""
    # Create many files
    for i in range(100):
        (tmp_path / f"file{i}.txt").touch()

    for i in range(50):
        (tmp_path / f"image{i}.jpg").touch()

    counts = scan_directory(tmp_path)

    assert counts[".txt"] == 100
    assert counts[".jpg"] == 50


def test_scan_directory_special_characters_in_names(tmp_path):
    """scan_directory handles files with special characters in names."""
    (tmp_path / "file with spaces.txt").touch()
    (tmp_path / "file-with-dashes.txt").touch()
    (tmp_path / "file_with_underscores.txt").touch()
    (tmp_path / "file[brackets].txt").touch()

    counts = scan_directory(tmp_path)

    assert counts[".txt"] == 4


def test_scan_directory_permission_denied(tmp_path):
    """scan_directory handles permission denied gracefully without crashing."""
    # Create files: one accessible, one that will trigger PermissionError
    (tmp_path / "accessible.txt").touch()
    restricted_file = tmp_path / "restricted.txt"
    restricted_file.touch()

    original_is_symlink = Path.is_symlink

    def _is_symlink_with_error(self):
        if self == restricted_file:
            raise PermissionError(f"Permission denied: {self}")
        return original_is_symlink(self)

    with patch.object(Path, "is_symlink", _is_symlink_with_error):
        counts = scan_directory(tmp_path)

    # Accessible file counted, restricted file skipped due to PermissionError
    assert counts.get(".txt", 0) == 1


# -----------------------------------------------------------------------
# Integration Tests - Full Workflow
# -----------------------------------------------------------------------


@patch("file_organizer.cli.doctor.is_group_installed")
def test_full_workflow_detection_and_filtering(mock_is_installed, tmp_path):
    """Test complete workflow from scan to missing group detection."""
    # Setup: Create test files
    (tmp_path / "song.mp3").touch()
    (tmp_path / "video.mp4").touch()
    (tmp_path / "doc.pdf").touch()

    # Mock: audio and video installed, parsers not installed
    def side_effect(group):
        return group in {"audio", "video"}

    mock_is_installed.side_effect = side_effect

    # Step 1: Scan directory
    extension_counts = scan_directory(tmp_path)
    assert ".mp3" in extension_counts
    assert ".mp4" in extension_counts
    assert ".pdf" in extension_counts

    # Step 2: Get groups for extensions
    extensions = set(extension_counts.keys())
    detected_groups = get_groups_for_extensions(extensions)
    assert detected_groups == {"audio", "video", "parsers"}

    # Step 3: Filter to missing groups
    missing_groups = get_missing_groups(detected_groups)
    assert missing_groups == {"parsers"}


def test_edge_case_no_supported_files(tmp_path):
    """Test workflow when directory has no supported file types."""
    # Create files with unsupported extensions
    (tmp_path / "notes.txt").touch()
    (tmp_path / "config.json").touch()
    (tmp_path / "script.sh").touch()

    extension_counts = scan_directory(tmp_path)
    extensions = set(extension_counts.keys())
    detected_groups = get_groups_for_extensions(extensions)

    assert detected_groups == set()


@patch("file_organizer.cli.doctor.is_group_installed")
def test_edge_case_all_groups_installed(mock_is_installed, tmp_path):
    """Test workflow when all needed groups are already installed."""
    mock_is_installed.return_value = True

    (tmp_path / "song.mp3").touch()
    (tmp_path / "video.mp4").touch()

    extension_counts = scan_directory(tmp_path)
    extensions = set(extension_counts.keys())
    detected_groups = get_groups_for_extensions(extensions)
    missing_groups = get_missing_groups(detected_groups)

    assert detected_groups == {"audio", "video"}
    assert missing_groups == set()
