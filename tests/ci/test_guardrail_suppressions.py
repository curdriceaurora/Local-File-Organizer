"""Regression tests for CI guardrail suppression parsing."""

from __future__ import annotations

import pytest

from scripts.ci.guardrails.suppressions import (
    _manual_comment_token,
    has_comment_marker,
    has_targeted_noqa,
)

pytestmark = [pytest.mark.unit, pytest.mark.ci]


def test_has_targeted_noqa_accepts_exact_rail() -> None:
    assert has_targeted_noqa("x = 1  # noqa: pytest-raises-hygiene", "pytest-raises-hygiene")


def test_has_targeted_noqa_rejects_bare_noqa() -> None:
    assert not has_targeted_noqa("x = 1  # noqa", "pytest-raises-hygiene")


def test_has_targeted_noqa_rejects_unrelated_codes() -> None:
    assert not has_targeted_noqa("x = 1  # noqa: F401, E501", "pytest-raises-hygiene")


def test_has_targeted_noqa_accepts_mixed_codes_when_target_present() -> None:
    assert has_targeted_noqa(
        "x = 1  # noqa: F401, pytest-raises-hygiene, E501",
        "pytest-raises-hygiene",
    )


def test_has_targeted_noqa_ignores_string_literals() -> None:
    assert not has_targeted_noqa(
        "marker = 'noqa: pytest-raises-hygiene'",
        "pytest-raises-hygiene",
    )


def test_has_comment_marker_ignores_string_literals() -> None:
    assert not has_comment_marker("marker = 'copilot: wontfix'", "copilot: wontfix")


def test_has_comment_marker_matches_real_comment() -> None:
    assert has_comment_marker("x = 1  # copilot: wontfix", "copilot: wontfix")


def test_token_error_fallback() -> None:
    # Open parenthesis at EOF raises TokenError in tokenize
    assert has_targeted_noqa("x = (1  # noqa: rail", "rail")


def test_indentation_error_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    import tokenize

    def mock_generate_tokens(*args, **kwargs):
        raise IndentationError("unindent does not match any outer indentation level")

    monkeypatch.setattr(tokenize, "generate_tokens", mock_generate_tokens)
    assert has_targeted_noqa("x = 1  # noqa: rail", "rail")


def test_manual_comment_token_double_quotes() -> None:
    assert _manual_comment_token('message = "hello"  # noqa: rail') == "# noqa: rail"


def test_manual_comment_token_single_quotes() -> None:
    assert _manual_comment_token("message = 'hello'  # noqa: rail") == "# noqa: rail"


def test_manual_comment_token_escaped_quote() -> None:
    assert _manual_comment_token('message = "hello \\" world"  # noqa: rail') == "# noqa: rail"


def test_manual_comment_token_triple_double_quotes() -> None:
    assert _manual_comment_token('message = """hello"""  # noqa: rail') == "# noqa: rail"


def test_manual_comment_token_triple_single_quotes() -> None:
    assert _manual_comment_token("message = '''hello'''  # noqa: rail") == "# noqa: rail"


def test_manual_comment_token_unfinished_double_quote() -> None:
    assert _manual_comment_token("message = 'hello  # noqa: rail") is None


def test_manual_comment_token_unfinished_triple_double_quote() -> None:
    assert _manual_comment_token('message = """hello  # noqa: rail') is None


def test_manual_comment_token_unfinished_triple_single_quote() -> None:
    assert _manual_comment_token("message = '''hello  # noqa: rail") is None


def test_manual_comment_token_escaped_backslash() -> None:
    assert _manual_comment_token('message = "hello \\\\"  # noqa: rail') == "# noqa: rail"


def test_manual_comment_token_comment_in_string() -> None:
    assert _manual_comment_token('message = "hello # noqa: rail"') is None
