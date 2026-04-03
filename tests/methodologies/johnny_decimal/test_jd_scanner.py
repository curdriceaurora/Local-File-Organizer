"""Tests for Johnny Decimal scanner uncovered branches.

Targets: _scan_folder max depth, permission error, _create_folder_info
permission error, _detect_patterns date/JD/flat/deep, _looks_like_jd_number,
_generate_warnings deep/many/duplicates.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest

from file_organizer.methodologies.johnny_decimal.categories import get_default_scheme
from file_organizer.methodologies.johnny_decimal.scanner import FolderInfo, FolderScanner
from file_organizer.methodologies.johnny_decimal.system import JohnnyDecimalSystem

pytestmark = pytest.mark.unit


def _create_broken_symlink_or_skip(link_path: Path, target_path: Path) -> None:
    try:
        link_path.symlink_to(target_path)
    except (NotImplementedError, OSError):
        pytest.skip("Symlink creation is not supported in this environment")


@pytest.fixture
def scanner() -> FolderScanner:
    return FolderScanner(max_depth=3)


class TestScanDirectory:
    """Cover scan_directory edge cases — lines 144-146, 163-164."""

    def test_nonexistent_path_raises(self, scanner: FolderScanner) -> None:
        with pytest.raises(ValueError, match="does not exist"):
            scanner.scan_directory(Path("/nonexistent"))

    def test_not_a_dir_raises(self, scanner: FolderScanner, tmp_path: Path) -> None:
        f = tmp_path / "file.txt"
        f.write_text("x")
        with pytest.raises(ValueError, match="not a directory"):
            scanner.scan_directory(f)

    def test_basic_scan(self, scanner: FolderScanner, tmp_path: Path) -> None:
        (tmp_path / "folder1").mkdir()
        (tmp_path / "folder1" / "sub").mkdir()
        (tmp_path / "file.txt").write_text("content")
        result = scanner.scan_directory(tmp_path)
        assert result.total_folders >= 1
        assert result.total_files >= 1

    def test_max_depth_exceeded(self, tmp_path: Path) -> None:
        """Folders beyond max_depth are not scanned (line 136-138)."""
        scanner = FolderScanner(max_depth=1)
        deep = tmp_path / "a" / "b" / "c"
        deep.mkdir(parents=True)
        result = scanner.scan_directory(tmp_path)
        assert result.max_depth <= 2

    def test_skip_hidden(self, tmp_path: Path) -> None:
        """Hidden files/folders are skipped by default."""
        (tmp_path / ".hidden").mkdir()
        (tmp_path / ".hidden_file.txt").write_text("x")
        (tmp_path / "visible").mkdir()
        scanner = FolderScanner(skip_hidden=True)
        result = scanner.scan_directory(tmp_path)
        names = [f.name for f in result.folder_tree]
        assert ".hidden" not in names


class TestDetectPatterns:
    """Cover _detect_patterns branches — lines 188-191, 246, 262, 272-283."""

    def test_para_pattern_detected(self, scanner: FolderScanner, tmp_path: Path) -> None:
        for name in ["Projects", "Areas", "Resources", "Archive"]:
            (tmp_path / name).mkdir()
        result = scanner.scan_directory(tmp_path)
        assert any("PARA" in p for p in result.detected_patterns)

    def test_date_based_pattern(self, tmp_path: Path) -> None:
        scanner = FolderScanner()
        for year in ["2020", "2021", "2022"]:
            (tmp_path / year).mkdir()
        result = scanner.scan_directory(tmp_path)
        assert any("Date" in p for p in result.detected_patterns)

    def test_jd_pattern_detected(self, tmp_path: Path) -> None:
        scanner = FolderScanner()
        (tmp_path / "10 Finance").mkdir()
        (tmp_path / "20 Projects").mkdir()
        result = scanner.scan_directory(tmp_path)
        assert any("Johnny Decimal" in p for p in result.detected_patterns)

    def test_flat_structure(self, tmp_path: Path) -> None:
        scanner = FolderScanner()
        for i in range(25):
            (tmp_path / f"folder_{i}").mkdir()
        result = scanner.scan_directory(tmp_path)
        assert any("Flat" in p for p in result.detected_patterns)

    def test_deep_structure(self, tmp_path: Path) -> None:
        scanner = FolderScanner(max_depth=10)
        parent = tmp_path / "root"
        parent.mkdir()
        # Create 6+ children in a single folder to trigger "Deep hierarchical"
        for i in range(7):
            (parent / f"sub{i}").mkdir()
        result = scanner.scan_directory(tmp_path)
        assert any("hierarchical" in p.lower() or "Deep" in p for p in result.detected_patterns)

    def test_no_pattern(self, tmp_path: Path) -> None:
        scanner = FolderScanner()
        (tmp_path / "a").mkdir()
        (tmp_path / "b").mkdir()
        result = scanner.scan_directory(tmp_path)
        assert any("No specific" in p for p in result.detected_patterns)


class TestLooksLikeJDNumber:
    """Cover _looks_like_jd_number — lines 262, 272-283, 353."""

    def test_two_digit_area(self, scanner: FolderScanner) -> None:
        assert scanner._looks_like_jd_number("10 Finance") is True

    def test_category_format(self, scanner: FolderScanner) -> None:
        assert scanner._looks_like_jd_number("11.01 Budgets") is True

    def test_id_format(self, scanner: FolderScanner) -> None:
        assert scanner._looks_like_jd_number("11.01.001 Q1") is True

    def test_not_jd(self, scanner: FolderScanner) -> None:
        assert scanner._looks_like_jd_number("Finance Folder") is False

    def test_empty_name(self, scanner: FolderScanner) -> None:
        assert scanner._looks_like_jd_number("") is False

    def test_three_digit_not_jd(self, scanner: FolderScanner) -> None:
        assert scanner._looks_like_jd_number("100 Something") is False


class TestGenerateWarnings:
    """Cover _generate_warnings — lines 337, 344, 353."""

    def test_deep_hierarchy_warning(self, tmp_path: Path) -> None:
        scanner = FolderScanner(max_depth=10)
        parent = tmp_path
        for i in range(7):
            child = parent / f"sub{i}"
            child.mkdir()
            parent = child
        result = scanner.scan_directory(tmp_path)
        assert any("Deep hierarchy" in w for w in result.warnings)

    def test_many_top_level_warning(self, tmp_path: Path) -> None:
        scanner = FolderScanner()
        for i in range(15):
            (tmp_path / f"folder_{i}").mkdir()
        result = scanner.scan_directory(tmp_path)
        assert any("Many top-level" in w for w in result.warnings)

    def test_duplicate_names_warning(self, tmp_path: Path) -> None:
        """Duplicate folder names at same level produce warning (line 353)."""
        # Can't have actual duplicates at same level, but we test through
        # the _generate_warnings directly
        scanner = FolderScanner()
        tree = [
            FolderInfo(path=tmp_path / "dup", name="dup", depth=0),
            FolderInfo(path=tmp_path / "dup2", name="dup", depth=0),
        ]
        warnings = scanner._generate_warnings(tree, 2)
        assert any("Duplicate" in w for w in warnings)


class TestScannerCoverage:
    """Cover all missing lines in scanner.py."""

    @pytest.fixture
    def scanner(self) -> FolderScanner:
        return FolderScanner(get_default_scheme())

    # Lines 144-146: _scan_folder with max depth exceeded
    def test_scan_folder_max_depth(self, tmp_path: Path) -> None:
        scanner = FolderScanner(scheme=JohnnyDecimalSystem().scheme, max_depth=0)
        (tmp_path / "sub" / "inner").mkdir(parents=True)
        result = scanner.scan_directory(tmp_path)
        assert len(result.folder_tree) == 1
        assert result.folder_tree[0].name == "sub"
        assert result.folder_tree[0].children == []

    # Lines 158->148: _scan_folder PermissionError in iterdir (branch)
    def test_scan_folder_permission_denied(self, scanner: FolderScanner, tmp_path: Path) -> None:
        restricted = tmp_path / "restricted"
        restricted.mkdir()
        original_iterdir = Path.iterdir

        def guarded_iterdir(path_self: Path) -> Iterator[Path]:
            if path_self == restricted:
                raise PermissionError("permission denied")
            return original_iterdir(path_self)

        with patch.object(Path, "iterdir", guarded_iterdir):
            result = scanner.scan_directory(tmp_path)
        assert result is not None
        assert any(folder.path == restricted for folder in result.folder_tree)

    # Lines 163-164: _scan_folder counts files and handles OSError on stat
    def test_scan_counts_files(self, scanner: FolderScanner, tmp_path: Path) -> None:
        (tmp_path / "file.txt").write_text("hello")
        result = scanner.scan_directory(tmp_path)
        assert result.total_files >= 1

    # Lines 188-191: _create_folder_info PermissionError
    def test_create_folder_info_permission_error(
        self, scanner: FolderScanner, tmp_path: Path
    ) -> None:
        restricted = tmp_path / "restricted_inner"
        restricted.mkdir()
        inner_file = restricted / "data.txt"
        inner_file.write_text("data")

        def denied_iterdir(path_self: Path) -> Iterator[Path]:
            if path_self == restricted:
                raise PermissionError("permission denied")
            return iter(())

        with patch.object(Path, "iterdir", denied_iterdir):
            info = scanner._create_folder_info(restricted, depth=0)
        assert info.file_count == 0

    # Lines 163-164: OSError on file stat in _scan_folder
    def test_scan_folder_file_stat_oserror(self, scanner: FolderScanner, tmp_path: Path) -> None:
        class BrokenSizeFile:
            name = "file.txt"

            def is_dir(self) -> bool:
                return False

            def is_file(self) -> bool:
                return True

            def stat(self) -> object:
                raise OSError("bad stat")

        with patch.object(Path, "iterdir", return_value=iter([BrokenSizeFile()])):
            result = scanner.scan_directory(tmp_path)
        assert result is not None
        assert result.total_files == 1
        assert result.total_size == 0

    # Lines 188-189: OSError on file stat in _create_folder_info
    def test_create_folder_info_file_stat_oserror(
        self, scanner: FolderScanner, tmp_path: Path
    ) -> None:
        sub = tmp_path / "sub"
        sub.mkdir()

        class BrokenSizeFile:
            name = "file.txt"

            def is_file(self) -> bool:
                return True

            def stat(self) -> object:
                raise OSError("bad stat")

        with patch.object(Path, "iterdir", return_value=iter([BrokenSizeFile()])):
            info = scanner._create_folder_info(sub, depth=0)
        assert info.file_count == 1
        assert info.total_size == 0

    # Lines 284->293, 285->293: _looks_like_jd_number with various formats
    def test_looks_like_jd_id_format(self, scanner: FolderScanner) -> None:
        assert scanner._looks_like_jd_number("11.01.001 Report") is True
        assert scanner._looks_like_jd_number("11.01.1 Bad") is False  # third part not 3 digits
        assert scanner._looks_like_jd_number("") is False
        # 4-part format: not 2 or 3 parts, falls through
        assert scanner._looks_like_jd_number("11.01.001.99 Extra") is False
        # 2-part with non-digit parts
        assert scanner._looks_like_jd_number("ab.cd Nope") is False
        # 2-part with wrong lengths
        assert scanner._looks_like_jd_number("1.1 TooShort") is False

    # Branch 158->148: item is neither file nor dir (broken symlink)
    def test_scan_folder_broken_symlink_skipped(
        self, scanner: FolderScanner, tmp_path: Path
    ) -> None:
        broken = tmp_path / "broken_link"
        _create_broken_symlink_or_skip(broken, tmp_path / "nonexistent")
        result = scanner.scan_directory(tmp_path)
        assert result.total_files == 0

    # PermissionError in _scan_folder during sorted(path.iterdir())
    def test_scan_folder_iterdir_permission_error(
        self, scanner: FolderScanner, tmp_path: Path
    ) -> None:
        sub = tmp_path / "noperm"
        sub.mkdir()
        (sub / "inner").mkdir()

        original_iterdir = Path.iterdir

        def guarded_iterdir(path_self: Path) -> Iterator[Path]:
            if path_self == sub:
                raise PermissionError("permission denied")
            return original_iterdir(path_self)

        with patch.object(Path, "iterdir", guarded_iterdir):
            result = scanner.scan_directory(tmp_path)
        assert result is not None
