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
