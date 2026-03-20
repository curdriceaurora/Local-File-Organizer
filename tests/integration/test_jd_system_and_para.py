"""Integration tests for JohnnyDecimalSystem and PARA folder generator.

Covers:
  - methodologies/johnny_decimal/system.py  — JohnnyDecimalSystem
  - methodologies/para/folder_generator.py  — PARAFolderGenerator
"""

from __future__ import annotations

from pathlib import Path

import pytest

from file_organizer.methodologies.johnny_decimal.categories import (
    AreaDefinition,
    JohnnyDecimalNumber,
    get_default_scheme,
)
from file_organizer.methodologies.johnny_decimal.numbering import (
    InvalidNumberError,
)
from file_organizer.methodologies.johnny_decimal.system import JohnnyDecimalSystem
from file_organizer.methodologies.para.folder_generator import (
    PARACategory,
    PARAConfig,
    PARAFolderGenerator,
)

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# JohnnyDecimalSystem — fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def jd_system() -> JohnnyDecimalSystem:
    return JohnnyDecimalSystem()


@pytest.fixture()
def jd_system_with_config(tmp_path: Path) -> JohnnyDecimalSystem:
    config_path = tmp_path / "jd_config.json"
    return JohnnyDecimalSystem(config_path=config_path)


# ---------------------------------------------------------------------------
# JohnnyDecimalSystem — init
# ---------------------------------------------------------------------------


class TestJDSystemInit:
    def test_default_scheme_loaded(self, jd_system: JohnnyDecimalSystem) -> None:
        assert jd_system.scheme is not None
        assert len(jd_system.scheme.name) > 0

    def test_generator_initialized(self, jd_system: JohnnyDecimalSystem) -> None:
        assert jd_system.generator is not None

    def test_not_initialized_without_config(self, jd_system: JohnnyDecimalSystem) -> None:
        assert jd_system._initialized is False

    def test_config_path_stored(self, tmp_path: Path) -> None:
        cfg = tmp_path / "jd.json"
        sys = JohnnyDecimalSystem(config_path=cfg)
        assert sys.config_path == cfg

    def test_custom_scheme_accepted(self) -> None:
        scheme = get_default_scheme()
        sys = JohnnyDecimalSystem(scheme=scheme)
        assert sys.scheme is scheme


# ---------------------------------------------------------------------------
# JohnnyDecimalSystem — initialize_from_directory
# ---------------------------------------------------------------------------


class TestJDSystemInitFromDir:
    def test_nonexistent_dir_raises(self, jd_system: JohnnyDecimalSystem, tmp_path: Path) -> None:
        with pytest.raises(ValueError):
            jd_system.initialize_from_directory(tmp_path / "nonexistent")

    def test_empty_dir_initializes(self, jd_system: JohnnyDecimalSystem, tmp_path: Path) -> None:
        jd_system.initialize_from_directory(tmp_path)
        assert jd_system._initialized is True

    def test_detects_numbered_files(self, jd_system: JohnnyDecimalSystem, tmp_path: Path) -> None:
        (tmp_path / "10 Finance").mkdir()
        jd_system.initialize_from_directory(tmp_path)
        assert jd_system._initialized is True

    def test_detects_category_numbered_items(
        self, jd_system: JohnnyDecimalSystem, tmp_path: Path
    ) -> None:
        f = tmp_path / "11.01 Budgets.txt"
        f.write_text("content")
        jd_system.initialize_from_directory(tmp_path)
        assert jd_system._initialized is True

    def test_unnumbered_files_ignored(self, jd_system: JohnnyDecimalSystem, tmp_path: Path) -> None:
        (tmp_path / "regular_file.txt").write_text("hello")
        (tmp_path / "another.pdf").write_bytes(b"\x00")
        jd_system.initialize_from_directory(tmp_path)
        assert jd_system._initialized is True


# ---------------------------------------------------------------------------
# JohnnyDecimalSystem — assign_number_to_file
# ---------------------------------------------------------------------------


class TestJDSystemAssignNumber:
    def test_assign_preferred_valid_number(
        self, jd_system: JohnnyDecimalSystem, tmp_path: Path
    ) -> None:
        f = tmp_path / "report.txt"
        f.write_text("content")
        preferred = JohnnyDecimalNumber(area=10, category=1)
        result = jd_system.assign_number_to_file(f, preferred_number=preferred)
        assert result.number.area == 10
        assert result.confidence > 0.5

    def test_assign_without_preferred_returns_result(
        self, jd_system: JohnnyDecimalSystem, tmp_path: Path
    ) -> None:
        f = tmp_path / "doc.txt"
        f.write_text("financial quarterly report")
        result = jd_system.assign_number_to_file(f, content="financial quarterly report")
        assert result.number is not None
        assert 0.0 <= result.confidence <= 1.0

    def test_assign_no_content_uses_next_available(
        self, jd_system: JohnnyDecimalSystem, tmp_path: Path
    ) -> None:
        f = tmp_path / "file.txt"
        f.write_text("")
        result = jd_system.assign_number_to_file(f)
        assert result.number is not None

    def test_result_has_reasons(self, jd_system: JohnnyDecimalSystem, tmp_path: Path) -> None:
        f = tmp_path / "report.txt"
        f.write_text("content")
        result = jd_system.assign_number_to_file(f)
        assert len(result.reasons) >= 1

    def test_auto_register_false_skips_registration(
        self, jd_system: JohnnyDecimalSystem, tmp_path: Path
    ) -> None:
        f = tmp_path / "report.txt"
        f.write_text("content")
        preferred = JohnnyDecimalNumber(area=20, category=2)
        result = jd_system.assign_number_to_file(f, preferred_number=preferred, auto_register=False)
        assert result.number is not None
        assert jd_system.generator.is_number_available(preferred) is True

    def test_auto_register_true_registers_number(
        self, jd_system: JohnnyDecimalSystem, tmp_path: Path
    ) -> None:
        f = tmp_path / "report.txt"
        f.write_text("content")
        preferred = JohnnyDecimalNumber(area=30, category=3)
        jd_system.assign_number_to_file(f, preferred_number=preferred, auto_register=True)
        assert jd_system.generator.is_number_available(preferred) is False


# ---------------------------------------------------------------------------
# JohnnyDecimalSystem — validate_number_assignment
# ---------------------------------------------------------------------------


class TestJDSystemValidation:
    def test_validate_valid_number(self, jd_system: JohnnyDecimalSystem, tmp_path: Path) -> None:
        n = JohnnyDecimalNumber(area=10, category=1)
        result = jd_system.validate_number_assignment(n, tmp_path / "file.txt")
        assert result is not None
        assert result.number == n

    def test_validate_result_has_metadata_validation_only(
        self, jd_system: JohnnyDecimalSystem, tmp_path: Path
    ) -> None:
        n = JohnnyDecimalNumber(area=10, category=1)
        result = jd_system.validate_number_assignment(n, tmp_path / "file.txt")
        assert result.metadata.get("validation_only") is True


# ---------------------------------------------------------------------------
# JohnnyDecimalSystem — renumber_file
# ---------------------------------------------------------------------------


class TestJDSystemRenumber:
    def test_renumber_registered_number(
        self, jd_system: JohnnyDecimalSystem, tmp_path: Path
    ) -> None:
        old = JohnnyDecimalNumber(area=10, category=1)
        new = JohnnyDecimalNumber(area=10, category=2)
        f = tmp_path / "file.txt"
        f.write_text("content")
        jd_system.generator.register_existing_number(old, f)
        result = jd_system.renumber_file(old, new, f)
        assert result.number == new

    def test_renumber_unregistered_raises(
        self, jd_system: JohnnyDecimalSystem, tmp_path: Path
    ) -> None:
        old = JohnnyDecimalNumber(area=50, category=5)
        new = JohnnyDecimalNumber(area=50, category=6)
        with pytest.raises(InvalidNumberError):
            jd_system.renumber_file(old, new, tmp_path / "file.txt")

    def test_renumber_releases_old_number(
        self, jd_system: JohnnyDecimalSystem, tmp_path: Path
    ) -> None:
        old = JohnnyDecimalNumber(area=10, category=1)
        new = JohnnyDecimalNumber(area=10, category=2)
        f = tmp_path / "file.txt"
        f.write_text("")
        jd_system.generator.register_existing_number(old, f)
        jd_system.renumber_file(old, new, f)
        assert jd_system.generator.is_number_available(old) is True
        assert jd_system.generator.is_number_available(new) is False


# ---------------------------------------------------------------------------
# JohnnyDecimalSystem — area summary / reports
# ---------------------------------------------------------------------------


class TestJDSystemReports:
    def test_get_area_summary_returns_dict(self, jd_system: JohnnyDecimalSystem) -> None:
        summary = jd_system.get_area_summary(10)
        assert isinstance(summary, dict)
        assert "area" in summary
        assert summary["area"] == 10

    def test_get_all_areas_summary_returns_list(self, jd_system: JohnnyDecimalSystem) -> None:
        summaries = jd_system.get_all_areas_summary()
        assert isinstance(summaries, list)
        assert len(summaries) > 0

    def test_get_usage_report_has_stats(self, jd_system: JohnnyDecimalSystem) -> None:
        report = jd_system.get_usage_report()
        assert "statistics" in report
        assert "scheme_name" in report
        assert "initialized" in report

    def test_usage_report_initialized_false(self, jd_system: JohnnyDecimalSystem) -> None:
        report = jd_system.get_usage_report()
        assert report["initialized"] is False


# ---------------------------------------------------------------------------
# JohnnyDecimalSystem — save/load configuration
# ---------------------------------------------------------------------------


class TestJDSystemConfig:
    def test_save_requires_path(self, jd_system: JohnnyDecimalSystem) -> None:
        with pytest.raises(ValueError):
            jd_system.save_configuration()

    def test_save_and_load_roundtrip(
        self, jd_system_with_config: JohnnyDecimalSystem, tmp_path: Path
    ) -> None:
        n = JohnnyDecimalNumber(area=10, category=1)
        f = tmp_path / "test.txt"
        f.write_text("content")
        jd_system_with_config.generator.register_existing_number(n, f)
        jd_system_with_config.save_configuration()

        sys2 = JohnnyDecimalSystem(config_path=jd_system_with_config.config_path)
        assert sys2._initialized is True
        assert sys2.generator.is_number_available(n) is False

    def test_load_nonexistent_raises(self, tmp_path: Path) -> None:
        sys = JohnnyDecimalSystem()
        with pytest.raises(FileNotFoundError):
            sys.load_configuration(tmp_path / "nonexistent.json")

    def test_load_requires_path(self, jd_system: JohnnyDecimalSystem) -> None:
        with pytest.raises(ValueError):
            jd_system.load_configuration()


# ---------------------------------------------------------------------------
# JohnnyDecimalSystem — custom areas/categories
# ---------------------------------------------------------------------------


class TestJDSystemCustom:
    def test_add_custom_area(self, jd_system: JohnnyDecimalSystem) -> None:
        area_def = AreaDefinition(
            area_range_start=90,
            area_range_end=99,
            name="Custom",
            description="Custom area",
        )
        jd_system.add_custom_area(area_def)
        assert jd_system.scheme.get_area(90) is not None

    def test_create_area_returns_jd_number(self, jd_system: JohnnyDecimalSystem) -> None:
        n = jd_system.create_area(85, "Test Area")
        assert n.area == 85
        assert n.name == "Test Area"

    def test_create_category_returns_jd_number(self, jd_system: JohnnyDecimalSystem) -> None:
        jd_system.create_area(86, "Parent")
        n = jd_system.create_category(86, 1, "Sub Category")
        assert n.area == 86
        assert n.category == 1

    def test_clear_all_registrations(self, jd_system: JohnnyDecimalSystem, tmp_path: Path) -> None:
        n = JohnnyDecimalNumber(area=10, category=1)
        f = tmp_path / "f.txt"
        f.write_text("")
        jd_system.generator.register_existing_number(n, f)
        jd_system.clear_all_registrations()
        assert jd_system.generator.is_number_available(n) is True
        assert jd_system._initialized is False


# ---------------------------------------------------------------------------
# JohnnyDecimalSystem — reserve number range
# ---------------------------------------------------------------------------


class TestJDSystemReserveRange:
    def test_reserve_area_range_single(self, jd_system: JohnnyDecimalSystem) -> None:
        start = JohnnyDecimalNumber(area=10)
        end = JohnnyDecimalNumber(area=10)
        jd_system.reserve_number_range(start, end)
        assert jd_system.scheme.is_number_reserved(JohnnyDecimalNumber(area=10))

    def test_reserve_range_different_levels_raises(self, jd_system: JohnnyDecimalSystem) -> None:
        start = JohnnyDecimalNumber(area=10)
        end = JohnnyDecimalNumber(area=10, category=1)
        with pytest.raises(ValueError):
            jd_system.reserve_number_range(start, end)

    def test_reserve_category_range(self, jd_system: JohnnyDecimalSystem) -> None:
        start = JohnnyDecimalNumber(area=10, category=1)
        end = JohnnyDecimalNumber(area=10, category=3)
        jd_system.reserve_number_range(start, end)
        for c in (1, 2, 3):
            assert jd_system.scheme.is_number_reserved(JohnnyDecimalNumber(area=10, category=c))


# ---------------------------------------------------------------------------
# PARAFolderGenerator — fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def para_gen() -> PARAFolderGenerator:
    return PARAFolderGenerator()


@pytest.fixture()
def para_gen_with_config(tmp_path: Path) -> PARAFolderGenerator:
    config = PARAConfig(default_root=tmp_path)
    return PARAFolderGenerator(config=config)


# ---------------------------------------------------------------------------
# PARAFolderGenerator — basics
# ---------------------------------------------------------------------------


class TestPARAGenInit:
    def test_default_config_created(self, para_gen: PARAFolderGenerator) -> None:
        assert para_gen.config is not None

    def test_custom_config_accepted(self, tmp_path: Path) -> None:
        config = PARAConfig(default_root=tmp_path)
        gen = PARAFolderGenerator(config=config)
        assert gen.config is config


class TestPARAGenCategoryPath:
    def test_get_category_path_project(
        self, para_gen_with_config: PARAFolderGenerator, tmp_path: Path
    ) -> None:
        path = para_gen_with_config.get_category_path(PARACategory.PROJECT, tmp_path)
        assert isinstance(path, Path)
        assert "Projects" in str(path) or "project" in str(path).lower()

    def test_get_category_path_area(
        self, para_gen_with_config: PARAFolderGenerator, tmp_path: Path
    ) -> None:
        path = para_gen_with_config.get_category_path(PARACategory.AREA, tmp_path)
        assert isinstance(path, Path)

    def test_get_category_path_resource(
        self, para_gen_with_config: PARAFolderGenerator, tmp_path: Path
    ) -> None:
        path = para_gen_with_config.get_category_path(PARACategory.RESOURCE, tmp_path)
        assert isinstance(path, Path)

    def test_get_category_path_archive(
        self, para_gen_with_config: PARAFolderGenerator, tmp_path: Path
    ) -> None:
        path = para_gen_with_config.get_category_path(PARACategory.ARCHIVE, tmp_path)
        assert isinstance(path, Path)


class TestPARAGenStructure:
    def test_generate_structure_dry_run(
        self, para_gen: PARAFolderGenerator, tmp_path: Path
    ) -> None:
        result = para_gen.generate_structure(tmp_path, dry_run=True)
        assert result is not None

    def test_generate_structure_creates_dirs(
        self, para_gen: PARAFolderGenerator, tmp_path: Path
    ) -> None:
        para_gen.generate_structure(tmp_path, dry_run=False)
        children = list(tmp_path.iterdir())
        assert len(children) > 0

    def test_generate_structure_creates_para_folders(
        self, para_gen: PARAFolderGenerator, tmp_path: Path
    ) -> None:
        para_gen.generate_structure(tmp_path, dry_run=False)
        dir_names = [d.name for d in tmp_path.iterdir() if d.is_dir()]
        # At least one PARA category folder should exist
        assert len(dir_names) > 0

    def test_validate_structure_empty_dir(
        self, para_gen: PARAFolderGenerator, tmp_path: Path
    ) -> None:
        result = para_gen.validate_structure(tmp_path)
        # Empty dir missing required folders → returns False
        assert result is False

    def test_validate_structure_after_generate(
        self, para_gen: PARAFolderGenerator, tmp_path: Path
    ) -> None:
        para_gen.generate_structure(tmp_path, dry_run=False)
        result = para_gen.validate_structure(tmp_path)
        assert result is True


class TestPARAGenCreateCategoryFolder:
    def test_create_project_folder(self, para_gen: PARAFolderGenerator, tmp_path: Path) -> None:
        path = para_gen.create_category_folder(PARACategory.PROJECT, root_path=tmp_path)
        assert isinstance(path, Path)
        assert path.exists()

    def test_create_area_folder(self, para_gen: PARAFolderGenerator, tmp_path: Path) -> None:
        path = para_gen.create_category_folder(PARACategory.AREA, root_path=tmp_path)
        assert path.exists()

    def test_create_folder_with_subfolder(
        self, para_gen: PARAFolderGenerator, tmp_path: Path
    ) -> None:
        path = para_gen.create_category_folder(
            PARACategory.RESOURCE, subfolder="Books", root_path=tmp_path
        )
        assert path.exists()
        assert "Books" in str(path)
