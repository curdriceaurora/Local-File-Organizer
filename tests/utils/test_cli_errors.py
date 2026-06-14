"""Tests for the CLI validation-error formatter.

Pins the contract that `format_validation_error` (a) lists every valid
value verbatim, (b) suggests a near-match via difflib, and (c) silently
omits the "did you mean" clause when the input isn't a string or no
fuzzy match exists. Step 3 uses this helper to replace bare validation
errors in `cli/config_cli.py` with hint-rich messages.
"""

from __future__ import annotations

import pytest

from file_organizer.utils.cli_errors import format_validation_error


@pytest.mark.unit
@pytest.mark.ci
def test_format_validation_error_lists_valid_values() -> None:
    """Every valid value appears in the message, comma-separated."""
    msg = format_validation_error(
        field="device",
        value="unknown",
        valid_values=["auto", "cpu", "cuda", "mps"],
    )
    assert "device" in msg
    assert "unknown" in msg
    assert "auto, cpu, cuda, mps" in msg


@pytest.mark.unit
@pytest.mark.ci
def test_format_validation_error_suggests_close_match() -> None:
    """A typo close to a valid value gets a 'did you mean' suggestion."""
    msg = format_validation_error(
        field="device",
        value="cdua",  # typo for "cuda"
        valid_values=["auto", "cpu", "cuda", "mps"],
    )
    assert "did you mean" in msg.lower()
    assert "cuda" in msg


@pytest.mark.unit
@pytest.mark.ci
def test_no_suggestion_when_input_is_not_a_string() -> None:
    """Non-string `value` skips difflib so an `int`/`None` doesn't
    crash on the type-checked path. The base "Valid values: ..." clause
    still fires."""
    msg = format_validation_error(
        field="max_workers",
        value=-1,
        valid_values=["1", "2", "4", "8"],
    )
    assert "max_workers" in msg
    assert "1, 2, 4, 8" in msg
    assert "did you mean" not in msg.lower()


@pytest.mark.unit
@pytest.mark.ci
def test_no_suggestion_when_input_is_distant_from_all_valid() -> None:
    """Below difflib's 0.6 cutoff, no suggestion appears — better to
    say nothing than to suggest something the user obviously didn't mean."""
    msg = format_validation_error(
        field="device",
        value="zzzzzz",
        valid_values=["auto", "cpu", "cuda", "mps"],
    )
    assert "did you mean" not in msg.lower()


@pytest.mark.unit
@pytest.mark.ci
def test_value_is_repr_quoted() -> None:
    """The bad value is `repr`-quoted so stray whitespace / non-ASCII
    is visible in the message, not silently embedded."""
    msg = format_validation_error(
        field="device",
        value="cuda\n",  # stray newline
        valid_values=["auto", "cuda"],
    )
    # repr() of a string with newline is "'cuda\\n'" with the literal backslash-n.
    assert "'cuda\\n'" in msg
