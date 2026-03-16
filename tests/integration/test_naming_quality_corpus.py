"""Naming quality regression corpus for TextProcessor._clean_ai_generated_name.

Each entry captures a (raw AI output, expected cleaned name) pair that exercises
specific cleaning rules.  The corpus is kept CI-friendly: no model calls, no I/O.
"""

from __future__ import annotations

import pytest

from file_organizer.services.text_processor import TextProcessor

# ---------------------------------------------------------------------------
# Corpus: (raw_ai_output, max_words, expected_result)
# ---------------------------------------------------------------------------

FOLDER_CORPUS: list[tuple[str, int, str]] = [
    # Digits must be preserved (regression for [^a-z\s] regex bug)
    ("budget_2023", 2, "budget_2023"),
    ("q3 report", 2, "q3_report"),
    ("phase2 analysis", 2, "phase2_analysis"),
    # Normal categories
    ("machine_learning", 2, "machine_learning"),
    ("healthcare technology", 2, "healthcare_technology"),
    ("recipes", 2, "recipes"),
    ("finance", 2, "finance"),
    # Strip stop-words, keep meaningful words
    ("the recipes", 2, "recipes"),
    ("a file about finance", 2, "finance"),
    # Deduplication
    ("ml ml analysis", 2, "ml_analysis"),
    # Respects max_words
    ("programming language best practices", 2, "programming_language"),
    # Hyphens/underscores converted to spaces first
    ("machine-learning", 2, "machine_learning"),
    # Short single-word result still valid
    ("coding", 2, "coding"),
    # Empty after filtering returns empty string (caller uses fallback)
    ("the a an", 2, ""),
]

FILENAME_CORPUS: list[tuple[str, int, str]] = [
    # Digits preserved (regression for [^a-z\s] regex bug)
    ("budget_2023", 3, "budget_2023"),
    ("chapter3 summary", 3, "chapter3_summary"),
    ("sales_q4_report", 3, "sales_q4_report"),
    # Normal filenames
    ("ai_healthcare_analysis", 3, "ai_healthcare_analysis"),
    ("python_coding_guide", 3, "python_coding_guide"),
    ("chocolate_chip_cookies", 3, "chocolate_chip_cookies"),
    # Strip stop-words
    ("the python coding guide", 3, "python_coding_guide"),
    # Deduplication
    ("python python guide", 3, "python_guide"),
    # Respects max_words
    ("very long filename with many words here", 3, "long_filename_many"),
    # Hyphens/underscores
    ("ai-healthcare-analysis", 3, "ai_healthcare_analysis"),
]


@pytest.mark.ci
class TestCleanAiGeneratedName:
    """Unit tests for _clean_ai_generated_name without any model calls."""

    def setup_method(self) -> None:
        # Patch the model so no Ollama/network access is needed
        import unittest.mock as mock

        with mock.patch("file_organizer.services.text_processor.get_text_model") as mock_factory:
            mock_factory.return_value = mock.MagicMock()
            self.processor = TextProcessor.__new__(TextProcessor)
            # Minimal initialisation — only the clean method is tested
            self.processor.text_model = mock.MagicMock()
            self.processor._owns_model = False

    @pytest.mark.parametrize("raw,max_words,expected", FOLDER_CORPUS)
    def test_folder_name_cleaning(self, raw: str, max_words: int, expected: str) -> None:
        result = self.processor._clean_ai_generated_name(raw, max_words=max_words)
        assert result == expected, (
            f"_clean_ai_generated_name({raw!r}, max_words={max_words}) "
            f"returned {result!r}, expected {expected!r}"
        )

    @pytest.mark.parametrize("raw,max_words,expected", FILENAME_CORPUS)
    def test_filename_cleaning(self, raw: str, max_words: int, expected: str) -> None:
        result = self.processor._clean_ai_generated_name(raw, max_words=max_words)
        assert result == expected, (
            f"_clean_ai_generated_name({raw!r}, max_words={max_words}) "
            f"returned {result!r}, expected {expected!r}"
        )

    def test_digits_preserved_regression(self) -> None:
        """Regression: the old [^a-z\\s] regex stripped all digits."""
        result = self.processor._clean_ai_generated_name("budget_2023", max_words=3)
        assert "2023" in result, f"Digits stripped from 'budget_2023', got: {result!r}"

    def test_digits_preserved_leading_number(self) -> None:
        result = self.processor._clean_ai_generated_name("42nd street", max_words=3)
        assert "42nd" in result, f"'42nd' was stripped, got: {result!r}"
