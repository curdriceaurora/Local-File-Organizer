"""Tests for PARA ai/file_mover uncovered branches.

Targets: MoveSuggestion validation, move_file source not exists,
move_file collision resolution, bulk_organize non-dir, suggest_archive
non-dir, suggest_archive stat error, _resolve_collision overflow.
"""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.methodologies.para.ai.file_mover import (
    MoveSuggestion,
    OrganizationReport,
    PARAFileMover,
)
from file_organizer.methodologies.para.categories import PARACategory
from file_organizer.methodologies.para.config import PARAConfig

pytestmark = pytest.mark.unit


class TestMoveSuggestionValidation:
    """Cover MoveSuggestion.__post_init__ — lines 43-44."""

    def test_confidence_too_high(self) -> None:
        with pytest.raises(ValueError, match="between 0.0 and 1.0"):
            MoveSuggestion(
                file_path=Path("/x.txt"),
                target_category=PARACategory.PROJECT,
                target_path=Path("/dst/x.txt"),
                confidence=1.5,
            )

    def test_confidence_too_low(self) -> None:
        with pytest.raises(ValueError, match="between 0.0 and 1.0"):
            MoveSuggestion(
                file_path=Path("/x.txt"),
                target_category=PARACategory.PROJECT,
                target_path=Path("/dst/x.txt"),
                confidence=-0.1,
            )


class TestOrganizationReport:
    """Cover OrganizationReport.success_rate — lines 91-93."""

    def test_success_rate_zero_total(self) -> None:
        report = OrganizationReport(total_files=0, moved=0)
        assert report.success_rate == 0.0

    def test_success_rate_with_files(self) -> None:
        report = OrganizationReport(total_files=10, moved=7)
        assert report.success_rate == pytest.approx(0.7)


class TestMoveFile:
    """Cover move_file branches — lines 222-224, 258, 276-277, 289-293."""

    def test_source_not_exists(self, tmp_path: Path) -> None:
        """Source file missing returns error (lines 178-185)."""
        config = PARAConfig()
        engine = MagicMock()
        mover = PARAFileMover(config, suggestion_engine=engine, root_dir=tmp_path)
        suggestion = MoveSuggestion(
            file_path=tmp_path / "missing.txt",
            target_category=PARACategory.PROJECT,
            target_path=tmp_path / "Projects" / "missing.txt",
            confidence=0.8,
        )
        result = mover.move_file(suggestion, dry_run=False)
        assert result.success is False
        assert "does not exist" in result.error

    def test_source_already_at_destination(self, tmp_path: Path) -> None:
        """Source == destination returns success."""
        f = tmp_path / "file.txt"
        f.write_text("content")
        config = PARAConfig()
        engine = MagicMock()
        mover = PARAFileMover(config, suggestion_engine=engine, root_dir=tmp_path)
        suggestion = MoveSuggestion(
            file_path=f,
            target_category=PARACategory.PROJECT,
            target_path=f,
            confidence=0.8,
        )
        result = mover.move_file(suggestion, dry_run=False)
        assert result.success is True

    def test_move_file_os_error(self, tmp_path: Path) -> None:
        """OSError during move returns error (lines 222-224)."""
        src = tmp_path / "src.txt"
        src.write_text("content")
        config = PARAConfig()
        engine = MagicMock()
        mover = PARAFileMover(config, suggestion_engine=engine, root_dir=tmp_path)
        suggestion = MoveSuggestion(
            file_path=src,
            target_category=PARACategory.PROJECT,
            target_path=Path("/proc/impossible/dst.txt"),
            confidence=0.8,
        )
        result = mover.move_file(suggestion, dry_run=False)
        assert result.success is False
        assert result.error is not None

    def test_move_file_collision_resolution(self, tmp_path: Path) -> None:
        """When target exists, collision resolution appends counter (lines 448-450)."""
        src = tmp_path / "src.txt"
        src.write_text("source")
        dst_dir = tmp_path / "Projects"
        dst_dir.mkdir()
        (dst_dir / "src.txt").write_text("existing")

        config = PARAConfig()
        engine = MagicMock()
        mover = PARAFileMover(config, suggestion_engine=engine, root_dir=tmp_path)
        suggestion = MoveSuggestion(
            file_path=src,
            target_category=PARACategory.PROJECT,
            target_path=dst_dir / "src.txt",
            confidence=0.8,
        )
        result = mover.move_file(suggestion, dry_run=False)
        assert result.success is True
        assert result.destination.name == "src_1.txt"


class TestBulkOrganize:
    """Cover bulk_organize branches — lines 258, 276-277, 289-293."""

    def test_bulk_organize_nonexistent_dir(self, tmp_path: Path) -> None:
        """Non-existent directory returns empty report (line 253-254)."""
        config = PARAConfig()
        engine = MagicMock()
        mover = PARAFileMover(config, suggestion_engine=engine, root_dir=tmp_path)
        report = mover.bulk_organize(tmp_path / "nonexistent")
        assert report.total_files == 0

    def test_bulk_organize_low_confidence_skipped(self, tmp_path: Path) -> None:
        """Files with low confidence are skipped (line 270-271)."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "file.txt").write_text("hello")

        config = PARAConfig()
        mock_suggestion = MagicMock()
        mock_suggestion.category = PARACategory.PROJECT
        mock_suggestion.confidence = 0.1
        mock_suggestion.reasoning = ["low"]
        mock_suggestion.suggested_subfolder = None

        engine = MagicMock()
        engine.suggest.return_value = mock_suggestion
        mover = PARAFileMover(config, suggestion_engine=engine, root_dir=tmp_path)
        report = mover.bulk_organize(src_dir, min_confidence=0.5)
        assert report.skipped >= 1

    def test_bulk_organize_error_handling(self, tmp_path: Path) -> None:
        """Exception during processing increments errors (lines 291-293)."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "file.txt").write_text("hello")

        config = PARAConfig()
        engine = MagicMock()
        engine.suggest.side_effect = RuntimeError("engine failure")
        mover = PARAFileMover(config, suggestion_engine=engine, root_dir=tmp_path)
        report = mover.bulk_organize(src_dir)
        assert report.errors >= 1


class TestSuggestArchive:
    """Cover suggest_archive branches — lines 324-326, 352-353."""

    def test_suggest_archive_non_dir(self, tmp_path: Path) -> None:
        """Non-directory returns empty list."""
        config = PARAConfig()
        engine = MagicMock()
        mover = PARAFileMover(config, suggestion_engine=engine, root_dir=tmp_path)
        result = mover.suggest_archive(tmp_path / "nonexistent")
        assert result == []

    def test_suggest_archive_old_files(self, tmp_path: Path) -> None:
        """Files older than threshold are suggested for archive."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        old_file = src_dir / "old.txt"
        old_file.write_text("old content")

        config = PARAConfig()
        engine = MagicMock()
        mover = PARAFileMover(config, suggestion_engine=engine, root_dir=tmp_path)

        # Patch time.time to make file appear old
        with patch("file_organizer.methodologies.para.ai.file_mover.time") as mock_time:
            mock_time.time.return_value = time.time() + 200 * 86400
            suggestions = mover.suggest_archive(src_dir, inactive_days=180)

        assert len(suggestions) >= 1
        assert suggestions[0].target_category == PARACategory.ARCHIVE


class TestResolveCollision:
    """Cover _resolve_collision overflow — lines 449-453."""

    def test_resolve_collision_no_conflict(self, tmp_path: Path) -> None:
        config = PARAConfig()
        engine = MagicMock()
        mover = PARAFileMover(config, suggestion_engine=engine, root_dir=tmp_path)
        dest = tmp_path / "new_file.txt"
        result = mover._resolve_collision(dest)
        assert result == dest

    def test_resolve_collision_finds_alternative(self, tmp_path: Path) -> None:
        config = PARAConfig()
        engine = MagicMock()
        mover = PARAFileMover(config, suggestion_engine=engine, root_dir=tmp_path)
        dest = tmp_path / "file.txt"
        dest.write_text("existing")
        result = mover._resolve_collision(dest)
        assert result.name == "file_1.txt"
