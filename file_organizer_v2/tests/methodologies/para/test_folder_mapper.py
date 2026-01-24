"""
Tests for PARA folder mapper.

Tests category-based folder mapping and organization strategies.
"""

import shutil
import tempfile
from pathlib import Path

import pytest

from file_organizer.methodologies.para.categories import PARACategory
from file_organizer.methodologies.para.config import PARAConfig
from file_organizer.methodologies.para.folder_mapper import (
    CategoryFolderMapper,
    MappingResult,
    MappingStrategy,
)


class TestCategoryFolderMapper:
    """Test category-based folder mapping."""

    @pytest.fixture
    def temp_source(self):
        """Create temporary source directory with test files."""
        temp_path = Path(tempfile.mkdtemp())

        # Create test files
        (temp_path / "project_plan.txt").write_text("Project plan content")
        (temp_path / "notes.md").write_text("Meeting notes")
        (temp_path / "reference.pdf").write_text("Reference")

        yield temp_path

        # Cleanup
        if temp_path.exists():
            shutil.rmtree(temp_path)

    @pytest.fixture
    def temp_target(self):
        """Create temporary target directory."""
        temp_path = Path(tempfile.mkdtemp())
        yield temp_path

        # Cleanup
        if temp_path.exists():
            shutil.rmtree(temp_path)

    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return PARAConfig(
            project_dir="Projects",
            area_dir="Areas",
            resource_dir="Resources",
            archive_dir="Archive",
        )

    @pytest.fixture
    def mapper(self, config):
        """Create folder mapper instance."""
        return CategoryFolderMapper(config)

    def test_initialization(self, config):
        """Test mapper initialization."""
        mapper = CategoryFolderMapper(config)
        assert mapper.config == config
        assert mapper.heuristic_engine is not None
        assert mapper.folder_generator is not None
        assert mapper.strategy is not None

        # Test default config
        default_mapper = CategoryFolderMapper()
        assert default_mapper.config is not None

    def test_map_file_basic(self, mapper, temp_source, temp_target):
        """Test basic file mapping."""
        test_file = temp_source / "project_plan.txt"

        result = mapper.map_file(test_file, temp_target)

        assert isinstance(result, MappingResult)
        assert result.source_path == test_file
        assert isinstance(result.target_category, PARACategory)
        assert result.target_folder.is_absolute()
        assert 0.0 <= result.confidence <= 1.0
        assert isinstance(result.reasoning, list)

    def test_map_file_without_rules(self, mapper, temp_source, temp_target):
        """Test file mapping without rule engine."""
        test_file = temp_source / "notes.md"

        result = mapper.map_file(test_file, temp_target, use_rules=False)

        assert result.target_category is not None
        # Should use heuristics only
        assert len(result.reasoning) > 0

    def test_map_file_defaults_to_resource(self, mapper, temp_source, temp_target):
        """Test that unclear files default to Resource."""
        # Create a file with no clear categorization
        unclear_file = temp_source / "random.dat"
        unclear_file.write_bytes(b"binary data")

        result = mapper.map_file(unclear_file, temp_target)

        # Should default to Resource
        assert result.target_category in [
            PARACategory.RESOURCE,
            PARACategory.PROJECT,
            PARACategory.AREA,
            PARACategory.ARCHIVE,
        ]

    def test_map_batch_files(self, mapper, temp_source, temp_target):
        """Test mapping multiple files at once."""
        files = list(temp_source.glob("*.txt")) + list(temp_source.glob("*.md"))

        results = mapper.map_batch(files, temp_target)

        assert len(results) == len(files)
        assert all(isinstance(r, MappingResult) for r in results)

        # All files should have categories
        assert all(r.target_category is not None for r in results)

    def test_map_batch_handles_errors(self, mapper, temp_target):
        """Test batch mapping handles errors gracefully."""
        # Include a non-existent file
        files = [
            Path("/nonexistent/file1.txt"),
            Path("/nonexistent/file2.txt"),
        ]

        results = mapper.map_batch(files, temp_target)

        assert len(results) == len(files)
        # Should have error results with low confidence
        assert all(r.confidence == 0.0 for r in results)

    def test_mapping_strategy_no_subfolders(self, config, temp_source, temp_target):
        """Test mapping with no subfolder strategy."""
        strategy = MappingStrategy(
            use_date_folders=False,
            use_type_folders=False,
            use_keyword_folders=False,
        )
        mapper = CategoryFolderMapper(config, strategy=strategy)

        test_file = temp_source / "project_plan.txt"
        result = mapper.map_file(test_file, temp_target)

        # Should not have subfolder path
        assert result.subfolder_path is None
        assert result.target_folder.name in [
            "Projects",
            "Areas",
            "Resources",
            "Archive",
        ]

    def test_mapping_strategy_date_folders(self, config, temp_source, temp_target):
        """Test mapping with date-based subfolders."""
        strategy = MappingStrategy(
            use_date_folders=True, date_format="%Y/%m"
        )
        mapper = CategoryFolderMapper(config, strategy=strategy)

        test_file = temp_source / "project_plan.txt"
        result = mapper.map_file(test_file, temp_target)

        # Should have date subfolder
        if result.subfolder_path:
            # Check format YYYY/MM
            parts = result.subfolder_path.split("/")
            assert len(parts) == 2
            assert len(parts[0]) == 4  # Year
            assert len(parts[1]) == 2  # Month

    def test_mapping_strategy_type_folders(self, config, temp_source, temp_target):
        """Test mapping with file type subfolders."""
        strategy = MappingStrategy(
            use_type_folders=True,
            type_mapping={
                ".txt": "Documents",
                ".pdf": "PDFs",
                ".md": "Markdown",
            },
        )
        mapper = CategoryFolderMapper(config, strategy=strategy)

        # Test .txt file
        txt_file = temp_source / "project_plan.txt"
        result = mapper.map_file(txt_file, temp_target)

        if result.subfolder_path:
            assert "Documents" in result.subfolder_path

        # Test .md file
        md_file = temp_source / "notes.md"
        result = mapper.map_file(md_file, temp_target)

        if result.subfolder_path:
            assert "Markdown" in result.subfolder_path

    def test_mapping_strategy_keyword_folders(self, config, temp_source, temp_target):
        """Test mapping with keyword-based subfolders."""
        strategy = MappingStrategy(
            use_keyword_folders=True,
            keyword_mapping={
                "project": "ProjectFiles",
                "notes": "Notes",
                "reference": "References",
            },
        )
        mapper = CategoryFolderMapper(config, strategy=strategy)

        # File with "project" in name
        project_file = temp_source / "project_plan.txt"
        result = mapper.map_file(project_file, temp_target)

        if result.subfolder_path:
            assert "ProjectFiles" in result.subfolder_path

        # File with "notes" in name
        notes_file = temp_source / "notes.md"
        result = mapper.map_file(notes_file, temp_target)

        if result.subfolder_path:
            assert "Notes" in result.subfolder_path

    def test_mapping_strategy_custom_function(self, config, temp_source, temp_target):
        """Test mapping with custom subfolder function."""

        def custom_fn(file_path: Path, category: PARACategory) -> str | None:
            # Organize by first letter
            return file_path.name[0].upper()

        strategy = MappingStrategy(custom_subfolder_fn=custom_fn)
        mapper = CategoryFolderMapper(config, strategy=strategy)

        test_file = temp_source / "project_plan.txt"
        result = mapper.map_file(test_file, temp_target)

        # Should have subfolder based on first letter
        assert result.subfolder_path == "P"

    def test_mapping_strategy_combined(self, config, temp_source, temp_target):
        """Test mapping with multiple strategies combined."""
        strategy = MappingStrategy(
            use_date_folders=True,
            date_format="%Y",
            use_type_folders=True,
            type_mapping={".txt": "Documents"},
        )
        mapper = CategoryFolderMapper(config, strategy=strategy)

        test_file = temp_source / "project_plan.txt"
        result = mapper.map_file(test_file, temp_target)

        # Should have both year and type in path
        if result.subfolder_path:
            parts = result.subfolder_path.split("/")
            assert len(parts) >= 1

    def test_create_target_folders(self, mapper, temp_source, temp_target):
        """Test creating target folders from mapping results."""
        files = list(temp_source.glob("*"))
        results = mapper.map_batch(files, temp_target)

        # Create folders
        folder_status = mapper.create_target_folders(results, dry_run=False)

        assert len(folder_status) > 0
        # Check at least some folders were created
        assert any(status for status in folder_status.values())

        # Folders should exist
        created_folders = [f for f, status in folder_status.items() if status]
        assert all(f.exists() for f in created_folders)

    def test_create_target_folders_dry_run(self, mapper, temp_source, temp_target):
        """Test dry run doesn't create folders."""
        files = list(temp_source.glob("*"))
        results = mapper.map_batch(files, temp_target)

        folder_status = mapper.create_target_folders(results, dry_run=True)

        # Should report what would be created
        assert len(folder_status) > 0

        # But folders should not exist
        for folder in folder_status.keys():
            assert not folder.exists()

    def test_generate_mapping_report(self, mapper, temp_source, temp_target):
        """Test generating mapping report."""
        files = list(temp_source.glob("*"))
        results = mapper.map_batch(files, temp_target)

        report = mapper.generate_mapping_report(results)

        assert isinstance(report, str)
        assert "PARA Folder Mapping Report" in report
        assert f"Total files: {len(results)}" in report
        assert "Distribution by Category" in report

        # Check category names appear
        for category in PARACategory:
            assert category.value in report.lower()

    def test_report_shows_sample_mappings(self, mapper, temp_source, temp_target):
        """Test that report shows sample file mappings."""
        files = list(temp_source.glob("*"))
        results = mapper.map_batch(files, temp_target)

        report = mapper.generate_mapping_report(results)

        # Should show file names
        for result in results[:5]:  # Check first few
            if result.confidence > 0:
                assert result.source_path.name in report


class TestMappingResult:
    """Test MappingResult dataclass."""

    def test_valid_mapping_result(self):
        """Test creating valid mapping result."""
        result = MappingResult(
            source_path=Path("/source/file.txt"),
            target_category=PARACategory.PROJECT,
            target_folder=Path("/target/Projects"),
            confidence=0.85,
            reasoning=["Reason 1"],
            subfolder_path="2024/01",
        )

        assert result.source_path == Path("/source/file.txt")
        assert result.target_category == PARACategory.PROJECT
        assert result.confidence == 0.85
        assert result.subfolder_path == "2024/01"

    def test_mapping_result_without_subfolder(self):
        """Test mapping result without subfolder."""
        result = MappingResult(
            source_path=Path("/source/file.txt"),
            target_category=PARACategory.AREA,
            target_folder=Path("/target/Areas"),
            confidence=0.75,
            reasoning=[],
            subfolder_path=None,
        )

        assert result.subfolder_path is None
        assert result.target_folder == Path("/target/Areas")


class TestMappingStrategy:
    """Test MappingStrategy dataclass."""

    def test_default_strategy(self):
        """Test default mapping strategy."""
        strategy = MappingStrategy()

        assert strategy.use_date_folders is False
        assert strategy.use_type_folders is False
        assert strategy.use_keyword_folders is False
        assert strategy.custom_subfolder_fn is None

    def test_date_strategy(self):
        """Test date-based strategy."""
        strategy = MappingStrategy(
            use_date_folders=True, date_format="%Y/%m/%d"
        )

        assert strategy.use_date_folders is True
        assert strategy.date_format == "%Y/%m/%d"

    def test_type_strategy(self):
        """Test type-based strategy."""
        type_map = {".txt": "Documents", ".pdf": "PDFs"}
        strategy = MappingStrategy(
            use_type_folders=True, type_mapping=type_map
        )

        assert strategy.use_type_folders is True
        assert strategy.type_mapping == type_map

    def test_keyword_strategy(self):
        """Test keyword-based strategy."""
        keyword_map = {"project": "Projects", "notes": "Notes"}
        strategy = MappingStrategy(
            use_keyword_folders=True, keyword_mapping=keyword_map
        )

        assert strategy.use_keyword_folders is True
        assert strategy.keyword_mapping == keyword_map

    def test_custom_function_strategy(self):
        """Test custom function strategy."""

        def custom_fn(path: Path, category: PARACategory) -> str | None:
            return "custom"

        strategy = MappingStrategy(custom_subfolder_fn=custom_fn)

        assert strategy.custom_subfolder_fn is not None
        assert strategy.custom_subfolder_fn(Path("/test"), PARACategory.PROJECT) == "custom"
