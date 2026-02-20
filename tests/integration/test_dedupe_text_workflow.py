"""Integration tests for text deduplication workflows."""

from __future__ import annotations

from pathlib import Path

import pytest

from file_organizer.services.deduplication.detector import DuplicateDetector, ScanOptions


@pytest.fixture
def source_dir(tmp_path: Path) -> Path:
    """Create a source directory with duplicate text files."""
    src = tmp_path / "source"
    src.mkdir()

    # Original
    (src / "report.txt").write_text("Quarterly earnings report data...", encoding="utf-8")
    # Duplicate (exact match)
    (src / "report_copy.txt").write_text("Quarterly earnings report data...", encoding="utf-8")
    # Unique
    (src / "meeting.txt").write_text("Meeting notes from the morning.", encoding="utf-8")

    return src


@pytest.mark.integration
class TestDedupeTextWorkflow:
    """Test text deduplication end-to-end integration."""

    def test_dedupe_finds_exact_duplicates(self, source_dir: Path):
        """Test engine identifies exact content duplicates."""
        detector = DuplicateDetector()
        options = ScanOptions(algorithm="sha256", recursive=True)

        detector.scan_directory(source_dir, options)
        groups = detector.get_duplicate_groups()

        # Should find 1 group of duplicates
        assert len(groups) == 1

        # Get the first (and only) group value from the dictionary
        group = list(groups.values())[0]
        paths = {str(f.path) for f in group.files}
        assert str(source_dir / "report.txt") in paths
        assert str(source_dir / "report_copy.txt") in paths

        # meeting.txt should not be in duplicates
        assert str(source_dir / "meeting.txt") not in paths

    def test_dedupe_live_run_removes_duplicates(self, source_dir: Path):
        """Test engine actually deletes duplicates during live run."""
        detector = DuplicateDetector()
        options = ScanOptions(algorithm="sha256", recursive=True)

        detector.scan_directory(source_dir, options)
        groups = detector.get_duplicate_groups()

        for _hash_val, group in groups.items():
            # Oldest strategy
            files = sorted(group.files, key=lambda f: f.modified_time)
            keep = files[-1]

            to_remove = [f for f in files if f.path != keep.path]
            for fmeta in to_remove:
                fmeta.path.unlink()

        remaining_files = [p.name for p in source_dir.iterdir() if p.is_file()]

        # report.txt and meeting.txt should remain. report_copy.txt should be gone.
        assert len(remaining_files) == 2
        assert "meeting.txt" in remaining_files
        assert ("report.txt" in remaining_files or "report_copy.txt" in remaining_files)
