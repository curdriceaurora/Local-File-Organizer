"""Tests for Johnny Decimal system uncovered branches.

Targets: initialize_from_directory, _extract_number_from_path,
assign_number_to_file conflict resolution, validate_number_assignment,
renumber_file, get_area_summary.
"""

from __future__ import annotations

import json
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


def _create_broken_symlink_or_skip(link_path: Path, target_path: Path) -> None:
    try:
        link_path.symlink_to(target_path)
    except (NotImplementedError, OSError):
        pytest.skip("Symlink creation is not supported in this environment")


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
        assert isinstance(summary, dict) and "area" in summary


class TestSystemCoverage:
    """Cover all missing lines in system.py."""

    @pytest.fixture
    def system(self) -> JohnnyDecimalSystem:
        return JohnnyDecimalSystem()

    # Line 56: load_configuration at init when config_path exists
    def test_init_loads_existing_config(self, tmp_path: Path) -> None:
        config_file = tmp_path / "jd_config.json"
        config_data = {
            "scheme": {"reserved_numbers": ["10.01"]},
            "used_numbers": {"10.02": str(tmp_path / "f.txt")},
        }
        config_file.write_text(json.dumps(config_data))

        system = JohnnyDecimalSystem(config_path=config_file)
        assert system._initialized is True

    # Line 107: _extract_number_from_path with empty name (parts is [])
    def test_extract_number_empty_name(self, system: JohnnyDecimalSystem) -> None:
        """Path with empty name returns None (line 107)."""
        num = system._extract_number_from_path(Path("."))
        assert num is None

    # Single part (just a number, no name)
    def test_extract_number_no_name_part(self, system: JohnnyDecimalSystem) -> None:
        """When path name is just '10' with no additional parts, name stays empty."""
        num = system._extract_number_from_path(Path("root/10"))
        assert num is not None
        assert num.area == 10
        assert num.name == ""

    # Line 116->122: when len(parts) > 1 with extension in name part
    def test_extract_number_with_extension_in_name(self, system: JohnnyDecimalSystem) -> None:
        """Name part containing a dot triggers Path().stem extraction."""
        num = system._extract_number_from_path(Path("root/10 report.pdf"))
        assert num is not None
        assert num.name == "report"

    # Lines 168-170: assign_number_to_file where preferred conflict cannot be resolved
    def test_assign_preferred_unresolvable_conflict(
        self, system: JohnnyDecimalSystem, tmp_path: Path
    ) -> None:
        f = tmp_path / "file.txt"
        f.write_text("x")
        preferred = JohnnyDecimalNumber(area=20, category=5)

        # Make validate return errors and resolve_conflict raise
        with (
            patch.object(system.generator, "validate_number", return_value=(False, ["taken"])),
            patch.object(
                system.generator,
                "resolve_conflict",
                side_effect=InvalidNumberError("no alt"),
            ),
            pytest.raises(NumberConflictError, match="no alternative found"),
        ):
            system.assign_number_to_file(f, preferred_number=preferred)

    # Lines 190-192: assign_number_to_file with no content; get_next_available raises
    def test_assign_no_content_no_areas(self, system: JohnnyDecimalSystem, tmp_path: Path) -> None:
        f = tmp_path / "file.txt"
        f.write_text("x")

        with (
            patch.object(
                system.generator,
                "get_next_available_area",
                side_effect=InvalidNumberError("no areas"),
            ),
            pytest.raises(InvalidNumberError, match="no areas"),
        ):
            system.assign_number_to_file(f)

    # Lines 204-205: auto_register fails with NumberConflictError during registration
    def test_assign_register_conflict_appended(
        self, system: JohnnyDecimalSystem, tmp_path: Path
    ) -> None:
        f = tmp_path / "file.txt"
        f.write_text("x")

        # Register 10.00 so it exists, then mock find_conflicts to return empty
        # but register_existing_number to raise
        preferred = JohnnyDecimalNumber(area=10, category=0)
        with (
            patch.object(system.generator, "find_conflicts", return_value=[]),
            patch.object(
                system.generator,
                "register_existing_number",
                side_effect=NumberConflictError("conflict"),
            ),
        ):
            result = system.assign_number_to_file(f, preferred_number=preferred)
        assert "conflict" in result.conflicts[0]

    # Line 289: renumber_file — new number is invalid
    def test_renumber_new_number_invalid(self, system: JohnnyDecimalSystem, tmp_path: Path) -> None:
        f = tmp_path / "f.txt"
        f.write_text("x")
        old = JohnnyDecimalNumber(area=10, category=1)
        system.generator.register_existing_number(old, f)
        new = JohnnyDecimalNumber(area=20, category=5)
        # Reserve the new number to make it invalid
        system.scheme.reserve_number(new)
        with pytest.raises(NumberConflictError, match="not available"):
            system.renumber_file(old, new, f)

    # Line 428: load_configuration with no path
    def test_load_config_no_path(self, system: JohnnyDecimalSystem) -> None:
        with pytest.raises(ValueError, match="No configuration path"):
            system.load_configuration(None)

    # Line 441->451: load_configuration with used_numbers containing bad number
    def test_load_config_bad_number_skipped(self, tmp_path: Path) -> None:
        config_file = tmp_path / "cfg.json"
        config_data = {
            "scheme": {"reserved_numbers": []},
            "used_numbers": {
                "10.01": str(tmp_path / "good.txt"),
                "INVALID": str(tmp_path / "bad.txt"),
            },
        }
        config_file.write_text(json.dumps(config_data))

        system = JohnnyDecimalSystem(config_path=config_file)
        # Good number loaded, bad skipped
        assert "10.01" in system.generator._used_numbers
        assert "INVALID" not in system.generator._used_numbers

    # Branch 441->451: load_configuration without used_numbers key
    def test_load_config_no_used_numbers(self, tmp_path: Path) -> None:
        config_file = tmp_path / "cfg.json"
        config_data = {"scheme": {"reserved_numbers": ["10.01"]}}
        config_file.write_text(json.dumps(config_data))

        system = JohnnyDecimalSystem()
        system.load_configuration(config_file)
        assert system._initialized is True
        assert len(system.generator._used_numbers) == 0

    # Line 487: reserve_number_range spanning multiple areas
    def test_reserve_range_different_areas(self, system: JohnnyDecimalSystem) -> None:
        start = JohnnyDecimalNumber(area=10, category=1)
        end = JohnnyDecimalNumber(area=20, category=5)
        with pytest.raises(ValueError, match="cannot span multiple areas"):
            system.reserve_number_range(start, end)

    # Lines 491-493: reserve at AREA level (same area required by line 486 guard)
    def test_reserve_range_area_level(self, system: JohnnyDecimalSystem) -> None:
        start = JohnnyDecimalNumber(area=10)
        end = JohnnyDecimalNumber(area=10)
        system.reserve_number_range(start, end)
        assert system.scheme.is_number_reserved(JohnnyDecimalNumber(area=10))

    # Lines 502-509: reserve at ID level
    def test_reserve_range_id_level(self, system: JohnnyDecimalSystem) -> None:
        start = JohnnyDecimalNumber(area=10, category=1, item_id=1)
        end = JohnnyDecimalNumber(area=10, category=1, item_id=3)
        system.reserve_number_range(start, end)
        assert system.scheme.is_number_reserved(JohnnyDecimalNumber(area=10, category=1, item_id=1))
        assert system.scheme.is_number_reserved(JohnnyDecimalNumber(area=10, category=1, item_id=3))

    # Line 392: get_area_summary with undefined area
    def test_get_area_summary_undefined_area(self, system: JohnnyDecimalSystem) -> None:
        summary = system.get_area_summary(99)
        assert summary["name"] == "Undefined"
        assert summary["description"] == ""
        assert summary["available"] is False

    # Branch 75->74: rglob item that is neither file nor dir (e.g. broken symlink)
    def test_initialize_skips_non_file_non_dir(
        self, system: JohnnyDecimalSystem, tmp_path: Path
    ) -> None:
        (tmp_path / "10 Finance").mkdir()
        broken = tmp_path / "broken_link"
        _create_broken_symlink_or_skip(broken, tmp_path / "nonexistent_target")
        system.initialize_from_directory(tmp_path)
        assert system._initialized is True

    # save_configuration no path
    def test_save_config_no_path(self, system: JohnnyDecimalSystem) -> None:
        with pytest.raises(ValueError, match="No configuration path"):
            system.save_configuration(None)

    # load_configuration file not found
    def test_load_config_file_not_found(self, system: JohnnyDecimalSystem, tmp_path: Path) -> None:
        missing_config = tmp_path / "missing_config.json"
        with pytest.raises(FileNotFoundError):
            system.load_configuration(missing_config)
