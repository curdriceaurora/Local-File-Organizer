"""Tests for text processor LLM tag generation (#1760)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.models.base import ModelType, StructuredParseError
from file_organizer.services.text_processor import ProcessedFile, TextAnalysisSchema, TextProcessor

pytestmark = [pytest.mark.unit, pytest.mark.ci]


@pytest.fixture
def mock_text_model() -> MagicMock:
    model = MagicMock()
    model.config.model_type = ModelType.TEXT
    model.is_initialized = True
    model.generate.return_value = "This is a summary of the text content."
    return model


@pytest.fixture
def processor(mock_text_model: MagicMock) -> TextProcessor:
    proc = TextProcessor(text_model=mock_text_model)
    proc.text_model = mock_text_model
    return proc


def test_tagging_disabled_does_not_call_structured(
    processor: TextProcessor, mock_text_model: MagicMock, tmp_path: Path
) -> None:
    test_file = tmp_path / "notes.txt"
    test_file.write_text("Meeting notes from Monday morning design sync.", encoding="utf-8")

    result = processor.process_file(
        test_file,
        generate_tags=False,
        generate_folder=False,
        generate_filename=False,
    )

    assert isinstance(result, ProcessedFile)
    assert result.tags == []
    mock_text_model.generate.assert_called_once()
    assert (
        not hasattr(mock_text_model, "generate_structured")
        or mock_text_model.generate_structured.call_count == 0
    )


def test_tagging_enabled_calls_structured_with_schema(
    processor: TextProcessor, mock_text_model: MagicMock, tmp_path: Path
) -> None:
    test_file = tmp_path / "project.txt"
    test_file.write_text("Quarterly roadmap and architecture planning document.", encoding="utf-8")

    fake_schema_result = TextAnalysisSchema(
        description="Summary: Roadmap and architecture design overview.",
        tags=["Roadmap", "Architecture", "planning-doc", "Q3"],
    )
    mock_text_model.generate_structured = MagicMock(return_value=fake_schema_result)

    result = processor.process_file(
        test_file,
        generate_tags=True,
        tag_style="code",
        tag_prompt="focus on dev deliverables",
    )

    mock_text_model.generate_structured.assert_called_once()
    (prompt_arg,) = mock_text_model.generate_structured.call_args[0]
    schema_kwarg = mock_text_model.generate_structured.call_args[1]["schema"]

    assert schema_kwarg is TextAnalysisSchema
    assert not prompt_arg.strip().endswith("SUMMARY:")
    assert "code" in prompt_arg
    assert "focus on dev deliverables" in prompt_arg
    assert result.description == "Roadmap and architecture design overview."
    assert "roadmap" in result.tags
    assert "architecture" in result.tags


def test_tagging_enabled_with_generate_description_false(
    processor: TextProcessor, mock_text_model: MagicMock, tmp_path: Path
) -> None:
    test_file = tmp_path / "data.txt"
    test_file.write_text(
        "Database schema migration logs and performance metrics.", encoding="utf-8"
    )

    fake_schema_result = TextAnalysisSchema(
        description="Database migrations summary.",
        tags=["database", "migration", "sql"],
    )
    mock_text_model.generate_structured = MagicMock(return_value=fake_schema_result)

    with patch.object(processor, "_generate_description") as mock_gen_desc:
        result = processor.process_file(
            test_file,
            generate_description=False,
            generate_tags=True,
        )
        mock_gen_desc.assert_not_called()

    assert result.description == ""
    assert result.tags == ["database", "migration", "sql"]


def test_structured_failure_with_generate_description_true_falls_back(
    processor: TextProcessor, mock_text_model: MagicMock, tmp_path: Path
) -> None:
    test_file = tmp_path / "report.txt"
    test_file.write_text("Financial audit report with detailed breakdowns.", encoding="utf-8")

    mock_text_model.generate_structured = MagicMock(
        side_effect=StructuredParseError("Invalid JSON")
    )

    with patch.object(
        processor, "_generate_description", return_value="Fallback financial summary."
    ) as mock_fallback:
        result = processor.process_file(
            test_file,
            generate_description=True,
            generate_tags=True,
        )
        mock_fallback.assert_called_once()

    assert result.description == "Fallback financial summary."
    assert result.tags == []


def test_structured_failure_with_generate_description_false_skips_fallback(
    processor: TextProcessor, mock_text_model: MagicMock, tmp_path: Path
) -> None:
    test_file = tmp_path / "doc.txt"
    test_file.write_text("Some plain documentation content.", encoding="utf-8")

    mock_text_model.generate_structured = MagicMock(
        side_effect=StructuredParseError("Invalid JSON")
    )

    with patch.object(processor, "_generate_description") as mock_fallback:
        result = processor.process_file(
            test_file,
            generate_description=False,
            generate_tags=True,
        )
        mock_fallback.assert_not_called()

    assert result.description == ""
    assert result.tags == []


def test_tagging_with_comma_separated_string_tags(
    processor: TextProcessor, mock_text_model: MagicMock, tmp_path: Path
) -> None:
    test_file = tmp_path / "article.txt"
    test_file.write_text("Article about machine learning algorithms.", encoding="utf-8")

    # Some models return string instead of list
    fake_schema_result = MagicMock()
    fake_schema_result.description = "Here is the summary: ML algorithms overview."
    fake_schema_result.tags = "machine-learning, python, AI"
    mock_text_model.generate_structured = MagicMock(return_value=fake_schema_result)

    result = processor.process_file(test_file, generate_tags=True)

    assert result.description == "ML algorithms overview."
    assert "machine-learning" in result.tags
    assert "python" in result.tags
    assert "ai" in result.tags
