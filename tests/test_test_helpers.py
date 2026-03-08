"""Tests for common test assertion helpers in test_helpers.py.

Covers: assert_file_order_in_html exact-token matching, ordering detection,
assert_html_contains, assert_html_contains_any, assert_html_tag_present.
"""

from __future__ import annotations

import pytest

from .test_helpers import (
    assert_file_order_in_html,
    assert_html_contains,
    assert_html_contains_any,
    assert_html_tag_present,
)

# ---------------------------------------------------------------------------
# assert_file_order_in_html
# ---------------------------------------------------------------------------


class TestAssertFileOrderInHtml:
    """Tests for assert_file_order_in_html."""

    def _html(self, *filenames: str) -> str:
        """Build a minimal HTML snippet listing filenames in order."""
        items = "".join(f"<li>{name}</li>" for name in filenames)
        return f"<ul>{items}</ul>"

    def test_correct_order_passes(self) -> None:
        """Files in the expected order should not raise."""
        html = self._html("alpha.txt", "beta.txt", "gamma.txt")
        assert_file_order_in_html(html, "alpha.txt", "beta.txt", "gamma.txt")

    def test_wrong_order_raises(self) -> None:
        """Files in the wrong order must raise AssertionError.

        When HTML lists [beta, alpha] but we assert [alpha, beta], the helper
        finds alpha first, then cannot locate beta after alpha's position, so
        it raises AssertionError noting beta was not found after alpha.
        """
        html = self._html("beta.txt", "alpha.txt")
        with pytest.raises(AssertionError, match="not found"):
            assert_file_order_in_html(html, "alpha.txt", "beta.txt")

    def test_missing_file_raises(self) -> None:
        """A filename absent from the HTML must raise AssertionError."""
        html = self._html("alpha.txt")
        with pytest.raises(AssertionError, match="not found"):
            assert_file_order_in_html(html, "alpha.txt", "missing.txt")

    def test_no_false_positive_substring_match(self) -> None:
        """'file.txt' must NOT match inside 'my-file.txt'."""
        # Only the long form appears; bare 'file.txt' is absent as a token.
        html = "<ul><li>my-file.txt</li></ul>"
        with pytest.raises(AssertionError, match="not found"):
            assert_file_order_in_html(html, "file.txt")

    def test_exact_token_matches_when_present(self) -> None:
        """'file.txt' should match when it appears as an exact token."""
        html = self._html("file.txt", "my-file.txt")
        # file.txt appears first as its own token — this must pass
        assert_file_order_in_html(html, "file.txt", "my-file.txt")

    def test_prefix_name_does_not_match_longer_name(self) -> None:
        """'report' must not match inside 'report_final.txt'."""
        html = "<li>report_final.txt</li>"
        with pytest.raises(AssertionError, match="not found"):
            assert_file_order_in_html(html, "report")

    def test_single_file_passes(self) -> None:
        """A single expected filename that is present must pass."""
        html = self._html("only.txt")
        assert_file_order_in_html(html, "only.txt")

    def test_case_insensitive(self) -> None:
        """Matching must be case-insensitive."""
        html = "<li>README.md</li>"
        assert_file_order_in_html(html, "readme.md")

    def test_empty_files_list_passes(self) -> None:
        """Calling with no filenames should always pass."""
        assert_file_order_in_html("<html></html>")

    def test_two_files_correct_order(self) -> None:
        """Two-file case mirrors real usage in test_web_files_routes."""
        html = self._html("file_old.txt", "file_new.txt")
        assert_file_order_in_html(html, "file_old.txt", "file_new.txt")

    def test_two_files_wrong_order_raises(self) -> None:
        """Two-file wrong-order case raises with a clear message."""
        html = self._html("file_new.txt", "file_old.txt")
        with pytest.raises(AssertionError, match="not found"):
            assert_file_order_in_html(html, "file_old.txt", "file_new.txt")

    def test_duplicate_filename_second_occurrence_used(self) -> None:
        """When a filename appears twice, the second occurrence is used for ordering."""
        # alpha.txt appears at positions 4 and 22; both are distinct tokens.
        # Searching for [alpha, alpha] must find the first at 4 then the second at 22.
        html = "<li>alpha.txt</li><li>alpha.txt</li>"
        assert_file_order_in_html(html, "alpha.txt", "alpha.txt")


# ---------------------------------------------------------------------------
# assert_html_contains
# ---------------------------------------------------------------------------


class TestAssertHtmlContains:
    """Tests for assert_html_contains."""

    def test_all_keywords_present_passes(self) -> None:
        """All requested keywords present must pass."""
        html = "<p>hello world</p>"
        assert_html_contains(html, "hello", "world")

    def test_missing_keyword_raises(self) -> None:
        """Any missing keyword must raise AssertionError."""
        with pytest.raises(AssertionError, match="missing"):
            assert_html_contains("<p>hello</p>", "hello", "missing")

    def test_case_insensitive(self) -> None:
        """Keyword matching must be case-insensitive."""
        assert_html_contains("<p>Hello World</p>", "hello", "WORLD")


# ---------------------------------------------------------------------------
# assert_html_contains_any
# ---------------------------------------------------------------------------


class TestAssertHtmlContainsAny:
    """Tests for assert_html_contains_any."""

    def test_one_match_passes(self) -> None:
        """At least one matching keyword must pass."""
        assert_html_contains_any("<p>foo</p>", "foo", "bar")

    def test_none_match_raises(self) -> None:
        """No matching keyword must raise AssertionError."""
        with pytest.raises(AssertionError):
            assert_html_contains_any("<p>baz</p>", "foo", "bar")


# ---------------------------------------------------------------------------
# assert_html_tag_present
# ---------------------------------------------------------------------------


class TestAssertHtmlTagPresent:
    """Tests for assert_html_tag_present."""

    def test_tag_present_passes(self) -> None:
        """A tag that exists in the HTML must pass."""
        assert_html_tag_present("<html><body></body></html>", "<html", "<body")

    def test_missing_tag_raises(self) -> None:
        """A tag absent from the HTML must raise AssertionError."""
        with pytest.raises(AssertionError, match="<table"):
            assert_html_tag_present("<html></html>", "<table")
