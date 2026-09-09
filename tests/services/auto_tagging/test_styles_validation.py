"""Unit tests for tagging styles and prompt validation."""

import pytest

from file_organizer.services.auto_tagging.styles import (
    normalize_tag_prompt,
    validate_tag_style,
)

pytestmark = [pytest.mark.ci, pytest.mark.unit, pytest.mark.integration]


class TestValidateTagStyle:
    @pytest.mark.parametrize(
        "style",
        ["sfx", "audio", "code", "descriptive", "hierarchical"],
    )
    def test_valid_styles_accepted(self, style: str) -> None:
        validate_tag_style(style)

    def test_none_accepted(self) -> None:
        validate_tag_style(None)

    def test_rejects_invalid_style_name(self) -> None:
        with pytest.raises(ValueError, match="Invalid tag_style 'custom'"):
            validate_tag_style("custom")

    def test_rejects_non_string_type(self) -> None:
        with pytest.raises(ValueError, match="tag_style must be a string or None"):
            validate_tag_style(123)  # type: ignore[arg-type]


class TestNormalizeTagPrompt:
    def test_none_returns_none(self) -> None:
        assert normalize_tag_prompt(None) is None

    def test_empty_or_whitespace_returns_none(self) -> None:
        assert normalize_tag_prompt("") is None
        assert normalize_tag_prompt("   ") is None
        assert normalize_tag_prompt("\t\n") is None

    def test_valid_prompt_trimmed(self) -> None:
        assert normalize_tag_prompt("  Focus on genre  ") == "Focus on genre"

    def test_rejects_non_string(self) -> None:
        with pytest.raises(ValueError, match="tag_prompt must be a string or None"):
            normalize_tag_prompt(123)  # type: ignore[arg-type]

    def test_rejects_exceeding_max_length(self) -> None:
        prompt_500 = "a" * 500
        assert normalize_tag_prompt(prompt_500) == prompt_500

        prompt_501 = "a" * 501
        with pytest.raises(ValueError, match="tag_prompt exceeds maximum length of 500 characters"):
            normalize_tag_prompt(prompt_501)
