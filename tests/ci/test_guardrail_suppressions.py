"""Regression tests for CI guardrail suppression parsing."""

from __future__ import annotations

import pytest

from scripts.ci.guardrails.suppressions import has_comment_marker, has_targeted_noqa

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
