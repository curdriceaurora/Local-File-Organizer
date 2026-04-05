"""Integration tests for PARAFileMover, MoveSuggestion, MoveResult, and OrganizationReport.

All filesystem operations run under pytest's tmp_path fixture.
The PARASuggestionEngine is replaced with a lightweight fake to avoid
invoking Ollama or any external service.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.ci]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_engine_stub(
    category: str = "resource",
    confidence: float = 0.75,
    subfolder: str | None = None,
) -> MagicMock:
    """Return a mock PARASuggestionEngine whose suggest() returns a PARASuggestion."""
    from file_organizer.methodologies.para.ai.suggestion_engine import PARASuggestion
    from file_organizer.methodologies.para.categories import PARACategory

    cat = PARACategory(category)
    suggestion = PARASuggestion(
        category=cat,
        confidence=confidence,
        reasoning=[f"stub: {category}"],
        suggested_subfolder=subfolder,
    )

    engine = MagicMock()
    engine.suggest.return_value = suggestion
    return engine


def _make_mover(
    tmp_path: Path,
    engine_stub: MagicMock | None = None,
    category: str = "resource",
    confidence: float = 0.75,
) -> Any:
    """Construct a PARAFileMover wired to a stub engine and tmp_path root."""
    from file_organizer.methodologies.para.ai.file_mover import PARAFileMover

    stub = engine_stub or _make_engine_stub(category=category, confidence=confidence)
    return PARAFileMover(suggestion_engine=stub, root_dir=tmp_path)


# ---------------------------------------------------------------------------
# MoveSuggestion
# ---------------------------------------------------------------------------


class TestMoveSuggestion:
    """Tests for MoveSuggestion dataclass validation."""

    def test_valid_confidence_stored(self, tmp_path: Path) -> None:
        """MoveSuggestion stores valid confidence without error."""
        from file_organizer.methodologies.para.ai.file_mover import MoveSuggestion
        from file_organizer.methodologies.para.categories import PARACategory

        sugg = MoveSuggestion(
            file_path=tmp_path / "note.txt",
            target_category=PARACategory.AREA,
            target_path=tmp_path / "Areas" / "note.txt",
            confidence=0.5,
        )

        assert sugg.confidence == 0.5
        assert sugg.target_category == PARACategory.AREA

    def test_confidence_zero_is_valid(self, tmp_path: Path) -> None:
        """confidence=0.0 is a valid boundary value."""
        from file_organizer.methodologies.para.ai.file_mover import MoveSuggestion
        from file_organizer.methodologies.para.categories import PARACategory

        sugg = MoveSuggestion(
            file_path=tmp_path / "f.txt",
            target_category=PARACategory.ARCHIVE,
            target_path=tmp_path / "Archive" / "f.txt",
            confidence=0.0,
        )
        assert sugg.confidence == 0.0

    def test_confidence_one_is_valid(self, tmp_path: Path) -> None:
        """confidence=1.0 is a valid boundary value."""
        from file_organizer.methodologies.para.ai.file_mover import MoveSuggestion
        from file_organizer.methodologies.para.categories import PARACategory

        sugg = MoveSuggestion(
            file_path=tmp_path / "f.txt",
            target_category=PARACategory.PROJECT,
            target_path=tmp_path / "Projects" / "f.txt",
            confidence=1.0,
        )
        assert sugg.confidence == 1.0

    def test_confidence_above_one_raises(self, tmp_path: Path) -> None:
        """confidence > 1.0 raises ValueError from __post_init__."""
        from file_organizer.methodologies.para.ai.file_mover import MoveSuggestion
        from file_organizer.methodologies.para.categories import PARACategory

        with pytest.raises(ValueError, match="confidence"):
            MoveSuggestion(
                file_path=tmp_path / "f.txt",
                target_category=PARACategory.AREA,
                target_path=tmp_path / "Areas" / "f.txt",
                confidence=1.5,
            )

    def test_confidence_below_zero_raises(self, tmp_path: Path) -> None:
        """confidence < 0.0 raises ValueError from __post_init__."""
        from file_organizer.methodologies.para.ai.file_mover import MoveSuggestion
        from file_organizer.methodologies.para.categories import PARACategory

        with pytest.raises(ValueError, match="confidence"):
            MoveSuggestion(
                file_path=tmp_path / "f.txt",
                target_category=PARACategory.RESOURCE,
                target_path=tmp_path / "Resources" / "f.txt",
                confidence=-0.1,
            )

    def test_reasoning_defaults_to_empty_list(self, tmp_path: Path) -> None:
        """reasoning field defaults to [] when not supplied."""
        from file_organizer.methodologies.para.ai.file_mover import MoveSuggestion
        from file_organizer.methodologies.para.categories import PARACategory

        sugg = MoveSuggestion(
            file_path=tmp_path / "f.txt",
            target_category=PARACategory.PROJECT,
            target_path=tmp_path / "Projects" / "f.txt",
            confidence=0.7,
        )
        assert sugg.reasoning == []


# ---------------------------------------------------------------------------
# OrganizationReport
# ---------------------------------------------------------------------------


class TestOrganizationReport:
    """Tests for OrganizationReport.success_rate property."""

    def test_success_rate_zero_when_no_files(self) -> None:
        """success_rate is 0.0 when total_files is 0."""
        from file_organizer.methodologies.para.ai.file_mover import OrganizationReport

        report = OrganizationReport()
        assert report.success_rate == 0.0

    def test_success_rate_all_moved(self) -> None:
        """success_rate is 1.0 when all files are moved."""
        from file_organizer.methodologies.para.ai.file_mover import OrganizationReport

        report = OrganizationReport(total_files=5, moved=5)
        assert report.success_rate == 1.0

    def test_success_rate_partial(self) -> None:
        """success_rate returns moved/total_files."""
        from file_organizer.methodologies.para.ai.file_mover import OrganizationReport

        report = OrganizationReport(total_files=4, moved=3)
        assert abs(report.success_rate - 0.75) < 1e-9

    def test_success_rate_none_moved(self) -> None:
        """success_rate is 0.0 when no files were moved but total_files > 0."""
        from file_organizer.methodologies.para.ai.file_mover import OrganizationReport

        report = OrganizationReport(total_files=3, moved=0)
        assert report.success_rate == 0.0


# ---------------------------------------------------------------------------
# PARAFileMover
# ---------------------------------------------------------------------------


class TestPARAFileMover:
    """Tests for PARAFileMover core operations."""

    # --- root_dir property ---

    def test_root_dir_property(self, tmp_path: Path) -> None:
        """root_dir property returns the directory supplied at construction."""
        mover = _make_mover(tmp_path)
        assert mover.root_dir == tmp_path

    # --- suggest_move ---

    def test_suggest_move_happy_path(self, tmp_path: Path) -> None:
        """suggest_move returns a MoveSuggestion with expected category and path."""
        from file_organizer.methodologies.para.categories import PARACategory

        stub = _make_engine_stub(category="resource", confidence=0.75)
        mover = _make_mover(tmp_path, engine_stub=stub)

        src = tmp_path / "guide.pdf"
        src.write_text("content")

        sugg = mover.suggest_move(src)

        assert sugg.file_path == src
        assert sugg.target_category == PARACategory.RESOURCE
        assert 0.0 <= sugg.confidence <= 1.0
        assert sugg.target_path.name == "guide.pdf"
        assert "Resources" in str(sugg.target_path)

    def test_suggest_move_includes_reasoning(self, tmp_path: Path) -> None:
        """suggest_move passes reasoning from the engine through to MoveSuggestion."""
        stub = _make_engine_stub(category="project", confidence=0.85)
        mover = _make_mover(tmp_path, engine_stub=stub)

        src = tmp_path / "plan.md"
        src.write_text("# plan")

        sugg = mover.suggest_move(src)
        # Verify the engine's exact stub reasoning was passed through
        assert len(sugg.reasoning) >= 1
        assert sugg.reasoning[0] == "stub: project"

    def test_suggest_move_with_subfolder(self, tmp_path: Path) -> None:
        """When engine returns a suggested_subfolder, target_path includes it."""
        stub = _make_engine_stub(category="project", confidence=0.80, subfolder="2024-Q1")
        mover = _make_mover(tmp_path, engine_stub=stub)

        src = tmp_path / "sprint.md"
        src.write_text("sprint notes")

        sugg = mover.suggest_move(src)
        assert "2024-Q1" in str(sugg.target_path)

    # --- move_file ---

    def test_move_file_dry_run_does_not_move(self, tmp_path: Path) -> None:
        """move_file with dry_run=True leaves the source file in place."""
        stub = _make_engine_stub(category="archive", confidence=0.9)
        mover = _make_mover(tmp_path, engine_stub=stub)

        src = tmp_path / "old.txt"
        src.write_text("old content")

        sugg = mover.suggest_move(src)
        result = mover.move_file(sugg, dry_run=True)

        assert result.success is True
        assert result.dry_run is True
        assert src.exists()  # file not moved
        # Target must not have been created — a buggy dry-run might copy it
        assert not sugg.target_path.exists()

    def test_move_file_actual_move_succeeds(self, tmp_path: Path) -> None:
        """move_file with dry_run=False moves the file and returns success."""
        stub = _make_engine_stub(category="resource", confidence=0.8)
        mover = _make_mover(tmp_path, engine_stub=stub)

        src = tmp_path / "manual.pdf"
        src.write_text("manual content")

        sugg = mover.suggest_move(src)
        result = mover.move_file(sugg, dry_run=False)

        assert result.success is True
        assert result.dry_run is False
        assert result.error is None
        assert not src.exists()
        assert result.destination.exists()

    def test_move_file_missing_source_returns_failure(self, tmp_path: Path) -> None:
        """move_file returns MoveResult with success=False when source is missing."""
        from file_organizer.methodologies.para.ai.file_mover import MoveSuggestion
        from file_organizer.methodologies.para.categories import PARACategory

        mover = _make_mover(tmp_path)
        sugg = MoveSuggestion(
            file_path=tmp_path / "nonexistent.txt",
            target_category=PARACategory.ARCHIVE,
            target_path=tmp_path / "Archive" / "nonexistent.txt",
            confidence=0.7,
        )

        result = mover.move_file(sugg, dry_run=False)

        assert result.success is False
        assert result.error is not None
        assert "does not exist" in result.error

    # --- collision resolution ---

    def test_move_file_collision_resolved_with_counter(self, tmp_path: Path) -> None:
        """When destination already exists, _resolve_collision appends a counter."""
        stub = _make_engine_stub(category="resource", confidence=0.8)
        mover = _make_mover(tmp_path, engine_stub=stub)

        src = tmp_path / "report.pdf"
        src.write_text("new report")

        # Pre-create the destination so a collision exists
        dest_dir = tmp_path / "Resources"
        dest_dir.mkdir(parents=True, exist_ok=True)
        existing = dest_dir / "report.pdf"
        existing.write_text("existing report")

        sugg = mover.suggest_move(src)
        result = mover.move_file(sugg, dry_run=False)

        assert result.success is True
        assert result.destination.name == "report_1.pdf"
        assert result.destination.exists()
        assert existing.exists()  # original not touched

    # --- already-organized detection ---

    def test_is_already_organized_true_when_in_category_dir(self, tmp_path: Path) -> None:
        """_is_already_organized returns True for a file already in its category folder."""
        from file_organizer.methodologies.para.categories import PARACategory

        mover = _make_mover(tmp_path)

        category_dir = tmp_path / "Resources"
        category_dir.mkdir()
        file_in_dir = category_dir / "guide.txt"
        file_in_dir.write_text("guide")

        assert mover._is_already_organized(file_in_dir, PARACategory.RESOURCE) is True

    def test_is_already_organized_false_when_outside_category_dir(self, tmp_path: Path) -> None:
        """_is_already_organized returns False for a file outside the category folder."""
        from file_organizer.methodologies.para.categories import PARACategory

        mover = _make_mover(tmp_path)

        other_dir = tmp_path / "Projects"
        other_dir.mkdir()
        file_in_wrong = other_dir / "guide.txt"
        file_in_wrong.write_text("guide")

        assert mover._is_already_organized(file_in_wrong, PARACategory.RESOURCE) is False

    # --- bulk_organize ---

    def test_bulk_organize_processes_multiple_files(self, tmp_path: Path) -> None:
        """bulk_organize returns OrganizationReport with total_files matching input."""
        stub = _make_engine_stub(category="resource", confidence=0.9)
        mover = _make_mover(tmp_path, engine_stub=stub)

        src_dir = tmp_path / "inbox"
        src_dir.mkdir()
        for name in ("a.txt", "b.txt", "c.txt"):
            (src_dir / name).write_text("content")

        report = mover.bulk_organize(src_dir, dry_run=True, min_confidence=0.5)

        assert report.total_files == 3

    def test_bulk_organize_dry_run_does_not_move_files(self, tmp_path: Path) -> None:
        """bulk_organize with dry_run=True leaves all files in place."""
        stub = _make_engine_stub(category="project", confidence=0.8)
        mover = _make_mover(tmp_path, engine_stub=stub)

        src_dir = tmp_path / "inbox"
        src_dir.mkdir()
        f = src_dir / "work.txt"
        f.write_text("work")

        report = mover.bulk_organize(src_dir, dry_run=True, min_confidence=0.5)

        assert f.exists()  # not moved
        assert report.moved >= 1  # counted as would-be moved

    def test_bulk_organize_skips_low_confidence(self, tmp_path: Path) -> None:
        """bulk_organize skips files whose suggestion confidence is below min_confidence."""
        stub = _make_engine_stub(category="archive", confidence=0.3)
        mover = _make_mover(tmp_path, engine_stub=stub)

        src_dir = tmp_path / "inbox"
        src_dir.mkdir()
        (src_dir / "low.txt").write_text("low confidence file")

        report = mover.bulk_organize(src_dir, dry_run=True, min_confidence=0.6)

        assert report.skipped == 1
        assert report.moved == 0

    def test_bulk_organize_empty_directory(self, tmp_path: Path) -> None:
        """bulk_organize on an empty directory returns a zero-count report."""
        mover = _make_mover(tmp_path)
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        report = mover.bulk_organize(empty_dir, dry_run=True)

        assert report.total_files == 0
        assert report.moved == 0

    def test_bulk_organize_nonexistent_directory(self, tmp_path: Path) -> None:
        """bulk_organize on a nonexistent path returns an empty report, no exception."""
        mover = _make_mover(tmp_path)

        report = mover.bulk_organize(tmp_path / "does_not_exist", dry_run=True)

        assert report.total_files == 0

    def test_bulk_organize_actual_move_updates_distribution(self, tmp_path: Path) -> None:
        """bulk_organize populates category_distribution when moves succeed."""
        stub = _make_engine_stub(category="resource", confidence=0.9)
        mover = _make_mover(tmp_path, engine_stub=stub)

        src_dir = tmp_path / "inbox"
        src_dir.mkdir()
        (src_dir / "doc1.txt").write_text("doc1")
        (src_dir / "doc2.txt").write_text("doc2")

        report = mover.bulk_organize(src_dir, dry_run=False, min_confidence=0.5)

        assert report.moved == 2
        assert report.category_distribution.get("resource", 0) == 2

    # --- suggest_archive ---

    def test_suggest_archive_old_file_gets_archive_suggestion(self, tmp_path: Path) -> None:
        """suggest_archive returns ARCHIVE suggestion for files older than threshold."""
        import time

        from file_organizer.methodologies.para.categories import PARACategory

        mover = _make_mover(tmp_path)

        scan_dir = tmp_path / "scan"
        scan_dir.mkdir()
        old_file = scan_dir / "old_report.pdf"
        old_file.write_text("old report")

        # Set mtime to 400 days ago (well past 180-day threshold)
        past_mtime = time.time() - (400 * 86400)
        import os

        os.utime(old_file, (past_mtime, past_mtime))

        suggestions = mover.suggest_archive(scan_dir, inactive_days=180)

        assert len(suggestions) >= 1
        archive_sugg = next((s for s in suggestions if s.file_path == old_file), None)
        assert archive_sugg is not None
        assert archive_sugg.target_category == PARACategory.ARCHIVE
        assert archive_sugg.confidence > 0.5

    def test_suggest_archive_recent_file_excluded(self, tmp_path: Path) -> None:
        """suggest_archive does not include recently modified files."""
        mover = _make_mover(tmp_path)

        scan_dir = tmp_path / "scan"
        scan_dir.mkdir()
        new_file = scan_dir / "current.md"
        new_file.write_text("active content")
        # mtime defaults to now — well within 180 days

        suggestions = mover.suggest_archive(scan_dir, inactive_days=180)

        file_paths = [s.file_path for s in suggestions]
        assert new_file not in file_paths

    def test_suggest_archive_nonexistent_directory_returns_empty(self, tmp_path: Path) -> None:
        """suggest_archive returns [] for a nonexistent directory."""
        mover = _make_mover(tmp_path)
        suggestions = mover.suggest_archive(tmp_path / "no_such_dir")
        assert suggestions == []

    def test_suggest_archive_reasoning_mentions_days(self, tmp_path: Path) -> None:
        """suggest_archive includes day count in reasoning."""
        import os
        import time

        mover = _make_mover(tmp_path)

        scan_dir = tmp_path / "scan"
        scan_dir.mkdir()
        old_file = scan_dir / "stale.txt"
        old_file.write_text("stale")
        past_mtime = time.time() - (200 * 86400)
        os.utime(old_file, (past_mtime, past_mtime))

        suggestions = mover.suggest_archive(scan_dir, inactive_days=180)

        assert len(suggestions) >= 1
        s = suggestions[0]
        assert len(s.reasoning) >= 1
        assert "days" in s.reasoning[0]
