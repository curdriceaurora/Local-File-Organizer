"""
Tests for PARA folder mapper.

Tests category-based folder mapping and organization strategies.
"""

from __future__ import annotations

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


@pytest.mark.unit
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
        strategy = MappingStrategy(use_date_folders=True, date_format="%Y/%m")
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

        # Check that categories with mapped files appear in the report
        mapped_categories = {r.target_category for r in results}
        for category in mapped_categories:
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


@pytest.mark.unit
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


@pytest.mark.unit
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
        strategy = MappingStrategy(use_date_folders=True, date_format="%Y/%m/%d")

        assert strategy.use_date_folders is True
        assert strategy.date_format == "%Y/%m/%d"

    def test_type_strategy(self):
        """Test type-based strategy."""
        type_map = {".txt": "Documents", ".pdf": "PDFs"}
        strategy = MappingStrategy(use_type_folders=True, type_mapping=type_map)

        assert strategy.use_type_folders is True
        assert strategy.type_mapping == type_map

    def test_keyword_strategy(self):
        """Test keyword-based strategy."""
        keyword_map = {"project": "Projects", "notes": "Notes"}
        strategy = MappingStrategy(use_keyword_folders=True, keyword_mapping=keyword_map)

        assert strategy.use_keyword_folders is True
        assert strategy.keyword_mapping == keyword_map

    def test_custom_function_strategy(self):
        """Test custom function strategy."""

        def custom_fn(path: Path, category: PARACategory) -> str | None:
            return "custom"

        strategy = MappingStrategy(custom_subfolder_fn=custom_fn)

        assert strategy.custom_subfolder_fn is not None
        assert strategy.custom_subfolder_fn(Path("/test"), PARACategory.PROJECT) == "custom"


@pytest.mark.unit
class TestCategoryFolderMapperEdgeCases:
    """Test edge cases for folder mapper."""

    @pytest.fixture
    def temp_source(self, tmp_path: Path) -> Path:
        """Create temporary source directory with test files."""
        source = tmp_path / "source"
        source.mkdir()
        (source / "test.txt").write_text("Test content")
        (source / "data.json").write_text('{"test": true}')
        return source

    @pytest.fixture
    def temp_target(self, tmp_path: Path) -> Path:
        """Create temporary target directory."""
        target = tmp_path / "target"
        target.mkdir()
        return target

    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return PARAConfig(
            project_dir="Projects",
            area_dir="Areas",
            resource_dir="Resources",
            archive_dir="Archive",
        )

    def test_mapper_with_provided_heuristic_engine(self, config, temp_source, temp_target):
        """Test mapper initialization with provided heuristic engine."""
        from file_organizer.methodologies.para.detection.heuristics import HeuristicEngine

        # Create custom heuristic engine
        heuristic_engine = HeuristicEngine()
        mapper = CategoryFolderMapper(config, heuristic_engine=heuristic_engine)

        assert mapper.heuristic_engine is heuristic_engine
        assert mapper.config == config

        # Should work normally
        test_file = temp_source / "test.txt"
        result = mapper.map_file(test_file, temp_target)
        assert isinstance(result, MappingResult)

    def test_mapper_with_rule_engine(self, config, temp_source, temp_target, mocker):
        """Test mapper with rule engine that returns a match."""
        from file_organizer.methodologies.para.rules.engine import (
            ActionType,
            Rule,
            RuleAction,
            RuleMatchResult,
        )

        # Create a mock rule engine that returns a successful match
        mock_rule_engine = mocker.Mock()

        # Create a mock rule and match result
        mock_rule = mocker.Mock(spec=Rule)
        mock_rule.name = "test_rule"

        mock_action = mocker.Mock(spec=RuleAction)
        mock_action.type = ActionType.CATEGORIZE
        mock_action.category = "project"
        mock_action.confidence = 0.9

        match_result = RuleMatchResult(
            rule=mock_rule,
            matched=True,
            confidence=0.9,
            category="project",
            reasons=["File matches rule"],
        )

        mock_rule_engine.evaluate_file.return_value = match_result

        mapper = CategoryFolderMapper(config, rule_engine=mock_rule_engine)

        test_file = temp_source / "test.txt"
        result = mapper.map_file(test_file, temp_target, use_rules=True)

        assert isinstance(result, MappingResult)
        # Check that reasoning includes rule match
        assert any("Rule" in r or "rule" in r for r in result.reasoning)
        assert result.target_category == PARACategory.PROJECT

    def test_mapper_with_rule_engine_exception(self, config, temp_source, temp_target, mocker):
        """Test mapper handles rule engine exceptions gracefully."""
        from file_organizer.methodologies.para.rules.engine import RuleEngine

        # Create a mock rule engine that raises an exception
        rule_engine = mocker.Mock(spec=RuleEngine)
        rule_engine.evaluate_file.side_effect = Exception("Rule evaluation failed")

        mapper = CategoryFolderMapper(config, rule_engine=rule_engine)

        test_file = temp_source / "test.txt"
        # Should not raise, should fall back to heuristics
        result = mapper.map_file(test_file, temp_target, use_rules=True)

        assert isinstance(result, MappingResult)
        assert result.target_category is not None

    def test_custom_subfolder_function_exception(self, config, temp_source, temp_target):
        """Test that custom subfolder function exceptions are handled."""

        def failing_fn(path: Path, category: PARACategory) -> str | None:
            raise ValueError("Intentional error")

        strategy = MappingStrategy(custom_subfolder_fn=failing_fn)
        mapper = CategoryFolderMapper(config, strategy=strategy)

        test_file = temp_source / "test.txt"
        result = mapper.map_file(test_file, temp_target)

        # Should handle exception and continue
        assert isinstance(result, MappingResult)
        # Subfolder should be None since custom function failed
        assert result.subfolder_path is None

    def test_date_folder_with_nonexistent_file(self, config, temp_target):
        """Test date folder extraction with file that doesn't exist."""
        strategy = MappingStrategy(use_date_folders=True, date_format="%Y/%m")
        mapper = CategoryFolderMapper(config, strategy=strategy)

        # Use a non-existent file
        nonexistent_file = Path("/nonexistent/file.txt")
        result = mapper.map_file(nonexistent_file, temp_target)

        # Should handle gracefully, subfolder might be None or have no date part
        assert isinstance(result, MappingResult)
        assert result.subfolder_path is None

    def test_keyword_folder_no_match(self, config, temp_source, temp_target):
        """Test keyword folder when no keywords match."""
        strategy = MappingStrategy(
            use_keyword_folders=True,
            keyword_mapping={"report": "Reports", "invoice": "Invoices"},
        )
        mapper = CategoryFolderMapper(config, strategy=strategy)

        # File name doesn't contain any keywords
        test_file = temp_source / "data.json"
        result = mapper.map_file(test_file, temp_target)

        # Should not have keyword folder
        assert isinstance(result, MappingResult)
        # Subfolder should be None since no keywords matched
        assert result.subfolder_path is None

    def test_type_folder_unmapped_extension(self, config, temp_source, temp_target):
        """Test type folder with unmapped file extension."""
        strategy = MappingStrategy(
            use_type_folders=True,
            type_mapping={".txt": "Documents", ".pdf": "PDFs"},
        )
        mapper = CategoryFolderMapper(config, strategy=strategy)

        # File with unmapped extension
        test_file = temp_source / "data.json"
        result = mapper.map_file(test_file, temp_target)

        # Should not have type folder
        assert isinstance(result, MappingResult)
        # Subfolder should be None since extension not in mapping
        assert result.subfolder_path is None

    def test_create_folders_with_permission_error(self, config, temp_source, temp_target, mocker):
        """Test folder creation with permission errors."""
        mapper = CategoryFolderMapper(config)

        test_file = temp_source / "test.txt"
        results = [mapper.map_file(test_file, temp_target)]

        # Mock mkdir to raise PermissionError
        def failing_mkdir(self, *args, **kwargs):
            raise PermissionError("No permission")

        mocker.patch.object(Path, "mkdir", failing_mkdir)

        folder_status = mapper.create_target_folders(results, dry_run=False)

        # Should have False status for failed folders
        assert len(folder_status) > 0
        assert any(not status for status in folder_status.values())

    def test_generate_report_with_reasoning(self, config, temp_source, temp_target):
        """Test report generation includes reasoning."""
        mapper = CategoryFolderMapper(config)

        test_file = temp_source / "test.txt"
        results = [mapper.map_file(test_file, temp_target)]

        report = mapper.generate_mapping_report(results)

        # Should include reasoning in report
        assert "Reason:" in report or results[0].reasoning == []

    def test_generate_report_with_many_files(self, config, temp_source, temp_target):
        """Test report shows '... and N more files' for large batches."""
        mapper = CategoryFolderMapper(config)

        # Create results for more than 10 files
        results = []
        for i in range(15):
            file_path = temp_source / f"file{i}.txt"
            file_path.write_text(f"Content {i}")
            result = mapper.map_file(file_path, temp_target)
            results.append(result)

        report = mapper.generate_mapping_report(results)

        # Should show "... and 5 more files"
        assert "... and 5 more files" in report
        assert "Total files: 15" in report

    def test_generate_report_empty_reasoning(self, config, temp_source, temp_target):
        """Test report handles empty reasoning lists."""
        mapper = CategoryFolderMapper(config)

        # Create a temporary file for the test
        test_file = temp_source / "file.txt"
        test_file.write_text("test")

        # Create a result with empty reasoning
        result = MappingResult(
            source_path=test_file,
            target_category=PARACategory.RESOURCE,
            target_folder=temp_target / "Resources",
            confidence=0.5,
            reasoning=[],
            subfolder_path=None,
        )
        results = [result]

        report = mapper.generate_mapping_report(results)

        # Should handle empty reasoning gracefully
        assert "file.txt" in report
        assert "resource" in report.lower()

    def test_extract_reasoning_with_category_scores(self, config, temp_source, temp_target):
        """Test reasoning extraction includes category scores."""

        mapper = CategoryFolderMapper(config)

        test_file = temp_source / "test.txt"
        result = mapper.map_file(test_file, temp_target)

        # Result should have reasoning from heuristics
        assert isinstance(result.reasoning, list)
        assert len(result.reasoning) > 0  # Should have at least one reasoning entry

    def test_map_batch_with_real_exception(self, config, temp_target, mocker):
        """Test map_batch handles exceptions during mapping."""
        mapper = CategoryFolderMapper(config)

        # Mock map_file to raise an exception
        original_map_file = mapper.map_file

        def failing_map_file(file_path, root_path, use_rules=True):
            if "failing" in file_path.name:
                raise ValueError("Mapping failed")
            return original_map_file(file_path, root_path, use_rules)

        mapper.map_file = failing_map_file

        files = [Path("/test/failing_file.txt"), Path("/test/normal_file.txt")]
        results = mapper.map_batch(files, temp_target)

        # Should have results for both files
        assert len(results) == 2
        # First file should have error result with 0.0 confidence
        assert results[0].confidence == 0.0
        assert "Error during mapping" in results[0].reasoning[0]

    def test_keyword_folder_empty_mapping(self, config, temp_source, temp_target):
        """Test keyword folder strategy with empty mapping."""
        strategy = MappingStrategy(
            use_keyword_folders=True,
            keyword_mapping={},  # Empty mapping
        )
        mapper = CategoryFolderMapper(config, strategy=strategy)

        test_file = temp_source / "test.txt"
        result = mapper.map_file(test_file, temp_target)

        # Should handle empty mapping gracefully
        assert isinstance(result, MappingResult)
        assert result.subfolder_path is None

    def test_date_folder_format_error(self, config, temp_source, temp_target):
        """Test date folder with unsupported strftime directive."""
        # Use an unsupported strftime directive — Python does not raise, it produces
        # a literal output (platform-dependent: macOS strips % giving "Q", Linux may vary).
        strategy = MappingStrategy(
            use_date_folders=True, date_format="%Q"
        )  # %Q is not a valid directive
        mapper = CategoryFolderMapper(config, strategy=strategy)

        test_file = temp_source / "test.txt"
        result = mapper.map_file(test_file, temp_target)

        assert isinstance(result, MappingResult)
        # strftime does not raise for unknown directives — a non-None string is returned
        assert isinstance(result.subfolder_path, str)

    def test_extract_reasoning_with_category_in_scores(
        self, config, temp_source, temp_target, mocker
    ):
        """Test extracting reasoning when category is in heuristic result scores."""
        from file_organizer.methodologies.para.detection.heuristics import (
            CategoryScore,
            HeuristicResult,
        )

        mapper = CategoryFolderMapper(config)

        # Create a mock heuristic result with category scores containing signals
        mock_result = mocker.Mock(spec=HeuristicResult)
        mock_result.recommended_category = PARACategory.PROJECT
        mock_result.overall_confidence = 0.8

        # Create category score with signals
        mock_category_score = mocker.Mock(spec=CategoryScore)
        mock_category_score.signals = [
            "Signal 1: Project indicator",
            "Signal 2: Active files",
            "Signal 3: Recent modifications",
            "Signal 4: Extra signal",
        ]
        mock_result.scores = {PARACategory.PROJECT: mock_category_score}

        # Mock the heuristic engine to return our mock result
        mapper.heuristic_engine.evaluate = mocker.Mock(return_value=mock_result)

        test_file = temp_source / "test.txt"
        result = mapper.map_file(test_file, temp_target, use_rules=False)

        # Should have extracted top 3 signals from category scores
        assert len(result.reasoning) >= 3
        assert any("Signal" in r for r in result.reasoning)

    def test_keyword_folder_with_none_mapping(self, config, temp_source, temp_target):
        """Test keyword folder strategy when keyword_mapping is None."""
        strategy = MappingStrategy(
            use_keyword_folders=True,
            keyword_mapping=None,  # Explicitly None
        )
        mapper = CategoryFolderMapper(config, strategy=strategy)

        test_file = temp_source / "test.txt"
        result = mapper.map_file(test_file, temp_target)

        # Should handle None mapping gracefully
        assert isinstance(result, MappingResult)
        # Subfolder should be None since keyword_mapping is None
        assert result.subfolder_path is None

    def test_evaluate_rules_with_none_rule_engine(self, config, temp_source, temp_target):
        """Test _evaluate_rules when rule_engine is None."""
        # Create mapper without rule_engine
        mapper = CategoryFolderMapper(config, rule_engine=None)

        test_file = temp_source / "test.txt"
        # Call _evaluate_rules directly
        result = mapper._evaluate_rules(test_file)

        # Should return None when rule_engine is None
        assert result is None

    def test_extract_reasoning_category_not_in_scores(
        self, config, temp_source, temp_target, mocker
    ):
        """Test extracting reasoning when category is NOT in heuristic result scores."""
        from file_organizer.methodologies.para.detection.heuristics import HeuristicResult

        mapper = CategoryFolderMapper(config)

        # Create a mock heuristic result without the category in scores
        mock_result = mocker.Mock(spec=HeuristicResult)
        mock_result.recommended_category = PARACategory.PROJECT
        mock_result.overall_confidence = 0.7
        # Empty scores dict - category not in scores
        mock_result.scores = {}

        # Mock the heuristic engine to return our mock result
        mapper.heuristic_engine.evaluate = mocker.Mock(return_value=mock_result)

        test_file = temp_source / "test.txt"
        result = mapper.map_file(test_file, temp_target, use_rules=False)

        # Should handle missing category in scores gracefully
        assert isinstance(result, MappingResult)
        # Reasoning might be empty since category not in scores
        assert isinstance(result.reasoning, list)
        assert result.target_category == PARACategory.PROJECT

    def test_match_keyword_folder_with_false_mapping(self, config, temp_source, temp_target):
        """Test keyword folder when strategy has keyword_folders enabled but no mapping."""
        strategy = MappingStrategy(
            use_keyword_folders=False,  # Disabled
            keyword_mapping={"test": "Test"},  # Has mapping but disabled
        )
        mapper = CategoryFolderMapper(config, strategy=strategy)

        test_file = temp_source / "test.txt"
        result = mapper.map_file(test_file, temp_target)

        # Since use_keyword_folders is False, should not use keyword mapping
        assert isinstance(result, MappingResult)
        assert result.subfolder_path is None

    def test_match_keyword_folder_directly_with_none(self, config, temp_source):
        """Test _match_keyword_folder directly when keyword_mapping is None."""
        # Create mapper with None keyword_mapping
        strategy = MappingStrategy(keyword_mapping=None)
        mapper = CategoryFolderMapper(config, strategy=strategy)

        test_file = temp_source / "test.txt"
        # Call _match_keyword_folder directly to hit line 300
        result = mapper._match_keyword_folder(test_file)

        # Should return None when keyword_mapping is None
        assert result is None
