"""Tests for path and filename prompt enrichment and tag generation in TextProcessor (#66, #64).

Marked ci so branch coverage counts toward the diff-coverage gate.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.models.base import ModelType
from file_organizer.services.text_processor import ProcessedFile, TextProcessor

pytestmark = [pytest.mark.unit, pytest.mark.ci]


@pytest.fixture
def mock_text_model() -> MagicMock:
    model = MagicMock()
    model.config.model_type = ModelType.TEXT
    model.is_initialized = True
    model.generate.return_value = "Mocked AI Response"
    return model


@pytest.fixture
def text_processor(mock_text_model: MagicMock) -> TextProcessor:
    with patch("file_organizer.services.text_processor.ensure_nltk_data"):
        return TextProcessor(text_model=mock_text_model)


class TestPromptEnrichment:
    """Test that path context and filename are embedded in prompts."""

    def test_generate_description_embeds_filename_and_path(
        self, text_processor: TextProcessor, mock_text_model: MagicMock
    ) -> None:
        mock_text_model.generate.return_value = "A project specification document."
        desc = text_processor._generate_description(
            "Sample text content",
            file_name="spec_v2.md",
            relative_path="docs/specs/spec_v2.md",
        )
        assert desc == "A project specification document."
        call_args = mock_text_model.generate.call_args[0][0]
        assert "FILENAME: spec_v2.md" in call_args
        assert "PATH CONTEXT: docs/specs/spec_v2.md" in call_args

    def test_generate_folder_name_embeds_relative_path(
        self, text_processor: TextProcessor, mock_text_model: MagicMock
    ) -> None:
        mock_text_model.generate.return_value = "finance"
        folder = text_processor._generate_folder_name(
            "Quarterly revenue data",
            relative_path="invoices/2026/Q1_revenue.csv",
        )
        assert folder == "finance"
        call_args = mock_text_model.generate.call_args[0][0]
        assert "PATH & FILENAME HINT: invoices/2026/Q1_revenue.csv" in call_args

    def test_generate_filename_embeds_relative_path(
        self, text_processor: TextProcessor, mock_text_model: MagicMock
    ) -> None:
        mock_text_model.generate.return_value = "2026_q1_revenue"
        name = text_processor._generate_filename(
            "Quarterly revenue data",
            relative_path="invoices/2026/Q1_revenue.csv",
        )
        assert name == "2026_q1_revenue"
        call_args = mock_text_model.generate.call_args[0][0]
        assert "PATH & FILENAME HINT: invoices/2026/Q1_revenue.csv" in call_args

    def test_generate_tags_parses_comma_separated_tokens(
        self, text_processor: TextProcessor, mock_text_model: MagicMock
    ) -> None:
        mock_text_model.generate.return_value = "Finance, Quarterly-Report, 2026, Revenue, AI"
        tags = text_processor._generate_tags(
            "Quarterly financial revenue",
            file_name="report.pdf",
            relative_path="finance/report.pdf",
        )
        assert "finance" in tags
        assert "quarterly_report" in tags
        assert "2026" in tags
        assert "revenue" in tags
        assert "ai" in tags


class TestProcessFileWithEnrichment:
    """Test process_file handles relative_path, scan_root, and generate_tags."""

    def test_process_file_with_explicit_relative_path_and_tags(
        self, text_processor: TextProcessor, mock_text_model: MagicMock, tmp_path: Path
    ) -> None:
        file_path = tmp_path / "subdir" / "notes.txt"
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text("Detailed meeting notes about project roadmap.", encoding="utf-8")

        mock_text_model.generate.side_effect = [
            "Project roadmap notes",  # description
            "notes",  # folder
            "project_roadmap_notes",  # filename
            "planning, roadmap, notes",  # tags
        ]

        result = text_processor.process_file(
            file_path,
            relative_path="subdir/notes.txt",
            generate_tags=True,
        )

        assert isinstance(result, ProcessedFile)
        assert result.folder_name == "notes"
        assert result.filename == "project_roadmap_notes"
        assert result.tags == ["planning", "roadmap", "notes"]

    def test_process_file_derives_relative_path_from_scan_root(
        self, text_processor: TextProcessor, mock_text_model: MagicMock, tmp_path: Path
    ) -> None:
        scan_root = tmp_path / "root"
        file_path = scan_root / "nested" / "doc.txt"
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text("Content inside root", encoding="utf-8")

        mock_text_model.generate.side_effect = [
            "Content description",
            "docs",
            "renamed_doc",
        ]

        result = text_processor.process_file(
            file_path,
            scan_root=scan_root,
            generate_tags=False,
        )

        assert result.tags == []
        assert result.folder_name == "docs"

    def test_process_file_derives_name_when_path_outside_scan_root(
        self, text_processor: TextProcessor, mock_text_model: MagicMock, tmp_path: Path
    ) -> None:
        scan_root = tmp_path / "root"
        file_path = tmp_path / "other" / "external.txt"
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text("External file content", encoding="utf-8")

        mock_text_model.generate.side_effect = [
            "External description",
            "external_folder",
            "external_name",
        ]

        result = text_processor.process_file(file_path, scan_root=scan_root)
        assert result.folder_name == "external_folder"

    def test_generate_tags_handles_style_prompt_and_exception(
        self, text_processor: TextProcessor, mock_text_model: MagicMock
    ) -> None:
        mock_text_model.generate.side_effect = RuntimeError("Generation failed")
        tags = text_processor._generate_tags(
            "Some content",
            style="sfx",
            custom_prompt="focus on lasers",
        )
        assert tags == []
