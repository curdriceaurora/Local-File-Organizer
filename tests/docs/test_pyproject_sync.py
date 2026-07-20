"""Tests verifying pyproject.toml extras and markers are documented.

Ensures that optional dependency groups and pytest markers defined in
pyproject.toml appear in the corresponding documentation files. Catches
omissions when new extras or markers are added without updating docs.
"""

import re
import tomllib
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
PYPROJECT = REPO_ROOT / "pyproject.toml"
DEPS_DOC = REPO_ROOT / "docs" / "setup" / "dependencies.md"
TESTING_DOC = REPO_ROOT / "docs" / "testing" / "testing-strategy.md"

pytestmark = pytest.mark.unit


def _load_pyproject() -> dict[str, Any]:
    """Load and parse pyproject.toml using stdlib tomllib."""
    with open(PYPROJECT, "rb") as f:
        return tomllib.load(f)


def _get_extras() -> list[str]:
    """Return list of optional-dependency group names from pyproject.toml."""
    data = _load_pyproject()
    return list(data.get("project", {}).get("optional-dependencies", {}).keys())


def _get_markers() -> list[str]:
    """Return list of pytest marker names from pyproject.toml."""
    data = _load_pyproject()
    raw_markers = data.get("tool", {}).get("pytest", {}).get("ini_options", {}).get("markers", [])
    # Markers are formatted as "name: description" — extract just the name
    return [m.split(":")[0].strip() for m in raw_markers]


def _extract_section(content: str, heading: str) -> str:
    """Extract markdown content under a heading up to the next same-level heading.

    Raises ValueError if the heading is not found, so callers know the section
    anchor is missing rather than silently searching the full document.
    """
    pattern = rf"^(#{{1,6}})\s+{re.escape(heading)}\s*$"
    match = re.search(pattern, content, re.MULTILINE)
    if not match:
        raise ValueError(f"Heading '{heading}' not found in document")
    level = match.group(1)  # e.g. "##"
    start = match.end()
    # Find next heading at same or higher level
    next_heading = re.search(rf"^#{{1,{len(level)}}}\s", content[start:], re.MULTILINE)
    if next_heading:
        return content[start : start + next_heading.start()]
    return content[start:]


def _extract_section_with_fallbacks(content: str, headings: tuple[str, ...]) -> str:
    """Extract section content by trying an ordered list of accepted headings."""
    for heading in headings:
        try:
            return _extract_section(content, heading)
        except ValueError:
            continue
    accepted = ", ".join(f"'{heading}'" for heading in headings)
    raise ValueError(f"None of the accepted headings were found: {accepted}")


@pytest.mark.parametrize("extra", _get_extras())
def test_extra_documented(extra: str) -> None:
    """Each pyproject.toml optional-dependency group must appear in dependencies.md."""
    content = DEPS_DOC.read_text(encoding="utf-8")
    section_headings = ("Optional extras matrix", "Optional Dependencies")
    section = _extract_section_with_fallbacks(content, section_headings)
    accepted_headings = ", ".join(f"'{heading}'" for heading in section_headings)
    assert re.search(rf"\b{re.escape(extra)}\b", section), (
        f"Optional extra '{extra}' not found in accepted extras section headings "
        f"({accepted_headings}) "
        f"of {DEPS_DOC.relative_to(REPO_ROOT)}"
    )


@pytest.mark.parametrize("marker", _get_markers())
def test_marker_documented(marker: str) -> None:
    """Each pytest marker must appear in testing-strategy.md."""
    content = TESTING_DOC.read_text(encoding="utf-8")
    section = _extract_section(content, "Test Markers")
    assert re.search(rf"\b{re.escape(marker)}\b", section), (
        f"Pytest marker '{marker}' not found in 'Test Markers' section "
        f"of {TESTING_DOC.relative_to(REPO_ROOT)}"
    )


class TestExtractSection:
    """Tests for _extract_section helper."""

    def test_extracts_target_section(self) -> None:
        content = "# Title\n\nIntro\n\n## Section A\n\nA content\n\n## Section B\n\nB content\n"
        result = _extract_section(content, "Section A")
        assert "A content" in result
        assert "B content" not in result

    def test_extracts_to_eof_when_last_section(self) -> None:
        content = "# Title\n\n## Only Section\n\nContent here\n"
        result = _extract_section(content, "Only Section")
        assert "Content here" in result

    def test_raises_when_heading_not_found(self) -> None:
        content = "# Title\n\nNo matching section\n"
        with pytest.raises(ValueError, match="Heading 'Missing' not found"):
            _extract_section(content, "Missing")

    def test_subsection_does_not_stop_extraction(self) -> None:
        content = (
            "## Target\n\nTop content\n\n"
            "### Nested\n\nNested content\n\n"
            "## Sibling\n\nSibling content\n"
        )
        result = _extract_section(content, "Target")
        assert "Nested content" in result
        assert "Sibling content" not in result

    def test_matches_any_heading_level(self) -> None:
        content = "### Optional Dependencies\n\nContent\n"
        result = _extract_section(content, "Optional Dependencies")
        assert "Content" in result


class TestExtractSectionWithFallbacks:
    """Tests for _extract_section_with_fallbacks helper."""

    def test_uses_first_heading_when_present(self) -> None:
        content = "## Optional extras matrix\n\nCanonical content\n"
        result = _extract_section_with_fallbacks(
            content, ("Optional extras matrix", "Optional Dependencies")
        )
        assert "Canonical content" in result

    def test_uses_second_heading_as_fallback(self) -> None:
        content = "## Optional Dependencies\n\nLegacy content\n"
        result = _extract_section_with_fallbacks(
            content, ("Optional extras matrix", "Optional Dependencies")
        )
        assert "Legacy content" in result

    def test_raises_when_no_fallback_heading_exists(self) -> None:
        content = "# Title\n\nNo matching section\n"
        with pytest.raises(
            ValueError,
            match=(
                "None of the accepted headings were found: "
                "'Optional extras matrix', 'Optional Dependencies'"
            ),
        ):
            _extract_section_with_fallbacks(
                content, ("Optional extras matrix", "Optional Dependencies")
            )

    def test_extraction_stops_at_next_same_or_higher_level_heading(self) -> None:
        content = (
            "## Optional Dependencies\n\nTop content\n\n"
            "### Nested\n\nNested content\n\n"
            "## Common install combinations\n\nSibling content\n"
        )
        result = _extract_section_with_fallbacks(
            content, ("Optional extras matrix", "Optional Dependencies")
        )
        assert "Top content" in result
        assert "Nested content" in result
        assert "Sibling content" not in result
