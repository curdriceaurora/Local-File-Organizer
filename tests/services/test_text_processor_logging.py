"""Tests verifying that TextProcessor does not leak generated names in logs.

Issue #343: Privacy: Potential Data Leak in Logs (Priv-1)
These tests ensure sensitive metadata (generated folder names, filenames, and raw
AI responses) is NOT logged at INFO or WARNING level, and that DEBUG logs only
emit lengths/counts rather than actual content values.
"""

from unittest.mock import MagicMock, patch

import pytest

from file_organizer.services.text_processor import TextProcessor

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_text_model():
    """Return a MagicMock that stands in for TextModel."""
    model = MagicMock()
    model.is_initialized = True
    # First call: description, second: folder name, third: filename
    model.generate.side_effect = [
        "A document about climate science and ocean temperatures.",  # description
        "climate_science",  # folder name
        "ocean_temperature_study",  # filename
    ]
    return model


@pytest.fixture
def processor(mock_text_model):
    """Create TextProcessor with a mock model, skipping NLTK init."""
    with patch("file_organizer.services.text_processor.ensure_nltk_data"):
        tp = TextProcessor(text_model=mock_text_model)
    return tp


def _reset_model_side_effect(mock_text_model, folder_resp="healthcare", filename_resp="patient_data_analysis"):
    """Helper to reset the side_effect on the mock model for a fresh call."""
    mock_text_model.generate.side_effect = [
        "A document about healthcare data.",  # description
        folder_resp,                           # folder name
        filename_resp,                          # filename
    ]


# ---------------------------------------------------------------------------
# Tests: INFO-level logs must NOT contain generated folder/file names
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestInfoLevelDoesNotLeakContent:
    """Verify that INFO log messages never contain the actual generated strings."""

    def test_folder_name_not_logged_at_info(self, processor, mock_text_model):
        """INFO logs must not contain the literal generated folder name."""
        _reset_model_side_effect(mock_text_model, folder_resp="healthcare_technology")

        with patch("file_organizer.services.text_processor.logger") as mock_logger, \
             patch("file_organizer.services.text_processor.read_file", return_value="healthcare content"):
            processor.process_file("/tmp/test.txt")

        info_messages = [str(c) for c in mock_logger.info.call_args_list]
        combined = " ".join(info_messages)
        assert "healthcare_technology" not in combined, (
            "Actual folder name 'healthcare_technology' must not appear in INFO logs"
        )

    def test_filename_not_logged_at_info(self, processor, mock_text_model):
        """INFO logs must not contain the literal generated filename."""
        _reset_model_side_effect(mock_text_model, filename_resp="patient_data_analysis")

        with patch("file_organizer.services.text_processor.logger") as mock_logger, \
             patch("file_organizer.services.text_processor.read_file", return_value="medical records"):
            processor.process_file("/tmp/records.txt")

        info_messages = [str(c) for c in mock_logger.info.call_args_list]
        combined = " ".join(info_messages)
        assert "patient_data_analysis" not in combined, (
            "Actual filename 'patient_data_analysis' must not appear in INFO logs"
        )

    def test_info_logs_contain_length_not_name(self, processor, mock_text_model):
        """INFO logs for folder/filename generation should reference char count, not the value."""
        _reset_model_side_effect(mock_text_model, folder_resp="finance", filename_resp="budget_report")

        with patch("file_organizer.services.text_processor.logger") as mock_logger, \
             patch("file_organizer.services.text_processor.read_file", return_value="financial planning"):
            processor.process_file("/tmp/budget.txt")

        # At least one INFO call should mention "chars" (length-based log)
        info_messages = [str(c) for c in mock_logger.info.call_args_list]
        combined = " ".join(info_messages)
        assert "chars" in combined, (
            "INFO logs should use length-based format (e.g. '7 chars') instead of the raw value"
        )


# ---------------------------------------------------------------------------
# Tests: WARNING-level logs must NOT contain generated folder/file names
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestWarningLevelDoesNotLeakContent:
    """Verify that WARNING log messages never contain user-generated content."""

    def test_folder_fallback_warning_has_no_folder_name(self, processor, mock_text_model):
        """When folder name is too short, WARNING must not include the bad value."""
        # Return a very short folder name to trigger fallback
        mock_text_model.generate.side_effect = [
            "Some description.",
            "ab",   # too short — triggers warning
            "good_filename",
        ]

        with patch("file_organizer.services.text_processor.logger") as mock_logger, \
             patch("file_organizer.services.text_processor.read_file", return_value="some text"), \
             patch("file_organizer.services.text_processor.clean_text", return_value="fallback_folder"):
            processor.process_file("/tmp/short_folder.txt")

        warning_messages = [str(c) for c in mock_logger.warning.call_args_list]
        combined = " ".join(warning_messages)
        assert "'ab'" not in combined, "Short folder name value 'ab' must not appear in WARNING logs"
        assert "ab" not in combined or "fallback" in combined.lower() or "keyword" in combined.lower(), (
            "WARNING log for short folder name must not expose the actual bad value"
        )

    def test_filename_fallback_warning_has_no_filename_value(self, processor, mock_text_model):
        """When filename is too short, WARNING must not include the bad value."""
        mock_text_model.generate.side_effect = [
            "Some description.",
            "programming",
            "xy",  # too short — triggers warning
        ]

        with patch("file_organizer.services.text_processor.logger") as mock_logger, \
             patch("file_organizer.services.text_processor.read_file", return_value="some code"), \
             patch("file_organizer.services.text_processor.clean_text", return_value="code_snippet"):
            processor.process_file("/tmp/short_fn.txt")

        warning_messages = [str(c) for c in mock_logger.warning.call_args_list]
        combined = " ".join(warning_messages)
        assert "'xy'" not in combined, "Short filename value 'xy' must not appear in WARNING logs"

    def test_folder_warning_message_is_generic(self, processor, mock_text_model):
        """The folder fallback warning message should be a static/generic string."""
        mock_text_model.generate.side_effect = [
            "Description text.",
            "ab",  # too short
            "some_filename",
        ]

        with patch("file_organizer.services.text_processor.logger") as mock_logger, \
             patch("file_organizer.services.text_processor.read_file", return_value="content"), \
             patch("file_organizer.services.text_processor.clean_text", return_value="fallback"):
            processor.process_file("/tmp/warn_test.txt")

        # The warning call should exist and contain generic text
        warning_calls = mock_logger.warning.call_args_list
        # Find the folder-related warning
        folder_warnings = [c for c in warning_calls if "folder" in str(c).lower() or "fallback" in str(c).lower()]
        assert len(folder_warnings) >= 1, "Should have logged a warning about short folder name"
        warning_text = str(folder_warnings[0])
        # It should NOT contain the f-string interpolation syntax evidence (curly braces with variable)
        assert "{folder_name}" not in warning_text


# ---------------------------------------------------------------------------
# Tests: DEBUG-level logs must NOT contain raw AI response content
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestDebugLevelDoesNotLeakAiResponses:
    """Verify that DEBUG logs for AI responses only emit lengths, not content."""

    def test_raw_ai_folder_response_not_logged(self, processor, mock_text_model):
        """The raw AI response string for folder generation must not appear in DEBUG logs."""
        sensitive_response = "SECRETCATEGORY_healthcare_private"
        mock_text_model.generate.side_effect = [
            "Description.",
            sensitive_response,
            "some_filename",
        ]

        with patch("file_organizer.services.text_processor.logger") as mock_logger, \
             patch("file_organizer.services.text_processor.read_file", return_value="text"):
            processor.process_file("/tmp/debug_test.txt")

        debug_messages = [str(c) for c in mock_logger.debug.call_args_list]
        combined = " ".join(debug_messages)
        assert sensitive_response not in combined, (
            f"Raw AI response '{sensitive_response}' must not appear in any DEBUG log"
        )

    def test_raw_ai_filename_response_not_logged(self, processor, mock_text_model):
        """The raw AI response string for filename generation must not appear in DEBUG logs."""
        sensitive_response = "SECRETFILENAME_private_medical_records"
        mock_text_model.generate.side_effect = [
            "Description.",
            "healthcare",
            sensitive_response,
        ]

        with patch("file_organizer.services.text_processor.logger") as mock_logger, \
             patch("file_organizer.services.text_processor.read_file", return_value="text"):
            processor.process_file("/tmp/debug_fn_test.txt")

        debug_messages = [str(c) for c in mock_logger.debug.call_args_list]
        combined = " ".join(debug_messages)
        assert sensitive_response not in combined, (
            f"Raw AI response '{sensitive_response}' must not appear in any DEBUG log"
        )

    def test_debug_logs_use_length_for_ai_response(self, processor, mock_text_model):
        """DEBUG logs for AI response receipt should log length, not the string value."""
        ai_response = "programming_guide"
        mock_text_model.generate.side_effect = [
            "A guide to Python programming.",
            ai_response,
            "python_tutorial",
        ]

        with patch("file_organizer.services.text_processor.logger") as mock_logger, \
             patch("file_organizer.services.text_processor.read_file", return_value="python code"):
            processor.process_file("/tmp/code_guide.txt")

        debug_messages = [str(c) for c in mock_logger.debug.call_args_list]
        combined = " ".join(debug_messages)
        # Should contain "chars" indicating length-based logging
        assert "chars" in combined, (
            "DEBUG logs for AI responses should use length format (e.g. '17 chars')"
        )
        # Should NOT contain the actual response value
        assert ai_response not in combined, (
            f"AI response value '{ai_response}' must not appear in DEBUG logs"
        )


# ---------------------------------------------------------------------------
# Tests: Verify specific log messages format (regression guards)
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestLogMessageFormats:
    """Guard the exact format of safe log messages."""

    def test_folder_info_log_uses_percent_format(self, processor, mock_text_model):
        """logger.info for folder generation should use %d-style format args."""
        _reset_model_side_effect(mock_text_model, folder_resp="recipes", filename_resp="chocolate_cake")

        with patch("file_organizer.services.text_processor.logger") as mock_logger, \
             patch("file_organizer.services.text_processor.read_file", return_value="recipe content"):
            processor.process_file("/tmp/recipe.txt")

        # Check that info was called with "Folder name generated" message
        info_call_strings = [str(c) for c in mock_logger.info.call_args_list]
        folder_info_calls = [s for s in info_call_strings if "Folder name generated" in s]
        assert len(folder_info_calls) >= 1, "Should have called logger.info with 'Folder name generated'"

    def test_filename_info_log_uses_percent_format(self, processor, mock_text_model):
        """logger.info for filename generation should use %d-style format args."""
        _reset_model_side_effect(mock_text_model, folder_resp="cooking", filename_resp="pasta_carbonara_recipe")

        with patch("file_organizer.services.text_processor.logger") as mock_logger, \
             patch("file_organizer.services.text_processor.read_file", return_value="cooking content"):
            processor.process_file("/tmp/cooking.txt")

        info_call_strings = [str(c) for c in mock_logger.info.call_args_list]
        filename_info_calls = [s for s in info_call_strings if "Filename generated" in s]
        assert len(filename_info_calls) >= 1, "Should have called logger.info with 'Filename generated'"
