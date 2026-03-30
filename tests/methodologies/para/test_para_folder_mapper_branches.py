"""Tests for PARA folder_mapper uncovered branches.

Targets: _evaluate_rules exception handling, _extract_reasoning empty category,
_determine_subfolder custom fn error, _get_date_folder error, _match_keyword_folder
empty mapping, create_target_folders error, generate_mapping_report >10 results.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from file_organizer.methodologies.para.categories import PARACategory
from file_organizer.methodologies.para.config import PARAConfig
from file_organizer.methodologies.para.folder_mapper import (
    CategoryFolderMapper,
    MappingResult,
    MappingStrategy,
)

pytestmark = pytest.mark.unit


class TestFolderMapperBranches:
    """Cover uncovered branches in folder_mapper.py."""

    @pytest.fixture
    def config(self) -> PARAConfig:
        return PARAConfig()

    def test_evaluate_rules_exception_returns_none(self, config: PARAConfig) -> None:
        """_evaluate_rules returns None when rule engine raises (line 200)."""
        rule_engine = MagicMock()
        rule_engine.evaluate_file.side_effect = RuntimeError("rule error")
        mapper = CategoryFolderMapper(config, rule_engine=rule_engine)
        result = mapper._evaluate_rules(Path("/fake/file.txt"))
        assert result is None

    def test_evaluate_rules_no_engine_returns_none(self, config: PARAConfig) -> None:
        """_evaluate_rules returns None when no rule engine (line 189)."""
        mapper = CategoryFolderMapper(config, rule_engine=None)
        result = mapper._evaluate_rules(Path("/fake/file.txt"))
        assert result is None

    def test_extract_reasoning_none_category(self, config: PARAConfig) -> None:
        """_extract_reasoning returns empty list for None category (line 217)."""
        mapper = CategoryFolderMapper(config)
        mock_result = MagicMock()
        reasoning = mapper._extract_reasoning(mock_result, None)
        assert reasoning == []

    def test_extract_reasoning_category_in_scores(self, config: PARAConfig) -> None:
        """_extract_reasoning extracts top 3 signals (lines 221-225)."""
        mapper = CategoryFolderMapper(config)
        mock_result = MagicMock()
        mock_score = MagicMock()
        mock_score.signals = ["sig1", "sig2", "sig3", "sig4"]
        mock_result.scores = {PARACategory.PROJECT: mock_score}
        reasoning = mapper._extract_reasoning(mock_result, PARACategory.PROJECT)
        assert reasoning == ["sig1", "sig2", "sig3"]

    def test_custom_subfolder_fn_exception(self, config: PARAConfig, tmp_path: Path) -> None:
        """Custom subfolder fn that raises is caught (line 241-242)."""

        def bad_fn(fp: Path, cat: PARACategory) -> str | None:
            raise RuntimeError("custom fn error")

        strategy = MappingStrategy(custom_subfolder_fn=bad_fn)
        mapper = CategoryFolderMapper(config, strategy=strategy)
        # Should not raise; should return None from custom fn then fallback
        result = mapper._determine_subfolder(tmp_path / "file.txt", PARACategory.PROJECT)
        assert result is None

    def test_match_keyword_folder_no_mapping(self, config: PARAConfig) -> None:
        """_match_keyword_folder returns None when keyword_mapping is None (line 299)."""
        strategy = MappingStrategy(use_keyword_folders=True, keyword_mapping=None)
        mapper = CategoryFolderMapper(config, strategy=strategy)
        result = mapper._match_keyword_folder(Path("/some/file.txt"))
        assert result is None

    def test_match_keyword_folder_no_match(self, config: PARAConfig) -> None:
        """_match_keyword_folder returns None when no keyword matches (line 308)."""
        strategy = MappingStrategy(use_keyword_folders=True, keyword_mapping={"budget": "Finance"})
        mapper = CategoryFolderMapper(config, strategy=strategy)
        result = mapper._match_keyword_folder(Path("/some/report.txt"))
        assert result is None

    def test_create_target_folders_error(self, config: PARAConfig, tmp_path: Path) -> None:
        """create_target_folders handles mkdir failure (lines 334-336)."""
        mapper = CategoryFolderMapper(config)
        bad_folder = Path("/proc/fake/folder")
        results = [
            MappingResult(
                source_path=tmp_path / "a.txt",
                target_category=PARACategory.PROJECT,
                target_folder=bad_folder,
                confidence=0.8,
                reasoning=["test"],
            )
        ]
        status = mapper.create_target_folders(results, dry_run=False)
        # Should have False for the bad folder
        assert bad_folder in status
        assert status[bad_folder] is False

    def test_generate_mapping_report_more_than_10(self, config: PARAConfig) -> None:
        """generate_mapping_report shows '...and N more files' (line 378)."""
        mapper = CategoryFolderMapper(config)
        results = [
            MappingResult(
                source_path=Path(f"/src/file{i}.txt"),
                target_category=PARACategory.RESOURCE,
                target_folder=Path("/dst/Resources"),
                confidence=0.7,
                reasoning=["reason"],
            )
            for i in range(15)
        ]
        report = mapper.generate_mapping_report(results)
        assert "... and 5 more files" in report

    def test_generate_mapping_report_empty(self, config: PARAConfig) -> None:
        """generate_mapping_report with empty results."""
        mapper = CategoryFolderMapper(config)
        report = mapper.generate_mapping_report([])
        assert "Total files: 0" in report

    def test_mapper_with_provided_heuristic_engine(self, config: PARAConfig) -> None:
        """CategoryFolderMapper uses provided heuristic engine (line 93)."""
        from file_organizer.methodologies.para.detection.heuristics import HeuristicEngine

        custom_engine = HeuristicEngine()
        mapper = CategoryFolderMapper(config, heuristic_engine=custom_engine)
        assert mapper.heuristic_engine is custom_engine

    def test_map_file_with_rules_override(self, config: PARAConfig, tmp_path: Path) -> None:
        """map_file uses rule result when available (lines 117-122)."""
        test_file = tmp_path / "project_plan.txt"
        test_file.write_text("test content")
        root = tmp_path / "para_root"

        # Create rule engine with a matching rule
        rule_engine = MagicMock()
        rule_result = MagicMock()
        rule_result.category = "project"
        rule_result.confidence = 0.95
        mock_rule = MagicMock()
        mock_rule.name = "test_rule"
        rule_result.rule = mock_rule
        rule_engine.evaluate_file.return_value = rule_result

        heuristic_engine = MagicMock()
        heuristic_result = MagicMock()
        heuristic_result.recommended_category = PARACategory.AREA
        heuristic_result.overall_confidence = 0.2
        heuristic_result.scores = {}
        heuristic_engine.evaluate.return_value = heuristic_result

        mapper = CategoryFolderMapper(
            config,
            heuristic_engine=heuristic_engine,
            rule_engine=rule_engine,
        )
        result = mapper.map_file(test_file, root, use_rules=True)

        assert result.target_category == PARACategory.PROJECT
        assert "Rule 'test_rule' matched" in result.reasoning
        assert result.confidence >= 0.95

    def test_map_file_defaults_to_resource(self, config: PARAConfig, tmp_path: Path) -> None:
        """map_file defaults to Resource when no clear category (lines 125-127)."""
        test_file = tmp_path / "unknown.bin"
        test_file.write_text("binary data")
        root = tmp_path / "para_root"

        # Mock heuristic engine to return None category
        heuristic_engine = MagicMock()
        mock_result = MagicMock()
        mock_result.recommended_category = None
        mock_result.overall_confidence = 0.2
        mock_result.scores = {}
        heuristic_engine.evaluate.return_value = mock_result

        mapper = CategoryFolderMapper(config, heuristic_engine=heuristic_engine)
        result = mapper.map_file(test_file, root, use_rules=False)

        assert result.target_category == PARACategory.RESOURCE
        assert "Defaulted to Resource" in result.reasoning[0]

    def test_map_file_with_subfolder(self, config: PARAConfig, tmp_path: Path) -> None:
        """map_file creates target with subfolder (lines 136-138)."""
        test_file = tmp_path / "report.pdf"
        test_file.write_text("test")
        root = tmp_path / "para_root"

        strategy = MappingStrategy(use_type_folders=True, type_mapping={".pdf": "Documents"})
        mapper = CategoryFolderMapper(config, strategy=strategy)
        result = mapper.map_file(test_file, root, use_rules=False)

        assert result.subfolder_path == "Documents"
        assert "Documents" in str(result.target_folder)

    def test_map_batch_handles_exception(self, config: PARAConfig, tmp_path: Path) -> None:
        """map_batch creates error result when map_file raises (lines 168-178)."""
        test_file = tmp_path / "bad.txt"
        test_file.write_text("test")
        root = tmp_path / "para_root"

        # Mock heuristic engine to raise
        heuristic_engine = MagicMock()
        heuristic_engine.evaluate.side_effect = RuntimeError("heuristic failure")

        mapper = CategoryFolderMapper(config, heuristic_engine=heuristic_engine)
        results = mapper.map_batch([test_file], root, use_rules=False)

        assert len(results) == 1
        assert results[0].target_category == PARACategory.RESOURCE
        assert results[0].confidence == 0.0
        assert "Error during mapping" in results[0].reasoning[0]

    def test_evaluate_rules_success(self, config: PARAConfig, tmp_path: Path) -> None:
        """_evaluate_rules returns result when successful (line 199)."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test")

        rule_engine = MagicMock()
        mock_result = MagicMock()
        mock_result.category = "project"
        rule_engine.evaluate_file.return_value = mock_result

        mapper = CategoryFolderMapper(config, rule_engine=rule_engine)
        result = mapper._evaluate_rules(test_file)

        assert result is not None
        assert result.category == "project"

    def test_custom_subfolder_fn_success(self, config: PARAConfig, tmp_path: Path) -> None:
        """Custom subfolder fn returns value (line 241)."""

        def custom_fn(fp: Path, cat: PARACategory) -> str | None:
            return "custom_folder"

        strategy = MappingStrategy(custom_subfolder_fn=custom_fn)
        mapper = CategoryFolderMapper(config, strategy=strategy)
        result = mapper._determine_subfolder(tmp_path / "file.txt", PARACategory.PROJECT)

        assert result == "custom_folder"

    def test_determine_subfolder_with_date(self, config: PARAConfig, tmp_path: Path) -> None:
        """_determine_subfolder uses date folders (lines 248-251)."""
        test_file = tmp_path / "dated.txt"
        test_file.write_text("test")

        strategy = MappingStrategy(use_date_folders=True, date_format="%Y/%m")
        mapper = CategoryFolderMapper(config, strategy=strategy)
        result = mapper._determine_subfolder(test_file, PARACategory.PROJECT)

        assert result is not None
        assert "/" in result  # Should have year/month format

    def test_determine_subfolder_with_type(self, config: PARAConfig, tmp_path: Path) -> None:
        """_determine_subfolder uses type folders (lines 254-257)."""
        test_file = tmp_path / "doc.pdf"
        test_file.write_text("test")

        strategy = MappingStrategy(use_type_folders=True, type_mapping={".pdf": "PDFs"})
        mapper = CategoryFolderMapper(config, strategy=strategy)
        result = mapper._determine_subfolder(test_file, PARACategory.RESOURCE)

        assert result == "PDFs"

    def test_determine_subfolder_with_keyword(self, config: PARAConfig, tmp_path: Path) -> None:
        """_determine_subfolder uses keyword folders (lines 260-263)."""
        test_file = tmp_path / "budget_report.txt"
        test_file.write_text("test")

        strategy = MappingStrategy(use_keyword_folders=True, keyword_mapping={"budget": "Finance"})
        mapper = CategoryFolderMapper(config, strategy=strategy)
        result = mapper._determine_subfolder(test_file, PARACategory.RESOURCE)

        assert result == "Finance"

    def test_determine_subfolder_combined(self, config: PARAConfig, tmp_path: Path) -> None:
        """_determine_subfolder combines multiple parts (line 267)."""
        test_file = tmp_path / "budget_report.pdf"
        test_file.write_text("test")

        strategy = MappingStrategy(
            use_type_folders=True,
            type_mapping={".pdf": "PDFs"},
            use_keyword_folders=True,
            keyword_mapping={"budget": "Finance"},
        )
        mapper = CategoryFolderMapper(config, strategy=strategy)
        result = mapper._determine_subfolder(test_file, PARACategory.RESOURCE)

        assert result is not None
        assert "/" in result
        parts = result.split("/")
        assert len(parts) == 2
        assert "PDFs" in parts
        assert "Finance" in parts

    def test_get_date_folder_success(self, config: PARAConfig, tmp_path: Path) -> None:
        """_get_date_folder returns formatted date (lines 280-285)."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test")

        strategy = MappingStrategy(date_format="%Y/%m")
        mapper = CategoryFolderMapper(config, strategy=strategy)
        result = mapper._get_date_folder(test_file)

        assert result is not None
        assert len(result) == 7  # YYYY/MM format
        assert result[4] == "/"

    def test_get_date_folder_nonexistent_file(self, config: PARAConfig) -> None:
        """_get_date_folder handles stat error (lines 286-288)."""
        mapper = CategoryFolderMapper(config)
        result = mapper._get_date_folder(Path("/nonexistent/file.txt"))
        assert result is None

    def test_match_keyword_folder_success(self, config: PARAConfig) -> None:
        """_match_keyword_folder returns folder when keyword matches (line 307)."""
        strategy = MappingStrategy(use_keyword_folders=True, keyword_mapping={"invoice": "Billing"})
        mapper = CategoryFolderMapper(config, strategy=strategy)
        result = mapper._match_keyword_folder(Path("/path/to/invoice_2024.pdf"))

        assert result == "Billing"

    def test_create_target_folders_dry_run(self, config: PARAConfig, tmp_path: Path) -> None:
        """create_target_folders dry run mode (lines 327-329)."""
        mapper = CategoryFolderMapper(config)
        target_folder = tmp_path / "new_folder"
        results = [
            MappingResult(
                source_path=tmp_path / "file.txt",
                target_category=PARACategory.PROJECT,
                target_folder=target_folder,
                confidence=0.8,
                reasoning=["test"],
            )
        ]

        status = mapper.create_target_folders(results, dry_run=True)

        assert status[target_folder] is True
        assert not target_folder.exists()  # Should not actually create

    def test_create_target_folders_success(self, config: PARAConfig, tmp_path: Path) -> None:
        """create_target_folders creates folders successfully (lines 332-334)."""
        mapper = CategoryFolderMapper(config)
        target_folder = tmp_path / "success_folder"
        results = [
            MappingResult(
                source_path=tmp_path / "file.txt",
                target_category=PARACategory.PROJECT,
                target_folder=target_folder,
                confidence=0.8,
                reasoning=["test"],
            )
        ]

        status = mapper.create_target_folders(results, dry_run=False)

        assert status[target_folder] is True
        assert target_folder.exists()

    def test_generate_mapping_report_with_reasoning(self, config: PARAConfig) -> None:
        """generate_mapping_report includes reasoning (lines 374-375)."""
        mapper = CategoryFolderMapper(config)
        results = [
            MappingResult(
                source_path=Path("/src/test.txt"),
                target_category=PARACategory.PROJECT,
                target_folder=Path("/dst/Projects"),
                confidence=0.85,
                reasoning=["Contains project keywords", "High priority"],
            )
        ]

        report = mapper.generate_mapping_report(results)

        assert "Reason: Contains project keywords" in report
        assert "Confidence: 85%" in report

    def test_map_file_rule_result_with_none_category(
        self, config: PARAConfig, tmp_path: Path
    ) -> None:
        """map_file doesn't override when rule result has None category (line 119->125)."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test")
        root = tmp_path / "para_root"

        # Create rule engine that returns result with None category
        rule_engine = MagicMock()
        rule_result = MagicMock()
        rule_result.category = None  # None category should not override
        rule_result.confidence = 0.8
        rule_engine.evaluate_file.return_value = rule_result

        # Mock heuristic to return a specific category
        heuristic_engine = MagicMock()
        mock_heuristic_result = MagicMock()
        mock_heuristic_result.recommended_category = PARACategory.AREA
        mock_heuristic_result.overall_confidence = 0.7
        mock_heuristic_result.scores = {}
        heuristic_engine.evaluate.return_value = mock_heuristic_result

        mapper = CategoryFolderMapper(
            config, heuristic_engine=heuristic_engine, rule_engine=rule_engine
        )
        result = mapper.map_file(test_file, root, use_rules=True)

        # Should keep heuristic category since rule category is None
        assert result.target_category == PARACategory.AREA

    def test_map_batch_success(self, config: PARAConfig, tmp_path: Path) -> None:
        """map_batch successfully processes files (line 167)."""
        test_file1 = tmp_path / "file1.txt"
        test_file1.write_text("test1")
        test_file2 = tmp_path / "file2.txt"
        test_file2.write_text("test2")
        root = tmp_path / "para_root"

        heuristic_engine = MagicMock()
        heuristic_result = MagicMock()
        heuristic_result.recommended_category = PARACategory.PROJECT
        heuristic_result.overall_confidence = 0.8
        heuristic_result.scores = {}
        heuristic_engine.evaluate.return_value = heuristic_result

        mapper = CategoryFolderMapper(config, heuristic_engine=heuristic_engine)
        results = mapper.map_batch([test_file1, test_file2], root, use_rules=False)

        assert len(results) == 2
        assert results[0].source_path == test_file1
        assert results[1].source_path == test_file2
        assert all(result.confidence == 0.8 for result in results)
        assert all(
            not result.reasoning or not result.reasoning[0].startswith("Error during mapping")
            for result in results
        )

    def test_extract_reasoning_category_not_in_scores(self, config: PARAConfig) -> None:
        """_extract_reasoning returns empty when category not in scores (line 222->226)."""
        mapper = CategoryFolderMapper(config)
        mock_result = MagicMock()
        mock_result.scores = {PARACategory.PROJECT: MagicMock()}  # Different category
        reasoning = mapper._extract_reasoning(mock_result, PARACategory.AREA)
        assert reasoning == []

    def test_determine_subfolder_date_disabled(self, config: PARAConfig, tmp_path: Path) -> None:
        """_determine_subfolder skips date when disabled (line 250->254)."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test")

        strategy = MappingStrategy(use_date_folders=False)
        mapper = CategoryFolderMapper(config, strategy=strategy)
        result = mapper._determine_subfolder(test_file, PARACategory.PROJECT)

        assert result is None

    def test_determine_subfolder_type_disabled(self, config: PARAConfig, tmp_path: Path) -> None:
        """_determine_subfolder skips type when disabled (line 256->260)."""
        test_file = tmp_path / "doc.pdf"
        test_file.write_text("test")

        strategy = MappingStrategy(use_type_folders=False)
        mapper = CategoryFolderMapper(config, strategy=strategy)
        result = mapper._determine_subfolder(test_file, PARACategory.PROJECT)

        assert result is None

    def test_determine_subfolder_keyword_disabled(self, config: PARAConfig, tmp_path: Path) -> None:
        """_determine_subfolder skips keyword when disabled (line 262->266)."""
        test_file = tmp_path / "budget.txt"
        test_file.write_text("test")

        strategy = MappingStrategy(use_keyword_folders=False)
        mapper = CategoryFolderMapper(config, strategy=strategy)
        result = mapper._determine_subfolder(test_file, PARACategory.PROJECT)

        assert result is None

    def test_generate_mapping_report_without_reasoning(self, config: PARAConfig) -> None:
        """generate_mapping_report handles empty reasoning (line 374->376)."""
        mapper = CategoryFolderMapper(config)
        results = [
            MappingResult(
                source_path=Path("/src/test.txt"),
                target_category=PARACategory.PROJECT,
                target_folder=Path("/dst/Projects"),
                confidence=0.85,
                reasoning=[],  # Empty reasoning
            )
        ]

        report = mapper.generate_mapping_report(results)

        # Should not include a "Reason:" line
        assert "Reason:" not in report
        assert "Confidence: 85%" in report

    def test_determine_subfolder_date_returns_none(self, config: PARAConfig) -> None:
        """_determine_subfolder when date is None (line 250->254)."""
        strategy = MappingStrategy(use_date_folders=True)
        mapper = CategoryFolderMapper(config, strategy=strategy)

        # Use nonexistent file so _get_date_folder returns None
        result = mapper._determine_subfolder(Path("/nonexistent/file.txt"), PARACategory.PROJECT)

        assert result is None

    def test_determine_subfolder_type_not_in_mapping(
        self, config: PARAConfig, tmp_path: Path
    ) -> None:
        """_determine_subfolder when extension not in type_mapping (line 256->260)."""
        test_file = tmp_path / "doc.xyz"  # Extension not in mapping
        test_file.write_text("test")

        strategy = MappingStrategy(use_type_folders=True, type_mapping={".pdf": "PDFs"})
        mapper = CategoryFolderMapper(config, strategy=strategy)
        result = mapper._determine_subfolder(test_file, PARACategory.PROJECT)

        assert result is None

    def test_determine_subfolder_keyword_no_match_returns_none(
        self, config: PARAConfig, tmp_path: Path
    ) -> None:
        """_determine_subfolder when keyword doesn't match (line 262->266)."""
        test_file = tmp_path / "random_file.txt"
        test_file.write_text("test")

        strategy = MappingStrategy(use_keyword_folders=True, keyword_mapping={"invoice": "Billing"})
        mapper = CategoryFolderMapper(config, strategy=strategy)
        result = mapper._determine_subfolder(test_file, PARACategory.PROJECT)

        assert result is None
