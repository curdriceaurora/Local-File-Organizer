"""Tests for the shared analyzer service."""

from __future__ import annotations

from unittest.mock import MagicMock

from file_organizer.services.analyzer import (
    MAX_CONFIDENCE,
    MIN_CONFIDENCE,
    calculate_confidence,
    generate_category,
    generate_description,
    truncate_content,
)

# ---------------------------------------------------------------------------
# generate_category
# ---------------------------------------------------------------------------


def test_generate_category_valid() -> None:
    """Model returns a valid category string."""
    model = MagicMock()
    model.generate.return_value = "technical"
    assert generate_category(model, "some code") == "technical"


def test_generate_category_invalid() -> None:
    """Model returns gibberish; should fall back to 'general'."""
    model = MagicMock()
    model.generate.return_value = "gibberish_xyz"
    assert generate_category(model, "content") == "general"


def test_generate_category_multiword() -> None:
    """Model returns multi-word response containing a valid category."""
    model = MagicMock()
    model.generate.return_value = "technical document"
    assert generate_category(model, "code snippet") == "technical"


# ---------------------------------------------------------------------------
# generate_description
# ---------------------------------------------------------------------------


def test_generate_description_normal() -> None:
    """Model returns a normal description string."""
    model = MagicMock()
    model.generate.return_value = "A Python utility for sorting files."
    result = generate_description(model, "import os; os.listdir()")
    assert result
    assert isinstance(result, str)


def test_generate_description_strips() -> None:
    """Common 'Description:' prefix is stripped."""
    model = MagicMock()
    model.generate.return_value = "Description: blah blah"
    result = generate_description(model, "content")
    assert result == "blah blah"


def test_generate_description_error() -> None:
    """When the model raises, fallback description is returned."""
    model = MagicMock()
    model.generate.side_effect = RuntimeError("model crashed")
    result = generate_description(model, "content")
    assert result == "Document content analysis"


# ---------------------------------------------------------------------------
# calculate_confidence
# ---------------------------------------------------------------------------


def test_calculate_confidence_short() -> None:
    """Short content (50 chars) should produce low confidence."""
    content = "x" * 50
    conf = calculate_confidence(content, "desc")
    assert conf <= 0.5


def test_calculate_confidence_long() -> None:
    """Long content (1500 chars) should produce higher confidence."""
    content = "x" * 1500
    description = "A detailed description of the content that is quite thorough in its analysis and explanation of the text."
    conf = calculate_confidence(content, description)
    assert conf >= 0.7


def test_calculate_confidence_bounds() -> None:
    """Confidence must always be within MIN and MAX bounds."""
    # Very short content -- pushes confidence down
    conf_low = calculate_confidence("", "")
    assert MIN_CONFIDENCE <= conf_low <= MAX_CONFIDENCE

    # Very long content + long description -- pushes confidence up
    conf_high = calculate_confidence("x" * 5000, "y" * 200)
    assert MIN_CONFIDENCE <= conf_high <= MAX_CONFIDENCE


# ---------------------------------------------------------------------------
# truncate_content
# ---------------------------------------------------------------------------


def test_truncate_content() -> None:
    """Content exceeding max length is truncated to 2000 chars."""
    long_text = "a" * 3000
    result = truncate_content(long_text)
    assert len(result) == 2000


def test_truncate_content_short() -> None:
    """Content under max length is returned unchanged."""
    short_text = "hello"
    result = truncate_content(short_text)
    assert result == "hello"


# ---------------------------------------------------------------------------
# API router integration
# ---------------------------------------------------------------------------


def test_api_router_uses_shared_service() -> None:
    """Verify API router imports from shared service (no duplicated logic)."""
    import importlib

    router_mod = importlib.import_module("file_organizer.api.routers.analyze")
    service_mod = importlib.import_module("file_organizer.services.analyzer")

    # The API router must import these from the shared service
    for name in (
        "generate_category",
        "generate_description",
        "calculate_confidence",
        "truncate_content",
    ):
        router_obj = getattr(router_mod, name, None)
        service_obj = getattr(service_mod, name, None)
        assert router_obj is service_obj, (
            f"API router's '{name}' is not the same object as services.analyzer.{name}. "
            "The router should import from the shared service, not define its own copy."
        )
