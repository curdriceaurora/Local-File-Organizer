"""Tests for RuleAction category validation in the PARA rules engine.

These tests cover the __post_init__ validation added in issue #108:
invalid PARA category strings passed to CATEGORIZE/SUGGEST actions
now raise ValueError with a clear message listing valid categories.
"""

from __future__ import annotations

import pytest

from file_organizer.methodologies.para.rules.engine import ActionType, RuleAction


@pytest.mark.unit
class TestRuleActionCategoryValidation:
    """RuleAction validates category strings for CATEGORIZE and SUGGEST actions."""

    def test_valid_category_accepted_for_categorize(self) -> None:
        """RuleAction accepts each valid PARA category value for CATEGORIZE."""
        valid_categories = ["project", "area", "resource", "archive"]
        for cat in valid_categories:
            action = RuleAction(
                type=ActionType.CATEGORIZE,
                category=cat,
                confidence=0.8,
            )
            assert action.category == cat, f"Expected category={cat!r} to be stored"

    def test_valid_category_accepted_for_suggest(self) -> None:
        """RuleAction accepts each valid PARA category value for SUGGEST."""
        valid_categories = ["project", "area", "resource", "archive"]
        for cat in valid_categories:
            action = RuleAction(
                type=ActionType.SUGGEST,
                category=cat,
                confidence=0.5,
            )
            assert action.category == cat

    def test_invalid_category_raises_value_error(self) -> None:
        """RuleAction raises ValueError for an unknown category string."""
        with pytest.raises(ValueError, match="Invalid PARA category"):
            RuleAction(
                type=ActionType.CATEGORIZE,
                category="invalid_cat",
                confidence=0.8,
            )

    def test_error_message_lists_valid_categories(self) -> None:
        """ValueError message enumerates all valid PARA categories."""
        with pytest.raises(ValueError) as exc_info:
            RuleAction(
                type=ActionType.CATEGORIZE,
                category="bad_value",
                confidence=0.8,
            )
        msg = str(exc_info.value)
        for expected in ["archive", "area", "project", "resource"]:
            assert expected in msg, (
                f"Expected valid category {expected!r} to appear in error: {msg!r}"
            )

    def test_category_validation_skipped_for_other_action_types(self) -> None:
        """Non-CATEGORIZE/SUGGEST action types do not validate the category field."""
        # ADD_TAG with a nonsensical category string should not raise
        action = RuleAction(type=ActionType.ADD_TAG, category="not_a_para_category")
        assert action.category == "not_a_para_category"

    def test_none_category_raises_for_categorize(self) -> None:
        """Existing validation: CATEGORIZE without a category raises ValueError."""
        with pytest.raises(ValueError, match="requires a category"):
            RuleAction(type=ActionType.CATEGORIZE, confidence=0.8)
