"""Tests for TextProcessor service."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.models.base import ModelConfig, ModelType
from file_organizer.services.text_processor import ProcessedFile, TextProcessor
from file_organizer.utils.file_readers import FileReadError

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_text_model() -> MagicMock:
    """Mocked TextModel instance."""
    model = MagicMock()
    model.is_initialized = True
    # Default generate response to something predictable
    model.generate.return_value = "Mocked AI Response"
    return model


@pytest.fixture
def text_processor(mock_text_model: MagicMock) -> TextProcessor:
    """TextProcessor instance with a mocked model."""
    with patch("file_organizer.services.text_processor.ensure_nltk_data"):
        processor = TextProcessor(text_model=mock_text_model)
        return processor


# ---------------------------------------------------------------------------
# ProcessedFile dataclass
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestProcessedFile:
    """Tests for ProcessedFile dataclass defaults and fields."""

    def test_defaults(self) -> None:
        """Verify default field values on ProcessedFile."""
        pf = ProcessedFile(
            file_path=Path("a.txt"),
            description="desc",
            folder_name="folder",
            filename="fname",
        )
        assert pf.original_content is None
        assert pf.processing_time == 0.0
        assert pf.error is None

    def test_all_fields(self) -> None:
        """Verify all fields are stored correctly."""
        pf = ProcessedFile(
            file_path=Path("/tmp/b.pdf"),
            description="A summary",
            folder_name="science",
            filename="research_paper",
            original_content="First 500 chars",
            processing_time=1.23,
            error="some error",
        )
        assert pf.file_path == Path("/tmp/b.pdf")
        assert pf.description == "A summary"
        assert pf.folder_name == "science"
        assert pf.filename == "research_paper"
        assert pf.original_content == "First 500 chars"
        assert pf.processing_time == 1.23
        assert pf.error == "some error"


# ---------------------------------------------------------------------------
# Initialization & lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTextProcessor:
    """Tests for TextProcessor class."""

    @patch("file_organizer.services.text_processor.TextModel")
    @patch("file_organizer.services.text_processor.ensure_nltk_data")
    def test_init_creates_own_model(
        self, mock_nltk: MagicMock, mock_text_model_cls: MagicMock
    ) -> None:
        """Test initialization creates its own TextModel if not provided."""
        config = ModelConfig(name="test-model", model_type=ModelType.TEXT)

        processor = TextProcessor(config=config)

        assert processor._owns_model is True
        mock_text_model_cls.assert_called_once_with(config)
        mock_nltk.assert_called_once()

    @patch("file_organizer.services.text_processor.TextModel")
    @patch("file_organizer.services.text_processor.ensure_nltk_data")
    def test_init_default_config_when_none(
        self, mock_nltk: MagicMock, mock_text_model_cls: MagicMock
    ) -> None:
        """When no model and no config, default config is used."""
        processor = TextProcessor()

        assert processor._owns_model is True
        mock_text_model_cls.assert_called_once()

    @patch("file_organizer.services.text_processor.ensure_nltk_data")
    def test_init_uses_provided_model(
        self, mock_nltk: MagicMock, mock_text_model: MagicMock
    ) -> None:
        """Test initialization uses provided TextModel."""
        processor = TextProcessor(text_model=mock_text_model)

        assert processor._owns_model is False
        assert processor.text_model == mock_text_model
        mock_nltk.assert_called_once()

    def test_initialize_when_not_initialized(
        self, text_processor: TextProcessor, mock_text_model: MagicMock
    ) -> None:
        """Test initialize delegates to model when not yet initialized."""
        mock_text_model.is_initialized = False
        text_processor.initialize()
        mock_text_model.initialize.assert_called_once()

    def test_initialize_when_already_initialized(
        self, text_processor: TextProcessor, mock_text_model: MagicMock
    ) -> None:
        """Test initialize is a no-op when model is already initialized."""
        mock_text_model.is_initialized = True
        text_processor.initialize()
        mock_text_model.initialize.assert_not_called()

    def test_cleanup_owns_model(self) -> None:
        """Test cleanup delegates to model if owned."""
        mock_model = MagicMock()
        with patch("file_organizer.services.text_processor.TextModel", return_value=mock_model):
            with patch("file_organizer.services.text_processor.ensure_nltk_data"):
                processor = TextProcessor()
                processor.cleanup()
                mock_model.cleanup.assert_called_once()

    def test_cleanup_does_not_own_model(
        self, text_processor: TextProcessor, mock_text_model: MagicMock
    ) -> None:
        """Test cleanup does not delegate to model if not owned."""
        text_processor.cleanup()
        mock_text_model.cleanup.assert_not_called()

    def test_context_manager(self) -> None:
        """Test entering and exiting context manager."""
        mock_model = MagicMock()
        mock_model.is_initialized = False
        with patch("file_organizer.services.text_processor.TextModel", return_value=mock_model):
            with patch("file_organizer.services.text_processor.ensure_nltk_data"):
                with TextProcessor() as processor:
                    assert processor.text_model == mock_model
                    mock_model.initialize.assert_called_once()
                mock_model.cleanup.assert_called_once()

    def test_context_manager_cleanup_on_exception(self) -> None:
        """Context manager calls cleanup even when an exception occurs."""
        mock_model = MagicMock()
        mock_model.is_initialized = False
        with patch("file_organizer.services.text_processor.TextModel", return_value=mock_model):
            with patch("file_organizer.services.text_processor.ensure_nltk_data"):
                with pytest.raises(RuntimeError, match="boom"):
                    with TextProcessor() as _processor:
                        raise RuntimeError("boom")
                mock_model.cleanup.assert_called_once()


# ---------------------------------------------------------------------------
# File processing pipeline
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTextProcessorFileProcessing:
    """Tests for file processing logic."""

    @patch("file_organizer.services.text_processor.read_file")
    def test_process_file_success(
        self, mock_read: MagicMock, text_processor: TextProcessor, mock_text_model: MagicMock
    ) -> None:
        """Test successful full pipeline processing."""
        mock_read.return_value = "This is a test file about python programming."

        mock_text_model.generate.side_effect = [
            "Summary of python programming",
            "python programming",
            "python script test",
        ]

        result = text_processor.process_file("test.txt")

        assert isinstance(result, ProcessedFile)
        assert result.error is None
        assert result.description == "Summary of python programming"
        assert result.folder_name == "python_programming"
        assert result.filename == "python_script_test"
        assert "test file about python" in result.original_content

    @patch("file_organizer.services.text_processor.read_file")
    def test_process_file_path_conversion(
        self, mock_read: MagicMock, text_processor: TextProcessor, mock_text_model: MagicMock
    ) -> None:
        """Verify that string paths are converted to Path objects."""
        mock_read.return_value = "content"
        mock_text_model.generate.side_effect = ["desc", "folder_cat", "file_name"]

        result = text_processor.process_file("/some/path/test.md")

        assert result.file_path == Path("/some/path/test.md")

    @patch("file_organizer.services.text_processor.read_file")
    def test_process_file_unsupported(
        self, mock_read: MagicMock, text_processor: TextProcessor
    ) -> None:
        """Test processing unsupported file type (read_file returns None)."""
        mock_read.return_value = None

        result = text_processor.process_file("test.unknown")

        assert result.error == "Unsupported file type"
        assert result.folder_name == "unsupported"
        assert result.filename == "test"

    @patch("file_organizer.services.text_processor.read_file")
    def test_process_file_read_error(
        self, mock_read: MagicMock, text_processor: TextProcessor
    ) -> None:
        """Test processing file that raises FileReadError."""
        mock_read.side_effect = FileReadError("Permission denied")

        result = text_processor.process_file("test.txt")

        assert result.error == "Permission denied"
        assert result.folder_name == "errors"

    @patch("file_organizer.services.text_processor.read_file")
    def test_process_file_general_exception(
        self, mock_read: MagicMock, text_processor: TextProcessor
    ) -> None:
        """Test processing file that raises generic Exception."""
        mock_read.side_effect = Exception("Unexpected failure")

        result = text_processor.process_file("test.txt")

        assert result.error == "Unexpected failure"
        assert result.folder_name == "errors"

    @patch("file_organizer.services.text_processor.read_file")
    def test_process_file_toggle_flags(
        self, mock_read: MagicMock, text_processor: TextProcessor, mock_text_model: MagicMock
    ) -> None:
        """Test processing with generation flags toggled off."""
        mock_read.return_value = "Content"

        result = text_processor.process_file(
            "test.txt",
            generate_description=False,
            generate_folder=False,
            generate_filename=False,
        )

        assert result.description == ""
        assert result.folder_name == ""
        assert result.filename == ""
        mock_text_model.generate.assert_not_called()

    @patch("file_organizer.services.text_processor.read_file")
    def test_process_file_original_content_truncated(
        self, mock_read: MagicMock, text_processor: TextProcessor, mock_text_model: MagicMock
    ) -> None:
        """original_content is limited to the first 500 chars."""
        long_content = "x" * 1000
        mock_read.return_value = long_content
        mock_text_model.generate.side_effect = ["desc", "categ", "fname"]

        result = text_processor.process_file("test.txt")

        assert result.original_content is not None
        assert len(result.original_content) == 500

    @patch("file_organizer.services.text_processor.read_file")
    def test_process_file_has_processing_time(
        self, mock_read: MagicMock, text_processor: TextProcessor, mock_text_model: MagicMock
    ) -> None:
        """processing_time should be a positive float on success."""
        mock_read.return_value = "short text"
        mock_text_model.generate.side_effect = ["d", "cat", "fn"]

        result = text_processor.process_file("test.txt")

        assert result.processing_time >= 0.0

    @patch("file_organizer.services.text_processor.read_file")
    def test_process_file_description_only(
        self, mock_read: MagicMock, text_processor: TextProcessor, mock_text_model: MagicMock
    ) -> None:
        """Only generate description, skip folder and filename."""
        mock_read.return_value = "some content"
        mock_text_model.generate.return_value = "A nice summary"

        result = text_processor.process_file(
            "test.txt",
            generate_description=True,
            generate_folder=False,
            generate_filename=False,
        )

        assert result.description == "A nice summary"
        assert result.folder_name == ""
        assert result.filename == ""
        mock_text_model.generate.assert_called_once()

    @patch("file_organizer.services.text_processor.read_file")
    def test_process_file_folder_uses_content_when_no_description(
        self, mock_read: MagicMock, text_processor: TextProcessor, mock_text_model: MagicMock
    ) -> None:
        """When generate_description=False, folder uses content directly."""
        mock_read.return_value = "raw content about cooking"
        mock_text_model.generate.side_effect = ["cooking", "recipe_book"]

        result = text_processor.process_file(
            "test.txt",
            generate_description=False,
            generate_folder=True,
            generate_filename=True,
        )

        assert result.description == ""
        # folder and filename should still be generated
        assert result.folder_name != ""
        assert result.filename != ""


# ---------------------------------------------------------------------------
# _clean_ai_generated_name
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCleanAiGeneratedName:
    """Tests for _clean_ai_generated_name helper."""

    def test_basic_cleaning(self, text_processor: TextProcessor) -> None:
        """Basic words are lowercased, joined with underscores."""
        assert text_processor._clean_ai_generated_name("Hello World!") == "hello_world"

    def test_bad_words_filtered(self, text_processor: TextProcessor) -> None:
        """Stop words and generic terms are removed."""
        assert text_processor._clean_ai_generated_name("The Document Test") == "test"

    def test_deduplication(self, text_processor: TextProcessor) -> None:
        """Duplicate words are removed."""
        assert text_processor._clean_ai_generated_name("test test file") == "test"

    def test_max_words(self, text_processor: TextProcessor) -> None:
        """Output is limited to max_words."""
        result = text_processor._clean_ai_generated_name("one two three four", max_words=2)
        assert result == "one_two"

    def test_empty_input(self, text_processor: TextProcessor) -> None:
        """Empty string yields empty string."""
        assert text_processor._clean_ai_generated_name("") == ""

    def test_all_bad_words(self, text_processor: TextProcessor) -> None:
        """All stop/bad words yield empty string."""
        assert text_processor._clean_ai_generated_name("the a an and or") == ""

    def test_single_character_words_filtered(self, text_processor: TextProcessor) -> None:
        """Single-character words are removed (len(word) > 1 check)."""
        assert text_processor._clean_ai_generated_name("a b c data") == "data"

    def test_numbers_removed(self, text_processor: TextProcessor) -> None:
        """Numbers and special chars are stripped."""
        result = text_processor._clean_ai_generated_name("report 2023 budget")
        assert result == "report_budget"

    def test_underscores_and_hyphens_converted(self, text_processor: TextProcessor) -> None:
        """Underscores and hyphens are treated as spaces."""
        result = text_processor._clean_ai_generated_name("machine-learning_model")
        assert result == "machine_learning_model"

    def test_max_words_default_is_three(self, text_processor: TextProcessor) -> None:
        """Default max_words=3."""
        result = text_processor._clean_ai_generated_name("alpha beta gamma delta")
        assert result == "alpha_beta_gamma"

    def test_special_characters_only(self, text_processor: TextProcessor) -> None:
        """Input of only special characters yields empty string."""
        assert text_processor._clean_ai_generated_name("!@#$%^&*()") == ""


# ---------------------------------------------------------------------------
# _generate_description
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGenerateDescription:
    """Tests for _generate_description."""

    def test_returns_ai_response_stripped(
        self, text_processor: TextProcessor, mock_text_model: MagicMock
    ) -> None:
        """Plain response is stripped and returned."""
        mock_text_model.generate.return_value = "  This is a good summary.  "
        desc = text_processor._generate_description("Content")
        assert desc == "This is a good summary."

    def test_prefix_strip_summary(
        self, text_processor: TextProcessor, mock_text_model: MagicMock
    ) -> None:
        """Strips 'Summary:' prefix."""
        mock_text_model.generate.return_value = "Summary: This is the actual summary."
        desc = text_processor._generate_description("Content")
        assert desc == "This is the actual summary."

    def test_prefix_strip_here_is(
        self, text_processor: TextProcessor, mock_text_model: MagicMock
    ) -> None:
        """Strips 'Here is the summary:' prefix."""
        mock_text_model.generate.return_value = "Here is the summary: Concise result."
        desc = text_processor._generate_description("Content")
        assert desc == "Concise result."

    def test_prefix_strip_the_summary_is(
        self, text_processor: TextProcessor, mock_text_model: MagicMock
    ) -> None:
        """Strips 'The summary is:' prefix."""
        mock_text_model.generate.return_value = "The summary is: Important text."
        desc = text_processor._generate_description("Content")
        assert desc == "Important text."

    def test_prefix_case_insensitive(
        self, text_processor: TextProcessor, mock_text_model: MagicMock
    ) -> None:
        """Prefix stripping is case-insensitive."""
        mock_text_model.generate.return_value = "SUMMARY: upper case test."
        desc = text_processor._generate_description("Content")
        assert desc == "upper case test."

    def test_error_fallback(
        self, text_processor: TextProcessor, mock_text_model: MagicMock
    ) -> None:
        """Fallback when AI description fails returns truncated content."""
        mock_text_model.generate.side_effect = Exception("AI Failed")

        long = "A very long piece of content that exceeds one hundred characters ... " * 5
        desc = text_processor._generate_description(long)

        assert desc.startswith("Content about A very long piece")
        assert desc.endswith("...")

    def test_model_called_with_correct_params(
        self, text_processor: TextProcessor, mock_text_model: MagicMock
    ) -> None:
        """Verify model is called with temperature=0.5 and max_tokens=200."""
        mock_text_model.generate.return_value = "Result"
        text_processor._generate_description("Test content")

        call_kwargs = mock_text_model.generate.call_args
        assert call_kwargs.kwargs["temperature"] == 0.5
        assert call_kwargs.kwargs["max_tokens"] == 200


# ---------------------------------------------------------------------------
# _generate_folder_name
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGenerateFolderName:
    """Tests for _generate_folder_name."""

    def test_clean_response(
        self, text_processor: TextProcessor, mock_text_model: MagicMock
    ) -> None:
        """Normal AI response is cleaned and returned."""
        mock_text_model.generate.return_value = "Healthcare Technology"
        folder = text_processor._generate_folder_name("Some content about hospitals")
        assert folder == "healthcare_technology"

    def test_strips_category_prefix(
        self, text_processor: TextProcessor, mock_text_model: MagicMock
    ) -> None:
        """'category:' prefix is removed."""
        mock_text_model.generate.return_value = "category: science"
        folder = text_processor._generate_folder_name("Content")
        assert folder == "science"

    def test_strips_folder_prefix(
        self, text_processor: TextProcessor, mock_text_model: MagicMock
    ) -> None:
        """'folder:' prefix is removed."""
        mock_text_model.generate.return_value = "folder: finance"
        folder = text_processor._generate_folder_name("Content about money")
        assert folder == "finance"

    def test_strips_the_category_is_prefix(
        self, text_processor: TextProcessor, mock_text_model: MagicMock
    ) -> None:
        """'the category is' prefix is removed."""
        mock_text_model.generate.return_value = "the category is programming"
        folder = text_processor._generate_folder_name("Content")
        assert folder == "programming"

    def test_strips_quotes(self, text_processor: TextProcessor, mock_text_model: MagicMock) -> None:
        """Surrounding quotes are removed."""
        mock_text_model.generate.return_value = '"recipes"'
        folder = text_processor._generate_folder_name("Content about cooking")
        assert folder == "recipes"

    @patch("file_organizer.services.text_processor.clean_text")
    def test_empty_fallback(
        self, mock_clean: MagicMock, text_processor: TextProcessor, mock_text_model: MagicMock
    ) -> None:
        """Falls back to clean_text if AI yields empty category after filtering."""
        mock_text_model.generate.return_value = "the"  # filtered out
        mock_clean.return_value = "fallback_folder"

        folder = text_processor._generate_folder_name("Content")

        assert folder == "fallback_folder"
        mock_clean.assert_called_once()

    @patch("file_organizer.services.text_processor.clean_text")
    def test_short_name_fallback(
        self, mock_clean: MagicMock, text_processor: TextProcessor, mock_text_model: MagicMock
    ) -> None:
        """Falls back when result is too short (< 3 chars)."""
        mock_text_model.generate.return_value = "ab"  # 2 chars after cleaning
        mock_clean.return_value = "keyword_fallback"

        _folder = text_processor._generate_folder_name("Content")

        mock_clean.assert_called_once()

    def test_error_returns_documents(
        self, text_processor: TextProcessor, mock_text_model: MagicMock
    ) -> None:
        """Returns 'documents' on exception."""
        mock_text_model.generate.side_effect = Exception("AI Error")

        folder = text_processor._generate_folder_name("Content")

        assert folder == "documents"

    def test_long_name_truncated(
        self, text_processor: TextProcessor, mock_text_model: MagicMock
    ) -> None:
        """Folder name is truncated to 50 characters."""
        mock_text_model.generate.return_value = "very " * 20 + "long"
        folder = text_processor._generate_folder_name("Content")
        assert len(folder) <= 50

    def test_multiline_response_handled(
        self, text_processor: TextProcessor, mock_text_model: MagicMock
    ) -> None:
        """Newlines in AI response are handled (joined as spaces)."""
        mock_text_model.generate.return_value = "machine\nlearning"
        folder = text_processor._generate_folder_name("Content about ML")
        assert "machine" in folder

    def test_model_called_with_correct_params(
        self, text_processor: TextProcessor, mock_text_model: MagicMock
    ) -> None:
        """Verify model is called with temperature=0.3 and max_tokens=30."""
        mock_text_model.generate.return_value = "programming"
        text_processor._generate_folder_name("Code content")

        call_kwargs = mock_text_model.generate.call_args
        assert call_kwargs.kwargs["temperature"] == 0.3
        assert call_kwargs.kwargs["max_tokens"] == 30

    @patch("file_organizer.services.text_processor.clean_text")
    def test_fallback_result_empty_returns_documents(
        self, mock_clean: MagicMock, text_processor: TextProcessor, mock_text_model: MagicMock
    ) -> None:
        """When both AI and fallback produce empty, returns 'documents'."""
        mock_text_model.generate.return_value = "the"  # filtered out
        mock_clean.return_value = ""  # fallback also empty

        folder = text_processor._generate_folder_name("Content")

        assert folder == "documents"


# ---------------------------------------------------------------------------
# _generate_filename
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGenerateFilename:
    """Tests for _generate_filename."""

    def test_clean_response(
        self, text_processor: TextProcessor, mock_text_model: MagicMock
    ) -> None:
        """Normal AI response is cleaned and returned."""
        mock_text_model.generate.return_value = "python coding guide"
        filename = text_processor._generate_filename("Content about Python")
        assert filename == "python_coding_guide"

    def test_strips_filename_prefix(
        self, text_processor: TextProcessor, mock_text_model: MagicMock
    ) -> None:
        """'filename:' prefix is removed."""
        mock_text_model.generate.return_value = "filename: budget_report"
        filename = text_processor._generate_filename("Content")
        assert filename == "budget_report"

    def test_strips_file_prefix(
        self, text_processor: TextProcessor, mock_text_model: MagicMock
    ) -> None:
        """'file:' prefix is removed."""
        mock_text_model.generate.return_value = "file: data_analysis"
        filename = text_processor._generate_filename("Content")
        assert filename == "data_analysis"

    def test_strips_name_prefix(
        self, text_processor: TextProcessor, mock_text_model: MagicMock
    ) -> None:
        """'name:' prefix is removed."""
        mock_text_model.generate.return_value = "name: quarterly_results"
        filename = text_processor._generate_filename("Content")
        assert filename == "quarterly_results"

    def test_strips_the_filename_is_prefix(
        self, text_processor: TextProcessor, mock_text_model: MagicMock
    ) -> None:
        """'the filename is' prefix is removed."""
        mock_text_model.generate.return_value = "the filename is great_report"
        filename = text_processor._generate_filename("Content")
        assert filename == "great_report"

    def test_strips_the_name_is_prefix(
        self, text_processor: TextProcessor, mock_text_model: MagicMock
    ) -> None:
        """'the name is' prefix is removed."""
        mock_text_model.generate.return_value = "the name is solar_energy"
        filename = text_processor._generate_filename("Content")
        assert filename == "solar_energy"

    def test_removes_txt_extension(
        self, text_processor: TextProcessor, mock_text_model: MagicMock
    ) -> None:
        """Removes .txt extension from AI response."""
        mock_text_model.generate.return_value = "report.txt"
        filename = text_processor._generate_filename("Content")
        assert "txt" not in filename

    def test_removes_pdf_extension(
        self, text_processor: TextProcessor, mock_text_model: MagicMock
    ) -> None:
        """Removes .pdf extension from AI response."""
        mock_text_model.generate.return_value = "analysis.pdf"
        filename = text_processor._generate_filename("Content")
        assert "pdf" not in filename

    def test_removes_docx_extension(
        self, text_processor: TextProcessor, mock_text_model: MagicMock
    ) -> None:
        """Removes .docx extension."""
        mock_text_model.generate.return_value = "memo.docx"
        filename = text_processor._generate_filename("Content")
        assert "docx" not in filename

    def test_removes_md_extension(
        self, text_processor: TextProcessor, mock_text_model: MagicMock
    ) -> None:
        """Removes .md extension."""
        mock_text_model.generate.return_value = "readme.md"
        filename = text_processor._generate_filename("Content")
        assert ".md" not in filename

    def test_removes_jpg_extension(
        self, text_processor: TextProcessor, mock_text_model: MagicMock
    ) -> None:
        """Removes .jpg extension."""
        mock_text_model.generate.return_value = "photo.jpg"
        filename = text_processor._generate_filename("Content")
        assert "jpg" not in filename

    def test_removes_png_extension(
        self, text_processor: TextProcessor, mock_text_model: MagicMock
    ) -> None:
        """Removes .png extension."""
        mock_text_model.generate.return_value = "chart.png"
        filename = text_processor._generate_filename("Content")
        assert "png" not in filename

    def test_strips_quotes(self, text_processor: TextProcessor, mock_text_model: MagicMock) -> None:
        """Surrounding quotes are removed."""
        mock_text_model.generate.return_value = "'research_paper'"
        filename = text_processor._generate_filename("Content")
        assert filename == "research_paper"

    @patch("file_organizer.services.text_processor.clean_text")
    def test_empty_fallback(
        self, mock_clean: MagicMock, text_processor: TextProcessor, mock_text_model: MagicMock
    ) -> None:
        """Falls back to clean_text if AI yields empty filename."""
        mock_text_model.generate.return_value = "document.pdf"  # filtered out
        mock_clean.return_value = "fallback_file"

        filename = text_processor._generate_filename("Content")

        assert filename == "fallback_file"
        mock_clean.assert_called_once()

    @patch("file_organizer.services.text_processor.clean_text")
    def test_short_name_fallback(
        self, mock_clean: MagicMock, text_processor: TextProcessor, mock_text_model: MagicMock
    ) -> None:
        """Falls back when result is too short (< 3 chars)."""
        mock_text_model.generate.return_value = "it"  # too short after cleaning
        mock_clean.return_value = "keyword_name"

        _filename = text_processor._generate_filename("Content")

        mock_clean.assert_called_once()

    def test_error_returns_document(
        self, text_processor: TextProcessor, mock_text_model: MagicMock
    ) -> None:
        """Returns 'document' on exception."""
        mock_text_model.generate.side_effect = Exception("AI Error")

        filename = text_processor._generate_filename("Content")

        assert filename == "document"

    def test_long_name_truncated(
        self, text_processor: TextProcessor, mock_text_model: MagicMock
    ) -> None:
        """Filename is truncated to 50 characters."""
        mock_text_model.generate.return_value = "very " * 20 + "long"
        filename = text_processor._generate_filename("Content")
        assert len(filename) <= 50

    def test_multiline_response_handled(
        self, text_processor: TextProcessor, mock_text_model: MagicMock
    ) -> None:
        """Newlines in AI response are joined as spaces."""
        mock_text_model.generate.return_value = "deep\nlearning\nmodel"
        filename = text_processor._generate_filename("Content about DL")
        assert "deep" in filename

    def test_model_called_with_correct_params(
        self, text_processor: TextProcessor, mock_text_model: MagicMock
    ) -> None:
        """Verify model is called with temperature=0.3 and max_tokens=30."""
        mock_text_model.generate.return_value = "result"
        text_processor._generate_filename("Content")

        call_kwargs = mock_text_model.generate.call_args
        assert call_kwargs.kwargs["temperature"] == 0.3
        assert call_kwargs.kwargs["max_tokens"] == 30

    @patch("file_organizer.services.text_processor.clean_text")
    def test_fallback_result_empty_returns_document(
        self, mock_clean: MagicMock, text_processor: TextProcessor, mock_text_model: MagicMock
    ) -> None:
        """When both AI and fallback produce empty, returns 'document'."""
        mock_text_model.generate.return_value = "the"  # filtered out
        mock_clean.return_value = ""  # fallback also empty

        filename = text_processor._generate_filename("Content")

        assert filename == "document"
