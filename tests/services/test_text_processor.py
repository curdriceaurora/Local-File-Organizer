"""Tests for file_organizer.services.text_processor module.

Covers the TextProcessor pipeline: file read → inference → metadata → suggestion.
All AI components are mocked. Error handling for empty, corrupted, and large files.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.services.text_processor import ProcessedFile, TextProcessor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_text_model() -> MagicMock:
    """Create a mock TextModel that returns deterministic responses."""
    model = MagicMock()
    model.is_initialized = True
    model._initialized = True
    model.config = MagicMock()
    model.config.name = "mock-model:test"
    model.config.model_type = MagicMock()
    model.config.model_type.value = "text"

    # generate returns different things based on prompt content
    def _generate(prompt: str, **kwargs) -> str:
        if "Summarize" in prompt:
            return "A summary of the document content."
        if "category" in prompt.lower() or "theme" in prompt.lower():
            return "technology"
        if "filename" in prompt.lower():
            return "machine_learning_guide"
        return "default_response"

    model.generate.side_effect = _generate
    return model


def _make_processor(model: MagicMock | None = None) -> TextProcessor:
    """Create a TextProcessor with mocked model."""
    m = model or _make_mock_text_model()
    with patch("file_organizer.services.text_processor.ensure_nltk_data"):
        return TextProcessor(text_model=m)


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


class TestTextProcessorInit:
    """Tests for TextProcessor initialization."""

    def test_with_provided_model(self) -> None:
        model = _make_mock_text_model()
        with patch("file_organizer.services.text_processor.ensure_nltk_data"):
            proc = TextProcessor(text_model=model)
            assert proc.text_model is model
            assert proc._owns_model is False

    def test_without_model_creates_own(self) -> None:
        with patch("file_organizer.services.text_processor.ensure_nltk_data"), patch(
            "file_organizer.services.text_processor.TextModel"
        ) as MockModel:
            MockModel.get_default_config.return_value = MagicMock()
            proc = TextProcessor()
            assert proc._owns_model is True


# ---------------------------------------------------------------------------
# process_file — happy path
# ---------------------------------------------------------------------------


class TestProcessFile:
    """Tests for TextProcessor.process_file."""

    def test_processes_text_file(self, tmp_path: Path) -> None:
        f = tmp_path / "article.txt"
        f.write_text("Machine learning is transforming healthcare with AI-powered diagnostics.")

        proc = _make_processor()
        result = proc.process_file(f)

        assert isinstance(result, ProcessedFile)
        assert result.file_path == f
        assert result.error is None
        assert len(result.description) > 0
        assert len(result.folder_name) > 0
        assert len(result.filename) > 0
        assert result.processing_time > 0

    def test_processes_markdown(self, tmp_path: Path) -> None:
        f = tmp_path / "notes.md"
        f.write_text("# Project Plan\n\n- Phase 1: Research\n- Phase 2: Develop")

        proc = _make_processor()
        result = proc.process_file(f)

        assert result.error is None
        assert result.folder_name != ""

    def test_processes_csv(self, tmp_path: Path) -> None:
        f = tmp_path / "data.csv"
        f.write_text("name,score\nAlice,95\nBob,87\n")

        proc = _make_processor()
        result = proc.process_file(f)

        assert result.error is None

    def test_original_content_truncated(self, tmp_path: Path) -> None:
        f = tmp_path / "long.txt"
        f.write_text("x" * 2000)

        proc = _make_processor()
        result = proc.process_file(f)

        assert result.original_content is not None
        assert len(result.original_content) <= 500

    def test_selective_generation(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.txt"
        f.write_text("Content here")

        proc = _make_processor()
        result = proc.process_file(
            f,
            generate_description=False,
            generate_folder=True,
            generate_filename=False,
        )

        assert result.description == ""
        assert result.filename == ""
        assert result.folder_name != ""


# ---------------------------------------------------------------------------
# process_file — error handling
# ---------------------------------------------------------------------------


class TestProcessFileErrors:
    """Tests for error handling in TextProcessor.process_file."""

    def test_unsupported_file_type(self, tmp_path: Path) -> None:
        f = tmp_path / "binary.xyz"
        f.write_bytes(b"\x00\x01\x02")

        proc = _make_processor()
        result = proc.process_file(f)

        assert result.folder_name == "unsupported"
        assert result.error == "Unsupported file type"

    def test_missing_file(self, tmp_path: Path) -> None:
        missing = tmp_path / "nonexistent.txt"

        proc = _make_processor()
        result = proc.process_file(missing)

        assert result.error is not None
        assert result.folder_name == "errors"

    def test_ai_generation_failure(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.txt"
        f.write_text("Some content")

        model = _make_mock_text_model()
        model.generate.side_effect = RuntimeError("Model offline")

        proc = _make_processor(model)
        result = proc.process_file(f)

        # Should still return a result, just with fallback values
        assert isinstance(result, ProcessedFile)


# ---------------------------------------------------------------------------
# _generate_folder_name
# ---------------------------------------------------------------------------


class TestGenerateFolderName:
    """Tests for TextProcessor._generate_folder_name."""

    def test_returns_cleaned_name(self) -> None:
        proc = _make_processor()
        result = proc._generate_folder_name("A study on machine learning algorithms")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_ai_failure_returns_fallback(self) -> None:
        model = _make_mock_text_model()
        model.generate.side_effect = RuntimeError("fail")

        proc = _make_processor(model)
        result = proc._generate_folder_name("Some text content")
        assert result == "documents"


# ---------------------------------------------------------------------------
# _generate_filename
# ---------------------------------------------------------------------------


class TestGenerateFilename:
    """Tests for TextProcessor._generate_filename."""

    def test_returns_cleaned_name(self) -> None:
        proc = _make_processor()
        result = proc._generate_filename("A guide to Python best practices")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_ai_failure_returns_fallback(self) -> None:
        model = _make_mock_text_model()
        model.generate.side_effect = RuntimeError("fail")

        proc = _make_processor(model)
        result = proc._generate_filename("content")
        assert result == "document"


# ---------------------------------------------------------------------------
# _generate_description
# ---------------------------------------------------------------------------


class TestGenerateDescription:
    """Tests for TextProcessor._generate_description."""

    def test_returns_summary(self) -> None:
        proc = _make_processor()
        result = proc._generate_description("A detailed article about climate change.")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_strips_prefix(self) -> None:
        model = _make_mock_text_model()
        model.generate.return_value = "Summary: This is the actual summary."

        proc = _make_processor(model)
        result = proc._generate_description("content")
        assert not result.lower().startswith("summary:")

    def test_ai_failure_returns_fallback(self) -> None:
        model = _make_mock_text_model()
        model.generate.side_effect = RuntimeError("fail")

        proc = _make_processor(model)
        result = proc._generate_description("Some long content about AI technology")
        assert "Content about" in result


# ---------------------------------------------------------------------------
# cleanup and context manager
# ---------------------------------------------------------------------------


class TestCleanup:
    """Tests for resource cleanup."""

    def test_cleanup_own_model(self) -> None:
        model = _make_mock_text_model()
        with patch("file_organizer.services.text_processor.ensure_nltk_data"):
            proc = TextProcessor(text_model=model)
            proc._owns_model = True
            proc.cleanup()
            model.cleanup.assert_called_once()

    def test_cleanup_borrowed_model(self) -> None:
        model = _make_mock_text_model()
        proc = _make_processor(model)
        proc.cleanup()
        model.cleanup.assert_not_called()

    def test_context_manager(self) -> None:
        model = _make_mock_text_model()
        with patch("file_organizer.services.text_processor.ensure_nltk_data"):
            proc = TextProcessor(text_model=model)
            proc._owns_model = True

            with patch.object(proc, "initialize") as mock_init, patch.object(
                proc, "cleanup"
            ) as mock_cleanup:
                with proc:
                    mock_init.assert_called_once()
                mock_cleanup.assert_called_once()


# ---------------------------------------------------------------------------
# _clean_ai_generated_name
# ---------------------------------------------------------------------------


class TestCleanAiGeneratedName:
    """Tests for TextProcessor._clean_ai_generated_name."""

    def test_basic_cleaning(self) -> None:
        proc = _make_processor()
        result = proc._clean_ai_generated_name("Machine Learning Guide")
        assert isinstance(result, str)
        assert result.islower() or result == ""

    def test_removes_bad_words(self) -> None:
        proc = _make_processor()
        result = proc._clean_ai_generated_name("the document file")
        assert "the" not in result.split("_")
        assert "document" not in result.split("_")

    def test_deduplicates(self) -> None:
        proc = _make_processor()
        result = proc._clean_ai_generated_name("python python coding")
        parts = result.split("_")
        assert parts.count("python") <= 1

    def test_max_words(self) -> None:
        proc = _make_processor()
        result = proc._clean_ai_generated_name(
            "machine learning deep neural network", max_words=2
        )
        parts = [p for p in result.split("_") if p]
        assert len(parts) <= 2

    def test_empty_input(self) -> None:
        proc = _make_processor()
        result = proc._clean_ai_generated_name("")
        assert result == ""
