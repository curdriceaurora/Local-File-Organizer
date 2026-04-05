"""Integration tests for CategoryFolderMapper.

Covers:
  - CategoryFolderMapper.__init__
  - map_file — real file, returns MappingResult
  - map_batch — multiple files, returns list of MappingResults
  - _determine_subfolder — date, type, keyword, custom function strategies
  - _get_date_folder — date-based subfolder string
  - _match_keyword_folder — keyword match in filename
  - create_target_folders — folders physically created; dry_run skips creation
  - generate_mapping_report — non-empty string output
  - _evaluate_rules — with and without rule engine
  - MappingResult fields: source_path, target_category, target_folder, confidence, reasoning
"""

from __future__ import annotations

from pathlib import Path

import pytest

from file_organizer.methodologies.para.categories import PARACategory
from file_organizer.methodologies.para.config import PARAConfig
from file_organizer.methodologies.para.folder_mapper import (
    CategoryFolderMapper,
    MappingResult,
    MappingStrategy,
)

pytestmark = [pytest.mark.integration, pytest.mark.ci]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mapper(
    tmp_path: Path,
    strategy: MappingStrategy | None = None,
) -> CategoryFolderMapper:
    """Create a CategoryFolderMapper with AI heuristics disabled."""
    config = PARAConfig(
        enable_temporal_heuristic=True,
        enable_content_heuristic=False,
        enable_structural_heuristic=True,
        enable_ai_heuristic=False,
    )
    return CategoryFolderMapper(config=config, strategy=strategy)


def _real_file(tmp_path: Path, name: str, content: str = "content") -> Path:
    """Create a real file in tmp_path and return its path."""
    p = tmp_path / name
    p.write_text(content)
    return p


# ---------------------------------------------------------------------------
# TestCategoryFolderMapperInit
# ---------------------------------------------------------------------------


class TestCategoryFolderMapperInit:
    """Tests for CategoryFolderMapper construction."""

    def test_init_with_defaults(self, tmp_path: Path) -> None:
        """Mapper can be constructed without explicit arguments."""
        mapper = CategoryFolderMapper()
        assert mapper.config is not None
        assert mapper.heuristic_engine is not None
        assert mapper.folder_generator is not None
        assert mapper.strategy is not None

    def test_init_accepts_custom_config(self, tmp_path: Path) -> None:
        """Custom PARAConfig is stored on the mapper."""
        config = PARAConfig(project_dir="MyProjects")
        mapper = CategoryFolderMapper(config=config)
        assert mapper.config.project_dir == "MyProjects"

    def test_init_accepts_custom_strategy(self, tmp_path: Path) -> None:
        """Custom MappingStrategy is stored on the mapper."""
        strategy = MappingStrategy(use_date_folders=True, date_format="%Y-%m")
        mapper = _make_mapper(tmp_path, strategy=strategy)
        assert mapper.strategy.use_date_folders is True
        assert mapper.strategy.date_format == "%Y-%m"

    def test_rule_engine_defaults_to_none(self, tmp_path: Path) -> None:
        """rule_engine is None when not provided."""
        mapper = _make_mapper(tmp_path)
        assert mapper.rule_engine is None


# ---------------------------------------------------------------------------
# TestMapFile
# ---------------------------------------------------------------------------


class TestMapFile:
    """Tests for map_file."""

    def test_returns_mapping_result(self, tmp_path: Path) -> None:
        """map_file returns a MappingResult instance."""
        file_path = _real_file(tmp_path, "notes.txt", "some notes content")
        mapper = _make_mapper(tmp_path)
        result = mapper.map_file(file_path, tmp_path / "para")

        assert isinstance(result, MappingResult)

    def test_source_path_matches_input(self, tmp_path: Path) -> None:
        """MappingResult.source_path equals the input file path."""
        file_path = _real_file(tmp_path, "doc.txt")
        mapper = _make_mapper(tmp_path)
        result = mapper.map_file(file_path, tmp_path / "para")

        assert result.source_path == file_path

    def test_target_category_is_para_category(self, tmp_path: Path) -> None:
        """MappingResult.target_category is a valid PARACategory value."""
        file_path = _real_file(tmp_path, "report.txt")
        mapper = _make_mapper(tmp_path)
        result = mapper.map_file(file_path, tmp_path / "para")

        assert isinstance(result.target_category, PARACategory)
        assert result.target_category in list(PARACategory)

    def test_confidence_in_valid_range(self, tmp_path: Path) -> None:
        """MappingResult.confidence is between 0.0 and 1.0 inclusive."""
        file_path = _real_file(tmp_path, "data.txt")
        mapper = _make_mapper(tmp_path)
        result = mapper.map_file(file_path, tmp_path / "para")

        assert 0.0 <= result.confidence <= 1.0

    def test_target_folder_is_path(self, tmp_path: Path) -> None:
        """MappingResult.target_folder is a Path instance."""
        file_path = _real_file(tmp_path, "item.txt")
        root = tmp_path / "para"
        mapper = _make_mapper(tmp_path)
        result = mapper.map_file(file_path, root)

        assert isinstance(result.target_folder, Path)

    def test_target_folder_is_under_root(self, tmp_path: Path) -> None:
        """target_folder is a subdirectory of the given root_path."""
        file_path = _real_file(tmp_path, "item.md")
        root = tmp_path / "para"
        mapper = _make_mapper(tmp_path)
        result = mapper.map_file(file_path, root)

        assert str(result.target_folder).startswith(str(root))

    def test_reasoning_is_list(self, tmp_path: Path) -> None:
        """MappingResult.reasoning is a list (may be empty)."""
        file_path = _real_file(tmp_path, "thing.txt")
        mapper = _make_mapper(tmp_path)
        result = mapper.map_file(file_path, tmp_path / "para")

        # reasoning is always a list (may be empty for a new file with no learned patterns)
        assert isinstance(result.reasoning, list)
        assert result.target_folder is not None  # mapping always returns a target

    def test_no_category_defaults_to_resource(self, tmp_path: Path) -> None:
        """A file with no keyword signals defaults to Resource category."""
        # Use a neutral filename with no PARA keyword indicators
        file_path = _real_file(tmp_path, "zzz_generic_xyz_file.txt", "aaa bbb ccc")
        mapper = _make_mapper(tmp_path)
        result = mapper.map_file(file_path, tmp_path / "para", use_rules=False)

        # Neutral input should default to PARACategory.RESOURCE
        assert result.target_category == PARACategory.RESOURCE


# ---------------------------------------------------------------------------
# TestMapBatch
# ---------------------------------------------------------------------------


class TestMapBatch:
    """Tests for map_batch."""

    def test_returns_list_of_results(self, tmp_path: Path) -> None:
        """map_batch returns a list with one MappingResult per file."""
        files = [
            _real_file(tmp_path, "a.txt", "alpha"),
            _real_file(tmp_path, "b.txt", "beta"),
            _real_file(tmp_path, "c.md", "gamma"),
        ]
        mapper = _make_mapper(tmp_path)
        results = mapper.map_batch(files, tmp_path / "para")

        assert len(results) == 3
        for r in results:
            assert isinstance(r, MappingResult)

    def test_empty_list_returns_empty(self, tmp_path: Path) -> None:
        """map_batch on empty file list returns empty list."""
        mapper = _make_mapper(tmp_path)
        results = mapper.map_batch([], tmp_path / "para")

        assert results == []

    def test_each_result_has_matching_source(self, tmp_path: Path) -> None:
        """Each MappingResult.source_path matches its corresponding input file."""
        files = [
            _real_file(tmp_path, "first.txt", "first"),
            _real_file(tmp_path, "second.txt", "second"),
        ]
        mapper = _make_mapper(tmp_path)
        results = mapper.map_batch(files, tmp_path / "para")

        result_sources = {r.source_path for r in results}
        assert set(files) == result_sources

    def test_batch_all_confidences_valid(self, tmp_path: Path) -> None:
        """All results from map_batch have confidence in [0.0, 1.0]."""
        files = [_real_file(tmp_path, f"file_{i}.txt", f"content {i}") for i in range(5)]
        mapper = _make_mapper(tmp_path)
        results = mapper.map_batch(files, tmp_path / "para")

        for r in results:
            assert 0.0 <= r.confidence <= 1.0, f"Confidence out of range: {r.confidence}"


# ---------------------------------------------------------------------------
# TestDetermineSubfolder
# ---------------------------------------------------------------------------


class TestDetermineSubfolder:
    """Tests for _determine_subfolder strategy dispatch."""

    def test_no_strategy_returns_none(self, tmp_path: Path) -> None:
        """Default strategy with no options enabled returns None."""
        file_path = _real_file(tmp_path, "plain.txt")
        mapper = _make_mapper(tmp_path, strategy=MappingStrategy())
        result = mapper._determine_subfolder(file_path, PARACategory.RESOURCE)

        assert result is None

    def test_date_strategy_returns_string(self, tmp_path: Path) -> None:
        """use_date_folders=True returns a non-None string subfolder."""
        file_path = _real_file(tmp_path, "dated.txt")
        strategy = MappingStrategy(use_date_folders=True, date_format="%Y/%m")
        mapper = _make_mapper(tmp_path, strategy=strategy)
        result = mapper._determine_subfolder(file_path, PARACategory.RESOURCE)

        assert result is not None
        assert "/" in result  # e.g. "2026/04"

    def test_type_strategy_maps_extension(self, tmp_path: Path) -> None:
        """use_type_folders=True maps .pdf to the configured subfolder name."""
        pdf_file = _real_file(tmp_path, "document.pdf", "PDF content")
        strategy = MappingStrategy(
            use_type_folders=True,
            type_mapping={".pdf": "PDFs", ".txt": "Texts"},
        )
        mapper = _make_mapper(tmp_path, strategy=strategy)
        result = mapper._determine_subfolder(pdf_file, PARACategory.RESOURCE)

        assert result == "PDFs"

    def test_type_strategy_unknown_extension_returns_none(self, tmp_path: Path) -> None:
        """Unknown extension with use_type_folders=True returns None."""
        file_path = _real_file(tmp_path, "image.png")
        strategy = MappingStrategy(
            use_type_folders=True,
            type_mapping={".pdf": "PDFs"},
        )
        mapper = _make_mapper(tmp_path, strategy=strategy)
        result = mapper._determine_subfolder(file_path, PARACategory.RESOURCE)

        assert result is None

    def test_keyword_strategy_matches_keyword(self, tmp_path: Path) -> None:
        """use_keyword_folders=True returns folder when keyword appears in filename."""
        file_path = _real_file(tmp_path, "budget_2026.txt")
        strategy = MappingStrategy(
            use_keyword_folders=True,
            keyword_mapping={"budget": "Finance", "meeting": "Meetings"},
        )
        mapper = _make_mapper(tmp_path, strategy=strategy)
        result = mapper._determine_subfolder(file_path, PARACategory.AREA)

        assert result == "Finance"

    def test_keyword_strategy_no_match_returns_none(self, tmp_path: Path) -> None:
        """File with no matching keyword returns None from keyword strategy."""
        file_path = _real_file(tmp_path, "random_xyz_file.txt")
        strategy = MappingStrategy(
            use_keyword_folders=True,
            keyword_mapping={"budget": "Finance"},
        )
        mapper = _make_mapper(tmp_path, strategy=strategy)
        result = mapper._determine_subfolder(file_path, PARACategory.AREA)

        assert result is None

    def test_custom_subfolder_function_takes_precedence(self, tmp_path: Path) -> None:
        """custom_subfolder_fn overrides all other strategies."""
        file_path = _real_file(tmp_path, "any.txt")

        def my_fn(path: Path, cat: PARACategory) -> str | None:
            return "CustomFolder"

        strategy = MappingStrategy(
            use_date_folders=True,
            use_type_folders=True,
            type_mapping={".txt": "Texts"},
            custom_subfolder_fn=my_fn,
        )
        mapper = _make_mapper(tmp_path, strategy=strategy)
        result = mapper._determine_subfolder(file_path, PARACategory.RESOURCE)

        assert result == "CustomFolder"

    def test_combined_date_and_type_strategy(self, tmp_path: Path) -> None:
        """Combining date and type strategies joins parts with '/'."""
        file_path = _real_file(tmp_path, "report.pdf")
        strategy = MappingStrategy(
            use_date_folders=True,
            date_format="%Y",
            use_type_folders=True,
            type_mapping={".pdf": "PDFs"},
        )
        mapper = _make_mapper(tmp_path, strategy=strategy)
        result = mapper._determine_subfolder(file_path, PARACategory.RESOURCE)

        assert result is not None
        parts = result.split("/")
        assert "PDFs" in parts
        # Year component is 4-digit numeric
        assert any(p.isdigit() and len(p) == 4 for p in parts)


# ---------------------------------------------------------------------------
# TestGetDateFolder
# ---------------------------------------------------------------------------


class TestGetDateFolder:
    """Tests for _get_date_folder."""

    def test_returns_formatted_date_string(self, tmp_path: Path) -> None:
        """_get_date_folder returns a non-None string from a real file's mtime."""
        file_path = _real_file(tmp_path, "dated.txt")
        strategy = MappingStrategy(date_format="%Y/%m")
        mapper = _make_mapper(tmp_path, strategy=strategy)
        result = mapper._get_date_folder(file_path)

        assert result is not None
        assert "/" in result

    def test_custom_date_format_respected(self, tmp_path: Path) -> None:
        """_get_date_folder uses the date_format from the strategy."""
        file_path = _real_file(tmp_path, "ts_file.txt")
        strategy = MappingStrategy(date_format="%Y-%m-%d")
        mapper = _make_mapper(tmp_path, strategy=strategy)
        result = mapper._get_date_folder(file_path)

        assert result is not None
        # Should match YYYY-MM-DD pattern
        parts = result.split("-")
        assert len(parts) == 3
        assert len(parts[0]) == 4  # 4-digit year


# ---------------------------------------------------------------------------
# TestMatchKeywordFolder
# ---------------------------------------------------------------------------


class TestMatchKeywordFolder:
    """Tests for _match_keyword_folder."""

    def test_matching_keyword_returns_folder_name(self, tmp_path: Path) -> None:
        """A filename containing exactly one mapped keyword returns that folder name."""
        # Use non-overlapping keyword so only "Projects" can match
        file_path = _real_file(tmp_path, "project_alpha_meeting.txt")
        strategy = MappingStrategy(
            use_keyword_folders=True,
            keyword_mapping={"project": "Projects", "invoice": "Finance"},
        )
        mapper = _make_mapper(tmp_path, strategy=strategy)
        result = mapper._match_keyword_folder(file_path)

        assert result == "Projects"

    def test_no_matching_keyword_returns_none(self, tmp_path: Path) -> None:
        """File with no matching keyword returns None."""
        file_path = _real_file(tmp_path, "unrelated_xyz.txt")
        strategy = MappingStrategy(
            use_keyword_folders=True,
            keyword_mapping={"budget": "Finance"},
        )
        mapper = _make_mapper(tmp_path, strategy=strategy)
        result = mapper._match_keyword_folder(file_path)

        assert result is None

    def test_case_insensitive_match(self, tmp_path: Path) -> None:
        """Keyword matching is case-insensitive."""
        file_path = _real_file(tmp_path, "BUDGET_REVIEW.txt")
        strategy = MappingStrategy(
            use_keyword_folders=True,
            keyword_mapping={"budget": "Finance"},
        )
        mapper = _make_mapper(tmp_path, strategy=strategy)
        result = mapper._match_keyword_folder(file_path)

        assert result == "Finance"

    def test_no_keyword_mapping_returns_none(self, tmp_path: Path) -> None:
        """_match_keyword_folder returns None when keyword_mapping is None."""
        file_path = _real_file(tmp_path, "budget.txt")
        strategy = MappingStrategy(use_keyword_folders=True, keyword_mapping=None)
        mapper = _make_mapper(tmp_path, strategy=strategy)
        result = mapper._match_keyword_folder(file_path)

        assert result is None


# ---------------------------------------------------------------------------
# TestCreateTargetFolders
# ---------------------------------------------------------------------------


class TestCreateTargetFolders:
    """Tests for create_target_folders."""

    def _make_results(self, root: Path, categories: list[PARACategory]) -> list[MappingResult]:
        """Build synthetic MappingResult objects with target_folders under root."""
        results = []
        for i, cat in enumerate(categories):
            results.append(
                MappingResult(
                    source_path=root / f"src_{i}.txt",
                    target_category=cat,
                    target_folder=root / "para" / cat.value / "subfolder",
                    confidence=0.75,
                    reasoning=[],
                )
            )
        return results

    def test_folders_created_on_disk(self, tmp_path: Path) -> None:
        """create_target_folders physically creates all unique target folders."""
        mapper = _make_mapper(tmp_path)
        results = self._make_results(
            tmp_path, [PARACategory.PROJECT, PARACategory.RESOURCE, PARACategory.AREA]
        )
        status = mapper.create_target_folders(results, dry_run=False)

        for folder, success in status.items():
            assert success is True
            assert folder.exists()

    def test_dry_run_skips_creation(self, tmp_path: Path) -> None:
        """create_target_folders with dry_run=True returns True but creates no dirs."""
        mapper = _make_mapper(tmp_path)
        results = self._make_results(tmp_path, [PARACategory.PROJECT])
        target_folder = results[0].target_folder
        status = mapper.create_target_folders(results, dry_run=True)

        assert list(status.values()) == [True]
        assert not target_folder.exists()

    def test_empty_results_returns_empty_dict(self, tmp_path: Path) -> None:
        """create_target_folders returns empty dict when results list is empty."""
        mapper = _make_mapper(tmp_path)
        status = mapper.create_target_folders([], dry_run=False)

        assert status == {}

    def test_duplicate_folders_created_once(self, tmp_path: Path) -> None:
        """Duplicate target folders across results are created exactly once."""
        mapper = _make_mapper(tmp_path)
        shared_folder = tmp_path / "para" / "shared_dir"
        results = [
            MappingResult(
                source_path=tmp_path / "a.txt",
                target_category=PARACategory.RESOURCE,
                target_folder=shared_folder,
                confidence=0.8,
                reasoning=[],
            ),
            MappingResult(
                source_path=tmp_path / "b.txt",
                target_category=PARACategory.RESOURCE,
                target_folder=shared_folder,
                confidence=0.7,
                reasoning=[],
            ),
        ]
        status = mapper.create_target_folders(results, dry_run=False)

        # Only one unique folder
        assert len(status) == 1
        assert shared_folder.exists()


# ---------------------------------------------------------------------------
# TestGenerateMappingReport
# ---------------------------------------------------------------------------


class TestGenerateMappingReport:
    """Tests for generate_mapping_report."""

    def test_non_empty_string(self, tmp_path: Path) -> None:
        """generate_mapping_report returns a non-empty string."""
        files = [_real_file(tmp_path, f"f{i}.txt", f"content {i}") for i in range(3)]
        mapper = _make_mapper(tmp_path)
        results = mapper.map_batch(files, tmp_path / "para")
        report = mapper.generate_mapping_report(results)

        assert len(report) > 0

    def test_report_contains_total_count(self, tmp_path: Path) -> None:
        """Report string contains the total file count."""
        files = [_real_file(tmp_path, f"g{i}.txt") for i in range(4)]
        mapper = _make_mapper(tmp_path)
        results = mapper.map_batch(files, tmp_path / "para")
        report = mapper.generate_mapping_report(results)

        assert "Total files: 4" in report

    def test_report_contains_header(self, tmp_path: Path) -> None:
        """Report starts with the PARA Folder Mapping Report header."""
        files = [_real_file(tmp_path, "h.txt", "header test")]
        mapper = _make_mapper(tmp_path)
        results = mapper.map_batch(files, tmp_path / "para")
        report = mapper.generate_mapping_report(results)

        assert "PARA Folder Mapping Report" in report

    def test_empty_results_report(self, tmp_path: Path) -> None:
        """generate_mapping_report handles empty results list without error."""
        mapper = _make_mapper(tmp_path)
        report = mapper.generate_mapping_report([])

        assert "0" in report


# ---------------------------------------------------------------------------
# TestEvaluateRules
# ---------------------------------------------------------------------------


class TestEvaluateRules:
    """Tests for _evaluate_rules with and without a rule engine."""

    def test_without_rule_engine_returns_none(self, tmp_path: Path) -> None:
        """_evaluate_rules returns None when rule_engine is not set."""
        file_path = _real_file(tmp_path, "test.txt")
        mapper = _make_mapper(tmp_path)
        # rule_engine is None by default
        result = mapper._evaluate_rules(file_path)

        assert result is None

    def test_map_file_without_rules_does_not_crash(self, tmp_path: Path) -> None:
        """map_file with use_rules=False executes without error."""
        file_path = _real_file(tmp_path, "no_rules.txt", "plain text")
        mapper = _make_mapper(tmp_path)
        result = mapper.map_file(file_path, tmp_path / "para", use_rules=False)

        assert isinstance(result, MappingResult)
        assert result.source_path == file_path
