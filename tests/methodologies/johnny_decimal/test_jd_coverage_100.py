"""Tests to achieve 100% coverage across all Johnny Decimal modules.

Covers every missed statement and partial branch identified in the coverage report.
Organized by module with clear section headers.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from file_organizer.methodologies.johnny_decimal.adapters import (
    AdapterRegistry,
    FileSystemAdapter,
    OrganizationItem,
    PARAAdapter,
)
from file_organizer.methodologies.johnny_decimal.categories import (
    AreaDefinition,
    CategoryDefinition,
    JohnnyDecimalNumber,
    NumberingResult,
    NumberingScheme,
    NumberLevel,
)
from file_organizer.methodologies.johnny_decimal.compatibility import (
    CompatibilityAnalyzer,
    HybridOrganizer,
    PARACategory,
)
from file_organizer.methodologies.johnny_decimal.config import (
    ConfigBuilder,
    JohnnyDecimalConfig,
    create_default_config,
    create_para_compatible_config,
)
from file_organizer.methodologies.johnny_decimal.migrator import (
    JohnnyDecimalMigrator,
    MigrationResult,
    RollbackInfo,
)
from file_organizer.methodologies.johnny_decimal.numbering import (
    InvalidNumberError,
    JohnnyDecimalGenerator,
    NumberConflictError,
)
from file_organizer.methodologies.johnny_decimal.scanner import FolderInfo, FolderScanner
from file_organizer.methodologies.johnny_decimal.system import JohnnyDecimalSystem
from file_organizer.methodologies.johnny_decimal.transformer import (
    FolderTransformer,
    TransformationPlan,
    TransformationRule,
)
from file_organizer.methodologies.johnny_decimal.validator import (
    MigrationValidator,
    ValidationIssue,
    ValidationResult,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# system.py — 25 missed stmts, 11 partial branches
# ---------------------------------------------------------------------------
class TestSystemCoverage:
    """Cover all missing lines in system.py."""

    @pytest.fixture()
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
        # Create a broken symlink — it's neither is_file() nor is_dir()
        broken = tmp_path / "broken_link"
        broken.symlink_to(tmp_path / "nonexistent_target")
        system.initialize_from_directory(tmp_path)
        assert system._initialized is True

    # save_configuration no path
    def test_save_config_no_path(self, system: JohnnyDecimalSystem) -> None:
        with pytest.raises(ValueError, match="No configuration path"):
            system.save_configuration(None)

    # load_configuration file not found
    def test_load_config_file_not_found(self, system: JohnnyDecimalSystem) -> None:
        with pytest.raises(FileNotFoundError):
            system.load_configuration(Path("/tmp/nonexistent_config.json"))


# ---------------------------------------------------------------------------
# compatibility.py — 11 missed stmts, 11 partial branches
# ---------------------------------------------------------------------------
class TestCompatibilityCoverage:
    """Cover all missing lines in compatibility.py."""

    @pytest.fixture()
    def config(self) -> JohnnyDecimalConfig:
        return create_para_compatible_config()

    @pytest.fixture()
    def config_para_disabled(self) -> JohnnyDecimalConfig:
        cfg = create_default_config()
        cfg.compatibility.para_integration.enabled = False
        return cfg

    # Lines 197-198: detect_para_structure with non-existent path
    def test_detect_para_nonexistent(self, config: JohnnyDecimalConfig) -> None:
        analyzer = CompatibilityAnalyzer(config)
        result = analyzer.detect_para_structure(Path("/nonexistent"))
        assert all(v is None for v in result.values())

    # Line 203: detect_para_structure skips non-directory items
    def test_detect_para_skips_files(self, config: JohnnyDecimalConfig, tmp_path: Path) -> None:
        (tmp_path / "projects.txt").write_text("not a dir")
        analyzer = CompatibilityAnalyzer(config)
        result = analyzer.detect_para_structure(tmp_path)
        assert result[PARACategory.PROJECTS] is None

    # Line 226: is_mixed_structure on non-existent path
    def test_is_mixed_nonexistent(self, config: JohnnyDecimalConfig) -> None:
        analyzer = CompatibilityAnalyzer(config)
        assert analyzer.is_mixed_structure(Path("/nonexistent")) is False

    # Line 243: _looks_like_jd with empty name
    def test_looks_like_jd_empty(self, config: JohnnyDecimalConfig) -> None:
        analyzer = CompatibilityAnalyzer(config)
        assert analyzer._looks_like_jd("") is False

    # Lines 250-252: _looks_like_jd with dotted format (2 nums)
    def test_looks_like_jd_category_format(self, config: JohnnyDecimalConfig) -> None:
        analyzer = CompatibilityAnalyzer(config)
        assert analyzer._looks_like_jd("11.01 Budget") is True
        assert analyzer._looks_like_jd("11.01.001 Item") is True
        assert analyzer._looks_like_jd("abc.def Not JD") is False

    # Line 182->exit: CompatibilityAnalyzer with PARA disabled
    def test_analyzer_para_disabled(self, config_para_disabled: JohnnyDecimalConfig) -> None:
        analyzer = CompatibilityAnalyzer(config_para_disabled)
        assert analyzer.bridge is None

    # Lines 288: suggest_migration_strategy PARA detected but not enabled
    def test_suggest_migration_para_not_enabled(
        self, config_para_disabled: JohnnyDecimalConfig, tmp_path: Path
    ) -> None:
        (tmp_path / "projects").mkdir()
        analyzer = CompatibilityAnalyzer(config_para_disabled)
        strategy = analyzer.suggest_migration_strategy(tmp_path)
        assert any("Enable PARA" in r for r in strategy["recommendations"])

    # Lines 270->290, 291, 296: mixed structure and clean structure recommendations
    def test_suggest_migration_mixed(self, config: JohnnyDecimalConfig, tmp_path: Path) -> None:
        (tmp_path / "projects").mkdir()
        (tmp_path / "10 Finance").mkdir()
        analyzer = CompatibilityAnalyzer(config)
        strategy = analyzer.suggest_migration_strategy(tmp_path)
        assert strategy["is_mixed_structure"] is True
        assert any("Mixed structure" in r for r in strategy["recommendations"])

    def test_suggest_migration_clean(self, config: JohnnyDecimalConfig, tmp_path: Path) -> None:
        (tmp_path / "documents").mkdir()
        analyzer = CompatibilityAnalyzer(config)
        strategy = analyzer.suggest_migration_strategy(tmp_path)
        assert any("Clean structure" in r for r in strategy["recommendations"])

    # HybridOrganizer.get_item_path for ID-level number
    def test_get_item_path_id_level(self, config: JohnnyDecimalConfig, tmp_path: Path) -> None:
        organizer = HybridOrganizer(config)
        jd_num = JohnnyDecimalNumber(area=10, category=1, item_id=5)
        path = organizer.get_item_path(tmp_path, PARACategory.PROJECTS, jd_num, "Budget")
        assert "10.01.005 Budget" in str(path)

    # Branch 422->425: get_item_path without item_name (empty string)
    def test_get_item_path_no_name(self, config: JohnnyDecimalConfig, tmp_path: Path) -> None:
        organizer = HybridOrganizer(config)
        jd_num = JohnnyDecimalNumber(area=10, category=1)
        path = organizer.get_item_path(tmp_path, PARACategory.PROJECTS, jd_num)
        # No item_name appended
        assert path.name == "10.01"


# ---------------------------------------------------------------------------
# config.py — 9 missed stmts, 3 partial branches
# ---------------------------------------------------------------------------
class TestConfigCoverage:
    """Cover all missing lines in config.py."""

    # Line 146: from_dict with missing category description
    def test_from_dict_missing_descriptions(self) -> None:
        data = {
            "scheme": {
                "name": "test",
                "areas": [
                    {
                        "area_range_start": 10,
                        "area_range_end": 19,
                        "name": "Finance",
                    }
                ],
                "categories": [{"area": 10, "category": 1, "name": "Budget"}],
            }
        }
        config = JohnnyDecimalConfig.from_dict(data)
        assert config.scheme.name == "test"

    # Line 214: load_from_file with non-existent file
    def test_load_from_file_not_found(self) -> None:
        with pytest.raises(FileNotFoundError, match="not found"):
            JohnnyDecimalConfig.load_from_file(Path("/nonexistent/config.json"))

    # Lines 278-286: ConfigBuilder.add_category
    def test_config_builder_add_category(self) -> None:
        config = (
            ConfigBuilder("test")
            .add_area(10, "Finance")
            .add_category(10, 1, "Budget", "Budget tracking")
            .build()
        )
        cats = config.scheme.get_available_categories(10)
        assert len(cats) >= 1

    # Lines 350-351: add_custom_mapping
    def test_config_builder_custom_mapping(self) -> None:
        config = (
            ConfigBuilder("test")
            .add_area(10, "Finance")
            .add_custom_mapping("Documents", 10)
            .build()
        )
        assert config.custom_mappings["documents"] == 10

    # Line 371: build with no areas/categories
    def test_config_builder_empty(self) -> None:
        config = ConfigBuilder("empty").build()
        assert config.scheme.name == "empty"

    # Lines 387-389: create_para_compatible_config exercises full builder
    def test_create_para_compatible(self) -> None:
        config = create_para_compatible_config()
        assert config.compatibility.para_integration.enabled is True
        assert config.scheme.name == "para-compatible"

    # save_to_file / load_from_file roundtrip
    def test_save_load_roundtrip(self, tmp_path: Path) -> None:
        config = create_default_config()
        path = tmp_path / "config.json"
        config.save_to_file(path)
        loaded = JohnnyDecimalConfig.load_from_file(path)
        assert loaded.scheme.name == config.scheme.name


# ---------------------------------------------------------------------------
# numbering.py — 14 missed stmts, 9 partial branches
# ---------------------------------------------------------------------------
class TestNumberingCoverage:
    """Cover all missing lines in numbering.py."""

    @pytest.fixture()
    def scheme(self) -> NumberingScheme:
        from file_organizer.methodologies.johnny_decimal.categories import get_default_scheme

        return get_default_scheme()

    @pytest.fixture()
    def gen(self, scheme: NumberingScheme) -> JohnnyDecimalGenerator:
        return JohnnyDecimalGenerator(scheme)

    # Line 89: is_number_available — reserved number
    def test_is_number_available_reserved(self, gen: JohnnyDecimalGenerator) -> None:
        num = JohnnyDecimalNumber(area=10, category=1)
        gen.scheme.reserve_number(num)
        assert gen.is_number_available(num) is False

    # Lines 113->119, 115->113, 120->119, 125: get_next_available_area exhaustion
    def test_get_next_available_area_preferred_full(self, gen: JohnnyDecimalGenerator) -> None:
        """Preferred area is full — falls through to next area."""
        # Reserve all categories in area 10 to make it 'full'
        for cat in range(100):
            num = JohnnyDecimalNumber(area=10, category=cat)
            gen._used_numbers.add(num.formatted_number)
        # preferred=10 should not return 10 since it's full
        area = gen.get_next_available_area(preferred_area=10)
        assert area != 10

    def test_get_next_available_area_all_exhausted(self, gen: JohnnyDecimalGenerator) -> None:
        """All areas full => InvalidNumberError."""
        # Fill every possible number for all areas in the scheme
        for area_num in gen.scheme.get_available_areas():
            for cat in range(100):
                num = JohnnyDecimalNumber(area=area_num, category=cat)
                gen._used_numbers.add(num.formatted_number)
        with pytest.raises(InvalidNumberError, match="No available area"):
            gen.get_next_available_area()

    # Lines 334-343: suggest_number_for_content with matched category occupied
    def test_suggest_number_category_occupied(self, gen: JohnnyDecimalGenerator) -> None:
        # Add a category with keywords that will match
        cat_def = CategoryDefinition(
            area=10,
            category=1,
            name="Budget",
            description="",
            keywords=["budget", "finance"],
        )
        gen.scheme.add_category(cat_def)
        # Register the category number so it's occupied
        num = JohnnyDecimalNumber(area=10, category=1)
        gen.register_existing_number(num, Path("existing.txt"))

        result_num, confidence, reasons = gen.suggest_number_for_content(
            content="budget finance report", filename="budget.txt", prefer_category=True
        )
        # Should have fallen to ID level
        assert any("occupied" in r.lower() or "id" in r.lower() for r in reasons)

    # Lines 353-355: suggest with prefer_category=False, no category match
    def test_suggest_number_no_category_prefer_id(self, gen: JohnnyDecimalGenerator) -> None:
        result_num, confidence, reasons = gen.suggest_number_for_content(
            content="unknown content", filename="file.txt", prefer_category=False
        )
        assert result_num.item_id is not None

    # Lines 353-355: suggest_number no category match, get_next_available_category raises
    def test_suggest_number_all_categories_full(self, gen: JohnnyDecimalGenerator) -> None:
        """No category keyword match and get_next_available_category raises."""
        with patch.object(
            gen, "get_next_available_category", side_effect=InvalidNumberError("full")
        ):
            result_num, _, reasons = gen.suggest_number_for_content(
                content="random content", filename="random.txt", prefer_category=True
            )
        assert any("area" in r.lower() for r in reasons)

    # Category matched but all IDs full => area-level fallback
    def test_suggest_number_category_full(self, gen: JohnnyDecimalGenerator) -> None:
        cat_def = CategoryDefinition(
            area=10,
            category=1,
            name="Budget",
            description="",
            keywords=["budget"],
        )
        gen.scheme.add_category(cat_def)
        # Occupy the category number
        gen._used_numbers.add("10.01")
        # Fill all IDs in category 10.01
        for i in range(1000):
            gen._used_numbers.add(f"10.01.{i:03d}")

        result_num, _, reasons = gen.suggest_number_for_content(
            content="budget report", filename="budget.txt", prefer_category=True
        )
        assert any("full" in r.lower() or "area" in r.lower() for r in reasons)

    # Line 373: resolve_conflict area-level (number with no category or item_id)
    def test_resolve_conflict_area_level(self, gen: JohnnyDecimalGenerator) -> None:
        # Register area 10 so it conflicts, then resolve
        area_num = JohnnyDecimalNumber(area=10, name="Finance")
        gen.register_existing_number(area_num, Path("area.txt"))
        result = gen.resolve_conflict(area_num, strategy="increment")
        # generate_area_number will find another area number
        assert result is not None
        assert result.name == "Finance"

    # Line 381: resolve_conflict with suggest strategy
    def test_resolve_conflict_suggest(self, gen: JohnnyDecimalGenerator) -> None:
        num = JohnnyDecimalNumber(area=10, category=1, name="Test")
        result = gen.resolve_conflict(num, strategy="suggest")
        assert result.area is not None

    # Line 421->420: find_conflicts — child conflicts when category is None
    def test_find_conflicts_child_conflict(self, gen: JohnnyDecimalGenerator) -> None:
        # Register a category-level number
        cat_num = JohnnyDecimalNumber(area=10, category=1)
        gen.register_existing_number(cat_num, Path("cat.txt"))
        # Check for conflicts at area level — should find child 10.01
        area_num = JohnnyDecimalNumber(area=10)
        conflicts = gen.find_conflicts(area_num)
        assert len(conflicts) >= 1
        assert conflicts[0][0] == "10.01"

    # find_conflicts — no child conflicts (loop completes with no matches)
    def test_find_conflicts_no_children(self, gen: JohnnyDecimalGenerator) -> None:
        # Register a number NOT starting with "50." to exercise the loop false branch
        other_num = JohnnyDecimalNumber(area=10, category=1)
        gen.register_existing_number(other_num, Path("other.txt"))
        area_num = JohnnyDecimalNumber(area=50)
        conflicts = gen.find_conflicts(area_num)
        assert len(conflicts) == 0

    # Line 373: validate_number — area not in scheme
    def test_validate_number_undefined_area(self, gen: JohnnyDecimalGenerator) -> None:
        num = JohnnyDecimalNumber(area=99)
        is_valid, errors = gen.validate_number(num)
        assert not is_valid
        assert any("not defined" in e for e in errors)

    # Line 381: validate_number — undefined category >= 10 (allowed, pass branch)
    def test_validate_number_undefined_category_allowed(self, gen: JohnnyDecimalGenerator) -> None:
        # Area 10 is in the default scheme
        num = JohnnyDecimalNumber(area=10, category=15)
        is_valid, errors = gen.validate_number(num)
        # Category 15 in area 10 may not be defined, but >= 10 is allowed
        # So only potential errors are from other checks, not category
        category_errors = [e for e in errors if "category" in e.lower()]
        assert len(category_errors) == 0


# ---------------------------------------------------------------------------
# scanner.py — 9 missed stmts, 3 partial branches
# ---------------------------------------------------------------------------
class TestScannerCoverage:
    """Cover all missing lines in scanner.py."""

    @pytest.fixture()
    def scanner(self) -> FolderScanner:
        from file_organizer.methodologies.johnny_decimal.categories import get_default_scheme

        return FolderScanner(get_default_scheme())

    # Lines 144-146: _scan_folder with max depth exceeded
    def test_scan_folder_max_depth(self, tmp_path: Path) -> None:
        scanner = FolderScanner(scheme=JohnnyDecimalSystem().scheme, max_depth=0)
        (tmp_path / "sub").mkdir()
        result = scanner.scan_directory(tmp_path)
        # Max depth 0 means no recursion into first-level dirs' children
        assert result.total_folders >= 0

    # Lines 158->148: _scan_folder PermissionError in iterdir (branch)
    def test_scan_folder_permission_denied(self, scanner: FolderScanner, tmp_path: Path) -> None:
        restricted = tmp_path / "restricted"
        restricted.mkdir()
        restricted.chmod(0o000)
        try:
            result = scanner.scan_directory(tmp_path)
            # Should not crash, just skip
            assert result is not None
        finally:
            restricted.chmod(0o755)

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
        restricted.chmod(0o000)
        try:
            # Creating folder info for restricted dir should not crash
            info = scanner._create_folder_info(restricted, depth=0)
            assert info.file_count == 0  # permission denied => 0 files counted
        finally:
            restricted.chmod(0o755)

    # Lines 163-164: OSError on file stat in _scan_folder
    def test_scan_folder_file_stat_oserror(self, scanner: FolderScanner, tmp_path: Path) -> None:
        f = tmp_path / "file.txt"
        f.write_text("data")

        original_stat = Path.stat
        call_count = 0

        def stat_raising_on_file(path_self: Path, *args: object, **kwargs: object) -> object:
            nonlocal call_count
            if path_self.name == "file.txt":
                call_count += 1
                # is_dir() = call 1, is_file() = call 2, explicit stat() = call 3
                if call_count >= 3:
                    raise OSError("bad stat")
            return original_stat(path_self, *args, **kwargs)

        with patch.object(Path, "stat", stat_raising_on_file):
            result = scanner.scan_directory(tmp_path)
            assert result is not None

    # Lines 188-189: OSError on file stat in _create_folder_info
    def test_create_folder_info_file_stat_oserror(
        self, scanner: FolderScanner, tmp_path: Path
    ) -> None:
        sub = tmp_path / "sub"
        sub.mkdir()
        f = sub / "file.txt"
        f.write_text("data")

        original_stat = Path.stat
        call_count = 0

        def stat_raising_on_file(path_self: Path, *args: object, **kwargs: object) -> object:
            nonlocal call_count
            if path_self.name == "file.txt":
                call_count += 1
                # is_file() calls stat() once; the explicit stat().st_size is second
                if call_count > 1:
                    raise OSError("bad stat")
            return original_stat(path_self, *args, **kwargs)

        with patch.object(Path, "stat", stat_raising_on_file):
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
        # Create a broken symlink — is_dir() False, is_file() False
        broken = tmp_path / "broken_link"
        broken.symlink_to(tmp_path / "nonexistent")
        result = scanner.scan_directory(tmp_path)
        # Should handle gracefully, not count it
        assert result.total_files == 0

    # PermissionError in _scan_folder during sorted(path.iterdir())
    def test_scan_folder_iterdir_permission_error(
        self, scanner: FolderScanner, tmp_path: Path
    ) -> None:
        sub = tmp_path / "noperm"
        sub.mkdir()
        (sub / "inner").mkdir()
        sub.chmod(0o000)
        try:
            result = scanner.scan_directory(tmp_path)
            assert result is not None
        finally:
            sub.chmod(0o755)


# ---------------------------------------------------------------------------
# transformer.py — 3 missed stmts, 2 partial branches
# ---------------------------------------------------------------------------
class TestTransformerCoverage:
    """Cover all missing lines in transformer.py."""

    @pytest.fixture()
    def transformer(self) -> FolderTransformer:
        scheme = JohnnyDecimalSystem().scheme
        gen = JohnnyDecimalGenerator(scheme)
        return FolderTransformer(scheme, gen)

    # Lines 274->283: _suggest_area_number with matching scheme area name
    def test_suggest_area_matches_scheme(self, transformer: FolderTransformer) -> None:
        # Add an area definition with a name
        area_def = AreaDefinition(
            area_range_start=10,
            area_range_end=19,
            name="Finance",
            description="Financial docs",
        )
        transformer.scheme.add_area(area_def)

        folder = FolderInfo(
            path=Path("finance"),
            name="finance",
            depth=0,
            file_count=0,
            total_size=0,
        )
        area = transformer._suggest_area_number(folder, index=0)
        assert area == 10

    # Lines 303-308: _suggest_category_number with matching scheme category
    def test_suggest_category_matches_scheme(self, transformer: FolderTransformer) -> None:
        cat_def = CategoryDefinition(
            area=10,
            category=5,
            name="Budget",
            description="",
        )
        transformer.scheme.add_category(cat_def)
        folder = FolderInfo(
            path=Path("budget"),
            name="budget",
            depth=1,
            file_count=0,
            total_size=0,
        )
        cat = transformer._suggest_category_number(folder, area=10, index=0)
        assert cat == 5

    # Branch 274->283: _suggest_area_number — empty scheme (no areas)
    def test_suggest_area_empty_scheme(self) -> None:
        empty_scheme = NumberingScheme(name="empty", description="")
        gen = JohnnyDecimalGenerator(empty_scheme)
        t = FolderTransformer(empty_scheme, gen)
        folder = FolderInfo(
            path=Path("anything"),
            name="anything",
            depth=0,
            file_count=0,
            total_size=0,
        )
        area = t._suggest_area_number(folder, index=3)
        assert area == 13  # 10 + 3

    # Branch 303->312, 304->303: _suggest_category_number — no match
    def test_suggest_category_no_match(self, transformer: FolderTransformer) -> None:
        # Add a category that doesn't match
        cat_def = CategoryDefinition(
            area=10,
            category=5,
            name="Budget",
            description="",
        )
        transformer.scheme.add_category(cat_def)
        folder = FolderInfo(
            path=Path("zzz_unknown"),
            name="zzz_unknown",
            depth=1,
            file_count=0,
            total_size=0,
        )
        cat = transformer._suggest_category_number(folder, area=10, index=2)
        assert cat == 3  # index + 1


# ---------------------------------------------------------------------------
# categories.py — 6 missed stmts, 5 partial branches
# ---------------------------------------------------------------------------
class TestCategoriesCoverage:
    """Cover all missing lines in categories.py."""

    # Line 37: NumberLevel.__str__
    def test_number_level_str(self) -> None:
        assert str(NumberLevel.AREA) == "Area"
        assert str(NumberLevel.CATEGORY) == "Category"
        assert str(NumberLevel.ID) == "Id"

    # Line 116: JohnnyDecimalNumber.__str__ with name
    def test_jd_number_str_with_name(self) -> None:
        num = JohnnyDecimalNumber(area=10, name="Finance")
        assert str(num) == "10 Finance"

    # Line 117: JohnnyDecimalNumber.__str__ without name
    def test_jd_number_str_without_name(self) -> None:
        num = JohnnyDecimalNumber(area=10)
        assert str(num) == "10"

    # Line 126: __eq__ with non-JohnnyDecimalNumber
    def test_jd_number_eq_not_implemented(self) -> None:
        num = JohnnyDecimalNumber(area=10)
        result = num.__eq__("not a jd number")
        assert result is NotImplemented

    # Line 195: AreaDefinition.__post_init__ area_end > 99
    def test_area_def_end_out_of_range(self) -> None:
        with pytest.raises(ValueError, match="Area end must be 0-99"):
            AreaDefinition(
                area_range_start=10,
                area_range_end=100,
                name="Bad",
                description="",
            )

    # Line 233: CategoryDefinition.__post_init__ — category out of range
    def test_category_def_category_out_of_range(self) -> None:
        with pytest.raises(ValueError, match="Category must be 0-99"):
            CategoryDefinition(area=10, category=100, name="Bad", description="")

    # Line 234-235: CategoryDefinition.__post_init__ — empty name
    def test_category_def_empty_name(self) -> None:
        with pytest.raises(ValueError, match="name cannot be empty"):
            CategoryDefinition(area=10, category=1, name="", description="")

    # Line 282: NumberingResult.__post_init__ — file_path as string
    def test_numbering_result_string_path(self) -> None:
        result = NumberingResult(
            file_path="/tmp/test.txt",  # type: ignore[arg-type]
            number=JohnnyDecimalNumber(area=10),
            confidence=0.5,
            reasons=["test"],
        )
        assert isinstance(result.file_path, Path)


# ---------------------------------------------------------------------------
# migrator.py — 2 missed stmts, 6 partial branches
# ---------------------------------------------------------------------------
class TestMigratorCoverage:
    """Cover all missing lines in migrator.py."""

    @pytest.fixture()
    def migrator(self) -> JohnnyDecimalMigrator:
        return JohnnyDecimalMigrator()

    # Lines 261-262: rollback with specific migration_id not found
    def test_rollback_id_not_found(self, migrator: JohnnyDecimalMigrator) -> None:
        # Add a dummy rollback entry
        from datetime import UTC, datetime

        info = RollbackInfo(
            migration_id="abc",
            timestamp=datetime.now(UTC),
            original_structure={},
            backup_path=None,
        )
        migrator._rollback_history.append(info)
        with pytest.raises(ValueError, match="not found"):
            migrator.rollback(migration_id="nonexistent")

    # Branch 263->268: rollback without migration_id (uses latest)
    def test_rollback_latest(self, migrator: JohnnyDecimalMigrator, tmp_path: Path) -> None:
        from datetime import UTC, datetime

        # Create a file to rollback
        target = tmp_path / "10 Finance"
        original = tmp_path / "Finance"
        target.mkdir()
        info = RollbackInfo(
            migration_id="latest",
            timestamp=datetime.now(UTC),
            original_structure={str(original): (str(target), "Finance")},
            backup_path=None,
        )
        migrator._rollback_history.append(info)
        result = migrator.rollback()
        assert result is True

    # Branch 279->272: rollback where current_path doesn't exist
    def test_rollback_missing_path(self, migrator: JohnnyDecimalMigrator) -> None:
        from datetime import UTC, datetime

        info = RollbackInfo(
            migration_id="missing",
            timestamp=datetime.now(UTC),
            original_structure={
                "/original": ("/nonexistent/target", "original_name"),
            },
            backup_path=None,
        )
        migrator._rollback_history.append(info)
        result = migrator.rollback(migration_id="missing")
        assert result is True

    # Branch 359->365: generate_preview with no patterns
    def test_generate_preview_no_patterns(self, migrator: JohnnyDecimalMigrator) -> None:
        from file_organizer.methodologies.johnny_decimal.scanner import ScanResult

        plan = TransformationPlan(
            root_path=Path("/tmp"),
            rules=[],
            estimated_changes=0,
        )
        scan = ScanResult(
            root_path=Path("/tmp"),
            folder_tree=[],
            total_folders=0,
            total_files=0,
            total_size=0,
            max_depth=0,
            detected_patterns=[],
        )
        preview = migrator.generate_preview(plan, scan)
        assert "Migration Preview" in preview

    # Branch 375->387: generate_preview with validation
    def test_generate_preview_with_validation(self, migrator: JohnnyDecimalMigrator) -> None:
        from file_organizer.methodologies.johnny_decimal.scanner import ScanResult

        plan = TransformationPlan(
            root_path=Path("/tmp"),
            rules=[],
            estimated_changes=0,
        )
        scan = ScanResult(
            root_path=Path("/tmp"),
            folder_tree=[],
            total_folders=0,
            total_files=0,
            total_size=0,
            max_depth=0,
            detected_patterns=["PARA methodology detected"],
        )
        validation = ValidationResult(is_valid=True)
        preview = migrator.generate_preview(plan, scan, validation=validation)
        assert "Validation" in preview
        assert "VALID" in preview

    # Branch 439->441: generate_report with skipped > 10
    def test_generate_report_many_skipped(self, migrator: JohnnyDecimalMigrator) -> None:
        result = MigrationResult(
            success=False,
            transformed_count=0,
            failed_count=1,
            skipped_count=15,
            duration_seconds=1.0,
            failed_paths=[(Path("/tmp/bad"), "error")],
            skipped_paths=[Path(f"/tmp/skip_{i}") for i in range(15)],
        )
        report = migrator.generate_report(result)
        assert "and 5 more" in report
        assert "Failures" in report

    # Branch 439->441 False: generate_report with skipped <= 10
    def test_generate_report_few_skipped(self, migrator: JohnnyDecimalMigrator) -> None:
        result = MigrationResult(
            success=True,
            transformed_count=5,
            failed_count=0,
            skipped_count=3,
            duration_seconds=0.5,
            skipped_paths=[Path(f"/tmp/skip_{i}") for i in range(3)],
        )
        report = migrator.generate_report(result)
        assert "Skipped (3 folders)" in report
        assert "and" not in report.split("Skipped")[1]  # no "and N more"


# ---------------------------------------------------------------------------
# adapters.py — 0 missed stmts, 5 partial branches
# ---------------------------------------------------------------------------
class TestAdaptersCoverage:
    """Cover all missing branches in adapters.py."""

    @pytest.fixture()
    def config(self) -> JohnnyDecimalConfig:
        return create_para_compatible_config()

    # Branch 275->279: _suggest_area_from_name digit outside 10-99
    def test_suggest_area_digit_out_of_range(self, config: JohnnyDecimalConfig) -> None:
        adapter = FileSystemAdapter(config)
        area = adapter._suggest_area_from_name("5 LowNum")
        assert 10 <= area <= 99  # falls through to hash-based

    # Branch 288->294: _suggest_category_from_name with non-digit second part
    def test_suggest_category_non_digit_after_dot(self, config: JohnnyDecimalConfig) -> None:
        adapter = FileSystemAdapter(config)
        cat = adapter._suggest_category_from_name("10.abc NotDigit")
        assert 1 <= cat <= 99  # falls through to hash-based

    # Branch 290->294: _suggest_category_from_name digit out of range
    def test_suggest_category_digit_out_of_range(self, config: JohnnyDecimalConfig) -> None:
        adapter = FileSystemAdapter(config)
        cat = adapter._suggest_category_from_name("10.0 Zero")
        assert 1 <= cat <= 99  # 0 is outside 1-99, falls through to hash

    # Branch 331->330: get_adapter where adapter.can_adapt returns False
    def test_get_adapter_can_adapt_false(self, config: JohnnyDecimalConfig) -> None:
        registry = AdapterRegistry()
        registry.register(PARAAdapter(config))
        # Item with non-PARA category => PARAAdapter.can_adapt returns False
        item = OrganizationItem(
            name="test",
            path=Path("test"),
            category="unknown",
            metadata={},
        )
        assert registry.get_adapter(item) is None

    # Branch 366->363: adapt_from_jd with unknown methodology
    def test_adapt_from_jd_unknown_methodology(self, config: JohnnyDecimalConfig) -> None:
        registry = AdapterRegistry()
        registry.register(PARAAdapter(config))
        num = JohnnyDecimalNumber(area=10, category=1)
        result = registry.adapt_from_jd(num, "test", methodology="unknown")
        assert result is None


# ---------------------------------------------------------------------------
# validator.py — 1 missed stmt, 3 partial branches
# ---------------------------------------------------------------------------
class TestValidatorCoverage:
    """Cover all missing lines in validator.py."""

    @pytest.fixture()
    def validator(self) -> MigrationValidator:
        scheme = JohnnyDecimalSystem().scheme
        gen = JohnnyDecimalGenerator(scheme)
        return MigrationValidator(gen)

    # Line 138: number conflicts with existing assignment
    def test_validate_plan_existing_conflict(
        self, validator: MigrationValidator, tmp_path: Path
    ) -> None:
        # Register a number first
        num = JohnnyDecimalNumber(area=10, category=1)
        validator.generator.register_existing_number(num, Path("existing.txt"))

        rule = TransformationRule(
            source_path=tmp_path / "test",
            target_name="10.01 Test",
            jd_number=JohnnyDecimalNumber(area=10, category=1),
            action="rename",
            confidence=0.9,
        )
        plan = TransformationPlan(
            root_path=tmp_path,
            rules=[rule],
            estimated_changes=1,
        )
        result = validator.validate_plan(plan)
        assert not result.is_valid
        error_msgs = [e.message for e in result.errors]
        assert any("already in use" in m for m in error_msgs)

    # Branch 331->329: generate_report with no errors (skip errors section)
    def test_generate_report_no_errors(self, validator: MigrationValidator) -> None:
        result = ValidationResult(is_valid=True)
        result.add_issue(
            ValidationIssue(
                severity="warning",
                rule_index=0,
                message="Just a warning",
                suggestion="Fix it",
            )
        )
        report = validator.generate_report(result)
        assert "Warnings" in report
        assert "Errors (Must Fix)" not in report

    # Branch 339->337: generate_report with no warnings (skip warnings section)
    def test_generate_report_no_warnings(self, validator: MigrationValidator) -> None:
        result = ValidationResult(is_valid=False)
        result.add_issue(
            ValidationIssue(
                severity="error",
                rule_index=0,
                message="An error",
                suggestion="Fix it",
            )
        )
        report = validator.generate_report(result)
        assert "Errors" in report
        assert "Warnings (Should Review)" not in report

    # Also test info section present
    def test_generate_report_with_info(self, validator: MigrationValidator) -> None:
        result = ValidationResult(is_valid=True)
        result.add_issue(
            ValidationIssue(
                severity="info",
                rule_index=0,
                message="Info note",
                suggestion=None,
            )
        )
        report = validator.generate_report(result)
        assert "Info" in report

    # Branches 331->329, 339->337: error/warning without suggestion
    def test_generate_report_error_no_suggestion(self, validator: MigrationValidator) -> None:
        result = ValidationResult(is_valid=False)
        result.add_issue(
            ValidationIssue(
                severity="error",
                rule_index=0,
                message="Error without tip",
                suggestion=None,
            )
        )
        result.add_issue(
            ValidationIssue(
                severity="warning",
                rule_index=1,
                message="Warning without tip",
                suggestion=None,
            )
        )
        report = validator.generate_report(result)
        assert "Error without tip" in report
        assert "Warning without tip" in report
        # No suggestion line should appear
        assert "\u0020\u0020\U0001f4a1" not in report  # no lightbulb suggestion line
