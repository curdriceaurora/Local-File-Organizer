"""Integration tests for shared file analysis service.

Covers:
  - services/analyzer.py  — generate_category, generate_description,
                            calculate_confidence, truncate_content
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from file_organizer.services.analyzer import (
    MAX_CONFIDENCE,
    MAX_CONTENT_LENGTH,
    MIN_CONFIDENCE,
    VALID_CATEGORIES,
    calculate_confidence,
    generate_category,
    generate_description,
    truncate_content,
)

pytestmark = pytest.mark.integration


def _model(response: str) -> MagicMock:
    """Return a model mock whose .generate() returns response."""
    m = MagicMock()
    m.generate.return_value = response
    return m


# ---------------------------------------------------------------------------
# generate_category
# ---------------------------------------------------------------------------


class TestGenerateCategory:
    def test_valid_first_word(self) -> None:
        result = generate_category(_model("technical"), "python code listing")
        assert result == "technical"

    def test_valid_category_in_response(self) -> None:
        result = generate_category(_model("the answer is business"), "quarterly report")
        assert result == "business"

    def test_invalid_category_defaults_to_general(self) -> None:
        result = generate_category(_model("completely made up"), "text")
        assert result == "general"

    def test_empty_response_defaults_to_general(self) -> None:
        result = generate_category(_model(""), "text")
        assert result == "general"

    def test_model_exception_returns_general(self) -> None:
        m = MagicMock()
        m.generate.side_effect = RuntimeError("model error")
        result = generate_category(m, "some content")
        assert result == "general"

    def test_all_valid_categories_recognized(self) -> None:
        for cat in VALID_CATEGORIES:
            result = generate_category(_model(cat), "content")
            assert result == cat

    def test_case_insensitive(self) -> None:
        result = generate_category(_model("TECHNICAL"), "code")
        assert result == "technical"

    def test_extra_whitespace_stripped(self) -> None:
        result = generate_category(_model("  education  "), "tutorial")
        assert result == "education"


# ---------------------------------------------------------------------------
# generate_description
# ---------------------------------------------------------------------------


class TestGenerateDescription:
    def test_returns_model_response(self) -> None:
        result = generate_description(_model("A report about Q4 earnings."), "content")
        assert result == "A report about Q4 earnings."

    def test_strips_prefix_description(self) -> None:
        result = generate_description(_model("description: a nice text"), "content")
        assert result == "a nice text"

    def test_strips_prefix_this_is(self) -> None:
        result = generate_description(_model("this is a story"), "content")
        assert result == "a story"

    def test_strips_prefix_the_text_is_about(self) -> None:
        result = generate_description(_model("the text is about science"), "content")
        assert result == "science"

    def test_empty_response_fallback(self) -> None:
        result = generate_description(_model(""), "content")
        assert result == "Document content analysis"

    def test_model_exception_returns_fallback(self) -> None:
        m = MagicMock()
        m.generate.side_effect = RuntimeError("boom")
        result = generate_description(m, "content")
        assert result == "Document content analysis"


# ---------------------------------------------------------------------------
# calculate_confidence
# ---------------------------------------------------------------------------


class TestCalculateConfidence:
    def test_short_content_low_confidence(self) -> None:
        score = calculate_confidence("short", "brief")
        assert score == MIN_CONFIDENCE

    def test_medium_content(self) -> None:
        content = "x" * 200
        desc = "y" * 30
        score = calculate_confidence(content, desc)
        assert MIN_CONFIDENCE <= score <= MAX_CONFIDENCE

    def test_long_content_and_desc_high_confidence(self) -> None:
        content = "x" * 1500
        desc = "y" * 150
        score = calculate_confidence(content, desc)
        assert score >= 0.8

    def test_score_bounded_between_min_max(self) -> None:
        # Very long content + long desc
        score = calculate_confidence("a" * 5000, "b" * 500)
        assert MIN_CONFIDENCE <= score <= MAX_CONFIDENCE

    def test_score_two_decimal_places(self) -> None:
        score = calculate_confidence("hello world", "desc")
        assert score == round(score, 2)

    def test_content_over_1000(self) -> None:
        content = "a" * 1100
        score = calculate_confidence(content, "short desc")
        assert score > 0.5


# ---------------------------------------------------------------------------
# truncate_content
# ---------------------------------------------------------------------------


class TestTruncateContent:
    def test_short_content_unchanged(self) -> None:
        result = truncate_content("hello", MAX_CONTENT_LENGTH)
        assert result == "hello"

    def test_long_content_truncated(self) -> None:
        content = "x" * (MAX_CONTENT_LENGTH + 100)
        result = truncate_content(content, MAX_CONTENT_LENGTH)
        assert len(result) == MAX_CONTENT_LENGTH

    def test_exact_length_unchanged(self) -> None:
        content = "a" * MAX_CONTENT_LENGTH
        result = truncate_content(content, MAX_CONTENT_LENGTH)
        assert len(result) == MAX_CONTENT_LENGTH

    def test_custom_max_chars(self) -> None:
        result = truncate_content("abcdefgh", max_chars=5)
        assert result == "abcde"

    def test_empty_string(self) -> None:
        assert truncate_content("") == ""
