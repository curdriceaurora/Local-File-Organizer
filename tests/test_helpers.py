"""Common test assertion helpers for web route tests."""

from __future__ import annotations

import functools
import re


@functools.lru_cache(maxsize=128)
def _filename_pattern(filename: str) -> re.Pattern[str]:
    """Return a compiled regex pattern that matches *filename* as an exact token.

    Results are cached so repeated calls with the same filename (common in
    multi-assertion test helpers) avoid redundant pattern compilation.

    Args:
        filename: The lowercased filename to build a pattern for.

    Returns:
        Compiled pattern with negative lookahead/lookbehind boundaries.
    """
    return re.compile(r"(?<![.\w-])" + re.escape(filename) + r"(?![.\w-])")


def _find_filename_in_html(text: str, filename: str, start: int = 0) -> int:
    """Find the position of a filename as an exact token in HTML text.

    Uses negative lookahead/lookbehind to avoid matching ``filename`` as a
    substring of a longer filename (e.g. ``file.txt`` inside ``my-file.txt``).
    Filename boundary characters are: alphanumerics, ``_``, ``-``, ``.``.

    The compiled-pattern ``pos`` parameter is used so no substring is allocated
    when searching from an offset (e.g. if *start* is 20 and the token is found
    at absolute position 35, ``match.start()`` returns 35 directly).

    Args:
        text: The lowercased HTML text to search.
        filename: The lowercased filename to locate.
        start: Offset to begin searching from.

    Returns:
        Start index of the exact-token match.

    Raises:
        ValueError: If no exact-token match is found at or after *start*.
    """
    match = _filename_pattern(filename).search(text, pos=start)
    if match is None:
        raise ValueError(filename)
    return match.start()


def assert_file_order_in_html(response_text: str, *files: str) -> None:
    """Assert files appear in HTML response in the specified order.

    Each filename is matched as an exact token so that a short name such as
    ``file.txt`` cannot accidentally match inside a longer name such as
    ``my-file.txt``, preventing structural false positives.

    Args:
        response_text: The HTML response text to check.
        *files: Variable number of filenames that should appear in order.

    Raises:
        AssertionError: If files are not found in response or not in order.
    """
    text_lower = response_text.lower()
    files_lower = [f.lower() for f in files]

    previous_index = -1
    previous_file: str | None = None
    for file_lower in files_lower:
        try:
            current_index = _find_filename_in_html(text_lower, file_lower, previous_index + 1)
        except ValueError as err:
            if previous_file is None:
                raise AssertionError(
                    f"File '{file_lower}' not found as exact token in response"
                ) from err
            raise AssertionError(
                f"File '{file_lower}' was not found after '{previous_file}' in the response"
            ) from err

        previous_index = current_index
        previous_file = file_lower


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
