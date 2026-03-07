"""Common test assertion helpers for web route tests."""

from __future__ import annotations


def assert_file_order_in_html(response_text: str, *files: str) -> None:
    """Assert files appear in HTML response in the specified order.

    Args:
        response_text: The HTML response text to check.
        *files: Variable number of filenames that should appear in order.

    Raises:
        AssertionError: If files are not found in response or not in order.
    """
    # Cache lowercased text to avoid repeated operations
    text_lower = response_text.lower()
    files_lower = [f.lower() for f in files]

    # Verify files appear in order (single pass)
    previous_index = -1
    for file_lower in files_lower:
        try:
            current_index = text_lower.index(file_lower, previous_index + 1)
        except ValueError as err:
            raise AssertionError(f"File {file_lower} not found in response") from err

        assert current_index > previous_index, (
            f"Files not in correct order: {file_lower} at index {current_index} "
            f"should come after previous at {previous_index}"
        )
        previous_index = current_index


def assert_html_contains(response_text: str, *keywords: str) -> None:
    """Assert HTML response contains all specified keywords (case-insensitive).

    Args:
        response_text: The HTML response text to check.
        *keywords: Variable number of keywords that must appear in response.

    Raises:
        AssertionError: If any keyword is not found in response.
    """
    text_lower = response_text.lower()
    keywords_lower = [k.lower() for k in keywords]
    for keyword_lower in keywords_lower:
        assert keyword_lower in text_lower, (
            f"Keyword '{keyword_lower}' not found in response"
        )


def assert_html_contains_any(response_text: str, *keywords: str) -> None:
    """Assert HTML response contains at least one of the specified keywords.

    Args:
        response_text: The HTML response text to check.
        *keywords: Variable number of keywords, at least one must appear.

    Raises:
        AssertionError: If none of the keywords are found in response.
    """
    text_lower = response_text.lower()
    keywords_lower = [k.lower() for k in keywords]
    assert any(k in text_lower for k in keywords_lower), (
        f"None of the keywords {keywords} found in response"
    )


def assert_html_tag_present(response_text: str, *tags: str) -> None:
    """Assert HTML response contains specified HTML tags (case-insensitive).

    Useful for verifying structured HTML response vs plain text.

    Args:
        response_text: The HTML response text to check.
        *tags: Variable number of HTML tags (e.g., "<html", "<body", "<div").

    Raises:
        AssertionError: If any tag is not found in response.
    """
    text_lower = response_text.lower()
    tags_lower = [t.lower() for t in tags]
    for tag_lower in tags_lower:
        assert tag_lower in text_lower, (
            f"HTML tag '{tag_lower}' not found in response"
        )
