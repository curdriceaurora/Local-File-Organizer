"""Tests for Johnny Decimal system uncovered branches.

Targets: initialize_from_directory, _extract_number_from_path,
assign_number_to_file conflict resolution, validate_number_assignment,
renumber_file, get_area_summary.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from file_organizer.methodologies.johnny_decimal.categories import (
    JohnnyDecimalNumber,
)
from file_organizer.methodologies.johnny_decimal.numbering import (
    InvalidNumberError,
    NumberConflictError,
)
from file_organizer.methodologies.johnny_decimal.system import JohnnyDecimalSystem

pytestmark = pytest.mark.unit


@pytest.fixture
def system() -> JohnnyDecimalSystem:
    return JohnnyDecimalSystem()


class TestInitializeFromDirectory:
    """Cover initialize_from_directory — lines 56, 82-83, 107."""

    def test_nonexistent_dir_raises(self, system: JohnnyDecimalSystem) -> None:
        with pytest.raises(ValueError, match="does not exist"):
            system.initialize_from_directory(Path("nonexistent"))

    def test_scans_jd_numbered_dirs(self, system: JohnnyDecimalSystem, tmp_path: Path) -> None:
        """Detects JD numbers from directory names."""
        (tmp_path / "10 Finance").mkdir()
        (tmp_path / "11.01 Budgets").mkdir()
        (tmp_path / "Random Folder").mkdir()
        system.initialize_from_directory(tmp_path)
        assert system._initialized is True
        stats = system.generator.get_usage_statistics()
        assert stats["total_numbers"] >= 1

    def test_handles_conflict_during_scan(
        self, system: JohnnyDecimalSystem, tmp_path: Path
    ) -> None:
        """Duplicate numbers during scan are warned, not raised (line 82-83)."""
        (tmp_path / "10 Finance").mkdir()
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "10 Also Finance").mkdir()
        # Should not raise
        system.initialize_from_directory(tmp_path)


class TestExtractNumberFromPath:
    """Cover _extract_number_from_path — lines 107."""

    def test_extract_area_number(self, system: JohnnyDecimalSystem) -> None:
        num = system._extract_number_from_path(Path("root/10 Finance"))
        assert num is not None
        assert num.area == 10

    def test_extract_category_number(self, system: JohnnyDecimalSystem) -> None:
        num = system._extract_number_from_path(Path("root/11.01 Budgets"))
        assert num is not None
        assert num.area == 11
        assert num.category == 1

    def test_extract_id_number(self, system: JohnnyDecimalSystem) -> None:
        num = system._extract_number_from_path(Path("root/11.01.001 Q1 Budget"))
        assert num is not None
        assert num.item_id == 1

    def test_extract_no_number(self, system: JohnnyDecimalSystem) -> None:
        num = system._extract_number_from_path(Path("root/Random Folder"))
        assert num is None

    def test_extract_empty_name(self, system: JohnnyDecimalSystem) -> None:
        """Edge case with empty name returns None — no crash expected."""
        num = system._extract_number_from_path(Path("root/"))
        assert num is None


class TestAssignNumberToFile:
    """Cover assign_number_to_file — lines 168-170, 190-192, 204-205."""

    def test_assign_with_content(self, system: JohnnyDecimalSystem, tmp_path: Path) -> None:
        f = tmp_path / "report.txt"
        f.write_text("finance budget quarterly")
        result = system.assign_number_to_file(f, content="finance budget quarterly")
        assert result.number is not None
        assert result.confidence > 0

    def test_assign_without_content(self, system: JohnnyDecimalSystem, tmp_path: Path) -> None:
        """No content uses next available number (lines 183-189)."""
        f = tmp_path / "file.txt"
        f.write_text("x")
        result = system.assign_number_to_file(f)
        assert result.number is not None
        assert result.confidence == 0.4

    def test_assign_preferred_valid(self, system: JohnnyDecimalSystem, tmp_path: Path) -> None:
        f = tmp_path / "file.txt"
        f.write_text("x")
        preferred = JohnnyDecimalNumber(area=20, category=5)
        result = system.assign_number_to_file(f, preferred_number=preferred)
        assert result.confidence == 0.95

    def test_assign_preferred_conflict(self, system: JohnnyDecimalSystem, tmp_path: Path) -> None:
        """Preferred number with conflict resolves it (lines 163-167)."""
        f1 = tmp_path / "f1.txt"
        f1.write_text("x")
        f2 = tmp_path / "f2.txt"
        f2.write_text("y")

        preferred = JohnnyDecimalNumber(area=20, category=5)
        system.assign_number_to_file(f1, preferred_number=preferred)

        # Now try same preferred for f2
        result = system.assign_number_to_file(f2, preferred_number=preferred)
        assert result.confidence == 0.7
        assert "Resolved conflict" in " ".join(result.reasons)


class TestValidateNumberAssignment:
    """Cover validate_number_assignment — line 289."""

    def test_validate_available_number(self, system: JohnnyDecimalSystem, tmp_path: Path) -> None:
        f = tmp_path / "file.txt"
        f.write_text("x")
        num = JohnnyDecimalNumber(area=10, category=1)
        result = system.validate_number_assignment(num, f)
        assert result.metadata["validation_only"] is True

    def test_validate_used_number(self, system: JohnnyDecimalSystem, tmp_path: Path) -> None:
        f1 = tmp_path / "f1.txt"
        f1.write_text("x")
        num = JohnnyDecimalNumber(area=10, category=1)
        system.generator.register_existing_number(num, f1)

        f2 = tmp_path / "f2.txt"
        f2.write_text("y")
        result = system.validate_number_assignment(num, f2)
        assert result.confidence == 0.0


class TestRenumberFile:
    """Cover renumber_file — lines 323-327, 289, 500-504."""

    def test_renumber_success(self, system: JohnnyDecimalSystem, tmp_path: Path) -> None:
        f = tmp_path / "file.txt"
        f.write_text("x")
        old_num = JohnnyDecimalNumber(area=10, category=1)
        system.generator.register_existing_number(old_num, f)

        new_num = JohnnyDecimalNumber(area=20, category=5)
        result = system.renumber_file(old_num, new_num, f)
        assert "Renumbered" in " ".join(result.reasons)

    def test_renumber_old_not_registered(self, system: JohnnyDecimalSystem, tmp_path: Path) -> None:
        f = tmp_path / "file.txt"
        f.write_text("x")
        old_num = JohnnyDecimalNumber(area=99, category=99)
        new_num = JohnnyDecimalNumber(area=20, category=5)
        with pytest.raises(InvalidNumberError, match="not registered"):
            system.renumber_file(old_num, new_num, f)

    def test_renumber_new_conflicts_rollback(
        self, system: JohnnyDecimalSystem, tmp_path: Path
    ) -> None:
        """New number conflicts at register time => old number restored (lines 323-327).

        We mock validate_number to pass, then let register_existing_number
        raise NumberConflictError so the rollback branch is actually exercised.
        """
        f1 = tmp_path / "f1.txt"
        f1.write_text("x")
        f2 = tmp_path / "f2.txt"
        f2.write_text("y")

        old_num = JohnnyDecimalNumber(area=10, category=1)
        system.generator.register_existing_number(old_num, f1)
        taken_num = JohnnyDecimalNumber(area=20, category=5)
        system.generator.register_existing_number(taken_num, f2)

        # validate_number returns (True, []) so we pass the pre-check,
        # but register_existing_number will raise because taken_num exists.
        with (
            patch.object(system.generator, "validate_number", return_value=(True, [])),
            pytest.raises(NumberConflictError),
        ):
            system.renumber_file(old_num, taken_num, f1)

        # Rollback must restore old number
        assert old_num.formatted_number in system.generator._used_numbers
        assert system.generator._number_mappings[old_num.formatted_number] == f1


class TestGetAreaSummary:
    """Cover get_area_summary — line 392, 428."""

    def test_get_area_summary(self, system: JohnnyDecimalSystem) -> None:
        summary = system.get_area_summary(10)
        assert isinstance(summary, dict)
