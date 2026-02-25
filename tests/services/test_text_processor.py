"""Tests for TextProcessor service."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from file_organizer.models.base import ModelConfig, ModelType
from file_organizer.services.text_processor import ProcessedFile, TextProcessor
from file_organizer.utils.file_readers import FileReadError

pytestmark = [pytest.mark.unit]


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

    @patch("file_organizer.services.text_processor.ensure_nltk_data")
    def test_init_uses_provided_model(
        self, mock_nltk: MagicMock, mock_text_model: MagicMock
    ) -> None:
        """Test initialization uses provided TextModel."""
        processor = TextProcessor(text_model=mock_text_model)

        assert processor._owns_model is False
        assert processor.text_model == mock_text_model
        mock_nltk.assert_called_once()

    def test_initialize(
        self, text_processor: TextProcessor, mock_text_model: MagicMock
    ) -> None:
        """Test initialize delegates to model."""
        mock_text_model.is_initialized = False
        text_processor.initialize()
        mock_text_model.initialize.assert_called_once()

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


class TestTextProcessorFileProcessing:
    """Tests for file processing logic."""

    @patch("file_organizer.services.text_processor.read_file")
    def test_process_file_success(
        self, mock_read: MagicMock, text_processor: TextProcessor, mock_text_model: MagicMock
    ) -> None:
        """Test successful full pipeline processing."""
        mock_read.return_value = "This is a test file about python programming."

        # We need specific responses for the different generation steps
        mock_text_model.generate.side_effect = [
            "Summary of python programming",  # Description
            "python programming",  # Folder
            "python script test",  # Filename
        ]

        result = text_processor.process_file("test.txt")

        assert isinstance(result, ProcessedFile)
        assert result.error is None
        assert result.description == "Summary of python programming"
        assert result.folder_name == "python_programming"
        assert result.filename == "python_script_test"
        assert "test file about python" in result.original_content

    @patch("file_organizer.services.text_processor.read_file")
    def test_process_file_unsupported(
        self, mock_read: MagicMock, text_processor: TextProcessor
    ) -> None:
        """Test processing unsupported file type."""
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


class TestTextProcessorGenerationOps:
    """Tests for specific generation functions."""

    def test_clean_ai_generated_name(self, text_processor: TextProcessor) -> None:
        """Test word filtering logic."""
        # Test basic cleaning
        assert text_processor._clean_ai_generated_name("Hello World!") == "hello_world"

        # Test bad words filtering
        assert text_processor._clean_ai_generated_name("The Document Test") == "test"

        # Test deduplication
        assert text_processor._clean_ai_generated_name("test test file") == "test"

        # Test max words
        assert text_processor._clean_ai_generated_name("one two three four", max_words=2) == "one_two"

    def test_generate_description_prefix_strip(
        self, text_processor: TextProcessor, mock_text_model: MagicMock
    ) -> None:
        """Test stripping AI prefixes from descriptions."""
        mock_text_model.generate.return_value = "Summary: This is the actual summary."

        desc = text_processor._generate_description("Content")

        assert desc == "This is the actual summary."

    def test_generate_description_error_fallback(
        self, text_processor: TextProcessor, mock_text_model: MagicMock
    ) -> None:
        """Test fallback when AI description fails."""
        mock_text_model.generate.side_effect = Exception("AI Failed")

        desc = text_processor._generate_description(
            "A very long piece of content that exceeds one hundred characters ... " * 5
        )

        assert "Content about A very long piece" in desc

    @patch("file_organizer.services.text_processor.clean_text")
    def test_generate_folder_name_empty_fallback(
        self, mock_clean: MagicMock, text_processor: TextProcessor, mock_text_model: MagicMock
    ) -> None:
        """Test falling back to clean_text if AI yields empty category."""
        mock_text_model.generate.return_value = "the"  # Gets filtered out
        mock_clean.return_value = "fallback_folder"

        folder = text_processor._generate_folder_name("Content")

        assert folder == "fallback_folder"
        mock_clean.assert_called_once()

    @patch("file_organizer.services.text_processor.clean_text")
    def test_generate_filename_empty_fallback(
        self, mock_clean: MagicMock, text_processor: TextProcessor, mock_text_model: MagicMock
    ) -> None:
        """Test falling back to clean_text if AI yields empty filename."""
        mock_text_model.generate.return_value = "document.pdf"  # Gets filtered out
        mock_clean.return_value = "fallback_file"

        filename = text_processor._generate_filename("Content")

        assert filename == "fallback_file"
        mock_clean.assert_called_once()

    def test_generate_folder_name_error(
        self, text_processor: TextProcessor, mock_text_model: MagicMock
    ) -> None:
        """Test error handling when generating folder name."""
        mock_text_model.generate.side_effect = Exception("AI Error")

        folder = text_processor._generate_folder_name("Content")

        assert folder == "documents"

    def test_generate_filename_error(
        self, text_processor: TextProcessor, mock_text_model: MagicMock
    ) -> None:
        """Test error handling when generating filename."""
        mock_text_model.generate.side_effect = Exception("AI Error")

        filename = text_processor._generate_filename("Content")

        assert filename == "document"
