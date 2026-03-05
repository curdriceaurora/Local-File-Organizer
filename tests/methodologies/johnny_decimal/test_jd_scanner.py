"""Tests for Johnny Decimal scanner uncovered branches.

Targets: _scan_folder max depth, permission error, _create_folder_info
permission error, _detect_patterns date/JD/flat/deep, _looks_like_jd_number,
_generate_warnings deep/many/duplicates.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from file_organizer.methodologies.johnny_decimal.scanner import FolderScanner

pytestmark = pytest.mark.unit


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
        from file_organizer.methodologies.johnny_decimal.scanner import FolderInfo

        scanner = FolderScanner()
        tree = [
            FolderInfo(path=tmp_path / "dup", name="dup", depth=0),
            FolderInfo(path=tmp_path / "dup2", name="dup", depth=0),
        ]
        warnings = scanner._generate_warnings(tree, 2)
        assert any("Duplicate" in w for w in warnings)
